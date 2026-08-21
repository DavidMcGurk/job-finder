"""CV (PDF) text extraction and candidate embedding-text construction."""

from __future__ import annotations

import logging
from pathlib import Path

from job_finder.config import CandidateConfig
from job_finder.models import Job

logger = logging.getLogger(__name__)


class CVError(Exception):
    """Raised when a CV cannot be read or parsed."""


def extract_cv_text(cv_path: str) -> str:
    """Extract text from a PDF CV using pypdf.

    Raises :class:`CVError` if the file cannot be read.
    """
    if not cv_path:
        raise CVError("No CV path configured.")
    path = Path(cv_path)
    if not path.exists():
        raise CVError(f"CV file not found: {path}")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise CVError("pypdf is required to read PDF CVs.") from exc
    try:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise CVError(f"Failed to read CV PDF: {exc}") from exc
    text = "\n".join(pages).strip()
    if not text:
        raise CVError(f"No text could be extracted from CV: {path}")
    logger.info("Extracted %d characters from CV", len(text))
    return text


def build_candidate_text(candidate: CandidateConfig, cv_text: str) -> str:
    """Construct the text representation of the candidate for embedding."""
    parts = [
        f"Candidate: {candidate.name}",
        f"Titles: {', '.join(candidate.titles)}",
        f"Must-have skills: {', '.join(candidate.must_have_skills)}",
        f"Desirable skills: {', '.join(candidate.desirable_skills)}",
        f"Preferred locations: {', '.join(candidate.location.cities)}",
        f"Countries: {', '.join(candidate.location.countries)}",
    ]
    if candidate.location.remote:
        parts.append("Open to remote work.")
    parts.append(f"CV:\n{cv_text}")
    return "\n".join(parts)


def build_job_text(job: Job) -> str:
    """Construct the text representation of a job for embedding."""
    return job.embedding_text()
