"""Integration tests for the CLI commands (LLM/discovery patched)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from kravu import config
from kravu.entrypoints import cli


def test_status_reports_per_step_counts(
    kravu_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kravu.adapters.db import init_db
    from kravu.adapters.repository import JobRepository
    from kravu.domain.models import Job

    monkeypatch.setenv("KRAVU_MIN_SCORE", "7")
    repo = JobRepository(init_db(kravu_home / "kravu.db"))
    repo.add_discovered(Job(url="https://a.test/1", title="Dev"))
    repo.set_enrichment("https://a.test/1", "JD requirements responsibilities", None)

    result = CliRunner().invoke(cli.app, ["status"])

    assert result.exit_code == 0
    assert "explore" in result.stdout
    assert "expand" in result.stdout


def test_run_requires_profile(kravu_home: Path) -> None:
    result = CliRunner().invoke(cli.app, ["run"])
    assert result.exit_code != 0
    assert "kravu init" in result.stdout


def test_clean_aborts_when_user_declines(kravu_home: Path) -> None:
    from kravu.adapters.db import init_db
    from kravu.adapters.repository import JobRepository
    from kravu.domain.models import Job

    repo = JobRepository(init_db(kravu_home / "kravu.db"))
    repo.add_discovered(Job(url="https://a.test/1", title="Dev"))

    result = CliRunner().invoke(cli.app, ["clean"], input="n\n")

    assert result.exit_code == 0
    assert "Nothing changed" in result.stdout
    assert JobRepository(init_db(kravu_home / "kravu.db")).stats()["total"] == 1


def test_clean_removes_jobs_when_user_confirms(kravu_home: Path) -> None:
    from kravu.adapters.db import init_db
    from kravu.adapters.repository import JobRepository
    from kravu.domain.models import Job

    repo = JobRepository(init_db(kravu_home / "kravu.db"))
    repo.add_discovered(Job(url="https://a.test/1", title="Dev"))
    repo.add_discovered(Job(url="https://a.test/2", title="Dev"))

    result = CliRunner().invoke(cli.app, ["clean"], input="y\n")

    assert result.exit_code == 0
    assert JobRepository(init_db(kravu_home / "kravu.db")).stats()["total"] == 0


class _SpySource:
    """A DiscoverySource that records whether discovery was invoked."""

    name = "spy"

    def __init__(self) -> None:
        self.called = False
        self.notes: dict[tuple[str, str], str] = {}

    def discover(self, searches: dict[str, object], limit: int) -> list[object]:
        self.called = True
        return []


class _ScoringLLM:
    """A fake LLMClient that returns a passing score for the score step."""

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return '{"reasoning": "great fit", "matched_keywords": ["Python"], "score": 9}'


def test_resume_score_does_not_rerun_discovery(
    kravu_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`resume score` must score pending jobs without re-running explore.

    Regression: resume re-ran the whole pipeline from explore, pulling in new
    jobs the user never asked for. It must now start at the named step.
    """
    from kravu.adapters.db import init_db
    from kravu.adapters.repository import JobRepository
    from kravu.domain.models import Job, Profile, ResumeFacts

    monkeypatch.setenv("KRAVU_MIN_SCORE", "7")
    monkeypatch.setenv("KRAVU_MODEL", "gemini/x")
    monkeypatch.setenv("KRAVU_COVER_LETTER", "never")
    monkeypatch.setenv("GEMINI_API_KEY", "present")
    monkeypatch.setattr(config, "load_env", lambda: None)

    repo = JobRepository(init_db(kravu_home / "kravu.db"))
    repo.add_discovered(Job(url="https://a.test/1", title="Dev"))
    repo.set_enrichment("https://a.test/1", "Python role. Requirements: Python.", None)

    config.save_profile(
        Profile(resume_facts=ResumeFacts(raw_text="Jane", skills=["Python"]))
    )
    spy = _SpySource()
    monkeypatch.setattr(cli, "_sources", lambda: [spy])
    monkeypatch.setattr(cli, "LiteLLMClient", lambda *a, **k: _ScoringLLM())

    result = CliRunner().invoke(cli.app, ["resume", "score"])

    assert result.exit_code == 0, result.stdout
    assert spy.called is False  # discovery must NOT have run
    scored = JobRepository(init_db(kravu_home / "kravu.db")).get("https://a.test/1")
    assert scored is not None and scored.fit_score == 9


def test_resume_rejects_unknown_step(kravu_home: Path) -> None:
    result = CliRunner().invoke(cli.app, ["resume", "bogus"])
    assert result.exit_code != 0
    assert "Unknown step" in result.stdout
