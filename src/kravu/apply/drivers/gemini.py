"""GeminiDriver: drive the browser agent via the Gemini CLI.

The Gemini CLI was not installed in the build environment, so these flags come
from docs rather than a live ``--help`` capture. Verify against the installed
CLI before relying on this driver. Builds the command only.
"""

from __future__ import annotations


class GeminiDriver:
    """BrowserAgentDriver for the Gemini CLI."""

    name = "gemini"

    def build_command(self, prompt: str, mcp_config_path: str) -> list[str]:
        """Return the argv to run Gemini headless against the MCP config."""
        # CONFIRM: gemini CLI not installed in build env; flags from docs —
        # verify against `gemini --help` before use.
        return ["gemini", "-p", prompt, "--output-format", "json"]
