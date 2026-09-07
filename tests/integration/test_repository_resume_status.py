"""Integration tests for resume/status/apply repository queries."""

from __future__ import annotations

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job


def _discover(repo: JobRepository, url: str) -> None:
    repo.add_discovered(Job(url=url, title="Dev", company="Acme"))


def test_step_counts_reports_per_phase(repo: JobRepository) -> None:
    _discover(repo, "https://a.test/1")
    _discover(repo, "https://a.test/2")
    repo.set_enrichment("https://a.test/1", "A full JD with requirements.", None)
    repo.set_score("https://a.test/1", 8, "good")

    counts = repo.step_counts(min_score=7)

    assert counts["explore"]["done"] == 2
    assert counts["expand"]["done"] == 1
    assert counts["expand"]["pending"] == 1
    assert counts["score"]["done"] == 1


def test_reset_step_for_retry_clears_failed_expand(repo: JobRepository) -> None:
    _discover(repo, "https://a.test/1")
    for _ in range(3):
        repo.bump_enrich_attempts("https://a.test/1")
    repo.set_enrichment_error("https://a.test/1", "boom")
    assert repo.pending_enrichment() == []

    n = repo.reset_step_for_retry("expand")

    assert n == 1
    pending = repo.pending_enrichment()
    assert len(pending) == 1
    assert pending[0].enrich_attempts == 0


def test_pending_apply_returns_tailored_high_fit(repo: JobRepository) -> None:
    _discover(repo, "https://a.test/1")
    repo.set_enrichment("https://a.test/1", "JD requirements responsibilities", None)
    repo.set_score("https://a.test/1", 9, "great")
    repo.set_tailored("https://a.test/1", "/tmp/r.md")

    pending = repo.pending_apply(min_score=7)

    assert [j.url for j in pending] == ["https://a.test/1"]


def test_set_apply_result_and_applied_today(repo: JobRepository) -> None:
    _discover(repo, "https://a.test/1")
    repo.set_apply_result("https://a.test/1", "applied", None)

    assert repo.applied_today() == 1
    job = repo.get("https://a.test/1")
    assert job is not None
    assert job.apply_status == "applied"
