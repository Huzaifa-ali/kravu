"""DraftCoverLetter produces identical results serially and in parallel."""

from __future__ import annotations

import pytest

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job, Profile, ResumeFacts
from kravu.services.cover_letter import DraftCoverLetter


def _profile() -> Profile:
    return Profile(
        name="Jane Dev",
        email="j@x.test",
        resume_facts=ResumeFacts(raw_text="Jane", skills=["Python"]),
    )


def _tailored(repo: JobRepository, url: str) -> None:
    repo.add_discovered(Job(url=url, title="Dev", company="Acme"))
    repo.set_enrichment(url, "A cover letter is required to apply.", None)
    repo.set_score(url, 9, "great")
    repo.set_tailored(url, "/tmp/resume.md")


@pytest.mark.parametrize("workers", [1, 4])
def test_cover_identical_serial_and_parallel(
    repo: JobRepository, kravu_home, workers: int
) -> None:
    urls = [f"https://a.test/{i}" for i in range(5)]
    for url in urls:
        _tailored(repo, url)

    DraftCoverLetter(
        _StubLLM(),
        _profile(),
        policy="only_if_required",
        min_score=7,
        workers=workers,
        store_factory=JobRepository,
    ).run(repo)

    decided = {j.url: j.cover_needed for j in repo.shortlist(min_score=1)}
    assert decided == {url: True for url in urls}


class _StubLLM:
    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return "Dear Hiring Manager,\n\nI am a Python developer. Regards, Jane"
