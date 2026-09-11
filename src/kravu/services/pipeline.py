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
    ) -> dict[str, str]:
        """Run every step in order and return a per-step status summary.

        Each value is ``"ok"`` on success or an error string if that step
        crashed. The pipeline never aborts on a single step's failure. The
        optional ``progress`` reporter is threaded into every step.
        """
        summary: dict[str, str] = {}
        for step in self._steps:
            try:
                step.use_case.run(store, progress=progress)
                summary[step.name] = "ok"
            except Exception as exc:  # noqa: BLE001 - report and continue per spec
                summary[step.name] = f"error: {exc}"
        return summary
