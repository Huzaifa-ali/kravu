"""Unit tests for the ATS discovery adapter (JSON fetch stubbed)."""

from __future__ import annotations

from typing import Any

from kravu.adapters.ats_source import AtsSource


def _fake_fetch(responses: dict[str, Any]):
    def fetch(url: str) -> Any:
        return responses.get(url, {})

    return fetch


def test_greenhouse_maps_jobs() -> None:
    url = "https://boards-api.greenhouse.io/v1/boards/stripe/jobs"
    fetch = _fake_fetch(
        {
            url: {
                "jobs": [
                    {
                        "absolute_url": "https://gh.test/1",
                        "title": "SRE",
                        "location": {"name": "Remote"},
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
                "companies": [{"ats": "greenhouse", "slug": "stripe"}],
            }
        }
    }
    jobs = source.discover(searches)
    assert [j.url for j in jobs] == ["https://gh.test/1"]
    assert jobs[0].source == "greenhouse:stripe"


def test_lever_epoch_ms_does_not_crash() -> None:
    url = "https://api.lever.co/v0/postings/netflix?mode=json"
    fetch = _fake_fetch(
        {
            url: [
                {
                    "hostedUrl": "https://lever.test/1",
                    "text": "Backend",
                    "createdAt": 1735689600000,
                    "categories": {"location": "NYC"},
                }
            ]
        }
    )
    source = AtsSource(fetch=fetch)
    searches = {
        "sources": {
            "ats": {"enabled": True, "companies": [{"ats": "lever", "slug": "netflix"}]}
        }
    }
    jobs = source.discover(searches)
    assert jobs[0].url == "https://lever.test/1"


def test_empty_board_is_recorded_not_crashed() -> None:
    url = "https://boards-api.greenhouse.io/v1/boards/typo/jobs"
    source = AtsSource(fetch=_fake_fetch({url: {"jobs": []}}))
    searches = {
        "sources": {
            "ats": {
                "enabled": True,
                "companies": [{"ats": "greenhouse", "slug": "typo"}],
            }
        }
    }
    jobs = source.discover(searches)
    assert jobs == []
    assert "greenhouse:typo" in source.notes


def test_disabled_ats_returns_empty() -> None:
    source = AtsSource(fetch=_fake_fetch({}))
    assert source.discover({"sources": {"ats": {"enabled": False}}}) == []
