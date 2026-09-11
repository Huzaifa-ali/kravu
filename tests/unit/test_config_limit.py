"""Unit tests: run limit resolves from KRAVU_LIMIT with a safe default."""

from __future__ import annotations

import pytest

from kravu import config


def test_limit_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_LIMIT", "42")
    assert config.limit() == 42


def test_limit_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KRAVU_LIMIT", raising=False)
    assert config.limit() == config.DEFAULT_LIMIT


def test_limit_defaults_on_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_LIMIT", "not-a-number")
    assert config.limit() == config.DEFAULT_LIMIT
