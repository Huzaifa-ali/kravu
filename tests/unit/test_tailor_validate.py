"""Unit tests for the deterministic fabrication validator (pure, no LLM)."""

from __future__ import annotations

from kravu.domain.models import ResumeFacts
from kravu.services.tailor_validate import validate_no_fabrication


def _facts() -> ResumeFacts:
    return ResumeFacts(
        raw_text="Worked at Acme. State University. Cut latency 40%.",
        companies=["Acme"],
        school="State University",
        metrics=["cut latency 40%"],
        skills=["Python", "AWS"],
    )


def test_passes_clean_rewording() -> None:
    resume = "Acme — built Python services on AWS. State University. Cut latency 40%."
    issues = validate_no_fabrication(resume, _facts())
    assert issues == []


def test_flags_out_of_set_skill() -> None:
    resume = "Acme. State University. Expert in Kubernetes and Python."
    issues = validate_no_fabrication(resume, _facts())
    assert any("Kubernetes" in i for i in issues)


def test_flags_dropped_company() -> None:
    resume = "Some Other Corp. State University."
    issues = validate_no_fabrication(resume, _facts())
    assert any("Acme" in i for i in issues)


def test_flags_banned_words() -> None:
    resume = "Acme. State University. A results-driven go-getter who leverages synergy."
    issues = validate_no_fabrication(resume, _facts())
    assert any("banned" in i.lower() for i in issues)
