"""TailorResume: rewrite a resume per role under a zero-fabrication guard.

The LLM returns structured sections; code assembles the resume and ALWAYS injects
the name/contact header from the profile (that fabrication class is removed by
construction — the ResumeFlow pattern). Two layers then gate the output: the
deterministic validator (cheap) and an always-on LLM judge (semantic). Only a
resume that passes both is written, alongside a ``_REPORT.json`` transparency
artifact. On exhaustion of ``tailor_attempts``, nothing is written (spec §7a).
"""

from __future__ import annotations

import json
import re

from kravu import config
from kravu.adapters import prompts
from kravu.adapters.llm import parse_json
from kravu.domain.models import Job, Profile
from kravu.domain.ports import NO_PROGRESS, JobStore, LLMClient, ProgressReporter
from kravu.exceptions import LLMResponseError
from kravu.services.parallel import StoreFactory, run_parallel
from kravu.services.tailor_validate import validate_no_fabrication

_MAX_ATTEMPTS = config.TAILOR_MAX_ATTEMPTS


def _slug(company: str, title: str) -> str:
    raw = f"{company}-{title}".lower()
    return re.sub(r"[^a-z0-9]+", "-", raw).strip("-") or "job"


class TailorResume:
    """Tailor resumes for high-fit jobs, enforcing zero fabrication."""

    def __init__(
        self,
        llm: LLMClient,
        profile: Profile,
        min_score: int,
        *,
        workers: int = 1,
        store_factory: StoreFactory | None = None,
    ) -> None:
        """Store the model port, candidate profile, and fit threshold.

        Args:
            llm: The model port used to tailor and judge each resume.
            profile: The candidate profile whose resume facts constrain tailoring.
            min_score: The threshold a job must clear to be tailored.
            workers: Degree of concurrency for per-job tailoring (``<= 1`` serial).
            store_factory: Builds a fresh per-thread store when running in
                parallel; each worker thread must use its own SQLite connection.
                ``None`` keeps the shared store (serial-safe default).
        """
        self._llm = llm
        self._profile = profile
        self._min_score = min_score
        self._workers = workers
        self._store_factory = store_factory

    def run(
        self,
        store: JobStore,
        limit: int | None = None,
        *,
        progress: ProgressReporter = NO_PROGRESS,
    ) -> None:
        """Tailor every pending high-fit job (up to ``limit``). Never raises."""
        config.ensure_dirs()
        jobs = store.pending_tailoring(self._min_score, limit)
        progress.start_step("tailor", len(jobs))
        run_parallel(
            jobs,
            lambda job: self._tailor_one(self._store_for(store), job),
            workers=self._workers,
            on_done=lambda job: progress.advance("tailor", job.company),
        )
        progress.finish_step("tailor")

    def _store_for(self, fallback: JobStore) -> JobStore:
        """Return this worker thread's own store, or the shared one if serial."""
        if self._store_factory is None:
            return fallback
        store = self._store_factory()
        assert isinstance(store, JobStore)
        return store

    def _tailor_one(self, store: JobStore, job: Job) -> None:
        prompt = prompts.tailor_prompt(
            self._profile.resume_facts, job.full_description or "", job.title
        )
        issues: list[str] = []
        for _ in range(_MAX_ATTEMPTS):
            store.bump_tailor_attempts(job.url)
            attempt_prompt = self._with_feedback(prompt, issues)
            try:
                sections = parse_json(self._llm.complete(attempt_prompt))
            except LLMResponseError:
                issues = ["Return valid JSON only."]
                continue
            resume = self._assemble(sections)
            issues = validate_no_fabrication(resume, self._profile.resume_facts)
            if issues:
                continue
            judge = self._judge(resume)
            if judge.get("verdict") != "pass":
                issues = [f"Judge flagged: {judge.get('fabrications')}"]
                continue
            self._write(store, job, resume, judge)
            return

    @staticmethod
    def _with_feedback(prompt: str, issues: list[str]) -> str:
        if not issues:
            return prompt
        return (
            prompt
            + "\n\nFix these problems from the last attempt:\n- "
            + "\n- ".join(issues)
        )

    def _judge(self, resume: str) -> dict[str, object]:
        prompt = prompts.tailor_judge_prompt(
            self._profile.resume_facts.raw_text, resume
        )
        try:
            return parse_json(self._llm.complete(prompt))
        except LLMResponseError:
            return {"verdict": "fail", "fabrications": ["unparseable judge output"]}

    def _assemble(self, sections: dict[str, object]) -> str:
        profile = self._profile
        lines = [f"# {profile.name}"]
        contact = " | ".join(p for p in (profile.email, profile.location) if p)
        if contact:
            lines.append(contact)
        title = sections.get("title")
        if title:
            lines.append(f"\n## {title}")
        summary = sections.get("summary")
        if summary:
            lines.append(f"\n{summary}")
        skills = sections.get("skills")
        if isinstance(skills, dict):
            lines.append("\n## Skills")
            for group, items in skills.items():
                joined = ", ".join(str(i) for i in items)
                lines.append(f"- **{group}:** {joined}")
        experience = sections.get("experience")
        if isinstance(experience, list):
            lines.append("\n## Experience")
            for role in experience:
                if not isinstance(role, dict):
                    continue
                lines.append(
                    f"\n### {role.get('role', '')} — {role.get('company', '')} "
                    f"({role.get('dates', '')})"
                )
                for bullet in role.get("bullets", []) or []:
                    lines.append(f"- {bullet}")
        projects = sections.get("projects")
        if isinstance(projects, list) and projects:
            lines.append("\n## Projects")
            for project in projects:
                if not isinstance(project, dict):
                    continue
                lines.append(f"\n### {project.get('name', '')}")
                for bullet in project.get("bullets", []) or []:
                    lines.append(f"- {bullet}")
        education = sections.get("education")
        if education:
            lines.append(f"\n## Education\n{education}")
        return "\n".join(lines)

    def _write(
        self, store: JobStore, job: Job, resume: str, judge: dict[str, object]
    ) -> None:
        name = _slug(job.company, job.title)
        resume_path = config.tailored_dir() / f"{name}.md"
        report_path = config.tailored_dir() / f"{name}_REPORT.json"
        resume_path.write_text(resume, encoding="utf-8")
        report = {"url": job.url, "validator_issues": [], "judge": judge}
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        store.set_tailored(job.url, str(resume_path))
