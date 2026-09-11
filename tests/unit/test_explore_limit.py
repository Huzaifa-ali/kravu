"""ExploreJobs enforces the overall run limit across all sources."""

from __future__ import annotations

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job
from kravu.services.explore import ExploreJobs


class _Source:
    def __init__(self, name: str, urls: list[str]) -> None:
        self.name = name
        self._urls = urls

    def discover(self, searches: dict[str, object], limit: int) -> list[Job]:
        return [Job(url=u, title="Dev", description="short") for u in self._urls]


def test_explore_admits_at_most_limit(repo: JobRepository) -> None:
    src_a = _Source("a", [f"https://a.test/{i}" for i in range(6)])
    src_b = _Source("b", [f"https://b.test/{i}" for i in range(6)])
    added = ExploreJobs([src_a, src_b]).run(repo, {"searches": []}, limit=4)
    assert added == 4
    assert repo.stats()["total"] == 4


def test_explore_dedupes_then_caps(repo: JobRepository) -> None:
    shared = ["https://x.test/1", "https://x.test/2"]
    src_a = _Source("a", shared)
    src_b = _Source("b", shared + ["https://x.test/3", "https://x.test/4"])
    added = ExploreJobs([src_a, src_b]).run(repo, {"searches": []}, limit=3)
    assert added == 3


def test_single_source_fills_limit(repo: JobRepository) -> None:
    src = _Source("a", [f"https://a.test/{i}" for i in range(10)])
    added = ExploreJobs([src]).run(repo, {"searches": []}, limit=5)
    assert added == 5
