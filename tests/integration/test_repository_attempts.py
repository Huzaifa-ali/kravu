"""Repository retry gates honor the config attempt budgets."""

from __future__ import annotations

import inspect

from kravu import config
from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job


def _job(url: str) -> Job:
    return Job(url=url, title="Dev")


def test_pending_gates_use_config_constants() -> None:
    src = inspect.getsource(JobRepository)
    assert "config.ENRICH_MAX_ATTEMPTS" in src
    assert "config.TAILOR_MAX_ATTEMPTS" in src
    assert "config.COVER_MAX_ATTEMPTS" in src
    assert "config.APPLY_MAX_ATTEMPTS" in src


def test_enrichment_excludes_job_at_budget(repo: JobRepository) -> None:
    repo.add_discovered(_job("https://a.test/enrich"))
    for _ in range(config.ENRICH_MAX_ATTEMPTS):
        repo.bump_enrich_attempts("https://a.test/enrich")
    assert repo.pending_enrichment() == []


def test_enrichment_includes_job_below_budget(repo: JobRepository) -> None:
    repo.add_discovered(_job("https://a.test/enrich2"))
    for _ in range(config.ENRICH_MAX_ATTEMPTS - 1):
        repo.bump_enrich_attempts("https://a.test/enrich2")
    assert len(repo.pending_enrichment()) == 1


def test_tailoring_excludes_job_at_budget(repo: JobRepository) -> None:
    url = "https://a.test/tailor"
    repo.add_discovered(_job(url))
    repo.set_enrichment(url, "Python role. Requirements: Python.", None)
    repo.set_score(url, 9, "great")
    for _ in range(config.TAILOR_MAX_ATTEMPTS):
        repo.bump_tailor_attempts(url)
    assert repo.pending_tailoring(min_score=7) == []
