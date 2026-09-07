"""Unit tests for the BuildProfile use case (fake LLM)."""

from __future__ import annotations

from kravu.services.build_profile import BuildProfile


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return self._reply


def test_build_profile_extracts_structured_facts() -> None:
    reply = (
        '{"name": "Jane Dev", "email": "j@x.io", "headline": "SRE", '
        '"location": "NYC", "summary": "Builds reliable systems.", '
        '"skills": ["Python", "AWS"], "companies": ["Acme"], '
        '"school": "State U", "metrics": ["cut latency 40%"]}'
    )
    profile = BuildProfile(_FakeLLM(reply)).run("Jane Dev, built X at Acme...")

    assert profile.name == "Jane Dev"
    assert profile.skills == ["Python", "AWS"]
    assert profile.resume_facts.companies == ["Acme"]
    assert profile.resume_facts.school == "State U"
    assert profile.resume_facts.raw_text.startswith("Jane Dev")


def test_build_profile_tolerates_missing_optional_fields() -> None:
    profile = BuildProfile(_FakeLLM('{"name": "Al"}')).run("Al resume text")
    assert profile.name == "Al"
    assert profile.resume_facts.companies == []
