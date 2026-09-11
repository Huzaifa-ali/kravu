"""Unit tests for the Pipeline orchestrator (fake use cases)."""

from __future__ import annotations

from kravu.domain.ports import NO_PROGRESS, ProgressReporter
from kravu.services.pipeline import Pipeline, PipelineStep


class _RecordingStep:
    def __init__(self, name: str, log: list[str]) -> None:
        self._name = name
        self._log = log

    def run(
        self,
        store: object,
        limit: int | None = None,
        *,
        progress: ProgressReporter = NO_PROGRESS,
    ) -> None:
        self._log.append(f"{self._name}:{limit}")


class _BoomStep:
    def run(
        self,
        store: object,
        limit: int | None = None,
        *,
        progress: ProgressReporter = NO_PROGRESS,
    ) -> None:
        raise RuntimeError("kaboom")


def test_pipeline_runs_steps_in_order_with_cap() -> None:
    log: list[str] = []
    steps = [
        PipelineStep("explore", _RecordingStep("explore", log), capped=False),
        PipelineStep("score", _RecordingStep("score", log), capped=True),
    ]
    result = Pipeline(steps, per_run_cap=25).run(store=object())
    assert log == ["explore:None", "score:25"]
    assert result["explore"] == "ok"
    assert result["score"] == "ok"


def test_pipeline_continues_after_step_crash() -> None:
    log: list[str] = []
    steps = [
        PipelineStep("expand", _BoomStep(), capped=False),
        PipelineStep("score", _RecordingStep("score", log), capped=True),
    ]
    result = Pipeline(steps, per_run_cap=10).run(store=object())
    assert "kaboom" in result["expand"]
    assert log == ["score:10"]
