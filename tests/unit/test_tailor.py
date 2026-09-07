"""Unit tests for the TailorResume use case (fake LLM + temp repo + tmp files)."""

from __future__ import annotations

import json
from pathlib import Path

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job, Profile, ResumeFacts
from kravu.services.tailor import TailorResume


class _ScriptedLLM:
    """Distinguishes tailor calls from judge calls by prompt content."""

    def __init__(self, sections: str, verdict: str) -> None:
        self._sections = sections
        self._verdict = verdict
        self.judge_calls = 0

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        if "faithfulness judge" in prompt:
            self.judge_calls += 1
            return self._verdict
        return self._sections


def _profile() -> Profile:
    return Profile(
        name="Jane Dev",
        email="jane@x.io",
        resume_facts=ResumeFacts(
            raw_text="Acme. State University. Cut latency 40%.",
            companies=["Acme"],
            school="State University",
            metrics=["cut latency 40%"],
            skills=["Python", "AWS"],
        ),
    )


def _ready_job(repo: JobRepository, url: str) -> None:
    repo.add_discovered(Job(url=url, title="Backend Engineer", company="Beta"))
    repo.set_enrichment(url, "Backend role. Requirements: Python, AWS.", None)
    repo.set_score(url, 9, "great")


_GOOD_SECTIONS = json.dumps(
    {
        "title": "Backend Engineer",
        "summary": "Built Python services on AWS at Acme.",
        "skills": {"Core": ["Python", "AWS"]},
        "experience": [
            {
                "company": "Acme",
                "role": "Engineer",
                "dates": "2021-2024",
                "bullets": ["Cut latency 40% on AWS with Python."],
            }
        ],
        "projects": [],
        "education": "State University",
    }
)


def test_tailor_writes_resume_and_report_on_pass(
    repo: JobRepository, kravu_home: Path
) -> None:
    _ready_job(repo, "https://a.test/1")
    llm = _ScriptedLLM(
        _GOOD_SECTIONS,
        '{"reasoning": "faithful", "fabrications": [], "verdict": "pass"}',
    )
    TailorResume(llm, _profile(), min_score=7).run(repo)

    job = repo.shortlist(7)[0]
    assert job.tailored_resume_path is not None
    path = Path(job.tailored_resume_path)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Jane Dev")
    assert "jane@x.io" in text
    report = Path(str(path).replace(".md", "_REPORT.json"))
    assert report.exists()


def test_tailor_writes_nothing_when_judge_fails(
    repo: JobRepository, kravu_home: Path
) -> None:
    _ready_job(repo, "https://a.test/2")
    llm = _ScriptedLLM(
        _GOOD_SECTIONS,
        '{"reasoning": "lie", "fabrications": ["Kubernetes"], "verdict": "fail"}',
    )
    TailorResume(llm, _profile(), min_score=7).run(repo)

    job = repo.get("https://a.test/2")
    assert job is not None
    assert job.tailored_resume_path is None
    assert job.tailor_attempts >= 1
