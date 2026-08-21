"""Hybrid scoring and explainable ranking."""

from __future__ import annotations

import logging

from job_finder.config import CandidateConfig, MatchingConfig, MatchingWeights
from job_finder.matching import (
    SkillMatchResult,
    is_excluded,
    is_senior_excluded,
    location_compatibility,
    match_skills,
    recency_score,
    title_similarity,
)
from job_finder.models import ComponentScores, Job, ScoredJob

logger = logging.getLogger(__name__)


def compute_component_scores(
    job: Job,
    candidate: CandidateConfig,
    semantic_score: float,
    max_age_days: int = 7,
) -> tuple[ComponentScores, SkillMatchResult]:
    """Compute all component scores for a job.

    Returns the component scores and the skill match result (for explanation).
    """
    title_score = title_similarity(job.title, candidate.titles)
    skill_result = match_skills(job, candidate.must_have_skills, candidate.desirable_skills)
    loc = candidate.location
    loc_score = location_compatibility(job.location, loc.countries, loc.cities, loc.remote)
    recency = recency_score(job.created_at, max_age_days)
    components = ComponentScores(
        semantic=semantic_score,
        title=title_score,
        skill=skill_result.score,
        location=loc_score,
        recency=recency,
    )
    return components, skill_result


def compute_final_score(components: ComponentScores, weights: MatchingWeights) -> float:
    """Compute the weighted final score, normalised to [0, 100]."""
    total_weight = weights.semantic + weights.title + weights.skill + weights.location + weights.recency
    if total_weight <= 0:
        return 0.0
    weighted = (
        components.semantic * weights.semantic
        + components.title * weights.title
        + components.skill * weights.skill
        + components.location * weights.location
        + components.recency * weights.recency
    )
    return (weighted / total_weight) * 100.0


def build_explanation(
    job: Job,
    components: ComponentScores,
    skill_result: SkillMatchResult,
    candidate: CandidateConfig,
) -> tuple[list[str], list[str]]:
    """Generate algorithmic strengths and concerns for a job."""
    strengths: list[str] = []
    concerns: list[str] = []

    # Semantic
    if components.semantic >= 0.75:
        strengths.append("Strong semantic match")
    elif components.semantic >= 0.55:
        strengths.append("Good semantic match")
    elif components.semantic < 0.35:
        concerns.append("Low semantic similarity to candidate profile")

    # Title
    if components.title >= 0.6:
        strengths.append("Title closely matches candidate titles")
    elif components.title < 0.2 and candidate.titles:
        concerns.append("Job title does not closely match candidate titles")

    # Skills
    for skill in skill_result.matched_must_have:
        strengths.append(f"{skill.capitalize()} matches candidate must-have")
    for skill in skill_result.matched_desirable:
        strengths.append(f"{skill.capitalize()} appears in the job requirements")
    for skill in skill_result.missing_must_have:
        concerns.append(f"Must-have skill '{skill}' not evident in this job description")

    # Location
    if components.location >= 0.8:
        strengths.append("Location is compatible")
    elif components.location < 0.5:
        concerns.append("Location compatibility uncertain")

    # Recency
    if components.recency >= 0.8:
        strengths.append("Recently posted")
    elif components.recency < 0.3:
        concerns.append("Listing may be older")

    return strengths, concerns


def rank_jobs(
    jobs: list[Job],
    candidate: CandidateConfig,
    matching_config: MatchingConfig,
    semantic_scores: dict[str, float],
) -> list[ScoredJob]:
    """Rank jobs by hybrid score, applying hard filters and minimum score threshold.

    ``semantic_scores`` maps job ID to normalised semantic similarity in [0, 1].
    """
    scored: list[ScoredJob] = []
    for job in jobs:
        # Hard filters
        if is_excluded(job, candidate.exclusions):
            logger.debug("Excluded (term match): %s — %s", job.title, job.company)
            continue
        if candidate.seniority_filter and is_senior_excluded(job):
            logger.debug("Excluded (senior): %s — %s", job.title, job.company)
            continue

        sem = semantic_scores.get(job.id, 0.0)
        components, skill_result = compute_component_scores(job, candidate, sem, matching_config.max_age_days)
        final = compute_final_score(components, matching_config.weights)
        min_score_100 = matching_config.minimum_score * 100
        if final < min_score_100:
            logger.debug("Below threshold (%.1f < %.1f): %s", final, min_score_100, job.title)
            continue

        strengths, concerns = build_explanation(job, components, skill_result, candidate)
        scored.append(
            ScoredJob(
                job=job,
                components=components,
                final_score=round(final, 1),
                strengths=strengths,
                concerns=concerns,
            )
        )
    scored.sort(key=lambda s: s.final_score, reverse=True)
    return scored
