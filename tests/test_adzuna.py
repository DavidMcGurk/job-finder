"""Tests for Adzuna response parsing and client behaviour."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from job_finder.adzuna import (
    AdzunaClient,
    AdzunaError,
    filter_recent,
    parse_adzuna_job,
)
from job_finder.config import AdzunaConfig
from job_finder.models import Job


def _sample_adzuna_job(job_id: str = "12345678") -> dict:
    return {
        "id": job_id,
        "title": "Machine Learning Engineer",
        "description": "We are looking for a Python developer with ML experience.",
        "location": {"area": ["UK", "London"]},
        "company": {"displayname": "Example Corp"},
        "redirect_url": "https://example.com/job/123",
        "created": "2024-01-15T10:30:00Z",
        "salary_min": 50000,
        "salary_max": 80000,
        "contract_type": "permanent",
        "contract_time": "full_time",
        "category": {"label": "IT Jobs"},
    }


class TestParseAdzunaJob:
    def test_parses_full_job(self) -> None:
        raw = _sample_adzuna_job()
        job = parse_adzuna_job(raw, "gb")
        assert job is not None
        assert job.id == "12345678"
        assert job.source == "adzuna:gb"
        assert job.title == "Machine Learning Engineer"
        assert job.company == "Example Corp"
        assert job.location == "UK, London"
        assert job.url == "https://example.com/job/123"
        assert job.salary_min == 50000.0
        assert job.salary_max == 80000.0
        assert job.contract_type == "permanent"
        assert job.contract_time == "full_time"
        assert job.category == "IT Jobs"
        assert job.created_at == datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

    def test_handles_missing_fields(self) -> None:
        raw = {"id": "999", "title": "Data Scientist"}
        job = parse_adzuna_job(raw, "us")
        assert job is not None
        assert job.id == "999"
        assert job.company == ""
        assert job.location == ""
        assert job.description == ""
        assert job.url == ""
        assert job.salary_min is None
        assert job.salary_max is None
        assert job.created_at is None

    def test_returns_none_for_empty(self) -> None:
        assert parse_adzuna_job({}) is None
        assert parse_adzuna_job(None) is None  # type: ignore[arg-type]

    def test_returns_none_without_id(self) -> None:
        raw = {"title": "Engineer"}
        assert parse_adzuna_job(raw) is None

    def test_returns_none_without_title(self) -> None:
        raw = {"id": "123"}
        assert parse_adzuna_job(raw) is None

    def test_handles_string_company(self) -> None:
        raw = {"id": "1", "title": "Dev", "company": "Acme Inc"}
        job = parse_adzuna_job(raw)
        assert job is not None
        assert job.company == "Acme Inc"

    def test_handles_non_dict_location(self) -> None:
        raw = {"id": "1", "title": "Dev", "location": "Remote"}
        job = parse_adzuna_job(raw)
        assert job is not None
        assert job.location == "Remote"

    def test_handles_invalid_created(self) -> None:
        raw = {"id": "1", "title": "Dev", "created": "not-a-date"}
        job = parse_adzuna_job(raw)
        assert job is not None
        assert job.created_at is None

    def test_handles_invalid_salary(self) -> None:
        raw = {"id": "1", "title": "Dev", "salary_min": "N/A"}
        job = parse_adzuna_job(raw)
        assert job is not None
        assert job.salary_min is None


class TestFilterRecent:
    def test_filters_old_jobs(self) -> None:
        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        recent = datetime.now(tz=timezone.utc)
        jobs = [
            Job(id="1", source="adzuna", title="A", company="", location="", description="", url="", created_at=old),
            Job(id="2", source="adzuna", title="B", company="", location="", description="", url="", created_at=recent),
        ]
        result = filter_recent(jobs, max_age_days=7)
        assert len(result) == 1
        assert result[0].id == "2"

    def test_keeps_unknown_age(self) -> None:
        jobs = [
            Job(id="1", source="adzuna", title="A", company="", location="", description="", url="", created_at=None),
        ]
        result = filter_recent(jobs, max_age_days=7)
        assert len(result) == 1

    def test_no_filter_when_zero(self) -> None:
        jobs = [
            Job(
                id="1",
                source="adzuna",
                title="A",
                company="",
                location="",
                description="",
                url="",
                created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            ),
        ]
        result = filter_recent(jobs, max_age_days=0)
        assert len(result) == 1


class TestAdzunaClient:
    def _config(self) -> AdzunaConfig:
        return AdzunaConfig(
            app_id="test_id",
            app_key="test_key",
            country="gb",
            results_per_query=10,
            max_age_days=7,
            queries=["machine learning"],
        )

    def test_search_all_deduplicates(self) -> None:
        config = self._config()
        client = AdzunaClient(config)
        # Two pages, each returning the same job
        with patch.object(
            client,
            "_search_query",
            return_value=[
                Job(id="1", source="adzuna:gb", title="A", company="", location="", description="", url=""),
                Job(id="2", source="adzuna:gb", title="B", company="", location="", description="", url=""),
            ],
        ):
            jobs = client.search_all()
        assert len(jobs) == 2

    def test_search_all_continues_on_error(self) -> None:
        config = AdzunaConfig(
            app_id="test_id",
            app_key="test_key",
            country="gb",
            results_per_query=5,
            max_age_days=7,
            queries=["good query", "bad query"],
        )
        client = AdzunaClient(config)
        call_count = [0]

        def mock_search(query: str) -> list[Job]:
            call_count[0] += 1
            if "bad" in query:
                raise AdzunaError("API error")
            return [Job(id="1", source="adzuna:gb", title="A", company="", location="", description="", url="")]

        with patch.object(client, "_search_query", side_effect=mock_search):
            jobs = client.search_all()
        assert call_count[0] == 2
        assert len(jobs) == 1

    def test_fetch_page_retries(self) -> None:
        config = self._config()
        client = AdzunaClient(config, timeout=5)
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": [{"id": "1", "title": "Test"}]}
        mock_response.raise_for_status.return_value = None

        with patch.object(client._session, "get") as mock_get:
            mock_get.side_effect = [
                requests.ConnectionError("fail"),
                requests.ConnectionError("fail"),
                mock_response,
            ]
            with patch("time.sleep"):
                results = client._fetch_page("test", 1, 10)
        assert len(results) == 1
        assert mock_get.call_count == 3

    def test_fetch_page_fails_after_max_retries(self) -> None:
        config = self._config()
        client = AdzunaClient(config, timeout=5)
        with patch.object(client._session, "get") as mock_get:
            mock_get.side_effect = requests.ConnectionError("fail")
            with patch("time.sleep"):
                with pytest.raises(AdzunaError):
                    client._fetch_page("test", 1, 10)
        assert mock_get.call_count == 3
