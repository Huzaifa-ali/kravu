"""CursorDriver: drive the browser agent via the cursor-agent CLI.

The cursor-agent CLI was not installed in the build environment, so these flags
come from community/official docs rather than a live ``--help`` capture. Verify
against the installed CLI before relying on this driver. Builds the command only.
"""

from __future__ import annotations


class CursorDriver:
    """BrowserAgentDriver for the Cursor agent CLI."""

    name = "cursor"

    def build_command(self, prompt: str, mcp_config_path: str) -> list[str]:
        """Return the argv to run cursor-agent headless against the MCP config."""
        # CONFIRM: cursor-agent not installed in build env; flags from community
        # docs — verify against `cursor-agent --help` before use.
        return [
            "cursor-agent",
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--approve-mcps",
        ]
