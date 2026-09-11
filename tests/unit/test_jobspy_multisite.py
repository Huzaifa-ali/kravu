"""Unit tests for per-site resilience in the JobSpy discovery adapter.

These pin the broadened behavior: each configured site is scraped in its own
call so one blocked/erroring board never zeroes out the others, a per-(search,
site) note records the outcome, and unknown site names are reported rather than
silently passed to JobSpy. ``jobspy`` is stubbed — offline and deterministic.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from kravu.adapters.jobspy_source import SUPPORTED_SITES, JobSpySource


class _FakeFrame:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def to_dict(self, orient: str) -> list[dict[str, Any]]:
        assert orient == "records"
        return self._rows


def _install_per_site_jobspy(
    monkeypatch: pytest.MonkeyPatch,
    behavior: dict[str, Any],
) -> None:
    """Install a fake jobspy whose scrape_jobs reacts to the single site given.

    ``behavior`` maps a site name to either a list of row-dicts (returned) or an
    Exception instance (raised). The adapter is expected to call scrape_jobs once
    per site with a single-element ``site_name`` list.
    """
    module = types.ModuleType("jobspy")

    def scrape_jobs(**kwargs: Any) -> _FakeFrame:
        site_name = kwargs["site_name"]
        site = site_name[0] if isinstance(site_name, list) else site_name
        outcome = behavior.get(site, [])
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeFrame(outcome)

    module.scrape_jobs = scrape_jobs  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "jobspy", module)


def _searches(sites: list[str]) -> dict[str, Any]:
    return {
        "sources": {"jobspy": {"enabled": True, "sites": sites}},
        "defaults": {"results_wanted": 5},
        "searches": [
            {
                "name": "primary",
                "search_term": "AI Engineer",
                "location": "Remote",
                "country_indeed": "USA",
            }
        ],
    }


def _row(url: str, site: str) -> dict[str, Any]:
    return {"job_url": url, "title": "AI Engineer", "company": "Acme", "site": site}


def test_supported_sites_covers_working_boards() -> None:
    assert SUPPORTED_SITES == frozenset(
        {
            "linkedin",
            "indeed",
            "glassdoor",
            "google",
            "zip_recruiter",
            "bayt",
            "naukri",
        }
    )
    # bdjobs is excluded: it crashes on the pinned python-jobspy version.
    assert "bdjobs" not in SUPPORTED_SITES


def test_one_failing_site_does_not_lose_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_per_site_jobspy(
        monkeypatch,
        {
            "indeed": [_row("https://i.test/1", "indeed")],
            "zip_recruiter": RuntimeError("403 forbidden"),
            "glassdoor": [_row("https://g.test/1", "glassdoor")],
        },
    )
    source = JobSpySource()
    jobs = source.discover(_searches(["indeed", "zip_recruiter", "glassdoor"]))

    urls = {j.url for j in jobs}
    assert urls == {"https://i.test/1", "https://g.test/1"}


def test_per_site_notes_record_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_per_site_jobspy(
        monkeypatch,
        {
            "indeed": [_row("https://i.test/1", "indeed")],
            "zip_recruiter": RuntimeError("403 forbidden"),
            "glassdoor": [],
        },
    )
    source = JobSpySource()
    source.discover(_searches(["indeed", "zip_recruiter", "glassdoor"]))

    assert source.notes[("primary", "indeed")] == "ok: 1"
    assert "403" in source.notes[("primary", "zip_recruiter")]
    assert source.notes[("primary", "glassdoor")] == "empty"


def test_unknown_site_is_noted_and_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_per_site_jobspy(
        monkeypatch, {"indeed": [_row("https://i.test/1", "indeed")]}
    )
    source = JobSpySource()
    jobs = source.discover(_searches(["indeed", "ziprecruiter"]))  # typo, not valid

    assert len(jobs) == 1
    assert "unsupported" in source.notes[("primary", "ziprecruiter")]


def test_disabled_jobspy_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_per_site_jobspy(monkeypatch, {"indeed": [_row("https://i.test/1", "x")]})
    source = JobSpySource()
    searches = _searches(["indeed"])
    searches["sources"]["jobspy"]["enabled"] = False
    assert source.discover(searches) == []
