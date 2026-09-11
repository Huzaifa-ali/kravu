"""End-to-end pipeline run with every external boundary faked (offline)."""

from __future__ import annotations

import json
from pathlib import Path

from kravu.adapters.db import init_db
from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job, Profile, ResumeFacts
from kravu.entrypoints.composition import build_pipeline_steps
from kravu.services.pipeline import Pipeline

_JSONLD = """
<html><head><script type="application/ld+json">
{"@type":"JobPosting","description":"Backend role. Responsibilities: build APIs. Requirements: Python and AWS. Qualifications: a degree."}
</script></head><body>x</body></html>
"""


class _Source:
    name = "fake"

    def discover(self, searches: dict[str, object], limit: int) -> list[Job]:
        return [
            Job(
                url="https://a.test/1",
                title="Backend Engineer",
                company="Beta",
                description="short preview",
            )
        ]


class _Renderer:
    def render(self, url: str) -> str:
        return _JSONLD


class _LLM:
    """Routes by prompt content: score, tailor sections, judge, cover."""

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        if "faithfulness judge" in prompt:
            return '{"reasoning":"ok","fabrications":[],"verdict":"pass"}'
        if "impartial career-fit evaluator" in prompt:
            return (
                '{"reasoning":"Strong Python/AWS fit.",'
                '"matched_keywords":["Python","AWS"],"missing_skills":[],'
                '"score":9}'
            )
        if "Rewrite the candidate" in prompt:
            return json.dumps(
                {
                    "title": "Backend Engineer",
                    "summary": "Built Python services on AWS at Acme.",
                    "skills": {"Core": ["Python", "AWS"]},
                    "experience": [
                        {
                            "company": "Acme",
                            "role": "Engineer",
                            "dates": "2021-2024",
                            "bullets": ["Cut latency 40% with Python on AWS."],
                        }
                    ],
                    "projects": [],
                    "education": "State University",
                }
            )
        return (
            "Dear Hiring Manager,\n\nI built a Python service on AWS at Acme "
            "that cut latency 40%. It maps to your reliability needs.\n\n"
            "I would bring that focus to your team.\n\nBest, Jane"
        )


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


def test_full_pipeline_produces_tailored_shortlist(kravu_home: Path) -> None:
    store = JobRepository(init_db(kravu_home / "kravu.db"))
    profile = _profile()
    llm = _LLM()
    steps = build_pipeline_steps(
        sources=[_Source()],
        llm=llm,
        profile=profile,
        renderer=_Renderer(),
        min_score=7,
        cover_policy="always",
        searches={"searches": []},
        limit=25,
    )
    summary = Pipeline(steps).run(store)

    assert all(v == "ok" for v in summary.values())
    shortlist = store.shortlist(7)
    assert len(shortlist) == 1
    job = shortlist[0]
    assert job.fit_score == 9
    assert job.tailored_resume_path is not None
    assert Path(job.tailored_resume_path).exists()
    assert job.cover_needed is True
    assert job.cover_letter_path is not None and Path(job.cover_letter_path).exists()
