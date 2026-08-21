"""Tests for configuration loading."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from job_finder.config import ConfigError, load_config


def _write_config(tmp_path: Path, data: dict) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump(data), encoding="utf-8")
    return config_path


def _base_config() -> dict:
    return {
        "adzuna": {
            "country": "gb",
            "results_per_query": 50,
            "max_age_days": 7,
            "queries": ["machine learning engineer"],
        },
        "candidate": {
            "name": "Test Candidate",
            "location": {
                "countries": ["United Kingdom"],
                "cities": ["London"],
                "remote": True,
            },
            "titles": ["Machine Learning Engineer"],
            "skills": {
                "must_have": ["machine learning"],
                "desirable": ["Python", "PyTorch"],
            },
            "exclusions": ["sales"],
            "cv_path": "config/cv.pdf",
        },
        "matching": {
            "model": "sentence-transformers/all-MiniLM-L6-v2",
            "minimum_score": 0.55,
            "top_n": 10,
        },
        "email": {"enabled": True, "max_results": 10},
        "database": {"path": "data/test.db"},
    }


class TestConfigLoading:
    def test_loads_full_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ADZUNA_APP_ID", "test_id")
        monkeypatch.setenv("ADZUNA_APP_KEY", "test_key")
        config_path = _write_config(tmp_path, _base_config())
        config = load_config(str(config_path))
        assert config.adzuna.app_id == "test_id"
        assert config.adzuna.app_key == "test_key"
        assert config.adzuna.country == "gb"
        assert config.adzuna.queries == ["machine learning engineer"]
        assert config.candidate.name == "Test Candidate"
        assert config.candidate.location.cities == ["London"]
        assert config.candidate.location.remote is True
        assert config.candidate.must_have_skills == ["machine learning"]
        assert config.candidate.desirable_skills == ["Python", "PyTorch"]
        assert config.candidate.exclusions == ["sales"]
        assert config.candidate.cv_path == "config/cv.pdf"
        assert config.matching.model == "sentence-transformers/all-MiniLM-L6-v2"
        assert config.matching.minimum_score == 0.55
        assert config.matching.top_n == 10
        assert config.matching.weights.semantic == 0.50
        assert config.email.enabled is True
        assert config.database.path == "data/test.db"

    def test_missing_adzuna_credentials_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
        monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
        config_path = _write_config(tmp_path, _base_config())
        with pytest.raises(ConfigError, match="ADZUNA_APP_ID"):
            load_config(str(config_path))

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_config(str(tmp_path / "nonexistent.yaml"))

    def test_env_var_config_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ADZUNA_APP_ID", "test_id")
        monkeypatch.setenv("ADZUNA_APP_KEY", "test_key")
        config_path = _write_config(tmp_path, _base_config())
        monkeypatch.setenv("JOB_FINDER_CONFIG", str(config_path))
        config = load_config()
        assert config.adzuna.app_id == "test_id"

    def test_email_env_vars(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ADZUNA_APP_ID", "test_id")
        monkeypatch.setenv("ADZUNA_APP_KEY", "test_key")
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_PORT", "587")
        monkeypatch.setenv("SMTP_USERNAME", "user")
        monkeypatch.setenv("SMTP_PASSWORD", "pass")
        monkeypatch.setenv("EMAIL_FROM", "from@example.com")
        monkeypatch.setenv("EMAIL_TO", "to@example.com")
        config_path = _write_config(tmp_path, _base_config())
        config = load_config(str(config_path))
        assert config.email.smtp_host == "smtp.example.com"
        assert config.email.smtp_port == 587
        assert config.email.smtp_username == "user"
        assert config.email.smtp_password == "pass"
        assert config.email.email_from == "from@example.com"
        assert config.email.email_to == "to@example.com"

    def test_custom_weights(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ADZUNA_APP_ID", "test_id")
        monkeypatch.setenv("ADZUNA_APP_KEY", "test_key")
        data = _base_config()
        data["matching"]["weights"] = {
            "semantic": 0.6,
            "title": 0.15,
            "skill": 0.15,
            "location": 0.05,
            "recency": 0.05,
        }
        config_path = _write_config(tmp_path, data)
        config = load_config(str(config_path))
        assert config.matching.weights.semantic == 0.6
        assert config.matching.weights.title == 0.15

    def test_missing_candidate_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ADZUNA_APP_ID", "test_id")
        monkeypatch.setenv("ADZUNA_APP_KEY", "test_key")
        data = _base_config()
        del data["candidate"]
        config_path = _write_config(tmp_path, data)
        with pytest.raises(ConfigError, match="Candidate"):
            load_config(str(config_path))
