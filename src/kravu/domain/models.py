"""Core data models for kravu.

These are plain, frozen-ish dataclasses that move between services.
Persistence lives in ``kravu.adapters``; nothing here talks to the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Stage(str, Enum):
    """The pipeline stages, in dependency order."""

    DISCOVER = "discover"
    ENRICH = "enrich"
    SCORE = "score"
    TAILOR = "tailor"
    COVER = "cover"

    @classmethod
    def order(cls) -> list["Stage"]:
        return [cls.DISCOVER, cls.ENRICH, cls.SCORE, cls.TAILOR, cls.COVER]


@dataclass(slots=True)
class Profile:
    """The user's structured profile, parsed from their CV + preferences.

    ``resume_facts`` is the ground truth that the tailoring stage must preserve
    verbatim — companies, titles, dates, metrics. The LLM may reorganize and
    re-emphasize, but must never invent anything not present here.
    """

    name: str = ""
    email: str = ""
    headline: str = ""
    location: str = ""
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    resume_facts: str = ""          # raw resume text — the non-negotiable source of truth
    target_titles: list[str] = field(default_factory=list)
    target_locations: list[str] = field(default_factory=list)
    preferences: dict[str, Any] = field(default_factory=dict)

    def compact_summary(self) -> str:
        """A short, focused profile block for LLM prompts.

        Deliberately compact: we send this (not the full CV) on every scoring
        call so the prompt stays small and the model doesn't lose the signal.
        """
        parts = []
        if self.headline:
            parts.append(f"Headline: {self.headline}")
        if self.location:
            parts.append(f"Location: {self.location}")
        if self.skills:
            parts.append("Skills: " + ", ".join(self.skills))
        if self.target_titles:
            parts.append("Target roles: " + ", ".join(self.target_titles))
        if self.summary:
            parts.append("Summary: " + self.summary)
        return "\n".join(parts)


@dataclass(slots=True)
class Job:
    """A single job posting as it flows through the pipeline.

    Fields are filled in progressively: discovery sets the basics, enrichment
    adds the full description, scoring adds the fit score, and so on. ``None``
    means "this stage hasn't run yet for this job".
    """

    # Discovery
    url: str
    title: str = ""
    company: str = ""
    location: str = ""
    salary: str = ""
    source: str = ""                 # which board it came from
    description: str = ""            # short/preview description from discovery
    discovered_at: str | None = None

    # Enrichment
    full_description: str | None = None
    apply_url: str | None = None
    enriched_at: str | None = None
    enrich_error: str | None = None

    # Scoring
    fit_score: int | None = None
    score_reasoning: str | None = None
    scored_at: str | None = None

    # Tailoring
    tailored_resume_path: str | None = None
    tailored_at: str | None = None

    # Cover letter
    cover_letter_path: str | None = None
    cover_needed: bool | None = None
    cover_at: str | None = None


@dataclass(slots=True)
class ScoreResult:
    """Structured output of the scoring stage for one job."""

    score: int                       # 1-10
    reasoning: str
    missing_skills: list[str] = field(default_factory=list)
