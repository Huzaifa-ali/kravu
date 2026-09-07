"""Unit tests for the Kiro/Cursor/Gemini drivers (flags confirmed at build)."""

from __future__ import annotations

from kravu.apply.drivers.base import BrowserAgentDriver
from kravu.apply.drivers.cursor import CursorDriver
from kravu.apply.drivers.gemini import GeminiDriver
from kravu.apply.drivers.kiro import KiroDriver


def test_kiro_driver_builds_command_including_prompt() -> None:
    driver = KiroDriver()
    cmd = driver.build_command("apply here", "/tmp/mcp.json")
    assert cmd[0] == "kiro"
    assert "apply here" in cmd
    assert isinstance(driver, BrowserAgentDriver)


def test_cursor_driver_builds_command_including_prompt() -> None:
    cmd = CursorDriver().build_command("apply here", "/tmp/mcp.json")
    assert cmd[0] == "cursor-agent"
    assert "apply here" in cmd


def test_gemini_driver_builds_command_including_prompt() -> None:
    cmd = GeminiDriver().build_command("apply here", "/tmp/mcp.json")
    assert cmd[0] == "gemini"
    assert "apply here" in cmd
