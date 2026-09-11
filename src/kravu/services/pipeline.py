"""Pipeline: sequence the use cases. Sequencing only — no business rules.

Runs each ordered step over its outstanding work. A per-step crash is caught,
recorded in the returned summary, and the pipeline continues — a run always
produces whatever output it could (spec §7b).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from kravu.domain.ports import NO_PROGRESS, JobStore, ProgressReporter


class _UseCase(Protocol):
    def run(
        self,
        store: JobStore,
        limit: int | None = None,
        *,
        progress: ProgressReporter = ...,
    ) -> None: ...


@dataclass(slots=True)
class PipelineStep:
    """One ordered step: a named use case."""

    name: str
    use_case: _UseCase


class Pipeline:
    """Ordered, fault-tolerant runner for the pipeline use cases."""

    def __init__(self, steps: list[PipelineStep]) -> None:
        """Store the ordered steps."""
        self._steps = steps

    def run(
        self,
        store: JobStore,
        progress: ProgressReporter = NO_PROGRESS,
        *,
        start_from: str | None = None,
    ) -> dict[str, str]:
        """Run steps in order from ``start_from`` onward; return a status summary.

        Each value is ``"ok"`` on success or an error string if that step
        crashed. A single step's failure never aborts the run. A
        ``KeyboardInterrupt`` (Ctrl+C), by contrast, propagates immediately so
        the user can always stop a run — it is not treated as a per-step error.

        Args:
            store: The persistence port threaded into every step.
            progress: Optional progress sink threaded into every step.
            start_from: If given, skip every step before this one and run from it
                to the end (so ``resume score`` runs score → tailor → cover, never
                re-running explore/expand). An unknown name runs nothing.
        """
        summary: dict[str, str] = {}
        for step in self._steps_from(start_from):
            try:
                step.use_case.run(store, progress=progress)
                summary[step.name] = "ok"
            except KeyboardInterrupt:
                raise  # let Ctrl+C stop the whole run — never swallow it
            except Exception as exc:  # noqa: BLE001 - report and continue per spec
                summary[step.name] = f"error: {exc}"
        return summary

    def _steps_from(self, start_from: str | None) -> list[PipelineStep]:
        """Return the steps to run: all of them, or those from ``start_from`` on.

        An unknown ``start_from`` yields an empty list rather than silently
        running everything, so a typo fails loud (nothing runs) instead of
        re-running the full pipeline.
        """
        if start_from is None:
            return self._steps
        names = [step.name for step in self._steps]
        if start_from not in names:
            return []
        return self._steps[names.index(start_from) :]
