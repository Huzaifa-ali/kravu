"""Unit tests: per-phase attempt budgets are named constants in config."""

from __future__ import annotations

from kravu import config


def test_attempt_budgets_are_defined() -> None:
    assert config.ENRICH_MAX_ATTEMPTS == 3
    assert config.TAILOR_MAX_ATTEMPTS == 5
    assert config.COVER_MAX_ATTEMPTS == 5
    assert config.APPLY_MAX_ATTEMPTS == 3
