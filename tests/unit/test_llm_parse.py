"""Unit tests for defensive JSON extraction from LLM text."""

from __future__ import annotations

import pytest

from kravu.adapters.llm import parse_json
from kravu.exceptions import LLMResponseError


def test_parse_plain_json_object() -> None:
    assert parse_json('{"score": 8}') == {"score": 8}


def test_parse_json_inside_markdown_fence() -> None:
    text = 'Here you go:\n```json\n{"score": 7}\n```\nthanks'
    assert parse_json(text) == {"score": 7}


def test_parse_json_with_leading_prose() -> None:
    text = 'Sure! {"reasoning": "ok", "score": 9} — done'
    assert parse_json(text) == {"reasoning": "ok", "score": 9}


def test_parse_unparseable_raises() -> None:
    with pytest.raises(LLMResponseError):
        parse_json("no json here at all")
