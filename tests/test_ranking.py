"""Tests for ranking and final score calculation."""

from __future__ import annotations

from datetime import datetime, timezone

from job_finder.config import CandidateConfig, LocationConfig, MatchingConfig, MatchingWeights
from job_finder.models import ComponentScores, Job
from job_finder.ranking import (
    build_explanation,
    compute_component_scores,
    compute_final_score,
    rank_jobs,
)
from job_finder.matching import SkillMatchResult


def _make_candidate() -> CandidateConfig:
    return CandidateConfig(
        name="Test",
        location=LocationConfig(countries=["UK"], cities=["London"], remote=True),
        titles=["Machine Learning Engineer"],
        must_have_skills=["machine learning"],
        desirable_skills=["Python", "PyTorch"],
        exclusions=["sales", "marketing"],
        cv_path="",
    )


def _make_job(
    title: str = "Machine Learning Engineer",
    description: str = "Machine learning with Python and PyTorch in London.",
    location: str = "London, UK",
    job_id: str = "1",
) -> Job:
    return Job(
        id=job_id,
        source="adzuna:gb",
        title=title,
        company="Example Corp",
        location=location,
        description=description,
        url="https://example.com/job",
        created_at=datetime.now(timezone.utc),
    )


class TestComputeFinalScore:
    def test_perfect_scores(self) -> None:
        components = ComponentScores(semantic=1.0, title=1.0, skill=1.0, location=1.0, recency=1.0)
        weights = MatchingWeights()
        score = compute_final_score(components, weights)
        assert score == 100.0

    def test_zero_scores(self) -> None:
        components = ComponentScores(semantic=0.0, title=0.0, skill=0.0, location=0.0, recency=0.0)
        weights = MatchingWeights()
        score = compute_final_score(components, weights)
        assert score == 0.0

    def test_weighted_average(self) -> None:
        components = ComponentScores(semantic=1.0, title=0.0, skill=0.0, location=0.0, recency=0.0)
        weights = MatchingWeights()
        score = compute_final_score(components, weights)
        # semantic weight is 0.50 out of total 1.0
        assert score == 50.0

    def test_custom_weights(self) -> None:
        components = ComponentScores(semantic=1.0, title=0.0, skill=0.0, location=0.0, recency=0.0)
        weights = MatchingWeights(semantic=1.0, title=0.0, skill=0.0, location=0.0, recency=0.0)
        score = compute_final_score(components, weights)
        assert score == 100.0

    def test_zero_weights(self) -> None:
        components = ComponentScores(semantic=1.0, title=1.0, skill=1.0, location=1.0, recency=1.0)
        weights = MatchingWeights(semantic=0, title=0, skill=0, location=0, recency=0)
        score = compute_final_score(components, weights)
        assert score == 0.0


class TestComponentScores:
    def test_computes_all_components(self) -> None:
        job = _make_job()
        candidate = _make_candidate()
        components, skill_result = compute_component_scores(job, candidate, 0.8)
        assert 0.0 <= components.semantic <= 1.0
        assert 0.0 <= components.title <= 1.0
        assert 0.0 <= components.skill <= 1.0
        assert 0.0 <= components.location <= 1.0
        assert 0.0 <= components.recency <= 1.0
        assert components.semantic == 0.8
        assert isinstance(skill_result, SkillMatchResult)


class TestBuildExplanation:
    def test_generates_strengths_and_concerns(self) -> None:
        job = _make_job()
        candidate = _make_candidate()
        components = ComponentScores(semantic=0.9, title=0.8, skill=0.9, location=1.0, recency=0.9)
        skill_result = SkillMatchResult(
            matched_must_have=["machine learning"],
            matched_desirable=["Python"],
            missing_must_have=[],
            score=0.9,
        )
        strengths, concerns = build_explanation(job, components, skill_result, candidate)
        assert any("semantic" in s.lower() for s in strengths)
        assert any("machine learning" in s.lower() for s in strengths)
        assert any("python" in s.lower() for s in strengths)
        assert any("location" in s.lower() for s in strengths)
        assert len(concerns) == 0

    def test_generates_concerns_for_low_scores(self) -> None:
        job = _make_job(title="Data Analyst", description="Some role", location="Unknown")
        candidate = _make_candidate()
        components = ComponentScores(semantic=0.2, title=0.1, skill=0.2, location=0.4, recency=0.2)
        skill_result = SkillMatchResult(
            matched_must_have=[],
            matched_desirable=[],
            missing_must_have=["machine learning"],
            score=0.0,
        )
        strengths, concerns = build_explanation(job, components, skill_result, candidate)
        assert any("semantic" in c.lower() for c in concerns)
        assert any("title" in c.lower() for c in concerns)
        assert any("machine learning" in c.lower() for c in concerns)
        assert any("location" in c.lower() for c in concerns)


class TestRankJobs:
    def test_ranks_by_score(self) -> None:
        candidate = _make_candidate()
        config = MatchingConfig(minimum_score=0.0, top_n=10)
        jobs = [
            _make_job(job_id="1", description="Machine learning Python PyTorch London"),
            _make_job(job_id="2", description="Machine learning Python PyTorch London"),
        ]
        semantic = {"1": 0.9, "2": 0.7}
        scored = rank_jobs(jobs, candidate, config, semantic)
        assert len(scored) == 2
        assert scored[0].final_score >= scored[1].final_score

    def test_filters_excluded(self) -> None:
        candidate = _make_candidate()
        config = MatchingConfig(minimum_score=0.0, top_n=10)
        jobs = [
            _make_job(job_id="1", title="Machine Learning Engineer"),
            _make_job(job_id="2", title="Sales Manager"),
        ]
        semantic = {"1": 0.9, "2": 0.9}
        scored = rank_jobs(jobs, candidate, config, semantic)
        assert len(scored) == 1
        assert scored[0].job.id == "1"

    def test_filters_below_threshold(self) -> None:
        candidate = _make_candidate()
        config = MatchingConfig(minimum_score=0.8, top_n=10)
        jobs = [_make_job(job_id="1", description="Machine learning Python PyTorch London")]
        semantic = {"1": 0.3}
        scored = rank_jobs(jobs, candidate, config, semantic)
        assert len(scored) == 0

    def test_top_n_limit(self) -> None:
        # rank_jobs returns all scored jobs; top_n is applied in the pipeline
        candidate = _make_candidate()
        config = MatchingConfig(minimum_score=0.0, top_n=2)
        jobs = [_make_job(job_id=str(i), description="Machine learning Python PyTorch London") for i in range(5)]
        semantic = {str(i): 0.8 for i in range(5)}
        scored = rank_jobs(jobs, candidate, config, semantic)
        assert len(scored) == 5  # all pass, top_n applied later in pipeline

    def test_empty_jobs(self) -> None:
        candidate = _make_candidate()
        config = MatchingConfig()
        scored = rank_jobs([], candidate, config, {})
        assert scored == []

    def test_seniority_filter_disabled_keeps_director(self) -> None:
        candidate = CandidateConfig(
            name="Test",
            location=LocationConfig(countries=["UK"], cities=["London"], remote=True),
            titles=["Research Scientist"],
            must_have_skills=[],
            desirable_skills=[],
            exclusions=["sales"],
            seniority_filter=False,
            cv_path="",
        )
        config = MatchingConfig(minimum_score=0.0, top_n=10)
        jobs = [
            _make_job(job_id="1", title="Director of Research"),
            _make_job(job_id="2", title="Research Scientist"),
        ]
        semantic = {"1": 0.9, "2": 0.9}
        scored = rank_jobs(jobs, candidate, config, semantic)
        assert len(scored) == 2

    def test_seniority_filter_enabled_excludes_director(self) -> None:
        candidate = CandidateConfig(
            name="Test",
            location=LocationConfig(countries=["UK"], cities=["London"], remote=True),
            titles=["Research Scientist"],
            must_have_skills=[],
            desirable_skills=[],
            exclusions=["sales"],
            seniority_filter=True,
            cv_path="",
        )
        config = MatchingConfig(minimum_score=0.0, top_n=10)
        jobs = [
            _make_job(job_id="1", title="Director of Research"),
            _make_job(job_id="2", title="Research Scientist"),
        ]
        semantic = {"1": 0.9, "2": 0.9}
        scored = rank_jobs(jobs, candidate, config, semantic)
        assert len(scored) == 1
        assert scored[0].job.id == "2"

    def test_experience_filter_excludes_high_requirement(self) -> None:
        candidate = CandidateConfig(
            name="Test",
            location=LocationConfig(countries=["UK"], cities=["London"], remote=True),
            titles=["Research Scientist"],
            must_have_skills=[],
            desirable_skills=[],
            exclusions=[],
            seniority_filter=False,
            max_years_experience=5,
            cv_path="",
        )
        config = MatchingConfig(minimum_score=0.0, top_n=10)
        jobs = [
            _make_job(job_id="1", description="Requires 9+ years of experience in research"),
            _make_job(job_id="2", description="Requires 3 years experience"),
        ]
        semantic = {"1": 0.9, "2": 0.9}
        scored = rank_jobs(jobs, candidate, config, semantic)
        assert len(scored) == 1
        assert scored[0].job.id == "2"

    def test_experience_filter_none_keeps_all(self) -> None:
        candidate = CandidateConfig(
            name="Test",
            location=LocationConfig(countries=["UK"], cities=["London"], remote=True),
            titles=["Research Scientist"],
            must_have_skills=[],
            desirable_skills=[],
            exclusions=[],
            seniority_filter=False,
            max_years_experience=None,
            cv_path="",
        )
        config = MatchingConfig(minimum_score=0.0, top_n=10)
        jobs = [
            _make_job(job_id="1", description="Requires 15+ years of experience"),
            _make_job(job_id="2", description="Entry level role"),
        ]
        semantic = {"1": 0.9, "2": 0.9}
        scored = rank_jobs(jobs, candidate, config, semantic)
        assert len(scored) == 2

    def test_strict_location_excludes_non_local(self) -> None:
        candidate = CandidateConfig(
            name="Test",
            location=LocationConfig(
                countries=["UK"],
                cities=["London"],
                remote=True,
                acceptable_areas=["Surrey", "Kent"],
                strict=True,
            ),
            titles=["Research Scientist"],
            must_have_skills=[],
            desirable_skills=[],
            exclusions=[],
            seniority_filter=False,
            cv_path="",
        )
        config = MatchingConfig(minimum_score=0.0, top_n=10)
        jobs = [
            _make_job(job_id="1", location="London, UK", description="Research role"),
            _make_job(job_id="2", location="Remote", description="Research role"),
            _make_job(job_id="3", location="Manchester, UK", description="Research role"),
        ]
        semantic = {"1": 0.9, "2": 0.9, "3": 0.9}
        scored = rank_jobs(jobs, candidate, config, semantic)
        ids = {s.job.id for s in scored}
        assert "1" in ids  # London — city match
        assert "2" in ids  # Remote — remote match
        assert "3" not in ids  # Manchester — not acceptable, filtered out
