"""JobSpySource: keyword-driven discovery via python-jobspy.

Runs each configured search across the enabled sites and returns ``Job`` rows
with the discovery fields populated. Each site is scraped in its own call so a
single blocked or erroring board (a 403/429, an empty page) never zeroes out the
others — one bad source records a note and is skipped, and the run continues
(spec §7a / principles: a failure is recorded, not fatal). ``jobspy`` is imported
lazily so importing this module has no heavy side effects.
"""

from __future__ import annotations

from typing import Any

from kravu.domain.models import Job

# Every board the stock ``python-jobspy`` can scrape and that works on the pinned
# version. ``bdjobs`` is intentionally excluded: python-jobspy 1.1.82 crashes its
# BDJobs scraper (``__init__() got an unexpected keyword argument 'user_agent'``),
# so it can never return results on this version. Source: JobSpy README
# (speedyapply/JobSpy). A site name outside this set is a config typo and is
# reported in ``notes`` rather than passed through to JobSpy.
SUPPORTED_SITES: frozenset[str] = frozenset(
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

# The boards enabled by default on a fresh setup. Kept lean to the two that are
# reliable from a single residential IP without proxies (Indeed has no rate
# limiting; LinkedIn works for modest volume). The rest of SUPPORTED_SITES stay
# valid to enable in searches.yaml, but they frequently 403/empty per-IP, so they
# are opt-in rather than default noise.
DEFAULT_SITES: tuple[str, ...] = ("indeed", "linkedin")

# Per-JobSpy-search fields passed straight through to scrape_jobs().
_PASSTHROUGH = (
    "search_term",
    "location",
    "hours_old",
    "job_type",
    "is_remote",
    "distance",
    "google_search_term",
    "description_format",
)


class JobSpySource:
    """DiscoverySource backed by python-jobspy, one call per site."""

    name = "jobspy"

    def __init__(self) -> None:
        """Initialize with an empty per-(search, site) notes map."""
        self.notes: dict[tuple[str, str], str] = {}

    def discover(self, searches: dict[str, Any], limit: int) -> list[Job]:
        """Run every configured search across every site and return jobs.

        Args:
            searches: The parsed ``searches.yaml`` dict.
            limit: Per-board fetch ceiling (results requested from each board).

        Returns:
            A flat list of ``Job`` rows (discovery fields only). Duplicates are
            NOT removed here — ExploreJobs dedupes by normalized URL. Per-(search,
            site) outcomes are recorded in ``self.notes``.
        """
        config = searches.get("sources", {}).get("jobspy", {})
        if not config.get("enabled", True):
            return []
        sites = config.get("sites", ["indeed"])
        defaults = searches.get("defaults", {})
        jobs: list[Job] = []
        for entry in searches.get("searches", []):
            for site in sites:
                jobs.extend(self._run_one_site(entry, site, defaults, limit))
        return jobs

    def _run_one_site(
        self,
        entry: dict[str, Any],
        site: str,
        defaults: dict[str, Any],
        limit: int,
    ) -> list[Job]:
        """Scrape a single site for one search; record the outcome, never raise."""
        name = str(entry.get("name", entry.get("search_term", "search")))
        key = (name, site)
        if site not in SUPPORTED_SITES:
            self.notes[key] = (
                f"unsupported site (choose from {', '.join(sorted(SUPPORTED_SITES))})"
            )
            return []

        import jobspy  # type: ignore[import-untyped]  # no stubs shipped

        kwargs: dict[str, Any] = {"site_name": [site], "results_wanted": limit}
        for source in (defaults, entry):
            for field in _PASSTHROUGH:
                if field in source:
                    kwargs[field] = source[field]
            if source.get("country") is not None:
                kwargs["country_indeed"] = source["country"]
        try:
            frame = jobspy.scrape_jobs(**kwargs)
        except Exception as exc:  # noqa: BLE001 - record and continue per spec
            self.notes[key] = f"failed: {exc}"
            return []
        records = frame.to_dict("records") if frame is not None else []
        jobs = [self._to_job(r) for r in records if r.get("job_url")]
        self.notes[key] = f"ok: {len(jobs)}" if jobs else "empty"
        return jobs

    @staticmethod
    def _to_job(record: dict[str, Any]) -> Job:
        is_remote = bool(record.get("is_remote"))
        apply_type = "easy-apply" if record.get("site") == "linkedin" else "external"
        return Job(
            url=str(record["job_url"]),
            title=str(record.get("title") or ""),
            company=str(record.get("company") or ""),
            location=str(record.get("location") or ("Remote" if is_remote else "")),
            salary=str(record.get("salary") or record.get("compensation") or ""),
            source=str(record.get("site") or "jobspy"),
            apply_type=apply_type,
            description=str(record.get("description") or ""),
        )
