"""Composition root helpers: wire adapters and use cases into pipeline steps.

Pure wiring, kept out of the Typer layer so it can be unit-tested. Adapters are
constructed at the edge (in ``cli.py``) and passed in here; this module only
assembles them into the ordered ``PipelineStep`` list and selects an apply driver.

ExploreJobs takes ``run(store, searches)`` rather than the pipeline's uniform
``run(store, limit=None)``, so it is wrapped in ``_ExploreStep`` which captures
the searches dict and exposes the uniform signature (discovery is uncapped, so
``limit`` is ignored).
"""

from __future__ import annotations

from typing import Any

from kravu.apply.drivers.base import BrowserAgentDriver
from kravu.apply.drivers.claude_code import ClaudeCodeDriver
from kravu.apply.drivers.codex import CodexDriver
from kravu.apply.drivers.cursor import CursorDriver
from kravu.apply.drivers.gemini import GeminiDriver
from kravu.apply.drivers.kiro import KiroDriver
from kravu.domain.models import Profile
from kravu.domain.ports import DiscoverySource, JobStore, LLMClient
from kravu.services.cover_letter import DraftCoverLetter
from kravu.services.expand import ExpandJob, PageRenderer
from kravu.services.explore import ExploreJobs
from kravu.services.pipeline import PipelineStep
from kravu.services.score import ScoreJobFit
from kravu.services.tailor import TailorResume

_DRIVERS: dict[str, type[BrowserAgentDriver]] = {
    "kiro": KiroDriver,
    "claude_code": ClaudeCodeDriver,
    "codex": CodexDriver,
    "cursor": CursorDriver,
    "gemini": GeminiDriver,
}


class _ExploreStep:
    """Adapt ExploreJobs to the pipeline's uniform ``run(store, limit)`` shape.

    ExploreJobs needs the searches config, not a per-run cap; discovery is
    uncapped, so ``limit`` is accepted and ignored.
    """

    def __init__(self, explore: ExploreJobs, searches: dict[str, Any]) -> None:
        """Capture the ExploreJobs use case and the searches config."""
        self._explore = explore
        self._searches = searches

    def run(self, store: JobStore, limit: int | None = None) -> None:
        """Run discovery with the captured searches (``limit`` unused)."""
        self._explore.run(store, self._searches)


def build_pipeline_steps(
    sources: list[DiscoverySource],
    llm: LLMClient,
    profile: Profile,
    renderer: PageRenderer,
    min_score: int,
    cover_policy: str,
    searches: dict[str, Any],
) -> list[PipelineStep]:
    """Assemble the ordered pipeline steps from constructed adapters.

    LLM-spending steps (score/tailor/cover) are marked ``capped`` so the
    orchestrator applies the per-run cap; discovery/enrichment run uncapped.
    """
    return [
        PipelineStep(
            "explore", _ExploreStep(ExploreJobs(sources), searches), capped=False
        ),
        PipelineStep("expand", ExpandJob(renderer, llm), capped=False),
        PipelineStep("score", ScoreJobFit(llm, profile, min_score), capped=True),
        PipelineStep("tailor", TailorResume(llm, profile, min_score), capped=True),
        PipelineStep(
            "cover",
            DraftCoverLetter(llm, profile, cover_policy, min_score),
            capped=True,
        ),
    ]


def select_driver(name: str) -> BrowserAgentDriver:
    """Return the apply driver for ``name`` (defaults to Kiro if unknown)."""
    driver_cls = _DRIVERS.get(name, KiroDriver)
    return driver_cls()
