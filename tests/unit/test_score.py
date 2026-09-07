"""Unit tests for the ScoreJobFit use case (fake LLM + temp repo)."""

from __future__ import annotations

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job, Profile, ResumeFacts
from kravu.services.score import ScoreJobFit


class _SeqLLM:
    """Returns queued replies in order (to exercise the retry path)."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return reply


def _profile() -> Profile:
    return Profile(
        resume_facts=ResumeFacts(raw_text="Jane, Python dev", skills=["Python"])
    )


def _scored_job(repo: JobRepository, url: str) -> None:
    repo.add_discovered(Job(url=url, title="Dev"))
    repo.set_enrichment(url, "Python role. Requirements: Python.", None)


def test_score_writes_score_and_reasoning(repo: JobRepository) -> None:
    _scored_job(repo, "https://a.test/1")
    reply = (
        '{"reasoning": "Strong Python overlap.", '
        '"matched_keywords": ["Python"], "missing_skills": [], "score": 9}'
    )
    ScoreJobFit(_SeqLLM([reply]), _profile(), min_score=7).run(repo)

    job = repo.get("https://a.test/1")
    assert job is not None and job.fit_score == 9
    assert "Python" in (job.score_reasoning or "")


def test_score_clamps_out_of_range(repo: JobRepository) -> None:
    _scored_job(repo, "https://a.test/2")
    ScoreJobFit(
        _SeqLLM(['{"reasoning": "x", "score": 42}']), _profile(), min_score=7
    ).run(repo)
    job = repo.get("https://a.test/2")
    assert job is not None and job.fit_score == 10


def test_score_retries_once_then_records_zero(repo: JobRepository) -> None:
    _scored_job(repo, "https://a.test/3")
    llm = _SeqLLM(["not json", "still not json"])
    ScoreJobFit(llm, _profile(), min_score=7).run(repo)
    job = repo.get("https://a.test/3")
    assert job is not None and job.fit_score == 0
    assert "unparseable" in (job.score_reasoning or "")
    assert llm.calls == 2
