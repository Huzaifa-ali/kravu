"""Integration tests for the CLI commands (LLM/discovery patched)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

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
