"""Composition root helpers: wire adapters and use cases into pipeline steps.

Pure wiring, kept out of the Typer layer so it can be unit-tested. Adapters are
constructed at the edge (in ``cli.py``) and passed in here; this module only
assembles them into the ordered ``PipelineStep`` list and selects an apply driver.

ExploreJobs takes ``run(store, searches, limit)`` rather than the pipeline's
uniform ``run(store, limit=None)``, so it is wrapped in ``_ExploreStep`` which
captures the searches dict and the run limit and exposes the uniform signature.
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
from kravu.domain.ports import (
    NO_PROGRESS,
    DiscoverySource,
    JobStore,
    LLMClient,
    ProgressReporter,
)
from kravu.services.cover_letter import DraftCoverLetter
from kravu.services.expand import ExpandJob, PageRenderer
from kravu.services.explore import ExploreJobs
from kravu.services.parallel import StoreFactory
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
    """Adapt ExploreJobs to the pipeline's uniform ``run(store, ...)`` shape.

    ExploreJobs needs the searches config and the run limit, captured here so the
    step exposes the uniform ``run(store, limit=None, *, progress)`` signature the
    pipeline calls.
    """

    def __init__(
        self, explore: ExploreJobs, searches: dict[str, Any], limit: int
    ) -> None:
        """Capture the ExploreJobs use case, the searches config, and the limit."""
        self._explore = explore
        self._searches = searches
        self._limit = limit

    def run(
        self,
        store: JobStore,
        limit: int | None = None,
        *,
        progress: ProgressReporter = NO_PROGRESS,
    ) -> None:
        """Run discovery with the captured searches and limit."""
        self._explore.run(store, self._searches, self._limit, progress=progress)


def build_pipeline_steps(
    sources: list[DiscoverySource],
    llm: LLMClient,
    profile: Profile,
    renderer: PageRenderer,
    min_score: int,
    cover_policy: str,
    searches: dict[str, Any],
    limit: int,
    *,
    workers: int = 1,
    store_factory: StoreFactory | None = None,
) -> list[PipelineStep]:
    """Assemble the ordered pipeline steps from constructed adapters.

    Explore admits up to ``limit`` new jobs; the remaining steps process all of
    their pending work. ``workers`` and ``store_factory`` parallelize the score
    step; the serial-safe defaults leave every other step unchanged.
    """
    return [
        PipelineStep("explore", _ExploreStep(ExploreJobs(sources), searches, limit)),
        PipelineStep("expand", ExpandJob(renderer, llm)),
        PipelineStep(
            "score",
            ScoreJobFit(
                llm,
                profile,
                min_score,
                workers=workers,
                store_factory=store_factory,
            ),
        ),
        PipelineStep("tailor", TailorResume(llm, profile, min_score)),
        PipelineStep("cover", DraftCoverLetter(llm, profile, cover_policy, min_score)),
    ]


def select_driver(name: str) -> BrowserAgentDriver:
    """Return the apply driver for ``name`` (defaults to Kiro if unknown)."""
    driver_cls = _DRIVERS.get(name, KiroDriver)
    return driver_cls()
