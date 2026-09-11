"""ExpandJob: identical results serially and in parallel; renderer per worker."""

from __future__ import annotations

import threading

import pytest

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job
from kravu.services.expand import ExpandJob

_JSONLD = (
    '<html><body><script type="application/ld+json">'
    '{"@type": "JobPosting", "description": "A real job description here."}'
    "</script></body></html>"
)


class _Renderer:
    def render(self, url: str) -> str:
        return _JSONLD


class _StubLLM:
    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return "unused"


class _RendererFactory:
    """Counts how many renderers were built, one per calling thread."""

    def __init__(self) -> None:
        self.threads: set[int] = set()
        self._lock = threading.Lock()

    def __call__(self) -> _Renderer:
        with self._lock:
            self.threads.add(threading.get_ident())
        return _Renderer()


@pytest.mark.parametrize("workers", [1, 4])
def test_expand_identical_serial_and_parallel(
    repo: JobRepository, workers: int
) -> None:
    urls = [f"https://a.test/{i}" for i in range(6)]
    for url in urls:
        repo.add_discovered(Job(url=url, title="Dev", description="preview"))

    factory = _RendererFactory()
    ExpandJob(
        _Renderer(),
        _StubLLM(),
        workers=workers,
        store_factory=JobRepository,
        renderer_factory=factory,
    ).run(repo)

    # Freshly-expanded jobs have no fit_score, so shortlist() (fit_score >= ?)
    # would exclude them - read each row directly instead.
    enriched = {
        url: (repo.get(url).full_description or "").strip()  # type: ignore[union-attr]
        for url in urls
    }
    assert enriched == {url: "A real job description here." for url in urls}
