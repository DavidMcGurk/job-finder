"""End-to-end pipeline orchestration."""

from __future__ import annotations

import logging

from job_finder.adzuna import AdzunaClient
from job_finder.config import AppConfig
from job_finder.cv import build_candidate_text, extract_cv_text
from job_finder.database import JobDatabase
from job_finder.embeddings import Embedder, cosine_similarity_matrix, normalise_cosine
from job_finder.email import (
    format_salary,
    generate_html_email,
    generate_text_email,
    match_rating,
    send_email,
)
from job_finder.matching import is_excluded, is_senior_excluded
from job_finder.models import Job, ScoredJob
from job_finder.ranking import rank_jobs

logger = logging.getLogger(__name__)


def deduplicate(jobs: list[Job]) -> list[Job]:
    """Remove duplicate jobs by ID, keeping the first occurrence."""
    seen: set[str] = set()
    result: list[Job] = []
    for job in jobs:
        if job.id not in seen:
            seen.add(job.id)
            result.append(job)
    return result


def hard_filter(jobs: list[Job], config: AppConfig) -> list[Job]:
    """Apply exclusion and (optionally) seniority filters before embedding."""
    candidate = config.candidate
    result: list[Job] = []
    for job in jobs:
        if is_excluded(job, candidate.exclusions):
            logger.debug("Hard-filtered (exclusion): %s", job.title)
            continue
        if candidate.seniority_filter and is_senior_excluded(job):
            logger.debug("Hard-filtered (senior): %s", job.title)
            continue
        result.append(job)
    logger.info("Hard filter: %d → %d jobs", len(jobs), len(result))
    return result


def compute_semantic_scores(
    embedder: Embedder,
    candidate_text: str,
    jobs: list[Job],
) -> dict[str, float]:
    """Embed the candidate and all jobs, returning normalised cosine similarity per job."""
    candidate_emb = embedder.embed_single(candidate_text)
    job_texts = [job.embedding_text() for job in jobs]
    job_embeddings = embedder.embed(job_texts)
    if len(jobs) == 0:
        return {}
    sims = cosine_similarity_matrix(candidate_emb, job_embeddings)
    return {job.id: float(normalise_cosine(sim)) for job, sim in zip(jobs, sims)}


def run_pipeline(
    config: AppConfig,
    *,
    dry_run: bool = False,
    no_email: bool = False,
    limit: int | None = None,
) -> list[ScoredJob]:
    """Run the full job-finder pipeline.

    Args:
        config: Application configuration.
        dry_run: If True, do not modify the database or send email.
        no_email: If True, do not send email (even if enabled in config).
        limit: Override the top_n limit for results.

    Returns:
        The list of scored jobs that would be included in the digest.
    """
    logger.info("Starting job-finder pipeline (dry_run=%s)", dry_run)

    # 1. Extract CV and build candidate text
    cv_text = extract_cv_text(config.candidate.cv_path)
    candidate_text = build_candidate_text(config.candidate, cv_text)

    # 2. Fetch jobs from Adzuna
    client = AdzunaClient(config.adzuna)
    raw_jobs = client.search_all()
    logger.info("Fetched %d jobs from Adzuna", len(raw_jobs))

    # 3. Deduplicate
    jobs = deduplicate(raw_jobs)
    logger.info("After deduplication: %d jobs", len(jobs))

    # 4. Hard filter
    jobs = hard_filter(jobs, config)

    # 5. Filter unseen jobs (unless dry run, where we show all)
    db = JobDatabase(config.database.path)
    try:
        if not dry_run:
            unseen = db.filter_unseen(jobs)
            logger.info("Unseen jobs: %d (of %d)", len(unseen), len(jobs))
            jobs_to_rank = unseen
        else:
            jobs_to_rank = jobs
            logger.info("Dry run: ranking all %d jobs (no DB filter)", len(jobs))
    finally:
        if dry_run:
            db.close()

    if not jobs_to_rank:
        logger.info("No jobs to rank. Done.")
        if not dry_run:
            db.close()
        return []

    # 6. Compute embeddings and semantic scores
    embedder = Embedder(config.matching.model)
    semantic_scores = compute_semantic_scores(embedder, candidate_text, jobs_to_rank)

    # 7. Rank jobs
    scored = rank_jobs(
        jobs_to_rank,
        config.candidate,
        config.matching,
        semantic_scores,
    )
    logger.info("Scored %d jobs above threshold", len(scored))

    # 8. Apply limit
    top_n = limit if limit is not None else config.matching.top_n
    top_jobs = scored[:top_n]
    logger.info("Top %d jobs selected", len(top_jobs))

    # 9. Print results
    _print_results(top_jobs)

    # 10. Update state and send email
    if dry_run:
        logger.info("Dry run: skipping database update and email")
        db.close()
        return top_jobs

    # Mark only the emailed jobs as seen
    email_limit = config.email.max_results
    jobs_to_mark = top_jobs[:email_limit]
    db.mark_seen(jobs_to_mark)
    db.close()

    # Send email
    if config.email.enabled and not no_email:
        email_jobs = top_jobs[:email_limit]
        html = generate_html_email(email_jobs, total_below_threshold=len(scored) - len(email_jobs))
        text = generate_text_email(email_jobs, total_below_threshold=len(scored) - len(email_jobs))
        try:
            send_email(html, text, config.email)
        except Exception:
            logger.exception("Failed to send email")
    else:
        logger.info("Email disabled or skipped")

    return top_jobs


def _print_results(scored: list[ScoredJob]) -> None:
    """Print ranked results to stdout."""
    if not scored:
        print("No jobs matched your criteria.")
        return
    print(f"\nTop {len(scored)} job matches:")
    print("=" * 60)
    for i, s in enumerate(scored, 1):
        print(f"\n{i}. {s.job.title}")
        print(f"   {match_rating(s.final_score)}")
        if s.job.company:
            print(f"   Company: {s.job.company}")
        salary = format_salary(s.job)
        if salary:
            print(f"   Salary: {salary}")
        if s.job.location:
            print(f"   Location: {s.job.location}")
        if s.strengths:
            print("   Strengths:")
            for st in s.strengths:
                print(f"     + {st}")
        if s.concerns:
            print("   Concerns:")
            for c in s.concerns:
                print(f"     - {c}")
        if s.job.url:
            print(f"   URL: {s.job.url}")
