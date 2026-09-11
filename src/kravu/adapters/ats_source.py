"""AtsSource: company-driven discovery via public ATS JSON boards.

Supports Greenhouse, Lever, Ashby, Workable, and Workday — all expose open JSON
with no API key. Greenhouse/Lever/Ashby/Workable are simple GETs; Workday uses a
per-tenant CXS endpoint reached with a POST body. A wrong slug/URL returns an
empty list (or a recorded failure), never a crash: each company's outcome is
noted and the run continues (spec §7a).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from kravu.domain.models import Job

# A fetcher maps a URL (and optional JSON body, for POST endpoints like Workday)
# to parsed JSON. Tests inject a stub so the suite stays offline.
Fetcher = Callable[..., Any]


def _default_fetch(url: str, body: Any = None) -> Any:
    """GET the URL, or POST ``body`` as JSON when a body is supplied."""
    import httpx

    if body is None:
        response = httpx.get(url, timeout=20.0)
    else:
        response = httpx.post(url, json=body, timeout=20.0)
    response.raise_for_status()
    return response.json()


class AtsSource:
    """DiscoverySource backed by public ATS JSON boards."""

    name = "ats"

    def __init__(self, fetch: Fetcher | None = None) -> None:
        """Build the adapter.

        Args:
            fetch: Function mapping ``(url, body=None)`` to parsed JSON. Defaults
                to an httpx GET/POST; tests inject a stub so the suite stays
                offline.
        """
        self._fetch = fetch or _default_fetch
        self.notes: dict[str, str] = {}

    def discover(self, searches: dict[str, Any], limit: int) -> list[Job]:
        """Pull each configured company board and return at most ``limit`` jobs."""
        config = searches.get("sources", {}).get("ats", {})
        if not config.get("enabled", False):
            return []
        jobs: list[Job] = []
        for company in config.get("companies", []):
            jobs.extend(self._pull(company))
            if len(jobs) >= limit:
                return jobs[:limit]
        return jobs[:limit]

    def _pull(self, company: dict[str, Any]) -> list[Job]:
        """Fetch one company's board, mapping by ATS type; never raises."""
        ats = str(company.get("ats", ""))
        if ats == "workday":
            return self._pull_workday(company)
        return self._pull_simple(ats, str(company.get("slug", "")))

    def _pull_simple(self, ats: str, slug: str) -> list[Job]:
        """GET-based ATS boards keyed by a company slug."""
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
        self.notes[key] = f"ok: {len(jobs)}" if jobs else "empty"
        return jobs

    def _pull_workday(self, company: dict[str, Any]) -> list[Job]:
        """POST to a Workday tenant's CXS endpoint and map the postings.

        The company config gives a careers-site ``url`` such as
        ``https://{tenant}.{dc}.myworkdayjobs.com/{lang}/{site}``; tenant, data
        center and site are parsed from it to build the CXS jobs endpoint.
        """
        careers_url = str(company.get("url", ""))
        parsed = _parse_workday_url(careers_url)
        if parsed is None:
            self.notes[f"workday:{careers_url or '?'}"] = (
                "invalid workday url (expected "
                "https://<tenant>.<dc>.myworkdayjobs.com/<lang>/<site>)"
            )
            return []
        tenant, host, site = parsed
        key = f"workday:{tenant}/{site}"
        cxs = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
        body = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": ""}
        try:
            payload = self._fetch(cxs, body)
            jobs = self._map_workday(careers_url, key, payload)
        except Exception as exc:  # noqa: BLE001 - record and continue per spec
            self.notes[key] = f"failed: {exc}"
            return []
        self.notes[key] = f"ok: {len(jobs)}" if jobs else "empty"
        return jobs

    @staticmethod
    def _board_url(ats: str, slug: str) -> str | None:
        if ats == "greenhouse":
            return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        if ats == "lever":
            return f"https://api.lever.co/v0/postings/{slug}?mode=json"
        if ats == "ashby":
            return f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        if ats == "workable":
            return f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
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
        if ats == "workable":
            return [
                Job(
                    url=str(j["url"]),
                    title=str(j.get("title") or ""),
                    company=slug,
                    location=_workable_location(j),
                    source=source,
                    apply_type="ats",
                )
                for j in payload.get("jobs", [])
                if j.get("url")
            ]
        return []

    def _map_workday(self, careers_url: str, source: str, payload: Any) -> list[Job]:
        base = careers_url.rstrip("/")
        jobs: list[Job] = []
        for posting in payload.get("jobPostings", []):
            external_path = posting.get("externalPath")
            if not external_path:
                continue
            jobs.append(
                Job(
                    url=f"{base}{external_path}",
                    title=str(posting.get("title") or ""),
                    company=source.split(":", 1)[-1].split("/", 1)[0],
                    location=str(posting.get("locationsText") or ""),
                    source=source,
                    apply_type="ats",
                )
            )
        return jobs


def _workable_location(job: dict[str, Any]) -> str:
    """Join a Workable posting's city/state/country into one label."""
    parts = [str(job.get(k) or "") for k in ("city", "state", "country")]
    return ", ".join(p for p in parts if p)


def _parse_workday_url(careers_url: str) -> tuple[str, str, str] | None:
    """Parse a Workday careers URL into ``(tenant, host, site)``.

    Expects ``https://<tenant>.<dc>.myworkdayjobs.com/<lang>/<site>``. The site is
    the final non-empty path segment; the tenant is the first host label. Returns
    ``None`` when the URL is not a recognizable Workday careers URL.
    """
    parsed = urlparse(careers_url)
    host = parsed.netloc.lower()
    if "myworkdayjobs.com" not in host:
        return None
    tenant = host.split(".", 1)[0]
    segments = [seg for seg in parsed.path.split("/") if seg]
    if not tenant or not segments:
        return None
    site = segments[-1]
    return tenant, host, site
