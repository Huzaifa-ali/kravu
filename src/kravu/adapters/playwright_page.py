"""PlaywrightPageRenderer: render a URL to HTML with headless Chromium.

A thin I/O wrapper — it renders, nothing more. Extraction (JSON-LD / CSS / LLM)
lives in ``services.expand``. Playwright is imported lazily inside the default
render function so importing this module is cheap and the test suite stays
offline by injecting ``render_fn``.
"""

from __future__ import annotations

from collections.abc import Callable

RenderFn = Callable[[str, int], str]


def _default_render(url: str, timeout_ms: int) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            return page.content()
        finally:
            browser.close()


class PlaywrightPageRenderer:
    """Render web pages to HTML using headless Chromium."""

    def __init__(
        self, render_fn: RenderFn | None = None, timeout_ms: int = 30_000
    ) -> None:
        """Build the renderer.

        Args:
            render_fn: Injectable ``(url, timeout_ms) -> html``. Defaults to a
                Playwright Chromium render; tests inject a stub.
            timeout_ms: Navigation timeout in milliseconds.
        """
        self._render_fn = render_fn or _default_render
        self._timeout_ms = timeout_ms

    def render(self, url: str) -> str:
        """Return the fully-rendered HTML of ``url``."""
        return self._render_fn(url, self._timeout_ms)
