"""Integration tests for the `kravu init` wizard (LLM patched; CliRunner)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from kravu import config
from kravu.entrypoints import cli


class _FakeLLM:
    """A fake LLMClient returning canned BuildProfile / SuggestSearches JSON."""

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        if "job-search targets" in prompt:
            return '{"search_term": "DevOps engineer", "location": "NYC", "is_remote": true}'
        return (
            '{"name": "Jane Dev", "email": "j@x.io", "headline": "SRE", '
            '"location": "NYC", "summary": "Reliable systems.", '
            '"skills": ["Python", "AWS"], "companies": ["Acme"], '
            '"school": "State U", "metrics": ["cut latency 40%"]}'
        )


def _write_cv(tmp_path: Path) -> Path:
    cv = tmp_path / "cv.txt"
    cv.write_text("Jane Dev — SRE at Acme. Python, AWS. State U.", encoding="utf-8")
    return cv


def _patch_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "LiteLLMClient", lambda *a, **k: _FakeLLM())
    # Isolate the wizard from ambient .env files so tests control the env fully.
    monkeypatch.setattr(config, "load_env", lambda: None)


def test_init_happy_path_writes_profile_and_searches(
    kravu_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "present")
    cv = _write_cv(tmp_path)

    # Answers: resume path, model choice (1=default gemini), keep profile, keep searches
    stdin = f"{cv}\n1\ny\ny\n"
    result = CliRunner().invoke(cli.app, ["init"], input=stdin)

    assert result.exit_code == 0, result.stdout
    assert config.profile_exists()
    assert config.searches_exist()
    loaded = config.load_profile()
    assert loaded["name"] == "Jane Dev"
    assert loaded["resume_facts"]["companies"] == ["Acme"]
    searches = config.load_searches()
    assert searches["searches"][0]["search_term"] == "DevOps engineer"
    assert "kravu run" in result.stdout


def test_init_resume_file_not_found(
    kravu_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "present")

    missing = tmp_path / "nope.txt"
    stdin = f"{missing}\n"
    monkeypatch.chdir(tmp_path)  # empty CWD so no project .env is loaded
    result = CliRunner().invoke(cli.app, ["init"], input=stdin)

    assert result.exit_code != 0
    assert not config.profile_exists()


def test_init_hard_stops_when_key_missing(
    kravu_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    cv = _write_cv(tmp_path)

    stdin = f"{cv}\n1\n"  # resume path, choose gemini (needs key)
    # Empty CWD so a developer's project-level .env cannot supply the key.
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli.app, ["init"], input=stdin)

    assert result.exit_code != 0
    assert "GEMINI_API_KEY" in result.stdout
    assert not config.profile_exists()


def test_init_safe_rerun_declined_keeps_existing(
    kravu_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_llm(monkeypatch)
    monkeypatch.setenv("GEMINI_API_KEY", "present")
    config.ensure_dirs()
    from kravu.domain.models import Profile

    config.save_profile(Profile(name="Existing User"))

    # Decline the overwrite prompt.
    result = CliRunner().invoke(cli.app, ["init"], input="n\n")

    assert result.exit_code == 0
    # Existing profile untouched.
    assert config.load_profile()["name"] == "Existing User"
