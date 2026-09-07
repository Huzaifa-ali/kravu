"""Unit tests for the DraftCoverLetter use case (fake LLM + temp repo)."""

from __future__ import annotations

from pathlib import Path

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job, Profile, ResumeFacts
from kravu.services.cover_letter import DraftCoverLetter, jd_requires_cover_letter


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return self._reply


def _profile() -> Profile:
    return Profile(
        name="Jane",
        resume_facts=ResumeFacts(raw_text="Acme. Python.", skills=["Python"]),
    )


_LETTER = (
    "Dear Hiring Manager,\n\n"
    "I built a Python service at Acme that cut latency. It solves your "
    "reliability problem directly.\n\n"
    "I would bring the same focus to your team.\n\n"
    "Best, Jane"
)


def _tailored_job(repo: JobRepository, url: str, jd: str) -> None:
    repo.add_discovered(Job(url=url, title="Dev", company="Beta"))
    repo.set_enrichment(url, jd, None)
    repo.set_score(url, 9, "great")
    repo.set_tailored(url, "/tmp/r.md")


def test_jd_detection_finds_required_signal() -> None:
    assert jd_requires_cover_letter("Please include a cover letter with your app.")
    assert not jd_requires_cover_letter("Apply now, no cover letter needed to start.")


def test_never_policy_skips_llm(repo: JobRepository, kravu_home: Path) -> None:
    _tailored_job(repo, "https://a.test/1", "some jd")
    DraftCoverLetter(_FakeLLM(_LETTER), _profile(), policy="never", min_score=7).run(
        repo
    )
    job = repo.get("https://a.test/1")
    assert job is not None and job.cover_needed is False
    assert job.cover_letter_path is None


def test_only_if_required_writes_when_detected(
    repo: JobRepository, kravu_home: Path
) -> None:
    _tailored_job(repo, "https://a.test/2", "A cover letter is required to apply.")
    DraftCoverLetter(
        _FakeLLM(_LETTER), _profile(), policy="only_if_required", min_score=7
    ).run(repo)
    job = repo.get("https://a.test/2")
    assert job is not None and job.cover_needed is True
    assert job.cover_letter_path is not None
    assert Path(job.cover_letter_path).exists()


def test_always_policy_writes_even_without_signal(
    repo: JobRepository, kravu_home: Path
) -> None:
    _tailored_job(repo, "https://a.test/3", "no signal here")
    DraftCoverLetter(_FakeLLM(_LETTER), _profile(), policy="always", min_score=7).run(
        repo
    )
    job = repo.get("https://a.test/3")
    assert job is not None and job.cover_needed is True
