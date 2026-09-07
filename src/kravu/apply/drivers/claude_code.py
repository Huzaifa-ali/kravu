"""ClaudeCodeDriver: drive the browser agent via the Claude Code headless CLI.

Flags confirmed against docs.claude.com (spec §8): ``claude -p`` with
``--output-format json`` and ``--mcp-config <json>``. Builds the command only;
process control lives in ``apply.agent``.
"""

from __future__ import annotations


class ClaudeCodeDriver:
    """BrowserAgentDriver for the Claude Code CLI."""

    name = "claude_code"

    def build_command(self, prompt: str, mcp_config_path: str) -> list[str]:
        """Return the argv to run Claude Code headless against the MCP config."""
        return [
            "claude",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--mcp-config",
            mcp_config_path,
        ]
