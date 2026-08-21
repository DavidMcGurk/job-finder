"""Configuration loading and typed config models."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = "config/config.yaml"
ENV_CONFIG_VAR = "JOB_FINDER_CONFIG"


@dataclass(frozen=True)
class AdzunaConfig:
    """Adzuna API search configuration."""

    app_id: str
    app_key: str
    country: str = "gb"
    results_per_query: int = 50
    max_age_days: int = 7
    queries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LocationConfig:
    """Candidate location preferences."""

    countries: list[str] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    remote: bool = False


@dataclass(frozen=True)
class CandidateConfig:
    """Candidate profile loaded from YAML."""

    name: str
    location: LocationConfig
    titles: list[str] = field(default_factory=list)
    must_have_skills: list[str] = field(default_factory=list)
    desirable_skills: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    seniority_filter: bool = True
    cv_path: str = ""


@dataclass(frozen=True)
class MatchingWeights:
    """Configurable weights for the hybrid scoring system. Need not sum to 1."""

    semantic: float = 0.50
    title: float = 0.20
    skill: float = 0.15
    location: float = 0.10
    recency: float = 0.05


@dataclass(frozen=True)
class MatchingConfig:
    """Embedding and ranking configuration."""

    model: str = "sentence-transformers/all-MiniLM-L6-v2"
    minimum_score: float = 0.55
    top_n: int = 10
    max_age_days: int = 7
    weights: MatchingWeights = field(default_factory=MatchingWeights)


@dataclass(frozen=True)
class EmailConfig:
    """SMTP email configuration. Credentials come from environment variables."""

    enabled: bool = True
    max_results: int = 10
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: str = ""


@dataclass(frozen=True)
class DatabaseConfig:
    """SQLite database configuration."""

    path: str = "data/job_finder.db"


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    adzuna: AdzunaConfig
    candidate: CandidateConfig
    matching: MatchingConfig
    email: EmailConfig
    database: DatabaseConfig


class ConfigError(Exception):
    """Raised when configuration is invalid or missing."""


def _get_env(name: str, default: str = "") -> str:
    """Read an environment variable, returning default if unset or empty."""
    value = os.environ.get(name, "").strip()
    return value if value else default


def _build_adzuna_config(raw: dict) -> AdzunaConfig:
    app_id = _get_env("ADZUNA_APP_ID")
    app_key = _get_env("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        raise ConfigError("ADZUNA_APP_ID and ADZUNA_APP_KEY environment variables are required.")
    return AdzunaConfig(
        app_id=app_id,
        app_key=app_key,
        country=raw.get("country", "gb"),
        results_per_query=int(raw.get("results_per_query", 50)),
        max_age_days=int(raw.get("max_age_days", 7)),
        queries=list(raw.get("queries", [])),
    )


def _build_location_config(raw: dict) -> LocationConfig:
    return LocationConfig(
        countries=list(raw.get("countries", [])),
        cities=list(raw.get("cities", [])),
        remote=bool(raw.get("remote", False)),
    )


def _build_candidate_config(raw: dict) -> CandidateConfig:
    if not raw:
        raise ConfigError("Candidate configuration section is required.")
    skills = raw.get("skills", {}) or {}
    return CandidateConfig(
        name=raw.get("name", "Candidate"),
        location=_build_location_config(raw.get("location", {}) or {}),
        titles=list(raw.get("titles", [])),
        must_have_skills=list(skills.get("must_have", [])),
        desirable_skills=list(skills.get("desirable", [])),
        exclusions=list(raw.get("exclusions", [])),
        seniority_filter=bool(raw.get("seniority_filter", True)),
        cv_path=raw.get("cv_path", ""),
    )


def _build_matching_config(raw: dict) -> MatchingConfig:
    weights_raw = raw.get("weights", {}) or {}
    weights = MatchingWeights(
        semantic=float(weights_raw.get("semantic", 0.50)),
        title=float(weights_raw.get("title", 0.20)),
        skill=float(weights_raw.get("skill", 0.15)),
        location=float(weights_raw.get("location", 0.10)),
        recency=float(weights_raw.get("recency", 0.05)),
    )
    return MatchingConfig(
        model=raw.get("model", "sentence-transformers/all-MiniLM-L6-v2"),
        minimum_score=float(raw.get("minimum_score", 0.55)),
        top_n=int(raw.get("top_n", 10)),
        max_age_days=int(raw.get("max_age_days", 7)),
        weights=weights,
    )


def _build_email_config(raw: dict) -> EmailConfig:
    return EmailConfig(
        enabled=bool(raw.get("enabled", True)),
        max_results=int(raw.get("max_results", 10)),
        smtp_host=_get_env("SMTP_HOST", raw.get("smtp_host", "")),
        smtp_port=int(_get_env("SMTP_PORT", str(raw.get("smtp_port", 587)))),
        smtp_username=_get_env("SMTP_USERNAME", raw.get("smtp_username", "")),
        smtp_password=_get_env("SMTP_PASSWORD", raw.get("smtp_password", "")),
        email_from=_get_env("EMAIL_FROM", raw.get("email_from", "")),
        email_to=_get_env("EMAIL_TO", raw.get("email_to", "")),
    )


def _build_database_config(raw: dict) -> DatabaseConfig:
    return DatabaseConfig(path=raw.get("path", "data/job_finder.db"))


def load_config(config_path: str | None = None) -> AppConfig:
    """Load configuration from a YAML file and environment variables.

    The config path is resolved in this order:
    1. The ``config_path`` argument.
    2. The ``JOB_FINDER_CONFIG`` environment variable.
    3. The default path ``config/config.yaml``.
    """
    path_str = config_path or _get_env(ENV_CONFIG_VAR, DEFAULT_CONFIG_PATH)
    path = Path(path_str)
    if not path.exists():
        raise ConfigError(f"Configuration file not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return _build_config(raw)


def _build_config(raw: dict) -> AppConfig:
    """Build an :class:`AppConfig` from a raw dictionary."""
    adzuna_raw = raw.get("adzuna", {}) or {}
    candidate_raw = raw.get("candidate", {}) or {}
    matching_raw = raw.get("matching", {}) or {}
    email_raw = raw.get("email", {}) or {}
    database_raw = raw.get("database", {}) or {}
    return AppConfig(
        adzuna=_build_adzuna_config(adzuna_raw),
        candidate=_build_candidate_config(candidate_raw),
        matching=_build_matching_config(matching_raw),
        email=_build_email_config(email_raw),
        database=_build_database_config(database_raw),
    )
