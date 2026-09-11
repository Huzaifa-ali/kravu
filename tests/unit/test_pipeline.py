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
        self._log.append(self._name)


class _BoomStep:
    def run(
        self,
        store: object,
        limit: int | None = None,
        *,
        progress: ProgressReporter = NO_PROGRESS,
    ) -> None:
        raise RuntimeError("kaboom")


class _InterruptStep:
    def run(
        self,
        store: object,
        limit: int | None = None,
        *,
        progress: ProgressReporter = NO_PROGRESS,
    ) -> None:
        raise KeyboardInterrupt


def test_pipeline_runs_steps_in_order() -> None:
    log: list[str] = []
    steps = [
        PipelineStep("explore", _RecordingStep("explore", log)),
        PipelineStep("score", _RecordingStep("score", log)),
    ]
    result = Pipeline(steps).run(store=object())
    assert log == ["explore", "score"]
    assert result["explore"] == "ok"
    assert result["score"] == "ok"


def test_pipeline_continues_after_step_crash() -> None:
    log: list[str] = []
    steps = [
        PipelineStep("expand", _BoomStep()),
        PipelineStep("score", _RecordingStep("score", log)),
    ]
    result = Pipeline(steps).run(store=object())
    assert "kaboom" in result["expand"]
    assert log == ["score"]


def test_pipeline_start_from_skips_earlier_steps() -> None:
    log: list[str] = []
    steps = [
        PipelineStep("explore", _RecordingStep("explore", log)),
        PipelineStep("expand", _RecordingStep("expand", log)),
        PipelineStep("score", _RecordingStep("score", log)),
        PipelineStep("tailor", _RecordingStep("tailor", log)),
    ]
    result = Pipeline(steps).run(store=object(), start_from="score")
    assert log == ["score", "tailor"]
    assert set(result) == {"score", "tailor"}


def test_pipeline_start_from_first_step_runs_all() -> None:
    log: list[str] = []
    steps = [
        PipelineStep("explore", _RecordingStep("explore", log)),
        PipelineStep("score", _RecordingStep("score", log)),
    ]
    Pipeline(steps).run(store=object(), start_from="explore")
    assert log == ["explore", "score"]


def test_pipeline_start_from_unknown_step_runs_nothing() -> None:
    log: list[str] = []
    steps = [PipelineStep("explore", _RecordingStep("explore", log))]
    result = Pipeline(steps).run(store=object(), start_from="nope")
    assert log == []
    assert result == {}


def test_pipeline_keyboard_interrupt_aborts_immediately() -> None:
    log: list[str] = []
    steps = [
        PipelineStep("score", _InterruptStep()),
        PipelineStep("tailor", _RecordingStep("tailor", log)),
    ]
    try:
        Pipeline(steps).run(store=object())
    except KeyboardInterrupt:
        pass
    else:  # pragma: no cover - the test fails loudly if no interrupt propagates
        raise AssertionError("KeyboardInterrupt did not propagate")
    # tailor must NOT have run — an interrupt stops the whole pipeline.
    assert log == []
