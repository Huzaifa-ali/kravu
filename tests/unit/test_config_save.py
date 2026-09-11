"""Unit tests for config save helpers (profile.json / searches.yaml round-trip)."""

from __future__ import annotations

from pathlib import Path

from kravu import config
from kravu.domain.models import Profile, ResumeFacts


def test_save_profile_round_trips(kravu_home: Path) -> None:
    profile = Profile(
        name="Jane Dev",
        email="j@x.io",
        headline="SRE",
        location="NYC",
        summary="Builds reliable systems.",
        skills=["Python", "AWS"],
        resume_facts=ResumeFacts(
            raw_text="Jane Dev resume text",
            companies=["Acme"],
            school="State U",
            metrics=["cut latency 40%"],
            skills=["Python", "AWS"],
        ),
    )

    config.ensure_dirs()
    config.save_profile(profile)

    assert config.profile_path().exists()
    loaded = config.load_profile()
    assert loaded["name"] == "Jane Dev"
    assert loaded["skills"] == ["Python", "AWS"]
    assert loaded["resume_facts"]["companies"] == ["Acme"]
    assert loaded["resume_facts"]["raw_text"] == "Jane Dev resume text"


def test_save_searches_round_trips(kravu_home: Path) -> None:
    searches = {
        "sources": {"jobspy": {"enabled": True, "sites": ["indeed"]}},
        "defaults": {"per_run_cap": 25},
        "min_score": 7,
        "searches": [
            {"name": "primary", "search_term": "DevOps", "country_indeed": "USA"}
        ],
    }

    config.ensure_dirs()
    config.save_searches(searches)

    assert config.searches_path().exists()
    loaded = config.load_searches()
    assert loaded["searches"][0]["search_term"] == "DevOps"
    assert loaded["min_score"] == 7


def test_config_exists_helpers(kravu_home: Path) -> None:
    assert config.profile_exists() is False
    assert config.searches_exist() is False
    config.ensure_dirs()
    config.save_profile(Profile(name="Al"))
    assert config.profile_exists() is True
