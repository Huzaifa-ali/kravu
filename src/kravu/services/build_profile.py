"""BuildProfile: raw resume text -> structured Profile (setup-time use case).

One LLM call extracts structured facts; the raw text is preserved verbatim as
``ResumeFacts.raw_text`` (the tailoring ground truth). Used by ``kravu init``; it
does NOT run during ``kravu run``.
"""

from __future__ import annotations

from kravu.adapters import prompts
from kravu.adapters.llm import parse_json
from kravu.domain.models import Profile, ResumeFacts
from kravu.domain.ports import LLMClient


class BuildProfile:
    """Extract a structured ``Profile`` from raw resume text."""

    def __init__(self, llm: LLMClient) -> None:
        """Store the injected model port."""
        self._llm = llm

    def run(self, raw_resume_text: str) -> Profile:
        """Return a structured ``Profile`` for ``raw_resume_text``.

        Args:
            raw_resume_text: The full text extracted from the user's CV.

        Returns:
            A ``Profile`` whose ``resume_facts.raw_text`` is the original text.
        """
        reply = self._llm.complete(
            prompts.build_profile_prompt(raw_resume_text), temperature=0.0
        )
        data = parse_json(reply)
        skills = [str(s) for s in data.get("skills", [])]
        facts = ResumeFacts(
            raw_text=raw_resume_text,
            companies=[str(c) for c in data.get("companies", [])],
            school=str(data.get("school", "")),
            metrics=[str(m) for m in data.get("metrics", [])],
            skills=skills,
        )
        return Profile(
            name=str(data.get("name", "")),
            email=str(data.get("email", "")),
            headline=str(data.get("headline", "")),
            location=str(data.get("location", "")),
            summary=str(data.get("summary", "")),
            skills=skills,
            resume_facts=facts,
        )
