"""Unit tests for SuggestSearches and searches-schema validation."""

from __future__ import annotations

import pytest

from kravu.domain.models import Profile, ResumeFacts
from kravu.exceptions import SearchesConfigError
from kravu.services.suggest_searches import SuggestSearches, validate_searches


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return self._reply


def _profile() -> Profile:
    return Profile(
        name="Jane",
        location="NYC",
        skills=["Python"],
        resume_facts=ResumeFacts(raw_text="x", skills=["Python"]),
    )


def test_suggest_builds_valid_searches_dict() -> None:
    reply = '{"search_term": "DevOps engineer", "location": "NYC", "is_remote": true}'
    result = SuggestSearches(_FakeLLM(reply)).run(_profile())

    assert result["searches"][0]["search_term"] == "DevOps engineer"
    assert result["sources"]["jobspy"]["enabled"] is True
    assert result["defaults"]["per_run_cap"] == 25
    validate_searches(result)


def test_validate_requires_country_indeed_when_indeed_site() -> None:
    bad = {
        "sources": {"jobspy": {"enabled": True, "sites": ["indeed"]}},
        "searches": [{"name": "d", "search_term": "x", "location": "US"}],
    }
    with pytest.raises(SearchesConfigError):
        validate_searches(bad)


def test_validate_requires_at_least_one_source() -> None:
    with pytest.raises(SearchesConfigError):
        validate_searches(
            {
                "sources": {"jobspy": {"enabled": False}, "ats": {"enabled": False}},
                "searches": [],
            }
        )


def test_validate_rejects_indeed_filter_conflict() -> None:
    bad = {
        "sources": {"jobspy": {"enabled": True, "sites": ["indeed"]}},
        "searches": [
            {
                "name": "d",
                "search_term": "x",
                "location": "US",
                "country_indeed": "USA",
                "hours_old": 168,
                "job_type": "fulltime",
                "is_remote": True,
            }
        ],
    }
    with pytest.raises(SearchesConfigError):
        validate_searches(bad)
