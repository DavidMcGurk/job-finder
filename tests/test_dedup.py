"""Tests for job deduplication."""

from __future__ import annotations

from job_finder.models import Job
from job_finder.pipeline import deduplicate


def _make_job(job_id: str, title: str = "Test") -> Job:
    return Job(
        id=job_id,
        source="adzuna:gb",
        title=title,
        company="",
        location="",
        description="",
        url="",
    )


class TestDeduplication:
    def test_removes_duplicates_by_id(self) -> None:
        jobs = [
            _make_job("1", "A"),
            _make_job("2", "B"),
            _make_job("1", "Duplicate"),
        ]
        result = deduplicate(jobs)
        assert len(result) == 2
        assert result[0].id == "1"
        assert result[0].title == "A"
        assert result[1].id == "2"

    def test_empty_list(self) -> None:
        assert deduplicate([]) == []

    def test_no_duplicates(self) -> None:
        jobs = [_make_job("1"), _make_job("2"), _make_job("3")]
        result = deduplicate(jobs)
        assert len(result) == 3

    def test_all_same(self) -> None:
        jobs = [_make_job("1"), _make_job("1"), _make_job("1")]
        result = deduplicate(jobs)
        assert len(result) == 1
