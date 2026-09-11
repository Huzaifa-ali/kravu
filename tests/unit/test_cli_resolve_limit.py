"""CLI resolves the run limit from searches.yaml, else config default."""

from __future__ import annotations

import pytest

from kravu import config
from kravu.entrypoints.cli import _resolve_limit


def test_resolve_limit_prefers_searches_value() -> None:
    assert _resolve_limit({"limit": 42}) == 42


def test_resolve_limit_falls_back_to_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KRAVU_LIMIT", raising=False)
    assert _resolve_limit({}) == config.DEFAULT_LIMIT
