"""Opt-in real-Chromium check for parallel enrichment (spec §4.7, §9).

The offline unit test (tests/unit/test_expand_parallel.py) uses a stateless fake
renderer, so it proves the renderer-per-worker *wiring* but NOT that Playwright's
sync API survives being driven across a thread pool. This test closes that gap
with real headless Chromium, mirroring ExpandJob at workers>1: run_parallel over a
bounded thread pool, each worker building its own PlaywrightPageRenderer via the
factory. It uses ``data:`` URLs, so it needs Chromium but no network.

Marked ``playwright`` and excluded from the default suite (see pyproject
``addopts = -m 'not playwright'``). Run it explicitly with::

    uv run pytest -m playwright

It is skipped automatically if the Chromium browser binary is not installed.
"""

from __future__ import annotations

import threading

import pytest

from kravu.adapters.playwright_page import PlaywrightPageRenderer
from kravu.services.parallel import run_parallel

pytestmark = pytest.mark.playwright

_HTML = (
    "data:text/html,<html><body><script type='application/ld+json'>"
    '{"@type":"JobPosting","description":"real chromium desc"}'
    "</script></body></html>"
)


def _chromium_available() -> bool:
    """True if a headless Chromium can actually launch in this environment."""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:  # noqa: BLE001 - any launch failure means skip
        return False


@pytest.mark.skipif(
    not _chromium_available(), reason="headless Chromium not installed/available"
)
def test_parallel_render_across_threads_with_real_chromium() -> None:
    """Real Chromium renders concurrently across a thread pool without error.

    Each worker constructs its own renderer (the factory contract) and calls
    ``render`` on its own thread; because ``PlaywrightPageRenderer`` opens a fresh
    ``sync_playwright()`` context per call, no Playwright object is shared across
    threads. Asserts every render succeeded and that more than one thread ran.
    """
    results: dict[int, str] = {}
    threads_seen: set[int] = set()
    lock = threading.Lock()

    def work(index: int) -> None:
        renderer = PlaywrightPageRenderer()  # per-worker, like ExpandJob._renderer_for
        html = renderer.render(_HTML)
        with lock:
            results[index] = html
            threads_seen.add(threading.get_ident())

    items = list(range(8))
    run_parallel(items, work, workers=4)

    assert len(results) == len(items)
    assert all("real chromium desc" in results[i] for i in items)
    assert len(threads_seen) > 1  # genuinely concurrent, not serialized
