"""ApplyGate: the safety decision before any application is submitted.

The human-approval gate is the DEFAULT (spec §8, principles.md): nothing is
submitted without explicit user approval. ``auto`` mode skips the per-job
approval but still respects the daily cap. Approval and the day's submission count
are injected so this is pure, testable decision logic.
"""

from __future__ import annotations

from collections.abc import Callable

Approver = Callable[[str], bool]


class ApplyGate:
    """Decide whether a specific job may be submitted right now."""

    def __init__(self, mode: str, daily_cap: int, approver: Approver) -> None:
        """Store the apply mode, daily cap, and the approval callback."""
        self._mode = mode
        self._daily_cap = daily_cap
        self._approver = approver

    def may_submit(self, url: str, applied_today: int) -> bool:
        """Return True if ``url`` may be submitted given today's count.

        Args:
            url: The job being considered.
            applied_today: Submissions already made today.

        Returns:
            True to proceed with submission, False to hold/skip.
        """
        if applied_today >= self._daily_cap:
            return False
        if self._mode == "auto":
            return True
        return self._approver(url)
