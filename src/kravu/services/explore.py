"""ExploreJobs: discover, dedupe by normalized URL, gate quality, persist.

Merges results from every configured ``DiscoverySource``, deduplicates by a
normalized URL (tracking query/fragment stripped, host lowercased) — catching
duplicates a raw-URL key misses — and promotes a description to
``full_description`` only if it looks like a real JD (length + section signals),
else keeps it as the preview ``description`` (spec §7a). Persists only new jobs.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

from kravu.domain.ports import (
    NO_PROGRESS,
    DiscoverySource,
    JobStore,
    ProgressReporter,
)

_SECTION_SIGNALS = (
    "responsibilit",
    "requirement",
    "qualification",
    "what you",
    "you will",
    "about the role",
)
_MIN_REAL_DESCRIPTION = 400


def normalize_url(url: str) -> str:
    """Return a canonical form of ``url`` for deduplication.

    Lowercases the host, drops the query string and fragment, and strips a
    trailing slash from the path.
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), host, path, "", "", ""))


def _is_real_description(text: str) -> bool:
    if len(text) < _MIN_REAL_DESCRIPTION:
        return False
    lowered = text.lower()
    return any(signal in lowered for signal in _SECTION_SIGNALS)


class ExploreJobs:
    """Discover and persist new jobs from the configured sources."""

    def __init__(self, sources: list[DiscoverySource]) -> None:
        """Store the injected discovery sources."""
        self._sources = sources

    def run(
        self,
        store: JobStore,
        searches: dict[str, Any],
        limit: int,
        *,
        progress: ProgressReporter = NO_PROGRESS,
    ) -> int:
        """Discover jobs from all sources, dedupe, and persist up to ``limit`` new.

        Args:
            store: The persistence port.
            searches: The parsed ``searches.yaml`` dict.
            limit: The overall run cap — at most this many new jobs are admitted,
                regardless of how many sources or sites are configured.
            progress: Optional progress sink; total is ``limit``, advanced once
                per newly persisted job.

        Returns:
            The number of newly persisted (previously unseen) jobs (<= limit).
        """
        seen: set[str] = set()
        added = 0
        progress.start_step("explore", limit)
        for source in self._sources:
            if added >= limit:
                break
            for job in source.discover(searches, limit):
                if added >= limit:
                    break
                canonical = normalize_url(job.url)
                if canonical in seen:
                    continue
                seen.add(canonical)
                job.url = canonical
                if store.add_discovered(job):
                    added += 1
                    progress.advance("explore", job.title)
                    if _is_real_description(job.description):
                        store.set_enrichment(canonical, job.description, None)
        progress.finish_step("explore", f"{added} new jobs")
        return added
