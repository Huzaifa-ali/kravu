"""kravu command-line interface (Typer). Parse, wire, render — no business logic.

Commands: ``init`` (setup wizard), ``run`` (full pipeline), ``resume <step>``
(retry a step then flow forward), ``status`` (per-step counts + shortlist), and
``apply`` (the gated Apply Agent). Adapters are constructed here at the edge and
injected into the use cases via the composition helpers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from kravu import config
from kravu.adapters.ats_source import AtsSource
from kravu.adapters.db import init_db
from kravu.adapters.jobspy_source import JobSpySource
from kravu.adapters.llm import LiteLLMClient
from kravu.adapters.playwright_page import PlaywrightPageRenderer
from kravu.adapters.repository import JobRepository
from kravu.adapters.resume_reader import read_resume_text
from kravu.apply.agent import ApplyAgent
from kravu.apply.gate import ApplyGate
from kravu.domain.models import Profile, ResumeFacts
from kravu.domain.ports import DiscoverySource
from kravu.entrypoints.composition import build_pipeline_steps, select_driver
from kravu.exceptions import ConfigError
from kravu.services.build_profile import BuildProfile
from kravu.services.clean import CleanWorkspace
from kravu.services.pipeline import Pipeline
from kravu.services.suggest_searches import SuggestSearches

app = typer.Typer(help="kravu — a local-first job-hunting pipeline.")
console = Console()

_STEPS = ("explore", "expand", "score", "tailor", "cover")

_LOGGER = logging.getLogger("kravu")


def _configure_logging() -> None:
    """Send kravu's own INFO logs to a rotating-per-run file under the app home.

    Idempotent: a second call does not attach duplicate handlers. The file lives
    at ``~/.kravu/logs/kravu.log`` (or under ``KRAVU_HOME``). Console progress is
    handled separately by the Rich reporter, so we keep the file handler quiet on
    stdout to avoid clobbering the progress bars.
    """
    config.ensure_dirs()
    root = logging.getLogger("kravu")
    root.setLevel(logging.INFO)
    log_file = str(config.log_dir() / "kravu.log")
    already = any(
        isinstance(h, logging.FileHandler)
        and getattr(h, "baseFilename", None) == str(Path(log_file).resolve())
        for h in root.handlers
    )
    if not already:
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
        )
        root.addHandler(handler)


class RichProgressReporter:
    """Concrete ``ProgressReporter`` that renders live per-step bars with Rich.

    One bar per step. ``start_step`` adds a task, ``advance`` moves it one item
    and updates the trailing detail label, ``finish_step`` completes it. Also
    mirrors each step boundary to the ``kravu`` file logger so runs are auditable.
    """

    def __init__(self, progress: Progress) -> None:
        """Store the live ``Progress`` instance and the per-step task registry."""
        self._progress = progress
        self._tasks: dict[str, TaskID] = {}

    def start_step(self, name: str, total: int) -> None:
        """Add (or reset) a bar for ``name`` sized to ``total`` items."""
        _LOGGER.info("%s: starting (%d items)", name, total)
        self._tasks[name] = self._progress.add_task(
            f"{name}", total=max(total, 1), detail=""
        )

    def advance(self, name: str, detail: str = "") -> None:
        """Advance ``name`` by one item and show ``detail`` as the trailing label."""
        task_id = self._tasks.get(name)
        if task_id is None:
            return
        self._progress.update(task_id, advance=1, detail=detail)

    def finish_step(self, name: str, note: str = "") -> None:
        """Mark ``name``'s bar done and record the summary note in the log.

        The bar is left at the count ``advance`` reached (the real number of
        items processed), then shrunk to that count so it renders as complete
        without inflating the total. This keeps a bar honest when a step
        processes fewer items than its cap — e.g. ``explore`` finding 1 job
        against a limit of 100 reads ``1/1``, never ``100/100``.
        """
        _LOGGER.info("%s: done%s", name, f" ({note})" if note else "")
        task_id = self._tasks.get(name)
        if task_id is None:
            return
        task = next((t for t in self._progress.tasks if t.id == task_id), None)
        if task is not None:
            self._progress.update(task_id, total=task.completed, detail=note)


def _progress_columns() -> list[Any]:
    """The column layout for the run progress display."""
    return [
        SpinnerColumn(),
        TextColumn("[bold]{task.description}[/bold]"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("[dim]{task.fields[detail]}[/dim]"),
        TimeElapsedColumn(),
    ]


def _run_pipeline_with_progress(
    pipeline: Pipeline, store: JobRepository, *, start_from: str | None = None
) -> dict[str, str]:
    """Run the pipeline under a live Rich progress display and return the summary.

    ``start_from`` scopes the run to that step onward (used by ``resume`` so it
    never re-runs discovery). A ``KeyboardInterrupt`` (Ctrl+C) stops the run
    cleanly: the progress display is torn down by the ``with`` block and a short
    message is printed, rather than leaving a half-rendered bar or a traceback.
    """
    try:
        with Progress(
            *_progress_columns(), console=console, transient=False
        ) as progress:
            return pipeline.run(
                store, RichProgressReporter(progress), start_from=start_from
            )
    except KeyboardInterrupt:
        console.print(
            "\n[yellow]Interrupted. Re-run to resume where it stopped.[/yellow]"
        )
        raise typer.Exit(code=130) from None


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


def _sources() -> list[DiscoverySource]:
    return [JobSpySource(), AtsSource()]


def _resolve_min_score(searches: dict[str, Any]) -> int:
    """Min score from ``searches.yaml`` if present, else ``KRAVU_MIN_SCORE``."""
    if "min_score" in searches:
        return int(searches["min_score"])
    return config.min_score()


def _resolve_cover_policy(searches: dict[str, Any]) -> str:
    """Cover policy from ``searches.yaml`` if present, else ``KRAVU_COVER_LETTER``."""
    if "cover_letter" in searches:
        return str(searches["cover_letter"])
    return config.cover_letter_default()


def _resolve_limit(searches: dict[str, Any]) -> int:
    """Run limit from ``searches.yaml`` if present, else ``KRAVU_LIMIT``/default."""
    if "limit" in searches:
        return int(searches["limit"])
    return config.limit()


def _pipeline(
    profile: Profile, searches: dict[str, Any], sources: list[DiscoverySource]
) -> Pipeline:
    min_score = _resolve_min_score(searches)
    cover_policy = _resolve_cover_policy(searches)
    limit = _resolve_limit(searches)
    steps = build_pipeline_steps(
        sources=sources,
        llm=LiteLLMClient(),
        profile=profile,
        renderer=PlaywrightPageRenderer(),
        min_score=min_score,
        cover_policy=cover_policy,
        searches=searches,
        limit=limit,
    )
    return Pipeline(steps)


def _log_source_notes(sources: list[DiscoverySource]) -> None:
    """Emit each discovery source's per-target outcome to log and console.

    Sources record why each board/company returned what it did (``ok: N``,
    ``empty``, ``failed: ...``, ``unsupported``). Surfacing them turns a silent
    ``0 new jobs`` into an explained one, per board — both in the log file and as
    a compact on-screen breakdown so the user never has to guess.
    """
    lines: list[str] = []
    for source in sources:
        notes = getattr(source, "notes", None)
        if not notes:
            continue
        for target, outcome in notes.items():
            label = ":".join(target) if isinstance(target, tuple) else str(target)
            _LOGGER.info("%s[%s]: %s", source.name, label, outcome)
            style = "green" if str(outcome).startswith("ok") else "yellow"
            lines.append(f"  [{style}]{source.name} · {label}[/{style}]: {outcome}")
    if lines:
        console.print("\n[bold]Discovery breakdown:[/bold]")
        for line in lines:
            console.print(line)


@app.command()
def init() -> None:
    """Interactive one-time setup: resume, provider, searches (see spec §13).

    Safe to re-run: if a profile already exists, asks before overwriting. Uses two
    LLM calls (BuildProfile + SuggestSearches). kravu never collects API keys —
    it verifies the chosen provider's key is present and hard-stops if it is not.
    """
    config.load_env()

    if config.profile_exists() and not typer.confirm(
        "A profile already exists. Overwrite it with a fresh setup?"
    ):
        console.print("Keeping the existing setup. Nothing changed.")
        return

    # 1. Resume ------------------------------------------------------------
    resume_path = Path(typer.prompt("Path to your resume (.txt, .md, .pdf, .docx)"))
    try:
        raw_resume_text = read_resume_text(resume_path)
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    # 2. Provider / model --------------------------------------------------
    options = config.model_options()
    console.print("\n[bold]Choose a model provider:[/bold]")
    for index, option in enumerate(options, start=1):
        console.print(f"  {index}. {option.label}  [dim]({option.model})[/dim]")
    choice = typer.prompt("Model number", default="1")
    chosen = _resolve_model_choice(choice, options)

    # 3. Preflight (hard-stop) --------------------------------------------
    if not config.key_present_for_model(chosen):
        required = config.required_key_for(chosen)
        console.print(
            f"[red]No API key found for this provider.[/red] Set [bold]{required}"
            "[/bold] in your environment or ~/.kravu/.env, then re-run `kravu init`. "
            "kravu never stores your key."
        )
        raise typer.Exit(code=1)

    config.set_model_in_env_file(chosen)
    console.print(f"Model set to [bold]{chosen}[/bold].")

    llm = LiteLLMClient(chosen)

    # 4. Structure resume (BuildProfile) ----------------------------------
    console.print("Reading your resume with the model...")
    try:
        profile = BuildProfile(llm).run(raw_resume_text)
    except ConfigError as exc:  # pragma: no cover - defensive
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None

    # 5. Suggest searches (SuggestSearches) -------------------------------
    console.print("Proposing job searches from your profile...")
    searches = SuggestSearches(llm).run(profile)

    # 6. Review both, then save -------------------------------------------
    _show_profile(profile)
    if typer.confirm("Save this profile?", default=True):
        config.save_profile(profile)
        console.print(f"Saved profile to {config.profile_path()}.")
    else:
        console.print(
            "Skipped saving the profile. Edit and re-run `kravu init` when ready."
        )
        raise typer.Exit(code=0)

    _show_searches(searches)
    if typer.confirm("Save these searches?", default=True):
        config.save_searches(searches)
        console.print(f"Saved searches to {config.searches_path()}.")
    else:
        console.print(
            f"Skipped saving searches. Edit {config.searches_path()} by hand, "
            "or re-run `kravu init`."
        )

    # 7. Done --------------------------------------------------------------
    console.print("\n[bold green]Setup complete.[/bold green] Run `kravu run`.")


def _resolve_model_choice(choice: str, options: list[config.ModelOption]) -> str:
    """Map a menu selection to a model string; fall back to the default."""
    try:
        index = int(choice)
    except ValueError:
        return options[0].model
    if 1 <= index <= len(options):
        return options[index - 1].model
    return options[0].model


def _show_profile(profile: Profile) -> None:
    """Render the extracted profile for the user to review."""
    console.print("\n[bold]Extracted profile:[/bold]")
    console.print(f"  Name:     {profile.name}")
    console.print(f"  Email:    {profile.email}")
    console.print(f"  Headline: {profile.headline}")
    console.print(f"  Location: {profile.location}")
    console.print(f"  Skills:   {', '.join(profile.skills) or '(none)'}")
    console.print(
        f"  Companies:{', '.join(profile.resume_facts.companies) or ' (none)'}"
    )


def _show_searches(searches: dict[str, Any]) -> None:
    """Render the proposed searches for the user to review."""
    console.print("\n[bold]Proposed searches:[/bold]")
    for entry in searches.get("searches", []):
        console.print(
            f"  - {entry.get('search_term')} @ {entry.get('location')} "
            f"(remote={entry.get('is_remote')})"
        )
    console.print(f"  min_score: {searches.get('min_score')}")


@app.command()
def run() -> None:
    """Run the full pipeline over all outstanding work."""
    config.load_env()
    _configure_logging()
    try:
        profile = _load_profile()
    except FileNotFoundError:
        console.print("No profile found. Run `kravu init` first.")
        raise typer.Exit(code=1) from None
    if not config.has_llm_key():
        console.print("No LLM key set. Set your provider's key, then re-run.")
        raise typer.Exit(code=1)
    try:
        config.model()
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None
    init_db()
    searches = config.load_searches()
    store = JobRepository()
    sources = _sources()
    summary = _run_pipeline_with_progress(_pipeline(profile, searches, sources), store)
    _log_source_notes(sources)
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
    _configure_logging()
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
    sources = _sources()
    summary = _run_pipeline_with_progress(
        _pipeline(profile, searches, sources), store, start_from=step
    )
    _log_source_notes(sources)
    for name, status in summary.items():
        console.print(f"{name}: {status}")
    _print_status()


@app.command()
def status() -> None:
    """Show per-step counts and the ranked shortlist."""
    config.load_env()
    init_db()
    try:
        _print_status()
    except ConfigError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from None


@app.command()
def apply(
    driver: str = typer.Option("kiro", help="Which agent driver to use."),
    auto: bool = typer.Option(False, help="Auto-submit (still capped)."),
    daily_cap: int = typer.Option(10, help="Max submissions per day."),
) -> None:
    """Run the gated Apply Agent over ready jobs (human-approval by default)."""
    config.load_env()
    try:
        _load_profile()
    except FileNotFoundError:
        console.print("No profile found. Run `kravu init` first.")
        raise typer.Exit(code=1) from None
    init_db()
    searches = config.load_searches()
    min_score = _resolve_min_score(searches)
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


@app.command()
def clean() -> None:
    """Reset the workspace: clear all jobs, artifacts, and logs (asks first).

    Prompts for confirmation before doing anything. On yes, removes every job from
    the database, deletes generated tailored resumes and cover letters, and empties
    the log file — a clean slate for re-testing. Setup (profile, searches, .env) is
    left untouched.
    """
    config.load_env()
    init_db()
    store = JobRepository()
    total = store.stats()["total"]
    if not typer.confirm(
        f"This will delete {total} job(s) plus generated resumes, cover letters, "
        "and logs. Continue?"
    ):
        console.print("Nothing changed.")
        return
    result = CleanWorkspace().run(store)
    console.print(
        f"Cleaned: removed {result.jobs_removed} job(s) and "
        f"{result.files_removed} generated file(s). Logs truncated."
    )


def _print_status() -> None:
    searches = config.load_searches()
    min_score = _resolve_min_score(searches)
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
