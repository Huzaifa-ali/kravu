"""Integration tests for JobRepository.clear_all (the `kravu clean` backend)."""

from __future__ import annotations

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job


def _discover(repo: JobRepository, url: str) -> None:
    repo.add_discovered(Job(url=url, title="Dev", company="Acme"))


def test_clear_all_removes_every_job_and_reports_count(repo: JobRepository) -> None:
    _discover(repo, "https://a.test/1")
    _discover(repo, "https://a.test/2")

    removed = repo.clear_all()

    assert removed == 2
    assert repo.stats()["total"] == 0


def test_clear_all_on_empty_table_returns_zero(repo: JobRepository) -> None:
    assert repo.clear_all() == 0
