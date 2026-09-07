"""Helpers to configure the shared @playwright/mcp browser-automation server.

All drivers point at the same Microsoft Playwright MCP server (run via ``npx``,
not a pip dependency — confirmed, spec §8). This module only *generates* the
launch command and a JSON ``mcpServers`` config file; spawning is the driver's
job. The JSON shape is what Claude Code / Cursor / Gemini consume; Codex reads
TOML and its driver translates (Task 20).
"""

from __future__ import annotations

import json
from pathlib import Path


def playwright_mcp_command() -> list[str]:
    """Return the command that launches the Playwright MCP server."""
    return ["npx", "@playwright/mcp@latest"]


def write_mcp_config(path: Path) -> str:
    """Write a JSON ``mcpServers`` config pointing at Playwright MCP.

    Args:
        path: Where to write the config file.

    Returns:
        The path written, as a string.
    """
    config = {
        "mcpServers": {
            "playwright": {
                "command": "npx",
                "args": ["@playwright/mcp@latest"],
            }
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return str(path)
