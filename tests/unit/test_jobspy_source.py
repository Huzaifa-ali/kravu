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
    source = JobSpySource()
    searches = {
        "sources": {"jobspy": {"enabled": True, "sites": ["indeed"]}},
        "defaults": {"results_wanted": 5},
        "searches": [
            {
                "name": "d",
                "search_term": "DevOps",
                "location": "US",
                "country_indeed": "USA",
            }
        ],
    }
    jobs = source.discover(searches)
    assert len(jobs) == 1
    assert jobs[0].url == "https://x.test/1"
    assert jobs[0].title == "DevOps Engineer"
    assert jobs[0].source == "indeed"


def test_discover_skips_failing_site_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = types.ModuleType("jobspy")

    def scrape_jobs(**_kwargs: Any) -> None:
        raise RuntimeError("429 blocked")

    module.scrape_jobs = scrape_jobs  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "jobspy", module)

    source = JobSpySource()
    searches = {
        "sources": {"jobspy": {"enabled": True, "sites": ["indeed"]}},
        "searches": [
            {
                "name": "d",
                "search_term": "DevOps",
                "location": "US",
                "country_indeed": "USA",
            }
        ],
    }
    jobs = source.discover(searches)
    assert jobs == []
    assert ("d", "indeed") in source.notes


def test_name_attribute() -> None:
    assert JobSpySource().name == "jobspy"
