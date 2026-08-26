"""Tests for matching components: title, skill, location, exclusions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from job_finder.matching import (
    is_deprioritised,
    is_excluded,
    is_senior_excluded,
    is_valid_url,
    location_compatibility,
    match_skills,
    recency_score,
    title_similarity,
)
from job_finder.models import Job


def _make_job(title: str, description: str = "", location: str = "") -> Job:
    return Job(
        id="1",
        source="adzuna:gb",
        title=title,
        company="",
        location=location,
        description=description,
        url="",
    )


class TestTitleSimilarity:
    def test_exact_match(self) -> None:
        score = title_similarity("Machine Learning Engineer", ["Machine Learning Engineer"])
        assert score == 1.0

    def test_partial_match(self) -> None:
        score = title_similarity("Machine Learning Engineer", ["ML Engineer"])
        assert 0.0 < score < 1.0

    def test_no_match(self) -> None:
        score = title_similarity("Sales Manager", ["Machine Learning Engineer"])
        assert score == 0.0

    def test_empty_candidate_titles(self) -> None:
        assert title_similarity("Engineer", []) == 0.0

    def test_empty_job_title(self) -> None:
        assert title_similarity("", ["Engineer"]) == 0.0

    def test_best_of_multiple(self) -> None:
        score = title_similarity(
            "Research Scientist",
            ["Machine Learning Engineer", "Research Scientist"],
        )
        assert score == 1.0


class TestSkillMatching:
    def test_matches_must_have(self) -> None:
        job = _make_job("ML Engineer", "Requires machine learning and Python skills.")
        result = match_skills(job, ["machine learning"], ["Python"])
        assert "machine learning" in result.matched_must_have
        assert "Python" in result.matched_desirable
        assert result.score > 0.5

    def test_missing_must_have(self) -> None:
        job = _make_job("Data Analyst", "Requires Python and data analysis.")
        result = match_skills(job, ["machine learning"], ["Python"])
        assert "machine learning" in result.missing_must_have
        assert result.score < 0.5

    def test_skill_alias_ml(self) -> None:
        job = _make_job("ML Engineer", "Looking for ML expertise.")
        result = match_skills(job, ["machine learning"], [])
        assert "machine learning" in result.matched_must_have

    def test_skill_alias_hyphen(self) -> None:
        job = _make_job("Engineer", "Experience with machine-learning systems.")
        result = match_skills(job, ["machine learning"], [])
        assert "machine learning" in result.matched_must_have

    def test_no_skills_configured(self) -> None:
        job = _make_job("Engineer", "Some description.")
        result = match_skills(job, [], [])
        assert result.score == 0.7  # must_score=1.0 * 0.7 + desirable_score=0.0 * 0.3

    def test_all_must_have_matched(self) -> None:
        job = _make_job("Engineer", "machine learning and python")
        result = match_skills(job, ["machine learning", "python"], [])
        assert len(result.matched_must_have) == 2
        assert len(result.missing_must_have) == 0
        # No desirable skills configured, so score is 0.7 * 1.0 + 0.3 * 0.0 = 0.7
        assert result.score == 0.7

    def test_penalty_for_missing_must_have(self) -> None:
        job = _make_job("Engineer", "python only")
        result = match_skills(job, ["machine learning", "python", "pytorch"], [])
        assert len(result.missing_must_have) == 2
        assert result.score < 0.5


class TestLocationCompatibility:
    def test_city_match(self) -> None:
        score = location_compatibility("London, UK", ["UK"], ["London"], True)
        assert score == 1.0

    def test_country_match(self) -> None:
        score = location_compatibility("Manchester, UK", ["UK"], ["London"], True)
        assert score == 0.7

    def test_remote_match(self) -> None:
        score = location_compatibility("Remote", ["UK"], ["London"], True)
        assert score == 0.8

    def test_wfh_match(self) -> None:
        score = location_compatibility("Work from home", ["UK"], ["London"], True)
        assert score == 0.8

    def test_unknown_location(self) -> None:
        score = location_compatibility("Unknown place", ["UK"], ["London"], True)
        assert score == 0.5

    def test_empty_location(self) -> None:
        score = location_compatibility("", ["UK"], ["London"], True)
        assert score == 0.5

    def test_remote_not_open(self) -> None:
        score = location_compatibility("Remote", ["UK"], ["London"], False)
        assert score == 0.5

    def test_acceptable_area_match(self) -> None:
        score = location_compatibility("Surrey, UK", ["UK"], ["London"], True, acceptable_areas=["Surrey", "Kent"])
        assert score == 0.8

    def test_non_acceptable_area(self) -> None:
        score = location_compatibility("Manchester, UK", ["UK"], ["London"], True, acceptable_areas=["Surrey", "Kent"])
        assert score == 0.7


class TestExclusionFilter:
    def test_excludes_by_word(self) -> None:
        job = _make_job("Sales Engineer")
        assert is_excluded(job, ["sales"]) is True

    def test_excludes_by_phrase(self) -> None:
        job = _make_job("Marketing Manager")
        assert is_excluded(job, ["marketing manager"]) is True

    def test_does_not_exclude_partial_word(self) -> None:
        job = _make_job("Data Scientist")
        assert is_excluded(job, ["sales"]) is False

    def test_no_exclusions(self) -> None:
        job = _make_job("Engineer")
        assert is_excluded(job, []) is False

    def test_case_insensitive(self) -> None:
        job = _make_job("SALES Manager")
        assert is_excluded(job, ["sales"]) is True


class TestSeniorExclusion:
    def test_excludes_director(self) -> None:
        job = _make_job("Director of Engineering")
        assert is_senior_excluded(job) is True

    def test_excludes_head_of(self) -> None:
        job = _make_job("Head of Data Science")
        assert is_senior_excluded(job) is True

    def test_does_not_exclude_engineer(self) -> None:
        job = _make_job("Senior Engineer")
        assert is_senior_excluded(job) is False

    def test_excludes_vp(self) -> None:
        job = _make_job("VP of Engineering")
        assert is_senior_excluded(job) is True

    def test_excludes_principal(self) -> None:
        job = _make_job("Principal Scientist")
        assert is_senior_excluded(job) is True

    def test_excludes_lead(self) -> None:
        job = _make_job("Lead Researcher")
        assert is_senior_excluded(job) is True


class TestDeprioritisation:
    def test_deprioritises_by_word(self) -> None:
        job = _make_job("Consultant Engineer")
        assert is_deprioritised(job, ["consultant"]) is True

    def test_deprioritises_by_phrase(self) -> None:
        job = _make_job("Sales Consultant")
        assert is_deprioritised(job, ["sales consultant"]) is True

    def test_does_not_deprioritise_unrelated(self) -> None:
        job = _make_job("Machine Learning Engineer")
        assert is_deprioritised(job, ["consultant"]) is False

    def test_no_deprioritise_terms(self) -> None:
        job = _make_job("Consultant")
        assert is_deprioritised(job, []) is False

    def test_case_insensitive(self) -> None:
        job = _make_job("CONSULTANT")
        assert is_deprioritised(job, ["consultant"]) is True


class TestExperienceExtraction:
    def test_extracts_years(self) -> None:
        from job_finder.matching import extract_years_required

        assert extract_years_required("Requires 5+ years of experience") == 5

    def test_extracts_years_no_plus(self) -> None:
        from job_finder.matching import extract_years_required

        assert extract_years_required("Minimum 3 years experience required") == 3

    def test_extracts_highest_years(self) -> None:
        from job_finder.matching import extract_years_required

        desc = "We need someone with 3 years experience, ideally 7 years of professional experience"
        assert extract_years_required(desc) == 7

    def test_no_years_mentioned(self) -> None:
        from job_finder.matching import extract_years_required

        assert extract_years_required("We are looking for a researcher") is None

    def test_is_experience_excluded(self) -> None:
        from job_finder.matching import is_experience_excluded

        job = _make_job("Researcher", description="Requires 9+ years of experience")
        assert is_experience_excluded(job, max_years=5) is True

    def test_is_experience_not_excluded(self) -> None:
        from job_finder.matching import is_experience_excluded

        job = _make_job("Researcher", description="Requires 3 years experience")
        assert is_experience_excluded(job, max_years=5) is False

    def test_is_experience_not_excluded_no_mention(self) -> None:
        from job_finder.matching import is_experience_excluded

        job = _make_job("Researcher", description="Great team environment")
        assert is_experience_excluded(job, max_years=5) is False


class TestRecencyScore:
    def test_recent_job(self) -> None:
        recent = datetime.now(tz=timezone.utc) - timedelta(days=1)
        score = recency_score(recent, max_age_days=7)
        assert 0.8 < score <= 1.0

    def test_old_job(self) -> None:
        old = datetime.now(tz=timezone.utc) - timedelta(days=30)
        score = recency_score(old, max_age_days=7)
        assert score == 0.0

    def test_unknown_date(self) -> None:
        score = recency_score(None, max_age_days=7)
        assert score == 0.5

    def test_future_date(self) -> None:
        future = datetime.now(tz=timezone.utc) + timedelta(days=1)
        score = recency_score(future, max_age_days=7)
        assert score == 1.0


class TestUrlValidation:
    def test_valid_http(self) -> None:
        assert is_valid_url("http://example.com/job") is True

    def test_valid_https(self) -> None:
        assert is_valid_url("https://example.com/job") is True

    def test_invalid_scheme(self) -> None:
        assert is_valid_url("ftp://example.com") is False

    def test_empty(self) -> None:
        assert is_valid_url("") is False

    def test_no_scheme(self) -> None:
        assert is_valid_url("example.com") is False
