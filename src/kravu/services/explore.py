"""ExploreJobs: discover, dedupe by normalized URL, gate quality, persist.

Merges results from every configured ``DiscoverySource``, deduplicates by a
normalized URL (tracking query/fragment stripped, host lowercased) — catching
duplicates a raw-URL key misses — and promotes a description to
``full_description`` only if it looks like a real JD (length + section signals),
else keeps it as the preview ``description`` (spec §7a). Persists only new jobs.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from kravu.domain.ports import (
    NO_PROGRESS,
    DiscoverySource,
    JobStore,
    ProgressReporter,
)

# Query parameters that carry no posting identity — analytics, campaign, and
# referral tags a board appends to the same job for different visitors. These are
# dropped during normalization; every OTHER query parameter is kept, because on
# many boards the posting id lives there (Indeed ``jk``, LinkedIn ``currentJobId``,
# Greenhouse ``gh_jid``). Stripping the whole query string would collapse every
# posting on such a board to one URL and admit only a single job per run.
_TRACKING_PARAMS: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_id",
        "gclid",
        "fbclid",
        "msclkid",
        "ref",
        "referer",
        "referrer",
        "source",
        "src",
        "from",
        "trk",
        "trackingid",
        "trk_trk",
        "sc_src",
    }
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

    Lowercases the host, drops the fragment, strips a trailing slash from the
    path, and removes only known tracking parameters (``utm_*``, ``gclid``,
    ``ref``, ...) from the query — keeping identifying parameters like Indeed's
    ``jk`` or LinkedIn's ``currentJobId`` so distinct postings stay distinct.
    Remaining query parameters are sorted so ordering never affects the key.
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    kept = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(sorted(kept))
    return urlunparse((parsed.scheme.lower(), host, path, "", query, ""))


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
