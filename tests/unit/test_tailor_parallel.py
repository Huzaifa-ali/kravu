"""TailorResume: identical results serially and in parallel; attempt integrity."""

from __future__ import annotations

import pytest

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job, Profile, ResumeFacts
from kravu.services.tailor import TailorResume

_SECTIONS = (
    '{"title": "Python Developer", "summary": "Python dev.",'
    ' "skills": {"Core": ["Python"]},'
    ' "experience": [{"role": "Dev", "company": "Acme", "dates": "2020",'
    ' "bullets": ["Built things with Python"]}]}'
)
_JUDGE = '{"verdict": "pass", "fabrications": []}'


class _StubLLM:
    """Returns tailor sections then a passing judge verdict, alternating."""

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return _JUDGE if "judge" in prompt.lower() else _SECTIONS


def _profile() -> Profile:
    return Profile(
        name="Jane Dev",
        email="j@x.test",
        resume_facts=ResumeFacts(
            raw_text="Acme. Python.", companies=["Acme"], skills=["Python"]
        ),
    )


def _scored(repo: JobRepository, url: str) -> None:
    repo.add_discovered(Job(url=url, title="Dev", company="Acme"))
    repo.set_enrichment(url, "Python role. Requirements: Python.", None)
    repo.set_score(url, 9, "great")


@pytest.mark.parametrize("workers", [1, 4])
def test_tailor_identical_serial_and_parallel(
    repo: JobRepository, kravu_home, workers: int
) -> None:
    urls = [f"https://a.test/{i}" for i in range(4)]
    for url in urls:
        _scored(repo, url)

    TailorResume(
        _StubLLM(),
        _profile(),
        min_score=7,
        workers=workers,
        store_factory=JobRepository,
    ).run(repo)

    tailored = {
        j.url: (j.tailored_resume_path is not None, j.tailor_attempts)
        for j in repo.shortlist(min_score=1)
    }
    assert tailored == {url: (True, 1) for url in urls}
