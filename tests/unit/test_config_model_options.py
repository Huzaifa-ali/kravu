"""Unit tests for model-option metadata and per-model key preflight."""

from __future__ import annotations

import pytest

from kravu import config


def test_model_options_include_default_first() -> None:
    options = config.model_options()
    assert options[0].model == "gemini/gemma-4-26b-a4b-it"
    assert all(opt.model and opt.label for opt in options)


def test_required_key_for_gemini() -> None:
    assert config.required_key_for("gemini/gemma-4-26b-a4b-it") == "GEMINI_API_KEY"


def test_required_key_for_ollama_is_none() -> None:
    assert config.required_key_for("ollama/qwen3.5:4b") is None


def test_key_present_for_model_true_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    assert config.key_present_for_model("gemini/gemma-4-26b-a4b-it") is True


def test_key_present_for_model_false_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert config.key_present_for_model("gemini/gemma-4-26b-a4b-it") is False


def test_key_present_for_ollama_always_true(monkeypatch: pytest.MonkeyPatch) -> None:
    assert config.key_present_for_model("ollama/qwen3.5:4b") is True
