"""Tests for email HTML and plain-text generation."""

from __future__ import annotations

from datetime import datetime, timezone

from job_finder.email import format_salary, generate_html_email, generate_text_email, match_rating
from job_finder.models import ComponentScores, Job, ScoredJob


def _make_job(
    title: str = "ML Engineer",
    company: str = "Example Corp",
    url: str = "https://example.com/job/1",
    location: str = "London, UK",
) -> Job:
    return Job(
        id="1",
        source="adzuna:gb",
        title=title,
        company=company,
        location=location,
        description="",
        url=url,
        created_at=datetime.now(timezone.utc),
    )


def _make_scored(job: Job, score: float = 87.0) -> ScoredJob:
    return ScoredJob(
        job=job,
        components=ComponentScores(semantic=0.9, title=0.8, skill=0.7, location=1.0, recency=0.9),
        final_score=score,
        strengths=["Strong semantic match", "Python appears in the job requirements"],
        concerns=["Kubernetes experience not evident"],
    )


class TestHtmlEmail:
    def test_generates_valid_html(self) -> None:
        scored = [_make_scored(_make_job())]
        html = generate_html_email(scored)
        assert "<html>" in html
        assert "</html>" in html
        assert "Job Finder — Daily Digest" in html
        assert "ML Engineer" in html
        assert "Example Corp" in html
        assert "Very strong match" in html

    def test_contains_strengths_and_concerns(self) -> None:
        scored = [_make_scored(_make_job())]
        html = generate_html_email(scored)
        assert "Why it matches" in html
        assert "Strong semantic match" in html
        assert "Potential concerns" in html
        assert "Kubernetes experience not evident" in html

    def test_contains_job_link(self) -> None:
        scored = [_make_scored(_make_job())]
        html = generate_html_email(scored)
        assert 'href="https://example.com/job/1"' in html
        assert "View job" in html

    def test_escapes_html_in_title(self) -> None:
        job = _make_job(title="<script>alert('xss')</script>")
        scored = [_make_scored(job)]
        html = generate_html_email(scored)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_escapes_html_in_strengths(self) -> None:
        job = _make_job()
        scored = ScoredJob(
            job=job,
            components=ComponentScores(0.9, 0.8, 0.7, 1.0, 0.9),
            final_score=85.0,
            strengths=["<b>bold</b> text"],
            concerns=[],
        )
        html = generate_html_email([scored])
        assert "<b>bold</b>" not in html
        assert "&lt;b&gt;bold&lt;/b&gt;" in html

    def test_empty_results(self) -> None:
        html = generate_html_email([])
        assert "No new jobs found" in html

    def test_below_threshold_count(self) -> None:
        scored = [_make_scored(_make_job())]
        html = generate_html_email(scored, total_below_threshold=5)
        assert "5" in html
        assert "below the email threshold" in html

    def test_no_link_for_invalid_url(self) -> None:
        job = _make_job(url="not-a-url")
        scored = _make_scored(job)
        html = generate_html_email([scored])
        assert "View job" not in html

    def test_multiple_jobs(self) -> None:
        jobs = [
            _make_scored(_make_job("ML Engineer", "Corp A", "https://a.com"), score=90),
            _make_scored(_make_job("Data Scientist", "Corp B", "https://b.com"), score=80),
        ]
        html = generate_html_email(jobs)
        assert "ML Engineer" in html
        assert "Data Scientist" in html
        assert "Corp A" in html
        assert "Corp B" in html


class TestTextEmail:
    def test_generates_text(self) -> None:
        scored = [_make_scored(_make_job())]
        text = generate_text_email(scored)
        assert "Job Finder — Daily Digest" in text
        assert "ML Engineer" in text
        assert "Example Corp" in text
        assert "Very strong match" in text
        assert "View job" in text or "https://example.com/job/1" in text

    def test_text_strengths_and_concerns(self) -> None:
        scored = [_make_scored(_make_job())]
        text = generate_text_email(scored)
        assert "Why it matches" in text
        assert "Strong semantic match" in text
        assert "Potential concerns" in text
        assert "Kubernetes" in text

    def test_text_empty(self) -> None:
        text = generate_text_email([])
        assert "No new jobs found" in text

    def test_text_below_threshold(self) -> None:
        text = generate_text_email([_make_scored(_make_job())], total_below_threshold=3)
        assert "3" in text
        assert "below the email threshold" in text


class TestMatchRating:
    def test_very_strong(self) -> None:
        assert match_rating(70) == "Very strong match"
        assert match_rating(85) == "Very strong match"
        assert match_rating(100) == "Very strong match"

    def test_strong(self) -> None:
        assert match_rating(65) == "Strong match"
        assert match_rating(69) == "Strong match"

    def test_good(self) -> None:
        assert match_rating(60) == "Good match"
        assert match_rating(64) == "Good match"

    def test_fair(self) -> None:
        assert match_rating(55) == "Fair match"
        assert match_rating(59) == "Fair match"

    def test_weak(self) -> None:
        assert match_rating(54) == "Weak match"
        assert match_rating(0) == "Weak match"


class TestFormatSalary:
    def test_both_min_and_max(self) -> None:
        job = _make_job()
        job = Job(
            id=job.id,
            source=job.source,
            title=job.title,
            company=job.company,
            location=job.location,
            description=job.description,
            url=job.url,
            created_at=job.created_at,
            salary_min=30000,
            salary_max=45000,
        )
        assert format_salary(job) == "£30,000–£45,000"

    def test_only_min(self) -> None:
        job = _make_job()
        job = Job(
            id=job.id,
            source=job.source,
            title=job.title,
            company=job.company,
            location=job.location,
            description=job.description,
            url=job.url,
            created_at=job.created_at,
            salary_min=35000,
        )
        assert format_salary(job) == "£35,000"

    def test_only_max(self) -> None:
        job = _make_job()
        job = Job(
            id=job.id,
            source=job.source,
            title=job.title,
            company=job.company,
            location=job.location,
            description=job.description,
            url=job.url,
            created_at=job.created_at,
            salary_max=50000,
        )
        assert format_salary(job) == "up to £50,000"

    def test_no_salary(self) -> None:
        job = _make_job()
        assert format_salary(job) == ""
