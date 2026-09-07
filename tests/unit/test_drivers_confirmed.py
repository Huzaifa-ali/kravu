"""Unit tests for the Claude Code and Codex drivers (confirmed flags)."""

from __future__ import annotations

from kravu.apply.drivers.base import BrowserAgentDriver
from kravu.apply.drivers.claude_code import ClaudeCodeDriver
from kravu.apply.drivers.codex import CodexDriver


def test_claude_code_command_shape() -> None:
    driver = ClaudeCodeDriver()
    cmd = driver.build_command("fill this form", "/tmp/mcp.json")
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "--mcp-config" in cmd
    assert "/tmp/mcp.json" in cmd
    assert "fill this form" in cmd
    assert isinstance(driver, BrowserAgentDriver)


def test_codex_command_shape_uses_exec() -> None:
    driver = CodexDriver()
    cmd = driver.build_command("fill this form", "/tmp/mcp.toml")
    assert cmd[0] == "codex"
    assert "exec" in cmd
    assert "fill this form" in cmd
    assert isinstance(driver, BrowserAgentDriver)
