"""ScoreJobFit produces identical results serially and in parallel."""

from __future__ import annotations

import pytest

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job, Profile, ResumeFacts
from kravu.services.score import ScoreJobFit


class _StubLLM:
    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return '{"reasoning": "ok", "matched_keywords": [], "score": 8}'


def _profile() -> Profile:
    return Profile(
        resume_facts=ResumeFacts(raw_text="Jane, Python dev", skills=["Python"])
    )


@pytest.mark.parametrize("workers", [1, 4])
def test_score_identical_serial_and_parallel(repo: JobRepository, workers: int) -> None:
    urls = [f"https://a.test/{i}" for i in range(6)]
    for url in urls:
        repo.add_discovered(Job(url=url, title="Dev"))
        repo.set_enrichment(url, "Python role. Requirements: Python.", None)

    ScoreJobFit(
        _StubLLM(),
        _profile(),
        min_score=7,
        workers=workers,
        store_factory=JobRepository,
    ).run(repo)

    scored = {j.url: j.fit_score for j in repo.shortlist(min_score=1)}
    assert scored == {url: 8 for url in urls}
