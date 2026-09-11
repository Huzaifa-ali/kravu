"""ExpandJob: render each un-enriched job and extract its full description.

Cascade, cheapest first (spec §7a): (1) JSON-LD ``JobPosting`` parsed from
``<script type="application/ld+json">`` blocks with stdlib ``json``; (2) CSS
selectors over the rendered DOM via ``selectolax`` with ``trafilatura`` cleanup;
(3) an LLM call on the FLATTENED page text as a last resort (higher accuracy,
less hallucination than raw HTML — NEXT-EVAL). Up to 3 attempts per job, then the
job is marked pending (non-fatal) and keeps its preview description.
"""

from __future__ import annotations

import json
from typing import Protocol

from kravu.adapters import prompts
from kravu.domain.ports import NO_PROGRESS, JobStore, LLMClient, ProgressReporter

_MAX_ATTEMPTS = 3
_MIN_EXTRACT_LEN = 200


class PageRenderer(Protocol):
    """A page renderer (implemented by ``PlaywrightPageRenderer``)."""

    def render(self, url: str) -> str:
        """Return the fully-rendered HTML of ``url``."""
        ...


def extract_jsonld(html: str) -> str | None:
    """Return the description from a JobPosting JSON-LD block, or None.

    Parses each ``<script type="application/ld+json">`` block and returns the
    ``description`` of the first object whose ``@type`` is ``JobPosting``.
    """
    from selectolax.parser import HTMLParser

    tree = HTMLParser(html)
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for obj in data if isinstance(data, list) else [data]:
            if not isinstance(obj, dict):
                continue
            types = obj.get("@type")
            type_set = types if isinstance(types, list) else [types]
            if "JobPosting" in type_set and obj.get("description"):
                return str(obj["description"])
    return None


def extract_css(html: str) -> str | None:
    """Extract the main job-content text via CSS heuristics + trafilatura.

    Returns cleaned main content if it is long enough to look like a JD, else
    None so the caller falls through to the LLM tier.
    """
    import trafilatura

    extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
    if extracted and len(extracted) >= _MIN_EXTRACT_LEN:
        return str(extracted)
    return None


def flatten_html(html: str) -> str:
    """Return cleaned, flattened text of a page for the LLM extraction tier."""
    from selectolax.parser import HTMLParser

    tree = HTMLParser(html)
    body = tree.body
    return body.text(separator="\n", strip=True) if body else ""


class ExpandJob:
    """Enrich jobs with a full description via the extraction cascade."""

    def __init__(self, renderer: PageRenderer, llm: LLMClient) -> None:
        """Store the injected page renderer and model port."""
        self._renderer = renderer
        self._llm = llm

    def run(
        self,
        store: JobStore,
        limit: int | None = None,
        *,
        progress: ProgressReporter = NO_PROGRESS,
    ) -> None:
        """Enrich every pending job (up to ``limit``). Never raises per job."""
        jobs = store.pending_enrichment(limit)
        progress.start_step("expand", len(jobs))
        for job in jobs:
            self._expand_one(store, job.url)
            progress.advance("expand", job.company)
        progress.finish_step("expand")

    def _expand_one(self, store: JobStore, url: str) -> None:
        store.bump_enrich_attempts(url)
        try:
            html = self._renderer.render(url)
            description = self._extract(html)
        except Exception as exc:  # noqa: BLE001 - record on the row, continue
            store.set_enrichment_error(url, str(exc))
            return
        if description:
            store.set_enrichment(url, description, None)
        else:
            store.set_enrichment_error(url, "no description extracted")

    def _extract(self, html: str) -> str | None:
        return extract_jsonld(html) or extract_css(html) or self._extract_with_llm(html)

    def _extract_with_llm(self, html: str) -> str | None:
        flattened = flatten_html(html)
        if not flattened:
            return None
        reply = self._llm.complete(
            prompts.extract_description_prompt(flattened), temperature=0.0
        )
        cleaned = reply.strip()
        return cleaned or None
