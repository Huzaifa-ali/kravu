"""Unit tests: model and min_score come from the environment, not hardcoding."""

from __future__ import annotations

import pytest

from kravu import config
from kravu.exceptions import ConfigError


def test_model_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_MODEL", "gemini/gemma-4-26b-a4b-it")
    assert config.model() == "gemini/gemma-4-26b-a4b-it"


def test_model_raises_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KRAVU_MODEL", raising=False)
    with pytest.raises(ConfigError) as exc:
        config.model()
    assert "KRAVU_MODEL" in str(exc.value)


def test_min_score_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_MIN_SCORE", "9")
    assert config.min_score() == 9


def test_min_score_raises_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KRAVU_MIN_SCORE", raising=False)
    with pytest.raises(ConfigError) as exc:
        config.min_score()
    assert "KRAVU_MIN_SCORE" in str(exc.value)


def test_min_score_raises_on_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_MIN_SCORE", "not-a-number")
    with pytest.raises(ConfigError):
        config.min_score()


def test_cover_letter_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_COVER_LETTER", "always")
    assert config.cover_letter_default() == "always"


def test_cover_letter_raises_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KRAVU_COVER_LETTER", raising=False)
    with pytest.raises(ConfigError) as exc:
        config.cover_letter_default()
    assert "KRAVU_COVER_LETTER" in str(exc.value)


def test_cover_letter_raises_on_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_COVER_LETTER", "sometimes")
    with pytest.raises(ConfigError):
        config.cover_letter_default()


def test_has_llm_key_does_not_require_model(monkeypatch: pytest.MonkeyPatch) -> None:
    # has_llm_key must be safe to call before a model is chosen.
    monkeypatch.delenv("KRAVU_MODEL", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert config.has_llm_key() is True
