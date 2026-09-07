"""KiroDriver: drive the browser agent via the Kiro headless CLI (v0.1 default).

CONFIRMED 2026-09-08 against kiro 1.0.337 (``kiro chat --help``): the real
invocation is the ``chat`` subcommand with a prompt; the default ``--mode`` is
``agent``. There is no ``--no-interactive`` flag and no per-invocation
``--mcp-config``; MCP servers are registered separately via the top-level
``kiro --add-mcp <json>``. ``mcp_config_path`` is therefore accepted for the
Strategy contract but not placed on the argv. Builds the command only.
"""

from __future__ import annotations


class KiroDriver:
    """BrowserAgentDriver for the Kiro CLI (default driver)."""

    name = "kiro"

    def build_command(self, prompt: str, mcp_config_path: str) -> list[str]:
        """Return the argv to run Kiro headless in agent mode.

        ``mcp_config_path`` is unused on the argv: Kiro registers MCP servers
        out-of-band via ``kiro --add-mcp``, not per chat invocation.
        """
        return ["kiro", "chat", "--mode", "agent", prompt]
