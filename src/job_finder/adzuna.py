"""Adzuna job-search API client."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from job_finder.config import AdzunaConfig
from job_finder.models import Job

logger = logging.getLogger(__name__)

ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api/jobs"
DEFAULT_TIMEOUT = 30  # seconds
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds


class AdzunaError(Exception):
    """Raised when an Adzuna API request fails."""


def _parse_created_at(raw: str | None) -> datetime | None:
    """Parse Adzuna's ISO-8601 created timestamp."""
    if not raw:
        return None
    try:
        # Adzuna returns e.g. "2024-01-15T10:30:00Z"
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError, TypeError:
        return None


def _parse_salary(value: Any) -> float | None:
    """Parse a salary value that may be None, int, float, or string."""
    if value is None:
        return None
    try:
        return float(value)
    except ValueError, TypeError:
        return None


def parse_adzuna_job(raw: dict, country: str = "gb") -> Job | None:
    """Convert a raw Adzuna job listing into an internal :class:`Job`.

    Returns ``None`` if the listing is missing essential fields.
    """
    if not raw:
        return None
    job_id = str(raw.get("id", "")).strip()
    title = str(raw.get("title", "")).strip()
    if not job_id or not title:
        return None
    location_parts = []
    loc = raw.get("location", {}) or {}
    if isinstance(loc, dict):
        area = loc.get("area", [])
        if isinstance(area, list):
            location_parts = [str(a) for a in area if a]
    location = ", ".join(location_parts) if location_parts else (str(loc) if loc else "")
    company_raw = raw.get("company", {})
    if isinstance(company_raw, dict):
        company = company_raw.get("display_name", "") or company_raw.get("displayname", "")
    else:
        company = str(company_raw or "")
    return Job(
        id=job_id,
        source=f"adzuna:{country}",
        title=title,
        company=company.strip(),
        location=location.strip(),
        description=str(raw.get("description", "")).strip(),
        url=str(raw.get("redirect_url", raw.get("url", ""))).strip(),
        created_at=_parse_created_at(raw.get("created")),
        salary_min=_parse_salary(raw.get("salary_min")),
        salary_max=_parse_salary(raw.get("salary_max")),
        contract_type=str(raw.get("contract_type", "")).strip(),
        contract_time=str(raw.get("contract_time", "")).strip(),
        category=(
            str(raw.get("category", {}).get("label", "")).strip()
            if isinstance(raw.get("category"), dict)
            else str(raw.get("category", "")).strip()
        ),
    )


class AdzunaClient:
    """Client for the Adzuna job-search API."""

    def __init__(self, config: AdzunaConfig, timeout: int = DEFAULT_TIMEOUT) -> None:
        self._config = config
        self._timeout = timeout
        self._session = requests.Session()

    def search_all(self) -> list[Job]:
        """Execute all configured queries and return deduplicated jobs."""
        all_jobs: list[Job] = []
        seen_ids: set[str] = set()
        for query in self._config.queries:
            logger.info("Searching Adzuna: query=%r country=%s", query, self._config.country)
            try:
                jobs = self._search_query(query)
            except AdzunaError:
                logger.exception("Query failed: %s", query)
                continue
            logger.info("Query %r returned %d jobs", query, len(jobs))
            for job in jobs:
                if job.id not in seen_ids:
                    seen_ids.add(job.id)
                    all_jobs.append(job)
        logger.info("Total unique jobs across all queries: %d", len(all_jobs))
        return all_jobs

    def _search_query(self, query: str) -> list[Job]:
        """Search a single query, handling pagination up to results_per_query."""
        jobs: list[Job] = []
        target = self._config.results_per_query
        page_size = min(target, 50)  # Adzuna max per page is 50
        page = 1
        while len(jobs) < target:
            results = self._fetch_page(query, page, page_size)
            if not results:
                break
            for raw in results:
                job = parse_adzuna_job(raw, self._config.country)
                if job:
                    jobs.append(job)
            if len(results) < page_size:
                break
            page += 1
            if page > 10:  # safety limit
                break
        return jobs[:target]

    def _fetch_page(self, query: str, page: int, page_size: int) -> list[dict]:
        """Fetch a single page of results with retry logic."""
        params: dict[str, str | int] = {
            "app_id": self._config.app_id,
            "app_key": self._config.app_key,
            "results_per_page": page_size,
            "what": query,
            "max_days_old": self._config.max_age_days,
        }
        url = f"{ADZUNA_BASE_URL}/{self._config.country}/search/{page}"
        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._session.get(url, params=params, timeout=self._timeout)
                response.raise_for_status()
                data = response.json()
                return data.get("results", [])
            except requests.RequestException as exc:
                last_error = exc
                logger.warning("Adzuna request failed (attempt %d/%d): %s", attempt, MAX_RETRIES, exc)
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BACKOFF * attempt)
        raise AdzunaError(f"Adzuna request failed after {MAX_RETRIES} attempts: {last_error}")


def filter_recent(jobs: list[Job], max_age_days: int) -> list[Job]:
    """Filter jobs to only those created within ``max_age_days`` of now."""
    if max_age_days <= 0:
        return jobs
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=max_age_days)
    result = []
    for job in jobs:
        if job.created_at is None:
            result.append(job)  # keep jobs with unknown age
            continue
        created = job.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if created >= cutoff:
            result.append(job)
    return result
