"""AtsSource: company-driven discovery via public ATS JSON boards.

Supports Greenhouse, Lever, and Ashby — all serve open JSON with no key. A wrong
slug returns HTTP 200 with an empty list (not 404), so "empty" is a real,
reportable outcome recorded in ``notes``, never a crash. Lever's ``createdAt`` is
epoch-milliseconds while Greenhouse/Ashby use ISO-8601; only the URL/title/location
are mapped here, so timestamp shape does not break mapping (spec §7a).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kravu.domain.models import Job

Fetcher = Callable[[str], Any]


def _default_fetch(url: str) -> Any:
    import httpx

    response = httpx.get(url, timeout=20.0)
    response.raise_for_status()
    return response.json()


class AtsSource:
    """DiscoverySource backed by public ATS JSON boards."""

    name = "ats"

    def __init__(self, fetch: Fetcher | None = None) -> None:
        """Build the adapter.

        Args:
            fetch: Function mapping a URL to parsed JSON. Defaults to an httpx
                GET; tests inject a stub so the suite stays offline.
        """
        self._fetch = fetch or _default_fetch
        self.notes: dict[str, str] = {}

    def discover(self, searches: dict[str, Any]) -> list[Job]:
        """Pull each configured company board and return discovered jobs."""
        config = searches.get("sources", {}).get("ats", {})
        if not config.get("enabled", False):
            return []
        jobs: list[Job] = []
        for company in config.get("companies", []):
            jobs.extend(self._pull(company.get("ats", ""), company.get("slug", "")))
        return jobs

    def _pull(self, ats: str, slug: str) -> list[Job]:
        key = f"{ats}:{slug}"
        url = self._board_url(ats, slug)
        if url is None:
            self.notes[key] = f"unknown ats: {ats}"
            return []
        try:
            payload = self._fetch(url)
            jobs = self._map(ats, slug, payload)
        except Exception as exc:  # noqa: BLE001 - record and continue per spec
            self.notes[key] = f"failed: {exc}"
            return []
        if not jobs:
            self.notes[key] = "empty"
        return jobs

    @staticmethod
    def _board_url(ats: str, slug: str) -> str | None:
        if ats == "greenhouse":
            return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        if ats == "lever":
            return f"https://api.lever.co/v0/postings/{slug}?mode=json"
        if ats == "ashby":
            return f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        return None

    def _map(self, ats: str, slug: str, payload: Any) -> list[Job]:
        source = f"{ats}:{slug}"
        if ats == "greenhouse":
            return [
                Job(
                    url=str(j["absolute_url"]),
                    title=str(j.get("title") or ""),
                    company=slug,
                    location=str((j.get("location") or {}).get("name") or ""),
                    source=source,
                    apply_type="ats",
                )
                for j in payload.get("jobs", [])
                if j.get("absolute_url")
            ]
        if ats == "lever":
            return [
                Job(
                    url=str(j["hostedUrl"]),
                    title=str(j.get("text") or ""),
                    company=slug,
                    location=str((j.get("categories") or {}).get("location") or ""),
                    source=source,
                    apply_type="ats",
                )
                for j in payload
                if j.get("hostedUrl")
            ]
        if ats == "ashby":
            return [
                Job(
                    url=str(j["jobUrl"]),
                    title=str(j.get("title") or ""),
                    company=slug,
                    location=str(j.get("location") or ""),
                    source=source,
                    apply_type="ats",
                )
                for j in payload.get("jobs", [])
                if j.get("jobUrl")
            ]
        return []
