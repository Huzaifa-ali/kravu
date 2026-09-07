"""BrowserAgentDriver: the Strategy interface for the Apply Agent's driver.

Each driver knows how to invoke ONE coding-agent CLI (Kiro, Claude Code, Codex,
Cursor, Gemini) pointed at the shared ``@playwright/mcp`` server. The agent
prints an agent-independent final line (``RESULT:APPLIED`` /
``RESULT:FAILED:<reason>`` / ``RESULT:CAPTCHA``) which ``parse_result_line`` maps
to a ``DriverResult`` (spec §8). This module holds no subprocess logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class DriverResult:
    """The parsed outcome of one apply attempt."""

    status: str  # applied | failed | parked
    reason: str | None


def parse_result_line(output: str) -> DriverResult:
    """Parse the agent's final RESULT line from its full stdout.

    Args:
        output: The agent's captured stdout.

    Returns:
        A ``DriverResult``. Missing/garbled output maps to ``failed``.
    """
    line = ""
    for candidate in reversed(output.splitlines()):
        if candidate.startswith("RESULT:"):
            line = candidate.strip()
            break
    if line == "RESULT:APPLIED":
        return DriverResult("applied", None)
    if line == "RESULT:CAPTCHA":
        return DriverResult("parked", "captcha")
    if line.startswith("RESULT:FAILED:"):
        return DriverResult("failed", line[len("RESULT:FAILED:") :] or None)
    return DriverResult("failed", "no RESULT line in agent output")


@runtime_checkable
class BrowserAgentDriver(Protocol):
    """A coding-agent CLI that can drive the browser via @playwright/mcp."""

    name: str

    def build_command(self, prompt: str, mcp_config_path: str) -> list[str]:
        """Return the argv to launch this agent for one apply attempt."""
        ...
