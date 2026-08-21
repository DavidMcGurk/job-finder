"""Typed internal data models for jobs, scores, and database records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Job:
    """Normalised internal representation of a job listing."""

    id: str
    source: str
    title: str
    company: str
    location: str
    description: str
    url: str
    created_at: datetime | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    contract_type: str = ""
    contract_time: str = ""
    category: str = ""

    def embedding_text(self) -> str:
        """Build the text representation used for semantic embedding."""
        parts = [self.title, self.company, self.location, self.category, self.description]
        return " ".join(p for p in parts if p)


@dataclass(frozen=True)
class ComponentScores:
    """Individual normalised component scores in [0, 1]."""

    semantic: float
    title: float
    skill: float
    location: float
    recency: float


@dataclass(frozen=True)
class ScoredJob:
    """A job with its computed scores and algorithmic explanation."""

    job: Job
    components: ComponentScores
    final_score: float  # 0–100
    strengths: list[str] = field(default_factory=list)
    concerns: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SeenJob:
    """A job record as stored in the SQLite database."""

    job_id: str
    source: str
    url: str
    title: str
    company: str
    first_seen: datetime
    last_seen: datetime
    last_score: float | None = None
