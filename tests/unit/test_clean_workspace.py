"""Unit tests for the CleanWorkspace use case."""

from __future__ import annotations

from pathlib import Path

import pytest

from kravu.services.clean import CleanResult, CleanWorkspace


class _FakeStore:
    """Minimal JobStore stand-in that only needs clear_all for this use case."""

    def __init__(self, count: int) -> None:
        self._count = count
        self.cleared = False

    def clear_all(self) -> int:
        self.cleared = True
        return self._count


def test_clean_clears_jobs_and_reports_count(
    kravu_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _FakeStore(count=5)

    result = CleanWorkspace().run(store)

    assert store.cleared is True
    assert isinstance(result, CleanResult)
    assert result.jobs_removed == 5


def test_clean_removes_generated_artifacts(
    kravu_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kravu import config

    config.ensure_dirs()
    (config.tailored_dir() / "job1.md").write_text("resume", encoding="utf-8")
    (config.tailored_dir() / "job2.md").write_text("resume", encoding="utf-8")
    (config.cover_dir() / "job1.md").write_text("cover", encoding="utf-8")

    result = CleanWorkspace().run(_FakeStore(count=0))

    assert result.files_removed == 3
    assert list(config.tailored_dir().iterdir()) == []
    assert list(config.cover_dir().iterdir()) == []


def test_clean_truncates_log_file(
    kravu_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kravu import config

    config.ensure_dirs()
    log_file = config.log_dir() / "kravu.log"
    log_file.write_text("old log lines\n", encoding="utf-8")

    CleanWorkspace().run(_FakeStore(count=0))

    assert log_file.read_text(encoding="utf-8") == ""


def test_clean_is_idempotent_on_empty_workspace(
    kravu_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = CleanWorkspace().run(_FakeStore(count=0))

    assert result.jobs_removed == 0
    assert result.files_removed == 0
