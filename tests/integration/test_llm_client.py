"""Integration test for LiteLLMClient with litellm stubbed out."""

from __future__ import annotations

import sys
import types

import pytest

from kravu.adapters.llm import LiteLLMClient
from kravu.exceptions import LLMResponseError


def _install_fake_litellm(monkeypatch: pytest.MonkeyPatch, content: object) -> None:
    module = types.ModuleType("litellm")

    def completion(**_kwargs: object) -> dict[str, object]:
        return {"choices": [{"message": {"content": content}}]}

    module.completion = completion  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "litellm", module)


def test_complete_returns_content(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_litellm(monkeypatch, '{"score": 8}')
    client = LiteLLMClient(model="fake/model")
    assert client.complete("hi") == '{"score": 8}'


def test_complete_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_litellm(monkeypatch, "")
    client = LiteLLMClient(model="fake/model")
    with pytest.raises(LLMResponseError):
        client.complete("hi")
