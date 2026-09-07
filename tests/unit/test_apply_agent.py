"""Unit tests for the ApplyAgent (driver + runner + gate injected)."""

from __future__ import annotations

from kravu.adapters.repository import JobRepository
from kravu.apply.agent import ApplyAgent
from kravu.apply.gate import ApplyGate
from kravu.domain.models import Job


class _Driver:
    name = "fake"

    def build_command(self, prompt: str, mcp_config_path: str) -> list[str]:
        return ["fake-agent", prompt]


def _ready(repo: JobRepository, url: str) -> None:
    repo.add_discovered(
        Job(url=url, title="Dev", company="Beta", apply_type="external")
    )
    repo.set_enrichment(url, "jd", None)
    repo.set_score(url, 9, "great")
    repo.set_tailored(url, "/tmp/r.md")


def test_agent_records_applied_when_approved(repo: JobRepository) -> None:
    _ready(repo, "https://a.test/1")
    gate = ApplyGate("human_gate", daily_cap=10, approver=lambda url: True)
    agent = ApplyAgent(
        driver=_Driver(),
        gate=gate,
        min_score=7,
        run_command=lambda cmd, timeout: "RESULT:APPLIED",
    )
    agent.run(repo)

    job = repo.get("https://a.test/1")
    assert job is not None and job.apply_status == "applied"
    assert job.apply_attempts == 1


def test_agent_skips_when_not_approved(repo: JobRepository) -> None:
    _ready(repo, "https://a.test/2")
    gate = ApplyGate("human_gate", daily_cap=10, approver=lambda url: False)
    ran: list[object] = []
    agent = ApplyAgent(
        driver=_Driver(),
        gate=gate,
        min_score=7,
        run_command=lambda cmd, timeout: ran.append(cmd) or "RESULT:APPLIED",
    )
    agent.run(repo)

    assert ran == []
    job = repo.get("https://a.test/2")
    assert job is not None and job.apply_status is None


def test_agent_records_captcha_as_parked(repo: JobRepository) -> None:
    _ready(repo, "https://a.test/3")
    gate = ApplyGate("auto", daily_cap=10, approver=lambda url: True)
    agent = ApplyAgent(
        driver=_Driver(),
        gate=gate,
        min_score=7,
        run_command=lambda cmd, timeout: "RESULT:CAPTCHA",
    )
    agent.run(repo)
    job = repo.get("https://a.test/3")
    assert job is not None and job.apply_status == "parked"
