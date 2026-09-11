"""Unit tests for the Workable and Workday ATS adapters (fetch stubbed).

Workable exposes a public widget JSON endpoint reached with a plain GET; Workday
exposes a per-tenant CXS endpoint reached with a POST body. Both are mapped into
``Job`` rows by ``AtsSource`` with per-company notes, and neither crashes the run
on a bad slug/URL — matching the existing Greenhouse/Lever/Ashby behavior.
"""

from __future__ import annotations

from typing import Any

from kravu.adapters.ats_source import AtsSource


def _recording_fetch(responses: dict[str, Any]) -> Any:
    """Fetch stub that records (url, body) calls and returns canned JSON.

    Supports the extended signature ``fetch(url, body=None)`` — a POST when a body
    is supplied (Workday), a GET otherwise (everything else).
    """
    calls: list[tuple[str, Any]] = []

    def fetch(url: str, body: Any = None) -> Any:
        calls.append((url, body))
        return responses.get(url, {})

    fetch.calls = calls  # type: ignore[attr-defined]
    return fetch


# --- Workable --------------------------------------------------------------


def test_workable_maps_jobs() -> None:
    url = "https://apply.workable.com/api/v1/widget/accounts/acme"
    fetch = _recording_fetch(
        {
            url: {
                "jobs": [
                    {
                        "title": "ML Engineer",
                        "shortcode": "ABC123",
                        "url": "https://apply.workable.com/acme/j/ABC123/",
                        "city": "Remote",
                        "state": "",
                        "country": "US",
                    }
                ]
            }
        }
    )
    source = AtsSource(fetch=fetch)
    searches = {
        "sources": {
            "ats": {
                "enabled": True,
                "companies": [{"ats": "workable", "slug": "acme"}],
            }
        }
    }
    jobs = source.discover(searches, limit=50)
    assert [j.url for j in jobs] == ["https://apply.workable.com/acme/j/ABC123/"]
    assert jobs[0].title == "ML Engineer"
    assert jobs[0].source == "workable:acme"


def test_workable_empty_board_recorded() -> None:
    url = "https://apply.workable.com/api/v1/widget/accounts/typo"
    source = AtsSource(fetch=_recording_fetch({url: {"jobs": []}}))
    searches = {
        "sources": {
            "ats": {
                "enabled": True,
                "companies": [{"ats": "workable", "slug": "typo"}],
            }
        }
    }
    assert source.discover(searches, limit=50) == []
    assert source.notes["workable:typo"] == "empty"


# --- Workday ---------------------------------------------------------------


def test_workday_posts_to_cxs_and_maps_jobs() -> None:
    # tenant=nvidia, site=NVIDIAExternalCareerSite, dc=wd5
    cxs = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"
    fetch = _recording_fetch(
        {
            cxs: {
                "total": 1,
                "jobPostings": [
                    {
                        "title": "AI Engineer",
                        "externalPath": "/job/Remote/AI-Engineer_JR123",
                        "locationsText": "Remote, US",
                    }
                ],
            }
        }
    )
    source = AtsSource(fetch=fetch)
    searches = {
        "sources": {
            "ats": {
                "enabled": True,
                "companies": [
                    {
                        "ats": "workday",
                        "url": (
                            "https://nvidia.wd5.myworkdayjobs.com/en-US/"
                            "NVIDIAExternalCareerSite"
                        ),
                    }
                ],
            }
        }
    }
    jobs = source.discover(searches, limit=50)

    # A POST body was sent (not a bare GET).
    assert fetch.calls[0][1] is not None  # type: ignore[attr-defined]
    assert len(jobs) == 1
    assert jobs[0].title == "AI Engineer"
    # externalPath is resolved to an absolute apply URL on the tenant host.
    assert jobs[0].url == (
        "https://nvidia.wd5.myworkdayjobs.com/en-US/"
        "NVIDIAExternalCareerSite/job/Remote/AI-Engineer_JR123"
    )
    assert jobs[0].source.startswith("workday:")


def test_workday_bad_url_recorded_not_raised() -> None:
    source = AtsSource(fetch=_recording_fetch({}))
    searches = {
        "sources": {
            "ats": {
                "enabled": True,
                "companies": [{"ats": "workday", "url": "https://not-a-workday-url"}],
            }
        }
    }
    jobs = source.discover(searches, limit=50)  # must not raise
    assert jobs == []
    assert any("workday" in key for key in source.notes)
