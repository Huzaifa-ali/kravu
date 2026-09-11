"""Unit tests for the entrypoint's concrete RichProgressReporter.

Drives a real Rich ``Progress`` (no live rendering) to lock the bar-honesty
rule: a step that processes fewer items than its declared total must NOT be
force-filled to that total. Explore capping at 100 but finding 1 job renders
``1/1`` — never ``100/100`` (bug: the bar inflated to the limit).
"""

from __future__ import annotations

from rich.progress import Progress

from kravu.entrypoints.cli import RichProgressReporter, _progress_columns


def _task(progress: Progress, name: str):
    return next(t for t in progress.tasks if t.description == name)


def test_finish_step_does_not_inflate_bar_to_total() -> None:
    with Progress(*_progress_columns(), auto_refresh=False) as progress:
        reporter = RichProgressReporter(progress)
        reporter.start_step("explore", total=100)
        reporter.advance("explore", "Acme")  # one real item of a 100 cap
        reporter.finish_step("explore", "1 new jobs")

        task = _task(progress, "explore")
        assert task.completed == 1
        assert task.total == 1
        assert task.finished


def test_finish_step_marks_full_step_complete() -> None:
    with Progress(*_progress_columns(), auto_refresh=False) as progress:
        reporter = RichProgressReporter(progress)
        reporter.start_step("expand", total=3)
        for company in ("A", "B", "C"):
            reporter.advance("expand", company)
        reporter.finish_step("expand")

        task = _task(progress, "expand")
        assert task.completed == 3
        assert task.total == 3
        assert task.finished


def test_finish_step_is_safe_without_start() -> None:
    with Progress(*_progress_columns(), auto_refresh=False) as progress:
        RichProgressReporter(progress).finish_step("never-started")  # no raise
