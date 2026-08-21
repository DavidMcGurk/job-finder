"""Deterministic matching components: title, skill, location, and exclusion filtering."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from job_finder.models import Job

# Common skill aliases for robust matching
SKILL_ALIASES: dict[str, list[str]] = {
    "machine learning": ["machine learning", "machine-learning", "ml"],
    "deep learning": ["deep learning", "deep-learning", "dl"],
    "python": ["python"],
    "pytorch": ["pytorch", "py torch"],
    "tensorflow": ["tensorflow", "tf"],
    "scientific computing": ["scientific computing", "scientific computing"],
    "numerical modelling": [
        "numerical modelling",
        "numerical modeling",
        "numerical model",
        "numerical models",
    ],
    "data science": ["data science", "data scientist"],
    "nlp": ["nlp", "natural language processing"],
    "computer vision": ["computer vision", "cv"],
}

# Seniority terms that indicate a leadership/management role
SENIOR_EXCLUSION_TERMS = {
    "director",
    "head of",
    "vp",
    "vice president",
    "chief",
    "cto",
    "cio",
    "principal",
    "lead",
    "senior manager",
    "senior director",
    "executive",
}

# Regex to extract years-of-experience requirements from job descriptions.
# Matches patterns like "5+ years", "3 years experience", "minimum 7 years".
_YEARS_RE = re.compile(
    r"(?:minimum\s+|at least\s+|require[ds]?\s+|need[s]?\s+)?"
    r"(\d+)\s*\+?\s*years?\s+(?:of\s+)?(?:experience|exp|professional)",
    re.IGNORECASE,
)


def extract_years_required(description: str) -> int | None:
    """Extract the maximum years-of-experience requirement from a job description.

    Returns the highest number found (jobs often mention multiple), or ``None``
    if no years requirement is stated.
    """
    matches = _YEARS_RE.findall(description)
    if not matches:
        return None
    return max(int(m) for m in matches)


def is_experience_excluded(job: Job, max_years: int) -> bool:
    """Check whether a job requires more years of experience than the candidate has."""
    required = extract_years_required(job.description)
    if required is None:
        return False
    return required > max_years


@dataclass
class SkillMatchResult:
    """Result of skill matching for a job."""

    matched_must_have: list[str] = field(default_factory=list)
    matched_desirable: list[str] = field(default_factory=list)
    missing_must_have: list[str] = field(default_factory=list)
    score: float = 0.0


def _normalise_text(text: str) -> str:
    """Lowercase and collapse whitespace for matching."""
    return re.sub(r"\s+", " ", text.lower().strip())


def _tokenise(text: str) -> set[str]:
    """Tokenise text into a set of lowercase word tokens."""
    return set(re.findall(r"[a-z0-9+#]+", text.lower()))


def _build_skill_pattern(skill: str) -> str:
    """Build a regex pattern for a skill, checking aliases."""
    skill_lower = skill.lower().strip()
    aliases = SKILL_ALIASES.get(skill_lower, [skill_lower])
    # Escape each alias and allow for word boundaries / hyphens
    patterns = []
    for alias in aliases:
        escaped = re.escape(alias)
        # Allow hyphen or space between words
        pattern = escaped.replace(r"\ ", r"[\s\-]")
        patterns.append(pattern)
    return r"(?:^|[\s/,(;:|])(" + "|".join(patterns) + r")(?=$|[\s/.,);:|!?\-])"


def _skill_found(skill: str, text: str) -> bool:
    """Check whether a skill appears in text, accounting for common aliases."""
    pattern = _build_skill_pattern(skill)
    return re.search(pattern, text, re.IGNORECASE) is not None


def title_similarity(job_title: str, candidate_titles: list[str]) -> float:
    """Compute title similarity using token overlap (Jaccard).

    Returns a score in [0, 1].
    """
    if not candidate_titles:
        return 0.0
    job_tokens = _tokenise(job_title)
    if not job_tokens:
        return 0.0
    best = 0.0
    for candidate_title in candidate_titles:
        cand_tokens = _tokenise(candidate_title)
        if not cand_tokens:
            continue
        intersection = job_tokens & cand_tokens
        union = job_tokens | cand_tokens
        score = len(intersection) / len(union) if union else 0.0
        best = max(best, score)
    return best


def match_skills(job: Job, must_have: list[str], desirable: list[str]) -> SkillMatchResult:
    """Match configured skills against the job title and description.

    Must-have skills have a stronger effect. If a job description states a
    must-have skill is required but the candidate has no evidence, the job is
    penalised via ``missing_must_have``.
    """
    text = _normalise_text(f"{job.title} {job.description}")
    matched_must = [s for s in must_have if _skill_found(s, text)]
    matched_desirable = [s for s in desirable if _skill_found(s, text)]
    missing_must = [s for s in must_have if s not in matched_must]

    total_must = len(must_have) if must_have else 0
    total_desirable = len(desirable) if desirable else 0

    must_score = len(matched_must) / total_must if total_must > 0 else 1.0
    desirable_score = len(matched_desirable) / total_desirable if total_desirable > 0 else 0.0
    # Weight must-have at 70%, desirable at 30%
    score = 0.7 * must_score + 0.3 * desirable_score
    # Penalise missing must-have skills
    if missing_must:
        score -= 0.1 * len(missing_must)
    score = max(0.0, min(1.0, score))
    return SkillMatchResult(
        matched_must_have=matched_must,
        matched_desirable=matched_desirable,
        missing_must_have=missing_must,
        score=score,
    )


def location_compatibility(
    job_location: str,
    countries: list[str],
    cities: list[str],
    remote: bool,
    acceptable_areas: list[str] | None = None,
) -> float:
    """Compute location compatibility score in [0, 1].

    - Exact city match: 1.0
    - Acceptable area match (e.g. Home Counties): 0.8
    - Country match: 0.7
    - Remote job and candidate open to remote: 0.8
    - Unknown location: 0.5 (never reject solely on uncertainty)
    """
    if not job_location:
        return 0.5
    loc_lower = job_location.lower().strip()

    # Check for remote
    if remote and any(word in loc_lower for word in ("remote", "work from home", "wfh", "anywhere")):
        return 0.8

    # Check city match
    for city in cities:
        if city.lower() in loc_lower:
            return 1.0

    # Check acceptable areas (e.g. Home Counties near London)
    if acceptable_areas:
        for area in acceptable_areas:
            if area.lower() in loc_lower:
                return 0.8

    # Check country match
    for country in countries:
        if country.lower() in loc_lower:
            return 0.7

    # Unknown location — be lenient
    return 0.5


def is_excluded(job: Job, exclusions: list[str]) -> bool:
    """Check whether a job should be hard-filtered based on exclusion terms.

    Checks the job title only. Conservative: only excludes on clear matches.
    """
    title_lower = job.title.lower()
    for term in exclusions:
        term_lower = term.lower().strip()
        if not term_lower:
            continue
        # Use word boundary matching for single-word terms
        if " " in term_lower:
            if term_lower in title_lower:
                return True
        else:
            pattern = r"\b" + re.escape(term_lower) + r"\b"
            if re.search(pattern, title_lower):
                return True
    return False


def is_senior_excluded(job: Job) -> bool:
    """Check whether a job title indicates a senior leadership role to exclude."""
    title_lower = job.title.lower()
    for term in SENIOR_EXCLUSION_TERMS:
        pattern = r"\b" + re.escape(term) + r"\b"
        if re.search(pattern, title_lower):
            return True
    return False


def recency_score(created_at: datetime | None, max_age_days: int = 7) -> float:
    """Compute a recency score in [0, 1].

    Jobs posted more recently score higher. Jobs with unknown dates get 0.5.
    """
    if created_at is None:
        return 0.5
    now = datetime.now(tz=timezone.utc)
    created = created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age = now - created
    if age < timedelta(0):
        return 1.0  # future-dated, treat as most recent
    if max_age_days <= 0:
        return 0.5
    age_days = age.total_seconds() / 86400
    if age_days >= max_age_days:
        return 0.0
    return 1.0 - (age_days / max_age_days)


def is_valid_url(url: str) -> bool:
    """Validate that a URL is well-formed and uses http(s)."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)
    except ValueError, AttributeError:
        return False
