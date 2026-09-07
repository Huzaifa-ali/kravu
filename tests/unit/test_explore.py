"""Unit tests for the ExploreJobs use case (fake source + real temp repo)."""

from __future__ import annotations

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job
from kravu.services.explore import ExploreJobs, normalize_url


class _FakeSource:
    name = "fake"

    def __init__(self, jobs: list[Job]) -> None:
        self._jobs = jobs
        self.notes: dict[str, str] = {}

    def discover(self, searches: dict[str, object]) -> list[Job]:
        return self._jobs


def test_normalize_url_strips_tracking_and_lowercases_host() -> None:
    a = normalize_url("https://Example.com/job/1?utm_source=x#frag")
    b = normalize_url("https://example.com/job/1")
    assert a == b


def test_explore_dedupes_by_normalized_url(repo: JobRepository) -> None:
    source = _FakeSource(
        [
            Job(
                url="https://Example.com/1?utm_source=x", title="A", description="short"
            ),
            Job(url="https://example.com/1", title="A dup", description="short"),
        ]
    )
    added = ExploreJobs([source]).run(repo, {"searches": []})
    assert added == 1
    assert len(repo.shortlist(min_score=0)) == 0
    assert repo.stats()["total"] == 1


def test_explore_promotes_only_rich_descriptions(repo: JobRepository) -> None:
    rich = (
        "Responsibilities: build things. Requirements: 5 years Python. "
        "Qualifications: degree. " * 5
    )
    source = _FakeSource(
        [
            Job(url="https://a.test/rich", title="R", description=rich),
            Job(url="https://a.test/thin", title="T", description="Apply now!"),
        ]
    )
    ExploreJobs([source]).run(repo, {"searches": []})
    rich_job = repo.get("https://a.test/rich")
    thin_job = repo.get("https://a.test/thin")
    assert rich_job is not None and rich_job.full_description is not None
    assert thin_job is not None and thin_job.full_description is None
