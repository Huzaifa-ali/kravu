"""Core data models for kravu.

These are plain, frozen-ish dataclasses that move between services.
Persistence lives in ``kravu.adapters``; nothing here talks to the database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PipelinePhase(str, Enum):
    """The pipeline's use cases, in dependency order.

    Named phases identify each use case for orchestration and reporting. The word
    "stage" is deliberately avoided; these correspond to the Use Case classes in
    ``kravu.services``.
    """

    EXPLORE = "explore"
    EXPAND = "expand"
    SCORE = "score"
    TAILOR = "tailor"
    COVER = "cover"

    @classmethod
    def order(cls) -> list["PipelinePhase"]:
        return [cls.EXPLORE, cls.EXPAND, cls.SCORE, cls.TAILOR, cls.COVER]


@dataclass(slots=True)
class ResumeFacts:
    """The non-negotiable ground truth extracted from the user's CV.

    ``TailorResume`` may reorder, reframe, reword, and re-emphasize freely, but may
    NEVER introduce a company, school, metric, or skill not present here. The
    deterministic validator checks that preserved entities survive and that no
    out-of-set skill is claimed; the LLM judge catches subtler fabrication.
    """

    raw_text: str = ""                       # the full original resume text (source of truth)
    companies: list[str] = field(default_factory=list)   # employers that must be preserved
    school: str = ""                         # education that must be preserved
    metrics: list[str] = field(default_factory=list)     # real numbers/metrics — must not change
    skills: list[str] = field(default_factory=list)      # the ONLY skills that may be claimed


@dataclass(slots=True)
class Profile:
    """The user's structured profile, parsed from their CV + preferences.

    ``resume_facts`` is the structured ground truth (see ``ResumeFacts``). The LLM
    may reorganize and re-emphasize, but must never invent anything not present in it.
    """

    name: str = ""
    email: str = ""
    headline: str = ""
    location: str = ""
    summary: str = ""
    skills: list[str] = field(default_factory=list)
    resume_facts: ResumeFacts = field(default_factory=ResumeFacts)
    target_titles: list[str] = field(default_factory=list)
    target_locations: list[str] = field(default_factory=list)
    preferences: dict[str, Any] = field(default_factory=dict)

    def compact_summary(self) -> str:
        """A short, focused profile block for LLM prompts."""
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
    means "this use case hasn't run yet for this job".
    """

    # Discovery
    url: str
    title: str = ""
    company: str = ""
    location: str = ""
    salary: str = ""
    source: str = ""                 # which board it came from
    apply_type: str = ""             # easy-apply | external | ats (for the Apply Agent)
    description: str = ""            # short/preview description from discovery
    discovered_at: str | None = None

    # Enrichment
    full_description: str | None = None
    apply_url: str | None = None
    enriched_at: str | None = None
    enrich_error: str | None = None
    enrich_attempts: int = 0

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

    # Apply (use case 6 — the Apply Agent)
    apply_status: str | None = None      # applied | pending | failed | parked | in_progress
    applied_at: str | None = None
    apply_error: str | None = None
    apply_attempts: int = 0


@dataclass(slots=True)
class ScoreResult:
    """Structured output of the ScoreJobFit use case for one job."""

    score: int                       # 1-10
    reasoning: str
    matched_keywords: list[str] = field(default_factory=list)
    missing_skills: list[str] = field(default_factory=list)
