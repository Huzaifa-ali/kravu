"""config.workers() reads KRAVU_WORKERS with a safe default of 4."""

from __future__ import annotations

import pytest

from kravu import config


def test_workers_defaults_to_4_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KRAVU_WORKERS", raising=False)
    assert config.workers() == 4


def test_workers_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_WORKERS", "8")
    assert config.workers() == 8


def test_workers_falls_back_on_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_WORKERS", "notanumber")
    assert config.workers() == 4


def test_workers_floors_at_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_WORKERS", "0")
    assert config.workers() == 1
