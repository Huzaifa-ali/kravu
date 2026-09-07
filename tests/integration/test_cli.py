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
