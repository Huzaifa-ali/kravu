"""ApplyAgent: run the selected browser-agent driver per ready job, gated.

For each tailored, high-fit job: consult the ``ApplyGate`` (human approval by
default), build the driver command pointed at the Playwright MCP config, run it
under a timeout, parse the agent's RESULT line, and record the outcome + attempt
count via ``JobStore``. The subprocess runner is injected so the unit suite never
spawns a process (spec §8).
"""

from __future__ import annotations

from collections.abc import Callable

from kravu import config
from kravu.apply.drivers.base import BrowserAgentDriver, parse_result_line
from kravu.apply.gate import ApplyGate
from kravu.apply.mcp_server import write_mcp_config
from kravu.domain.models import Job
from kravu.domain.ports import JobStore

RunCommand = Callable[[list[str], int], str]


def _default_run_command(command: list[str], timeout: int) -> str:
    import subprocess

    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return completed.stdout


def _build_prompt(job: Job) -> str:
    return (
        "Apply to this job using the browser tools. Use the tailored resume at "
        f"{job.tailored_resume_path}. Job URL: {job.apply_url or job.url}. "
        "Do NOT invent answers to custom questions; if a CAPTCHA, login wall, or "
        "required free-text question blocks you, stop and print RESULT:CAPTCHA. "
        "On success print RESULT:APPLIED; on failure print RESULT:FAILED:<reason>."
    )


class ApplyAgent:
    """Run the Apply Agent over ready jobs, honoring the gate and daily cap."""

    def __init__(
        self,
        driver: BrowserAgentDriver,
        gate: ApplyGate,
        min_score: int,
        run_command: RunCommand | None = None,
        timeout: int = 300,
    ) -> None:
        """Store the driver, gate, threshold, subprocess runner, and timeout."""
        self._driver = driver
        self._gate = gate
        self._min_score = min_score
        self._run_command = run_command or _default_run_command
        self._timeout = timeout

    def run(self, store: JobStore, limit: int | None = None) -> None:
        """Attempt each ready job (up to ``limit``), gated and recorded."""
        config.ensure_dirs()
        mcp_config = write_mcp_config(config.app_home() / "mcp.json")
        for job in store.pending_apply(self._min_score, limit):
            if not self._gate.may_submit(job.url, store.applied_today()):
                continue
            self._apply_one(store, job, mcp_config)

    def _apply_one(self, store: JobStore, job: Job, mcp_config: str) -> None:
        store.bump_apply_attempts(job.url)
        command = self._driver.build_command(_build_prompt(job), mcp_config)
        try:
            output = self._run_command(command, self._timeout)
        except Exception as exc:  # noqa: BLE001 - record on the row, continue
            store.set_apply_result(job.url, "failed", str(exc))
            return
        result = parse_result_line(output)
        store.set_apply_result(job.url, result.status, result.reason)
