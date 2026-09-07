"""kravu command-line interface (Typer). Parse, wire, render — no business logic.

Commands: ``init`` (setup wizard), ``run`` (full pipeline), ``resume <step>``
(retry a step then flow forward), ``status`` (per-step counts + shortlist), and
``apply`` (the gated Apply Agent). Adapters are constructed here at the edge and
injected into the use cases via the composition helpers.
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from kravu import config
from kravu.adapters.ats_source import AtsSource
from kravu.adapters.db import init_db
from kravu.adapters.jobspy_source import JobSpySource
from kravu.adapters.llm import LiteLLMClient
from kravu.adapters.playwright_page import PlaywrightPageRenderer
from kravu.adapters.repository import JobRepository
from kravu.apply.agent import ApplyAgent
from kravu.apply.gate import ApplyGate
from kravu.domain.models import Profile, ResumeFacts
from kravu.domain.ports import DiscoverySource
from kravu.entrypoints.composition import build_pipeline_steps, select_driver
from kravu.services.pipeline import Pipeline

app = typer.Typer(help="kravu — a local-first job-hunting pipeline.")
console = Console()

_STEPS = ("explore", "expand", "score", "tailor", "cover")


def _load_profile() -> Profile:
    data = config.load_profile()
    facts = data.get("resume_facts", {})
    return Profile(
        name=data.get("name", ""),
        email=data.get("email", ""),
        headline=data.get("headline", ""),
        location=data.get("location", ""),
        summary=data.get("summary", ""),
        skills=data.get("skills", []),
        resume_facts=ResumeFacts(
            raw_text=facts.get("raw_text", ""),
            companies=facts.get("companies", []),
            school=facts.get("school", ""),
            metrics=facts.get("metrics", []),
            skills=facts.get("skills", []),
        ),
        target_titles=data.get("target_titles", []),
        target_locations=data.get("target_locations", []),
    )


def _sources(searches: dict[str, Any]) -> list[DiscoverySource]:
    return [JobSpySource(), AtsSource()]


def _pipeline(profile: Profile, searches: dict[str, Any]) -> Pipeline:
    defaults = searches.get("defaults", {})
    per_run_cap = int(defaults.get("per_run_cap", 25))
    min_score = int(searches.get("min_score", config.min_score()))
    cover_policy = str(searches.get("cover_letter", config.COVER_LETTER_DEFAULT))
    steps = build_pipeline_steps(
        sources=_sources(searches),
        llm=LiteLLMClient(),
        profile=profile,
        renderer=PlaywrightPageRenderer(),
        min_score=min_score,
        cover_policy=cover_policy,
        searches=searches,
    )
    return Pipeline(steps, per_run_cap=per_run_cap)


@app.command()
def init() -> None:
    """Interactive one-time setup: resume, provider, searches (see spec §13)."""
    console.print(
        "[bold]kravu init[/bold] is interactive; see the plan/spec for the wizard "
        "steps. Set your provider key in the environment first."
    )


@app.command()
def run() -> None:
    """Run the full pipeline over all outstanding work."""
    config.load_env()
    try:
        profile = _load_profile()
    except FileNotFoundError:
        console.print("No profile found. Run `kravu init` first.")
        raise typer.Exit(code=1) from None
    if not config.has_llm_key():
        console.print("No LLM key set. Set your provider's key, then re-run.")
        raise typer.Exit(code=1)
    init_db()
    searches = config.load_searches()
    store = JobRepository()
    summary = _pipeline(profile, searches).run(store)
    for name, status in summary.items():
        console.print(f"{name}: {status}")
    _print_status()


@app.command()
def resume(step: str) -> None:
    """Retry a step's pending/failed jobs, then flow forward."""
    if step not in _STEPS:
        console.print(f"Unknown step '{step}'. Choose from {', '.join(_STEPS)}.")
        raise typer.Exit(code=1)
    config.load_env()
    try:
        profile = _load_profile()
    except FileNotFoundError:
        console.print("No profile found. Run `kravu init` first.")
        raise typer.Exit(code=1) from None
    init_db()
    searches = config.load_searches()
    store = JobRepository()
    reset = store.reset_step_for_retry(step)
    console.print(f"Reset {reset} job(s) at '{step}'.")
    summary = _pipeline(profile, searches).run(store)
    for name, status in summary.items():
        console.print(f"{name}: {status}")
    _print_status()


@app.command()
def status() -> None:
    """Show per-step counts and the ranked shortlist."""
    init_db()
    _print_status()


@app.command()
def apply(
    driver: str = typer.Option("kiro", help="Which agent driver to use."),
    auto: bool = typer.Option(False, help="Auto-submit (still capped)."),
    daily_cap: int = typer.Option(10, help="Max submissions per day."),
) -> None:
    """Run the gated Apply Agent over ready jobs (human-approval by default)."""
    config.load_env()
    init_db()
    searches = config.load_searches()
    min_score = int(searches.get("min_score", config.min_score()))
    store = JobRepository()

    def approver(url: str) -> bool:
        return typer.confirm(f"Submit application to {url}?")

    gate = ApplyGate(
        mode="auto" if auto else "human_gate",
        daily_cap=daily_cap,
        approver=approver,
    )
    ApplyAgent(select_driver(driver), gate, min_score).run(store)
    _print_status()


def _print_status() -> None:
    searches = config.load_searches()
    min_score = int(searches.get("min_score", config.min_score()))
    store = JobRepository()
    counts = store.step_counts(min_score)
    table = Table(title="Pipeline status")
    table.add_column("step")
    table.add_column("done", justify="right")
    table.add_column("pending", justify="right")
    for step in _STEPS:
        row = counts.get(step, {"done": 0, "pending": 0})
        table.add_row(step, str(row["done"]), str(row["pending"]))
    console.print(table)
    shortlist = store.shortlist(min_score)
    if shortlist:
        console.print(f"\n[bold]Shortlist ({len(shortlist)}):[/bold]")
        for job in shortlist[:25]:
            console.print(f"  [{job.fit_score}] {job.title} — {job.company}")


if __name__ == "__main__":  # pragma: no cover
    app()
