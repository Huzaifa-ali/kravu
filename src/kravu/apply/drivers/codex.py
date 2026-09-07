"""CodexDriver: drive the browser agent via the Codex CLI (TOML config).

Confirmed (spec §8): Codex uses ``codex exec --json`` and reads TOML config, not
the JSON the other agents use — so its MCP config path points at a TOML file the
agent composer writes. Builds the command only.
"""

from __future__ import annotations


class CodexDriver:
    """BrowserAgentDriver for the Codex CLI."""

    name = "codex"

    def build_command(self, prompt: str, mcp_config_path: str) -> list[str]:
        """Return the argv to run Codex headless. ``mcp_config_path`` is TOML."""
        return [
            "codex",
            "exec",
            "--json",
            "--config",
            mcp_config_path,
            prompt,
        ]
