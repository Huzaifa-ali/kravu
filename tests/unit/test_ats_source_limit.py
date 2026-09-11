"""AtsSource honors the run limit across its configured boards."""

from __future__ import annotations

from typing import Any

from kravu.adapters.ats_source import AtsSource


def _greenhouse_payload(n: int) -> dict[str, Any]:
    return {
        "jobs": [
            {
                "absolute_url": f"https://gh.test/{i}",
                "title": f"Role {i}",
                "location": {"name": "Remote"},
            }
            for i in range(n)
        ]
    }


def test_ats_returns_at_most_limit() -> None:
    def fetch(url: str, body: Any = None) -> Any:
        return _greenhouse_payload(10)

    searches = {
        "sources": {
            "ats": {
                "enabled": True,
                "companies": [{"ats": "greenhouse", "slug": "acme"}],
            }
        }
    }
    jobs = AtsSource(fetch=fetch).discover(searches, limit=4)
    assert len(jobs) == 4


def test_ats_disabled_returns_empty() -> None:
    jobs = AtsSource(fetch=lambda *a, **k: {}).discover(
        {"sources": {"ats": {"enabled": False}}}, limit=5
    )
    assert jobs == []
