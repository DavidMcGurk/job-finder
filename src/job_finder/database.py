"""SQLite database for tracking seen jobs."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from job_finder.models import Job, ScoredJob, SeenJob

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS seen_jobs (
    job_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    url TEXT,
    title TEXT,
    company TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    last_score REAL
);
"""


class JobDatabase:
    """SQLite-backed store for previously seen jobs."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        path = Path(self._db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "JobDatabase":
        self._connect()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def get_seen_ids(self) -> set[str]:
        """Return the set of all job IDs that have been seen."""
        conn = self._connect()
        rows = conn.execute("SELECT job_id FROM seen_jobs").fetchall()
        return {row["job_id"] for row in rows}

    def filter_unseen(self, jobs: list[Job]) -> list[Job]:
        """Return only the jobs whose IDs are not in the database."""
        seen = self.get_seen_ids()
        return [job for job in jobs if job.id not in seen]

    def mark_seen(self, scored_jobs: list[ScoredJob]) -> None:
        """Insert or update seen jobs with the current timestamp and score."""
        conn = self._connect()
        now = datetime.now(tz=timezone.utc).isoformat()
        for scored in scored_jobs:
            conn.execute(
                """
                INSERT INTO seen_jobs (job_id, source, url, title, company, first_seen, last_seen, last_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    last_seen = excluded.last_seen,
                    last_score = excluded.last_score
                """,
                (
                    scored.job.id,
                    scored.job.source,
                    scored.job.url,
                    scored.job.title,
                    scored.job.company,
                    now,
                    now,
                    scored.final_score,
                ),
            )
        conn.commit()
        logger.info("Marked %d jobs as seen", len(scored_jobs))

    def get_seen_jobs(self) -> list[SeenJob]:
        """Return all seen job records."""
        conn = self._connect()
        rows = conn.execute("SELECT * FROM seen_jobs ORDER BY last_seen DESC").fetchall()
        result = []
        for row in rows:
            first_seen = _parse_dt(row["first_seen"])
            last_seen = _parse_dt(row["last_seen"])
            result.append(
                SeenJob(
                    job_id=row["job_id"],
                    source=row["source"],
                    url=row["url"] or "",
                    title=row["title"] or "",
                    company=row["company"] or "",
                    first_seen=first_seen,
                    last_seen=last_seen,
                    last_score=row["last_score"],
                )
            )
        return result


def _parse_dt(raw: str) -> datetime:
    """Parse an ISO-format datetime stored in the database."""
    try:
        return datetime.fromisoformat(raw)
    except ValueError, TypeError:
        return datetime.now(tz=timezone.utc)
