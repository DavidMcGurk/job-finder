"""Tests for the SQLite database seen/unseen behaviour."""

from __future__ import annotations

from collections.abc import Generator

from datetime import datetime
from pathlib import Path

import pytest

from job_finder.database import JobDatabase
from job_finder.models import ComponentScores, Job, ScoredJob


def _make_job(job_id: str = "1") -> Job:
    return Job(
        id=job_id,
        source="adzuna:gb",
        title="ML Engineer",
        company="Example Corp",
        location="London",
        description="",
        url="https://example.com/job",
    )


def _make_scored(job: Job, score: float = 85.0) -> ScoredJob:
    return ScoredJob(
        job=job,
        components=ComponentScores(semantic=0.9, title=0.8, skill=0.7, location=1.0, recency=0.9),
        final_score=score,
        strengths=[],
        concerns=[],
    )


@pytest.fixture
def db(tmp_path: Path) -> Generator[JobDatabase, None, None]:
    database = JobDatabase(str(tmp_path / "test.db"))
    yield database
    database.close()


class TestJobDatabase:
    def test_empty_db_no_seen(self, db: JobDatabase) -> None:
        seen = db.get_seen_ids()
        assert seen == set()

    def test_filter_unseen_all(self, db: JobDatabase) -> None:
        jobs = [_make_job("1"), _make_job("2")]
        unseen = db.filter_unseen(jobs)
        assert len(unseen) == 2

    def test_mark_and_filter(self, db: JobDatabase) -> None:
        job1 = _make_job("1")
        job2 = _make_job("2")
        db.mark_seen([_make_scored(job1)])
        unseen = db.filter_unseen([job1, job2])
        assert len(unseen) == 1
        assert unseen[0].id == "2"

    def test_seen_ids_after_marking(self, db: JobDatabase) -> None:
        job = _make_job("1")
        db.mark_seen([_make_scored(job)])
        seen = db.get_seen_ids()
        assert "1" in seen

    def test_mark_seen_updates_existing(self, db: JobDatabase) -> None:
        job = _make_job("1")
        db.mark_seen([_make_scored(job, score=70.0)])
        db.mark_seen([_make_scored(job, score=90.0)])
        seen_jobs = db.get_seen_jobs()
        assert len(seen_jobs) == 1
        assert seen_jobs[0].last_score == 90.0

    def test_get_seen_jobs(self, db: JobDatabase) -> None:
        job = _make_job("1")
        db.mark_seen([_make_scored(job, score=85.0)])
        seen = db.get_seen_jobs()
        assert len(seen) == 1
        assert seen[0].job_id == "1"
        assert seen[0].title == "ML Engineer"
        assert seen[0].company == "Example Corp"
        assert seen[0].last_score == 85.0
        assert isinstance(seen[0].first_seen, datetime)
        assert isinstance(seen[0].last_seen, datetime)

    def test_persistence_across_connections(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "test.db")
        db1 = JobDatabase(db_path)
        job = _make_job("1")
        db1.mark_seen([_make_scored(job)])
        db1.close()
        db2 = JobDatabase(db_path)
        seen = db2.get_seen_ids()
        assert "1" in seen
        db2.close()

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "subdir" / "nested" / "test.db")
        db = JobDatabase(db_path)
        db.get_seen_ids()
        assert Path(db_path).exists()
        db.close()
