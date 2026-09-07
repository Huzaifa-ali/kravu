"""JobSpySource: keyword-driven discovery via python-jobspy.

Runs each configured search across the enabled sites and returns ``Job`` rows
with the discovery fields populated. A failing site is recorded in ``notes`` and
skipped — a bad source never aborts the run (spec §7a). ``jobspy`` is imported
lazily so importing this module has no heavy side effects.
"""

from __future__ import annotations

from typing import Any

from kravu.domain.models import Job

# Per-JobSpy-search fields passed straight through to scrape_jobs().
_PASSTHROUGH = (
    "search_term",
    "location",
    "results_wanted",
    "hours_old",
    "job_type",
    "is_remote",
    "distance",
    "google_search_term",
    "country_indeed",
    "description_format",
)


class JobSpySource:
    """DiscoverySource backed by python-jobspy."""

    name = "jobspy"

    def __init__(self) -> None:
        """Initialize with an empty per-search notes map."""
        self.notes: dict[str, str] = {}

    def discover(self, searches: dict[str, Any]) -> list[Job]:
        """Run every configured search and return discovered jobs.

        Args:
            searches: The parsed ``searches.yaml`` dict.

        Returns:
            A flat list of ``Job`` rows (discovery fields only). Duplicates are
            NOT removed here — ExploreJobs dedupes by normalized URL.
        """
        config = searches.get("sources", {}).get("jobspy", {})
        if not config.get("enabled", True):
            return []
        sites = config.get("sites", ["indeed"])
        defaults = searches.get("defaults", {})
        jobs: list[Job] = []
        for entry in searches.get("searches", []):
            jobs.extend(self._run_one(entry, sites, defaults))
        return jobs

    def _run_one(
        self, entry: dict[str, Any], sites: list[str], defaults: dict[str, Any]
    ) -> list[Job]:
        import jobspy  # type: ignore[import-untyped]  # no stubs shipped

        name = str(entry.get("name", entry.get("search_term", "search")))
        kwargs: dict[str, Any] = {"site_name": sites}
        for key in _PASSTHROUGH:
            if key in defaults:
                kwargs[key] = defaults[key]
        for key in _PASSTHROUGH:
            if key in entry:
                kwargs[key] = entry[key]
        try:
            frame = jobspy.scrape_jobs(**kwargs)
        except Exception as exc:  # noqa: BLE001 - record and continue per spec
            self.notes[name] = f"failed: {exc}"
            return []
        records = frame.to_dict("records") if frame is not None else []
        if not records:
            self.notes[name] = "empty"
        return [self._to_job(r) for r in records if r.get("job_url")]

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
