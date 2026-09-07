"""Unit tests for the Playwright page renderer wrapper (browser injected)."""

from __future__ import annotations

from kravu.adapters.playwright_page import PlaywrightPageRenderer


def test_render_delegates_to_injected_fn() -> None:
    calls: list[str] = []

    def fake_render(url: str, timeout_ms: int) -> str:
        calls.append(url)
        return "<html><body>ok</body></html>"

    renderer = PlaywrightPageRenderer(render_fn=fake_render)
    html = renderer.render("https://x.test/1")

    assert html == "<html><body>ok</body></html>"
    assert calls == ["https://x.test/1"]
