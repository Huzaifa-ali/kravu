"""Unit tests for the JobSpy discovery adapter (jobspy stubbed)."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from kravu.adapters.jobspy_source import JobSpySource


class _FakeFrame:
    """Minimal stand-in for the pandas DataFrame JobSpy returns."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def to_dict(self, orient: str) -> list[dict[str, Any]]:
        assert orient == "records"
        return self._rows


def _install_fake_jobspy(
    monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]
) -> None:
    module = types.ModuleType("jobspy")

    def scrape_jobs(**_kwargs: Any) -> _FakeFrame:
        return _FakeFrame(rows)

    module.scrape_jobs = scrape_jobs  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "jobspy", module)


def _capture_jobspy(
    monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Install a fake jobspy that records the kwargs of the last scrape call."""
    module = types.ModuleType("jobspy")
    captured: dict[str, Any] = {}

    def scrape_jobs(**kwargs: Any) -> _FakeFrame:
        captured.update(kwargs)
        return _FakeFrame(rows)

    module.scrape_jobs = scrape_jobs  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "jobspy", module)
    return captured


def _searches() -> dict[str, Any]:
    return {
        "sources": {"jobspy": {"enabled": True, "sites": ["indeed"]}},
        "searches": [
            {"name": "d", "search_term": "DevOps", "location": "US", "country": "USA"}
        ],
    }


def test_discover_maps_rows_to_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_jobspy(
        monkeypatch,
        [
            {
                "job_url": "https://x.test/1",
                "title": "DevOps Engineer",
                "company": "Acme",
                "location": "Remote, US",
                "is_remote": True,
                "site": "indeed",
                "description": "Do devops.",
            }
        ],
    )
    jobs = JobSpySource().discover(_searches(), limit=5)
    assert len(jobs) == 1
    assert jobs[0].url == "https://x.test/1"
    assert jobs[0].title == "DevOps Engineer"
    assert jobs[0].source == "indeed"


def test_discover_uses_limit_as_fetch_count(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_jobspy(monkeypatch, [])
    JobSpySource().discover(_searches(), limit=37)
    assert captured["results_wanted"] == 37


def test_discover_forwards_country(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_jobspy(monkeypatch, [])
    JobSpySource().discover(_searches(), limit=5)
    assert captured["country_indeed"] == "USA"


def test_discover_skips_failing_site_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = types.ModuleType("jobspy")

    def scrape_jobs(**_kwargs: Any) -> None:
        raise RuntimeError("429 blocked")

    module.scrape_jobs = scrape_jobs  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "jobspy", module)

    source = JobSpySource()
    jobs = source.discover(_searches(), limit=5)
    assert jobs == []
    assert ("d", "indeed") in source.notes


def test_name_attribute() -> None:
    assert JobSpySource().name == "jobspy"
