"""Tests for CV extraction and candidate text building."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from job_finder.config import CandidateConfig, LocationConfig
from job_finder.cv import CVError, build_candidate_text, extract_cv_text


class TestExtractCvText:
    def test_missing_path_raises(self) -> None:
        with pytest.raises(CVError, match="No CV path"):
            extract_cv_text("")

    def test_file_not_found(self, tmp_path: object) -> None:
        with pytest.raises(CVError, match="not found"):
            extract_cv_text("/nonexistent/file.pdf")

    def test_extracts_text(self, tmp_path: object) -> None:
        cv_path = "/tmp/fake_cv.pdf"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pypdf.PdfReader") as mock_reader:
                mock_reader.return_value.pages = [
                    type("Page", (), {"extract_text": lambda self: "Machine Learning Engineer"})()
                ]
                text = extract_cv_text(cv_path)
                assert "Machine Learning Engineer" in text

    def test_empty_text_raises(self) -> None:
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pypdf.PdfReader") as mock_reader:
                mock_reader.return_value.pages = [type("Page", (), {"extract_text": lambda self: ""})()]
                with pytest.raises(CVError, match="No text"):
                    extract_cv_text("/tmp/fake.pdf")


class TestBuildCandidateText:
    def test_includes_all_fields(self) -> None:
        candidate = CandidateConfig(
            name="Jane Doe",
            location=LocationConfig(countries=["UK"], cities=["London", "Cambridge"], remote=True),
            titles=["ML Engineer", "Research Scientist"],
            must_have_skills=["machine learning"],
            desirable_skills=["Python", "PyTorch"],
            exclusions=["sales"],
            cv_path="",
        )
        text = build_candidate_text(candidate, "My CV content with ML experience.")
        assert "Jane Doe" in text
        assert "ML Engineer" in text
        assert "machine learning" in text
        assert "Python" in text
        assert "London" in text
        assert "remote" in text.lower()
        assert "My CV content" in text

    def test_without_remote(self) -> None:
        candidate = CandidateConfig(
            name="Test",
            location=LocationConfig(countries=["UK"], cities=["London"], remote=False),
            titles=[],
            must_have_skills=[],
            desirable_skills=[],
            exclusions=[],
            cv_path="",
        )
        text = build_candidate_text(candidate, "CV text.")
        assert "remote" not in text.lower()
