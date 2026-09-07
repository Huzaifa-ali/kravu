"""Unit tests for the @playwright/mcp config helper."""

from __future__ import annotations

import json
from pathlib import Path

from kravu.apply.mcp_server import playwright_mcp_command, write_mcp_config


def test_command_uses_npx_playwright_mcp() -> None:
    cmd = playwright_mcp_command()
    assert cmd[0] == "npx"
    assert "@playwright/mcp@latest" in cmd


def test_write_mcp_config_emits_json_server_block(tmp_path: Path) -> None:
    path = write_mcp_config(tmp_path / "mcp.json")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert "playwright" in data["mcpServers"]
    assert data["mcpServers"]["playwright"]["command"] == "npx"
