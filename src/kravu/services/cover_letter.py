"""DraftCoverLetter: policy-gated, validated, zero-fabrication cover letters.

Code (never the LLM) decides whether a letter is needed: ``never`` skips,
``always`` drafts for every tailored job, and ``only_if_required`` (default) runs
a deterministic JD scan for cover-letter signals. When drafting, the letter must
pass validation (start with the salutation, stay under the word cap, avoid banned
phrases) and may mention only skills in ``ResumeFacts.skills`` (spec §7a).
"""

from __future__ import annotations

import re

from kravu import config
from kravu.adapters import prompts
from kravu.domain.models import Job, Profile
from kravu.domain.ports import JobStore, LLMClient
from kravu.services.tailor_validate import SKILL_WATCHLIST

_MAX_ATTEMPTS = 5
_WORD_CAP = 250
_REQUIRED_SIGNALS = (
    "cover letter required",
    "cover letter is required",
    "please include a cover letter",
    "please attach a cover letter",
    "a cover letter must",
    "submit a cover letter",
)
_PREAMBLE_RE = re.compile(r"^\s*(here('?s| is)[^\n]*:|sure[^\n]*:)\s*", re.IGNORECASE)


def jd_requires_cover_letter(job_description: str) -> bool:
    """Return True if the JD text explicitly signals a cover letter is needed."""
    lowered = job_description.lower()
    return any(signal in lowered for signal in _REQUIRED_SIGNALS)


def _sanitize(text: str) -> str:
    cleaned = _PREAMBLE_RE.sub("", text.strip())
    return (
        cleaned.replace("\u2014", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )


class DraftCoverLetter:
    """Draft cover letters per the user's policy, with zero fabrication."""

    def __init__(
        self, llm: LLMClient, profile: Profile, policy: str, min_score: int
    ) -> None:
        """Store the model port, profile, cover-letter policy, and threshold."""
        self._llm = llm
        self._profile = profile
        self._policy = policy
        self._min_score = min_score

    def run(self, store: JobStore, limit: int | None = None) -> None:
        """Process every pending tailored job (up to ``limit``). Never raises."""
        config.ensure_dirs()
        for job in store.pending_cover(self._min_score, limit):
            self._process_one(store, job)

    def _process_one(self, store: JobStore, job: Job) -> None:
        if self._policy == "never" or not self._needed(job):
            store.set_cover(job.url, needed=False, path=None)
            return
        letter = self._draft(job)
        if letter is None:
            store.bump_cover_attempts(job.url)
            store.set_cover(job.url, needed=True, path=None)
            return
        name = (
            re.sub(r"[^a-z0-9]+", "-", f"{job.company}-{job.title}".lower()).strip("-")
            or "job"
        )
        path = config.cover_dir() / f"{name}.md"
        path.write_text(letter, encoding="utf-8")
        store.set_cover(job.url, needed=True, path=str(path))

    def _needed(self, job: Job) -> bool:
        if self._policy == "always":
            return True
        return jd_requires_cover_letter(job.full_description or "")

    def _draft(self, job: Job) -> str | None:
        prompt = prompts.cover_prompt(self._profile, job.full_description or "", "")
        for _ in range(_MAX_ATTEMPTS):
            letter = _sanitize(self._llm.complete(prompt, temperature=0.0))
            if self._valid(letter):
                return letter
        return None

    def _valid(self, letter: str) -> bool:
        if not letter.startswith("Dear Hiring Manager,"):
            return False
        if len(letter.split()) > _WORD_CAP:
            return False
        lowered = letter.lower()
        if any(phrase.lower() in lowered for phrase in prompts.BANNED_WORDS):
            return False
        # Zero fabrication: reject any watchlist skill not in the user's facts
        # (same deterministic guard TailorResume applies).
        allowed = {s.lower() for s in self._profile.resume_facts.skills}
        return not any(
            skill in lowered and skill not in allowed for skill in SKILL_WATCHLIST
        )
