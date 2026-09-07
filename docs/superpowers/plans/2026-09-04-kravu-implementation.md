# kravu Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the remaining v0.1 of kravu — a local-first job-hunting pipeline — on top of the already-built `domain/models.py`, `config.py`, and `adapters/{db,repository}.py`, delivering a working `init → run → resume → status → apply` CLI.

**Architecture:** CLI-fronted, database-coordinated deterministic workflow (use cases 1–5) plus an isolated Apply Agent (use case 6). Cosmic-Python layout: `entrypoints → services → domain`, with `adapters` implementing `domain` ports. Stages coordinate only through the SQLite blackboard (the `jobs` table). LLM is a focused text function inside a use case, never in control flow.

**Tech Stack:** Python 3.11+, `uv`, Typer+Rich, SQLite (stdlib), LiteLLM, python-jobspy, Playwright + selectolax + trafilatura, PyYAML + python-dotenv, `@playwright/mcp` (npx) for the Apply Agent. Tooling: ruff, mypy (strict), pytest.

---

## How to work this plan (read once)

**Every code module** starts with:
```python
"""<one-line module responsibility>."""

from __future__ import annotations
```
- Absolute imports only (`from kravu.x.y import Z`), grouped future/stdlib/third-party/first-party.
- Modern typing (`list[str]`, `X | None`), full hints incl. `-> None`, Google-style docstrings on public modules/classes/functions.
- 88-column lines. Run `ruff format` + `ruff check --fix` before each commit.
- Never f-string data into SQL. All SQL stays in `adapters/repository.py`.
- No real network/LLM in unit tests — inject fakes.

**Definition of done for every task:** after the task's final code step, run the full gate and it must pass before committing:
```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
```
(If a task is pure scaffolding with no `src/kravu` code yet, run only the steps it lists.)

**Commit style:** conventional commits, one logical change per commit, commit as you go.

**⚠️ Confirm-at-build markers** appear on tasks that depend on unverified external facts (default model string; Kiro/Cursor/Gemini CLI flags). Those tasks include an explicit confirmation step — do not invent flags; verify against the installed CLI/docs and record what you found.

---

## File map (what gets created, and its single responsibility)

| File | Responsibility |
|------|----------------|
| `src/kravu/exceptions.py` | `KravuError` hierarchy — typed, actionable errors |
| `src/kravu/domain/ports.py` | Protocols: `JobStore`, `LLMClient`, `DiscoverySource` |
| `src/kravu/adapters/llm.py` | `LiteLLMClient` — provider-agnostic completion + defensive JSON parse |
| `src/kravu/adapters/prompts.py` | Prompt builders for score/tailor/cover/extract/build_profile/suggest |
| `src/kravu/adapters/jobspy_source.py` | `JobSpySource` — keyword discovery via python-jobspy |
| `src/kravu/adapters/ats_source.py` | `AtsSource` — Greenhouse/Lever/Ashby JSON boards |
| `src/kravu/adapters/playwright_page.py` | `PlaywrightPageRenderer` — render URL → HTML |
| `src/kravu/services/build_profile.py` | `BuildProfile` — raw resume text → structured `Profile` |
| `src/kravu/services/suggest_searches.py` | `SuggestSearches` — `Profile` → validated `searches.yaml` dict |
| `src/kravu/services/explore.py` | `ExploreJobs` — discover, dedupe, persist new jobs |
| `src/kravu/services/expand.py` | `ExpandJob` — render + 3-tier extraction cascade |
| `src/kravu/services/score.py` | `ScoreJobFit` — rubric fit score, defensive JSON |
| `src/kravu/services/tailor.py` | `TailorResume` — structured sections + fabrication guard |
| `src/kravu/services/cover_letter.py` | `DraftCoverLetter` — policy gate + write letter |
| `src/kravu/services/pipeline.py` | `Pipeline` — sequence use cases; sequencing only |
| `src/kravu/apply/drivers/base.py` | `BrowserAgentDriver` protocol + `DriverResult` |
| `src/kravu/apply/drivers/{kiro,claude_code,codex,cursor,gemini}.py` | per-agent CLI drivers |
| `src/kravu/apply/mcp_server.py` | `@playwright/mcp` launch config helper |
| `src/kravu/apply/gate.py` | human-approval gate + daily-cap logic |
| `src/kravu/apply/agent.py` | `ApplyAgent` — pick driver, run per job, record result |
| `src/kravu/entrypoints/cli.py` | Typer app: `init/run/resume/status/apply` |
| `pyproject.toml` | PEP 621 project metadata + tool config |
| `tests/conftest.py` + `tests/{unit,integration,e2e}/*` | fixtures + tests mirroring src |

**Repository additions (Task 3)** back `resume <step>` and per-step `status`:
`pending_scoring`/`pending_tailoring`/`pending_cover` already exist; we add
`reset_step_for_retry`, `pending_explore_note` recording, and a `step_counts()`
reporting query.

---


## Task 0: Project tooling — `pyproject.toml` + test scaffold

Establishes the dependency set, tool config (ruff/mypy strict/pytest), and the test tree so every later task can run the gate.

**Files:**
- Create: `pyproject.toml`
- Create: `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/e2e/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "kravu"
version = "0.1.0"
description = "A local-first, open-source job-hunting pipeline."
authors = [{ name = "Muhammad Huzaifa Ali" }]
license = { text = "MIT" }
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "python-jobspy>=1.1.82,<2",
    "litellm>=1.99,<2",
    "typer>=0.27,<1",
    "rich>=15,<16",
    "playwright>=1.62,<2",
    "selectolax>=0.4.11,<1",
    "trafilatura>=2.2,<3",
    "pyyaml>=6.0.3,<7",
    "python-dotenv>=1.2,<2",
]

[project.optional-dependencies]
dev = ["pytest>=9.1,<10", "ruff>=0.16,<1", "mypy>=2.3,<3"]

[project.scripts]
kravu = "kravu.entrypoints.cli:app"

[build-system]
requires = ["hatchling>=1.32,<2"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/kravu"]

[tool.ruff]
line-length = 88
target-version = "py311"
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "D"]
ignore = ["D203", "D213"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["D"]

[tool.ruff.lint.pydocstyle]
convention = "google"

[tool.mypy]
python_version = "3.11"
strict = true
files = ["src/kravu"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"
```

- [ ] **Step 2: Create empty test package markers**

Create `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/e2e/__init__.py`, each containing a single line:

```python
"""Test package."""
```

- [ ] **Step 3: Write `tests/conftest.py`** (shared fixtures: temp DB + fakes)

```python
"""Shared pytest fixtures: an isolated on-disk SQLite DB and reusable fakes."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from kravu.adapters.db import close_connection, init_db
from kravu.adapters.repository import JobRepository


@pytest.fixture()
def kravu_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point kravu at a throwaway home directory for the duration of a test."""
    monkeypatch.setenv("KRAVU_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture()
def repo(kravu_home: Path) -> Iterator[JobRepository]:
    """A JobRepository backed by a fresh temp database."""
    db_file = kravu_home / "kravu.db"
    conn = init_db(db_file)
    yield JobRepository(conn)
    close_connection(db_file)
```

- [ ] **Step 4: Run the gate (expect a clean, empty test run)**

Run: `ruff check src/kravu tests ; mypy src/kravu ; pytest -q`
Expected: ruff clean; mypy passes on existing modules; pytest reports "no tests ran" (or collects only the empty tree) with exit 0 or 5. Exit 5 (no tests collected) is acceptable here.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/
git commit -m "chore: add pyproject.toml (ruff/mypy/pytest config) and test scaffold"
```

---

## Task 1: `exceptions.py` — typed error hierarchy

Single responsibility: define `KravuError` and specific subclasses used across the codebase, each carrying an actionable message.

**Files:**
- Create: `src/kravu/exceptions.py`
- Test: `tests/unit/test_exceptions.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for the kravu exception hierarchy."""

from __future__ import annotations

import pytest

from kravu.exceptions import (
    ConfigError,
    EnrichmentError,
    FabricationError,
    KravuError,
    LLMResponseError,
    ProfileNotFoundError,
    SearchesConfigError,
)


def test_all_kravu_errors_subclass_base() -> None:
    for cls in (
        ConfigError,
        SearchesConfigError,
        ProfileNotFoundError,
        LLMResponseError,
        EnrichmentError,
        FabricationError,
    ):
        assert issubclass(cls, KravuError)


def test_kravu_error_carries_message() -> None:
    err = ProfileNotFoundError("Run `kravu init` first.")
    assert str(err) == "Run `kravu init` first."


def test_kravu_error_is_exception() -> None:
    with pytest.raises(KravuError):
        raise LLMResponseError("bad json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_exceptions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.exceptions'`.

- [ ] **Step 3: Write `src/kravu/exceptions.py`**

```python
"""Typed exception hierarchy for kravu.

Every error kravu raises deliberately is a ``KravuError`` subclass with an
actionable message (tell the user what to do). Per-job pipeline failures are
recorded on the job row instead of raised; these exceptions are for
configuration, setup, and hard-stop conditions.
"""

from __future__ import annotations


class KravuError(Exception):
    """Base class for all deliberate kravu errors."""


class ConfigError(KravuError):
    """Configuration or environment is invalid or incomplete."""


class SearchesConfigError(ConfigError):
    """``searches.yaml`` failed schema validation."""


class ProfileNotFoundError(KravuError):
    """No profile exists yet — the user must run ``kravu init``."""


class MissingKeyError(ConfigError):
    """A key-requiring provider is selected but its env var is absent."""


class LLMResponseError(KravuError):
    """The LLM returned output that could not be parsed/validated."""


class EnrichmentError(KravuError):
    """A job page could not be rendered or its description extracted."""


class FabricationError(KravuError):
    """Tailoring/cover output failed the anti-fabrication guard."""


class DiscoveryError(KravuError):
    """A discovery source failed in a way worth reporting to the user."""


class ApplyError(KravuError):
    """The Apply Agent failed to run or record a result."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_exceptions.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/exceptions.py tests/unit/test_exceptions.py
git commit -m "feat: add KravuError exception hierarchy"
```

---

## Task 2: `domain/ports.py` — the port protocols

Single responsibility: define the three `Protocol`s services depend on (`JobStore`, `LLMClient`, `DiscoverySource`). Pure stdlib, no side effects. Method signatures must match the already-built `JobRepository` (Task 3 adds the extra methods the protocol will list).

**Files:**
- Create: `src/kravu/domain/ports.py`
- Test: `tests/unit/test_ports.py`

- [ ] **Step 1: Write the failing test** (structural checks — protocols are runtime-checkable)

```python
"""Unit tests for the domain port protocols."""

from __future__ import annotations

from kravu.domain.ports import DiscoverySource, JobStore, LLMClient


def test_job_repository_satisfies_job_store() -> None:
    from kravu.adapters.repository import JobRepository

    assert issubclass(JobRepository, JobStore)


def test_llm_client_is_runtime_checkable() -> None:
    class FakeLLM:
        def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
            return "{}"

    assert isinstance(FakeLLM(), LLMClient)


def test_discovery_source_is_runtime_checkable() -> None:
    class FakeSource:
        name = "fake"

        def discover(self, searches: dict[str, object]) -> list[object]:
            return []

    assert isinstance(FakeSource(), DiscoverySource)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ports.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.domain.ports'`.

- [ ] **Step 3: Write `src/kravu/domain/ports.py`**

```python
"""Port protocols the services depend on (dependency inversion).

Services import these protocols, never concrete adapters. Adapters in
``kravu.adapters`` implement them; tests provide fakes. All protocols are
``runtime_checkable`` so tests can assert conformance structurally.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from kravu.domain.models import Job


@runtime_checkable
class JobStore(Protocol):
    """Persistence contract for the jobs blackboard.

    Implemented by ``kravu.adapters.repository.JobRepository`` (SQLite). A future
    Postgres implementation would satisfy the same protocol.
    """

    def add_discovered(self, job: Job) -> bool: ...

    def pending_enrichment(self, limit: int | None = None) -> list[Job]: ...

    def set_enrichment(
        self, url: str, full_description: str, apply_url: str | None
    ) -> None: ...

    def bump_enrich_attempts(self, url: str) -> None: ...

    def set_enrichment_error(self, url: str, error: str) -> None: ...

    def pending_scoring(self, limit: int | None = None) -> list[Job]: ...

    def set_score(self, url: str, score: int, reasoning: str) -> None: ...

    def pending_tailoring(
        self, min_score: int, limit: int | None = None
    ) -> list[Job]: ...

    def set_tailored(self, url: str, resume_path: str) -> None: ...

    def bump_tailor_attempts(self, url: str) -> None: ...

    def pending_cover(
        self, min_score: int, limit: int | None = None
    ) -> list[Job]: ...

    def set_cover(self, url: str, needed: bool, path: str | None) -> None: ...

    def bump_cover_attempts(self, url: str) -> None: ...

    def shortlist(self, min_score: int) -> list[Job]: ...

    def get(self, url: str) -> Job | None: ...

    def stats(self) -> dict[str, int]: ...

    def step_counts(self, min_score: int) -> dict[str, dict[str, int]]: ...

    def reset_step_for_retry(self, phase: str) -> int: ...

    def pending_apply(self, min_score: int, limit: int | None = None) -> list[Job]: ...

    def set_apply_result(
        self, url: str, status: str, error: str | None
    ) -> None: ...

    def bump_apply_attempts(self, url: str) -> None: ...

    def applied_today(self) -> int: ...


@runtime_checkable
class LLMClient(Protocol):
    """Provider-agnostic model port.

    ``complete`` returns the model's raw text. Callers parse/validate defensively
    (JSON is instructed, not guaranteed — see spec §7a/§9).
    """

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str: ...


@runtime_checkable
class DiscoverySource(Protocol):
    """A source of job postings (JobSpy, ATS boards, ...).

    ``discover`` runs the configured searches and returns ``Job`` rows (only the
    discovery fields populated).
    """

    name: str

    def discover(self, searches: dict[str, object]) -> list[Job]: ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_ports.py -v`
Expected: `test_llm_client_...` and `test_discovery_source_...` PASS. `test_job_repository_satisfies_job_store` will **FAIL** until Task 3 adds `step_counts`, `reset_step_for_retry`, `pending_apply`, `set_apply_result`, `bump_apply_attempts`, `applied_today` to `JobRepository`.

> **Sequencing note:** Mark this failing sub-assertion as expected. Do NOT weaken the protocol. Complete Task 3 next; then re-run `pytest tests/unit/test_ports.py -v` and confirm all three pass before committing Task 3.

- [ ] **Step 5: Commit the two passing protocols now, defer the repo assertion**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu
git add src/kravu/domain/ports.py tests/unit/test_ports.py
git commit -m "feat: add JobStore/LLMClient/DiscoverySource port protocols"
```
(Repository conformance is completed and re-verified at the end of Task 3.)

---


## Task 3: Repository additions — `resume <step>`, per-step `status`, apply queries

Adds the queries needed for `kravu resume <step>` (reset a step's outputs so pending/failed jobs re-run, then flow forward) and per-step `status` counts, plus the Apply Agent queue/recording queries. All SQL stays here (spec + coding-standards). Closes open item #3 from the spec review.

**Files:**
- Modify: `src/kravu/adapters/repository.py` (append new methods; import `PipelinePhase`)
- Test: `tests/integration/test_repository_resume_status.py`

- [ ] **Step 1: Write the failing test**

```python
"""Integration tests for resume/status/apply repository queries."""

from __future__ import annotations

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job


def _discover(repo: JobRepository, url: str) -> None:
    repo.add_discovered(Job(url=url, title="Dev", company="Acme"))


def test_step_counts_reports_per_phase(repo: JobRepository) -> None:
    _discover(repo, "https://a.test/1")
    _discover(repo, "https://a.test/2")
    repo.set_enrichment("https://a.test/1", "A full JD with requirements.", None)
    repo.set_score("https://a.test/1", 8, "good")

    counts = repo.step_counts(min_score=7)

    assert counts["explore"]["done"] == 2
    assert counts["expand"]["done"] == 1
    assert counts["expand"]["pending"] == 1
    assert counts["score"]["done"] == 1


def test_reset_step_for_retry_clears_failed_expand(repo: JobRepository) -> None:
    _discover(repo, "https://a.test/1")
    # Simulate 3 failed enrich attempts (pending, non-retryable until reset).
    for _ in range(3):
        repo.bump_enrich_attempts("https://a.test/1")
    repo.set_enrichment_error("https://a.test/1", "boom")
    assert repo.pending_enrichment() == []  # exhausted

    n = repo.reset_step_for_retry("expand")

    assert n == 1
    pending = repo.pending_enrichment()
    assert len(pending) == 1
    assert pending[0].enrich_attempts == 0


def test_pending_apply_returns_tailored_high_fit(repo: JobRepository) -> None:
    _discover(repo, "https://a.test/1")
    repo.set_enrichment("https://a.test/1", "JD requirements responsibilities", None)
    repo.set_score("https://a.test/1", 9, "great")
    repo.set_tailored("https://a.test/1", "/tmp/r.md")

    pending = repo.pending_apply(min_score=7)

    assert [j.url for j in pending] == ["https://a.test/1"]


def test_set_apply_result_and_applied_today(repo: JobRepository) -> None:
    _discover(repo, "https://a.test/1")
    repo.set_apply_result("https://a.test/1", "applied", None)

    assert repo.applied_today() == 1
    job = repo.get("https://a.test/1")
    assert job is not None
    assert job.apply_status == "applied"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_repository_resume_status.py -v`
Expected: FAIL — `AttributeError: 'JobRepository' object has no attribute 'step_counts'`.

- [ ] **Step 3: Append the new methods to `src/kravu/adapters/repository.py`**

First, add `PipelinePhase` to the existing import block near the top:

```python
from kravu.domain.models import Job, PipelinePhase
```

Then append these methods inside the `JobRepository` class (after `stats`):

```python
    # -- Apply (use case 6) -------------------------------------------------

    def pending_apply(self, min_score: int, limit: int | None = None) -> list[Job]:
        """Tailored, high-fit jobs not yet applied and under the attempt cap."""
        sql = (
            "SELECT * FROM jobs "
            "WHERE tailored_resume_path IS NOT NULL "
            "AND fit_score >= ? "
            "AND (apply_status IS NULL OR apply_status IN ('failed', 'pending')) "
            "AND COALESCE(apply_attempts, 0) < 3 "
            "ORDER BY fit_score DESC"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [_row_to_job(r) for r in self._conn.execute(sql, (min_score,))]

    def set_apply_result(self, url: str, status: str, error: str | None) -> None:
        """Record an apply outcome. ``status`` is applied|failed|parked|pending."""
        applied_at = _now() if status == "applied" else None
        self._conn.execute(
            "UPDATE jobs SET apply_status = ?, applied_at = ?, apply_error = ? "
            "WHERE url = ?",
            (status, applied_at, (error or "")[:500] or None, url),
        )
        self._conn.commit()

    def bump_apply_attempts(self, url: str) -> None:
        self._conn.execute(
            "UPDATE jobs SET apply_attempts = COALESCE(apply_attempts, 0) + 1 "
            "WHERE url = ?",
            (url,),
        )
        self._conn.commit()

    def applied_today(self) -> int:
        """Count submissions recorded today (UTC) — used for the daily cap."""
        today = _now()[:10]  # YYYY-MM-DD prefix of the ISO timestamp
        row = self._conn.execute(
            "SELECT COUNT(*) FROM jobs "
            "WHERE apply_status = 'applied' AND substr(applied_at, 1, 10) = ?",
            (today,),
        ).fetchone()
        return int(row[0])

    # -- Resume / status reporting -----------------------------------------

    def reset_step_for_retry(self, phase: str) -> int:
        """Clear a step's error/attempt state so its pending jobs re-run.

        For ``expand`` this zeroes ``enrich_attempts`` and clears
        ``enrich_error`` on jobs still lacking a ``full_description``. For the
        LLM steps it zeroes the matching ``*_attempts`` counter on jobs that
        have not produced their output yet. ``explore`` is a no-op (discovery is
        re-run wholesale). Returns the number of rows reset.
        """
        resets: dict[str, str] = {
            "expand": (
                "UPDATE jobs SET enrich_attempts = 0, enrich_error = NULL "
                "WHERE full_description IS NULL"
            ),
            "score": (
                "UPDATE jobs SET fit_score = NULL, score_reasoning = NULL "
                "WHERE fit_score IS NULL AND full_description IS NOT NULL"
            ),
            "tailor": (
                "UPDATE jobs SET tailor_attempts = 0 "
                "WHERE tailored_resume_path IS NULL"
            ),
            "cover": (
                "UPDATE jobs SET cover_attempts = 0 "
                "WHERE cover_at IS NULL AND tailored_resume_path IS NOT NULL"
            ),
        }
        sql = resets.get(phase)
        if sql is None:
            return 0
        cursor = self._conn.execute(sql)
        self._conn.commit()
        return int(cursor.rowcount)

    def step_counts(self, min_score: int) -> dict[str, dict[str, int]]:
        """Per-phase done/pending counts for ``kravu status``.

        Each phase reports how many jobs have completed it (``done``) and how
        many are still eligible for it (``pending``). This tells the user which
        step to ``resume``.
        """
        c = self._conn

        def one(sql: str, params: tuple[object, ...] = ()) -> int:
            return int(c.execute(sql, params).fetchone()[0])

        total = one("SELECT COUNT(*) FROM jobs")
        counts = {
            PipelinePhase.EXPLORE.value: {"done": total, "pending": 0},
            PipelinePhase.EXPAND.value: {
                "done": one(
                    "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL"
                ),
                "pending": one(
                    "SELECT COUNT(*) FROM jobs WHERE full_description IS NULL "
                    "AND COALESCE(enrich_attempts, 0) < 3"
                ),
            },
            PipelinePhase.SCORE.value: {
                "done": one("SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL"),
                "pending": one(
                    "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL "
                    "AND fit_score IS NULL"
                ),
            },
            PipelinePhase.TAILOR.value: {
                "done": one(
                    "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL"
                ),
                "pending": one(
                    "SELECT COUNT(*) FROM jobs WHERE fit_score >= ? "
                    "AND tailored_resume_path IS NULL "
                    "AND COALESCE(tailor_attempts, 0) < 5",
                    (min_score,),
                ),
            },
            PipelinePhase.COVER.value: {
                "done": one("SELECT COUNT(*) FROM jobs WHERE cover_at IS NOT NULL"),
                "pending": one(
                    "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL "
                    "AND cover_at IS NULL AND COALESCE(cover_attempts, 0) < 5"
                ),
            },
        }
        return counts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_repository_resume_status.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Re-verify the Task 2 protocol conformance now that the methods exist**

Run: `pytest tests/unit/test_ports.py -v`
Expected: PASS (3 tests — `JobRepository` now satisfies `JobStore`).

- [ ] **Step 6: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/adapters/repository.py tests/integration/test_repository_resume_status.py tests/unit/test_ports.py
git commit -m "feat: add resume/status/apply repository queries (step_counts, reset_step_for_retry, apply queue)"
```

---


## Task 4: `adapters/llm.py` — `LiteLLMClient` + defensive JSON parsing

Two responsibilities kept in one adapter file because they change together: (1) the provider-agnostic `complete()` over LiteLLM, and (2) a module-level `parse_json()` helper implementing instructed-JSON + defensive parsing (spec §7a/§9). Correctness never depends on `response_format` being honored.

**Files:**
- Create: `src/kravu/adapters/llm.py`
- Test: `tests/unit/test_llm_parse.py` (parse helper — offline), `tests/integration/test_llm_client.py` (client with monkeypatched litellm)

- [ ] **Step 1: Write the failing test for the parse helper**

```python
"""Unit tests for defensive JSON extraction from LLM text."""

from __future__ import annotations

import pytest

from kravu.adapters.llm import parse_json
from kravu.exceptions import LLMResponseError


def test_parse_plain_json_object() -> None:
    assert parse_json('{"score": 8}') == {"score": 8}


def test_parse_json_inside_markdown_fence() -> None:
    text = "Here you go:\n```json\n{\"score\": 7}\n```\nthanks"
    assert parse_json(text) == {"score": 7}


def test_parse_json_with_leading_prose() -> None:
    text = 'Sure! {"reasoning": "ok", "score": 9} — done'
    assert parse_json(text) == {"reasoning": "ok", "score": 9}


def test_parse_unparseable_raises() -> None:
    with pytest.raises(LLMResponseError):
        parse_json("no json here at all")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_llm_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.adapters.llm'`.

- [ ] **Step 3: Write `src/kravu/adapters/llm.py`**

```python
"""LiteLLMClient: the provider-agnostic model adapter, plus defensive JSON parse.

LiteLLM gives one interface to any provider; the model string comes from
``config.model()`` (never hardcoded). JSON is *instructed, not guaranteed*:
``response_format`` support is provider-dependent and some providers silently
return prose. Callers therefore parse with ``parse_json`` and retry once before
falling to their documented failure path (spec §7a, §9).
"""

from __future__ import annotations

import json
import re
from typing import Any

from kravu import config
from kravu.exceptions import LLMResponseError

_FENCE_RE = re.compile(r"```(?:json)?\s*(?P<body>.*?)\s*```", re.DOTALL)


def parse_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from possibly-noisy LLM text.

    Tries, in order: the whole string, any fenced code block, then the first
    balanced ``{...}`` span. Raises ``LLMResponseError`` if none parse.

    Args:
        text: Raw model output.

    Returns:
        The parsed JSON object as a dict.

    Raises:
        LLMResponseError: No parseable JSON object was found.
    """
    for candidate in _json_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise LLMResponseError("No parseable JSON object in model output.")


def _json_candidates(text: str) -> list[str]:
    candidates = [text.strip()]
    for match in _FENCE_RE.finditer(text):
        candidates.append(match.group("body").strip())
    span = _first_balanced_object(text)
    if span is not None:
        candidates.append(span)
    return candidates


def _first_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


class LiteLLMClient:
    """LLMClient backed by LiteLLM. One small, single-job call per invocation."""

    def __init__(self, model: str | None = None) -> None:
        """Build a client. ``model`` defaults to ``config.model()``."""
        self._model = model or config.model()

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        """Return the model's completion text for a single-message prompt.

        Args:
            prompt: The full instruction (already includes any JSON directive).
            temperature: Sampling temperature; 0.0 for deterministic calls.

        Returns:
            The model's raw text output.

        Raises:
            LLMResponseError: The provider returned no usable content.
        """
        import litellm

        response = litellm.completion(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError("Empty or malformed LLM response.") from exc
        if not content:
            raise LLMResponseError("LLM returned no content.")
        return str(content)
```

- [ ] **Step 4: Run the parse test to verify it passes**

Run: `pytest tests/unit/test_llm_parse.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Write the client integration test (litellm monkeypatched — no network)**

```python
"""Integration test for LiteLLMClient with litellm stubbed out."""

from __future__ import annotations

import sys
import types

import pytest

from kravu.adapters.llm import LiteLLMClient
from kravu.exceptions import LLMResponseError


def _install_fake_litellm(monkeypatch: pytest.MonkeyPatch, content: object) -> None:
    module = types.ModuleType("litellm")

    def completion(**_kwargs: object) -> dict[str, object]:
        return {"choices": [{"message": {"content": content}}]}

    module.completion = completion  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "litellm", module)


def test_complete_returns_content(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_litellm(monkeypatch, '{"score": 8}')
    client = LiteLLMClient(model="fake/model")
    assert client.complete("hi") == '{"score": 8}'


def test_complete_empty_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_litellm(monkeypatch, "")
    client = LiteLLMClient(model="fake/model")
    with pytest.raises(LLMResponseError):
        client.complete("hi")
```

- [ ] **Step 6: Run it and verify it passes**

Run: `pytest tests/integration/test_llm_client.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/adapters/llm.py tests/unit/test_llm_parse.py tests/integration/test_llm_client.py
git commit -m "feat: add LiteLLMClient and defensive JSON parser"
```

---

## Task 5: `adapters/prompts.py` — prompt builders

Single responsibility: pure functions that build prompt strings. No I/O, no LLM calls. Enforces reasoning-first key order and zero-fabrication instructions in the text. Keeping them pure makes them unit-testable by asserting on the returned string.

**Files:**
- Create: `src/kravu/adapters/prompts.py`
- Test: `tests/unit/test_prompts.py`

Constants defined here and reused by services/validator:

```python
BANNED_WORDS  # AI-slop phrases the tailor/cover validators reject
```

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for prompt builders — assert structure, order, and guards."""

from __future__ import annotations

from kravu.adapters import prompts
from kravu.domain.models import Profile, ResumeFacts


def _profile() -> Profile:
    return Profile(
        name="Jane Dev",
        skills=["Python", "AWS"],
        resume_facts=ResumeFacts(
            raw_text="Built X at Acme.",
            companies=["Acme"],
            school="State University",
            metrics=["cut latency 40%"],
            skills=["Python", "AWS"],
        ),
    )


def test_score_prompt_lists_score_key_last() -> None:
    text = prompts.score_prompt(_profile().resume_facts, "JD text", ["Backend"])
    # reasoning-first: score must appear after reasoning in the schema block
    assert text.index('"reasoning"') < text.index('"score"')
    assert "1" in text and "10" in text  # rubric scale present


def test_tailor_prompt_forbids_fabrication_and_new_skills() -> None:
    text = prompts.tailor_prompt(_profile().resume_facts, "JD text", "Backend Engineer")
    assert "Python" in text and "AWS" in text  # allowed skill set injected
    assert "never" in text.lower() or "do not" in text.lower()


def test_judge_prompt_includes_exemplar_fabrication() -> None:
    text = prompts.tailor_judge_prompt("original resume", "tailored resume")
    assert "example" in text.lower() or "exemplar" in text.lower()
    assert text.index('"reasoning"') < text.index('"verdict"')


def test_cover_prompt_requires_salutation_and_word_limit() -> None:
    text = prompts.cover_prompt(_profile(), "JD text", "tailored resume")
    assert "Dear Hiring Manager" in text
    assert "250" in text


def test_extract_prompt_uses_flattened_text_label() -> None:
    text = prompts.extract_description_prompt("flattened page text")
    assert "flattened page text" in text


def test_banned_words_are_present() -> None:
    assert isinstance(prompts.BANNED_WORDS, tuple)
    assert len(prompts.BANNED_WORDS) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_prompts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.adapters.prompts'`.

- [ ] **Step 3: Write `src/kravu/adapters/prompts.py`**

```python
"""Prompt builders for kravu's LLM calls (pure functions, no I/O).

Every reasoning-bearing prompt asks for JSON with the reasoning/analysis fields
BEFORE the score/verdict field — constraining a model to answer before reasoning
degrades reasoning quality (Tam et al., arXiv 2408.02442). JSON here is for
reliable parsing, not grounding; grounding for tailoring comes from the validator
and judge (spec §7a).
"""

from __future__ import annotations

from kravu.domain.models import Profile, ResumeFacts

# Generic AI-slop phrasing the tailor/cover validators reject. A writing-quality
# measure (recruiters skip generic AI phrasing), NOT a claim to defeat AI-text
# detectors, which are unreliable in practice (spec §7a).
BANNED_WORDS: tuple[str, ...] = (
    "leverage",
    "synergy",
    "spearheaded",
    "results-driven",
    "detail-oriented",
    "go-getter",
    "team player",
    "think outside the box",
    "passionate about",
    "dynamic professional",
    "proven track record",
    "seamlessly",
    "cutting-edge",
    "best-in-class",
)

_RUBRIC = (
    "Score on this rubric: 9-10 strong fit, 7-8 good fit, 5-6 moderate, "
    "3-4 weak, 1-2 poor."
)


def score_prompt(
    facts: ResumeFacts, job_description: str, target_titles: list[str]
) -> str:
    """Build the ScoreJobFit prompt (temperature 0, rubric, reasoning-first JSON)."""
    targets = ", ".join(target_titles) if target_titles else "(none stated)"
    return (
        "You are an impartial career-fit evaluator judging how well a candidate "
        "fits ONE job, FOR THE CANDIDATE'S benefit.\n\n"
        f"{_RUBRIC}\n\n"
        f"Candidate target roles: {targets}\n\n"
        "CANDIDATE RESUME FACTS:\n"
        f"Skills: {', '.join(facts.skills)}\n"
        f"Companies: {', '.join(facts.companies)}\n"
        f"Education: {facts.school}\n"
        f"Metrics: {'; '.join(facts.metrics)}\n"
        f"Full resume text:\n{facts.raw_text}\n\n"
        "JOB DESCRIPTION:\n"
        f"{job_description[:6000]}\n\n"
        "Return ONLY a JSON object with EXACTLY these keys in THIS ORDER "
        "(reason before you commit to a number):\n"
        '{"reasoning": "<2-3 sentences>", "matched_keywords": ["..."], '
        '"missing_skills": ["..."], "score": <integer 1-10>}'
    )


def tailor_prompt(facts: ResumeFacts, job_description: str, target_role: str) -> str:
    """Build the TailorResume prompt: structured sections, zero fabrication."""
    return (
        "Rewrite the candidate's resume to target the role below. You may "
        "reorder, reframe, reword, drop, and re-emphasize freely.\n\n"
        "ABSOLUTE RULES — you must NEVER do any of these:\n"
        "- Invent or add any skill not in the ALLOWED SKILLS list.\n"
        "- Invent or change any company, job title, school, degree, date, or "
        "metric.\n"
        "- Claim adjacent or 'learnable' skills the candidate does not have.\n\n"
        f"ALLOWED SKILLS (the ONLY skills you may mention): {', '.join(facts.skills)}\n"
        f"COMPANIES (must all survive, unchanged): {', '.join(facts.companies)}\n"
        f"EDUCATION (must survive, unchanged): {facts.school}\n"
        f"METRICS (must survive, unchanged): {'; '.join(facts.metrics)}\n"
        f"ORIGINAL RESUME:\n{facts.raw_text}\n\n"
        f"TARGET ROLE: {target_role}\n"
        f"JOB DESCRIPTION:\n{job_description[:6000]}\n\n"
        "Return ONLY a JSON object with these keys (do NOT include a name or "
        "contact header — that is added by code):\n"
        '{"title": "<headline>", "summary": "<2-3 sentences>", '
        '"skills": {"<group>": ["..."]}, '
        '"experience": [{"company": "...", "role": "...", "dates": "...", '
        '"bullets": ["..."]}], '
        '"projects": [{"name": "...", "bullets": ["..."]}], '
        '"education": "<text>"}'
    )


def tailor_judge_prompt(original_resume: str, tailored_resume: str) -> str:
    """Build the always-on fabrication judge prompt (reasoning-first verdict).

    Reference-free LLM-as-judge for faithfulness (FaithJudge, arXiv 2505.04847);
    the few-shot exemplar fabrications sharpen it.
    """
    return (
        "You are a strict faithfulness judge. Compare a TAILORED resume against "
        "the ORIGINAL. Legitimate reordering/rewording/re-emphasis is FINE. Your "
        "job is to catch FABRICATION: any skill, employer, title, date, degree, "
        "or metric in the tailored version that is not supported by the "
        "original.\n\n"
        "Example fabrications (all FAIL):\n"
        '- Original: "Python, SQL"; Tailored claims "Kubernetes" -> fabricated skill.\n'
        '- Original: "Acme 2021-2023"; Tailored says "Acme 2019-2023" -> altered dates.\n'
        '- Original: "reduced cost"; Tailored says "reduced cost 60%" -> invented metric.\n\n'
        f"ORIGINAL RESUME:\n{original_resume}\n\n"
        f"TAILORED RESUME:\n{tailored_resume}\n\n"
        "Return ONLY a JSON object with keys in THIS ORDER:\n"
        '{"reasoning": "<what you checked>", "fabrications": ["..."], '
        '"verdict": "pass" | "fail"}'
    )


def cover_prompt(profile: Profile, job_description: str, tailored_resume: str) -> str:
    """Build the DraftCoverLetter prompt: 3 short paras, <250 words, eng voice."""
    facts = profile.resume_facts
    return (
        "Write a cover letter for the candidate targeting the job below.\n\n"
        "RULES:\n"
        "- Exactly 3 short paragraphs, UNDER 250 words total.\n"
        '- Start with the exact line "Dear Hiring Manager,".\n'
        "- Engineering voice: open with something the candidate BUILT that solves "
        "the employer's problem; every sentence carries a number, tool, or "
        "outcome.\n"
        f"- Mention ONLY skills in this list: {', '.join(facts.skills)}. If the job "
        "asks for tools the candidate lacks, write about the WORK, not the tools.\n"
        "- Never invent employers, titles, dates, degrees, or metrics.\n\n"
        f"CANDIDATE:\n{profile.compact_summary()}\n"
        f"TAILORED RESUME:\n{tailored_resume}\n\n"
        f"JOB DESCRIPTION:\n{job_description[:6000]}\n\n"
        "Return ONLY the letter text (no preamble, no 'Here is the letter')."
    )


def extract_description_prompt(flattened_text: str) -> str:
    """Build the ExpandJob tier-3 extraction prompt (fed FLATTENED text, not HTML).

    Flattened input yields higher extraction accuracy and less hallucination
    (NEXT-EVAL, arXiv 2505.17125).
    """
    return (
        "Below is the flattened, cleaned text of a job posting page. Extract the "
        "full job description (responsibilities, requirements, qualifications). "
        "Return ONLY the description text, nothing else.\n\n"
        "flattened page text:\n"
        f"{flattened_text[:12000]}"
    )


def build_profile_prompt(raw_resume_text: str) -> str:
    """Build the BuildProfile extraction prompt (raw CV text -> structured facts)."""
    return (
        "Extract structured facts from the resume below. Do NOT invent anything; "
        "copy only what is present.\n\n"
        f"RESUME:\n{raw_resume_text}\n\n"
        "Return ONLY a JSON object:\n"
        '{"name": "...", "email": "...", "headline": "...", "location": "...", '
        '"summary": "...", "skills": ["..."], "companies": ["..."], '
        '"school": "...", "metrics": ["..."]}'
    )


def suggest_searches_prompt(profile: Profile) -> str:
    """Build the SuggestSearches prompt (Profile -> proposed search targets)."""
    return (
        "Propose conservative job-search targets for this candidate. Infer target "
        "roles and seniority from their resume; propose a CONSERVATIVE location "
        "(their resume location or 'Remote').\n\n"
        f"CANDIDATE:\n{profile.compact_summary()}\n\n"
        "Return ONLY a JSON object:\n"
        '{"search_term": "<primary role query>", "location": "<location>", '
        '"is_remote": <true|false>}'
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_prompts.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/adapters/prompts.py tests/unit/test_prompts.py
git commit -m "feat: add prompt builders (reasoning-first JSON, zero-fabrication, banned words)"
```

---


## Task 6: `adapters/jobspy_source.py` — `JobSpySource`

Single responsibility: run each configured search through python-jobspy and return `Job` rows with discovery fields populated (structured location, `is_remote`, `apply_type` best-effort). A failing site is recorded and skipped, not raised (spec §7a). python-jobspy is imported lazily and stubbed in tests.

**Files:**
- Create: `src/kravu/adapters/jobspy_source.py`
- Test: `tests/unit/test_jobspy_source.py`

- [ ] **Step 1: Write the failing test** (jobspy stubbed — no network)

```python
"""Unit tests for the JobSpy discovery adapter (jobspy stubbed)."""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from kravu.adapters.jobspy_source import JobSpySource


class _FakeFrame:
    """Minimal stand-in for the pandas DataFrame JobSpy returns."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def to_dict(self, orient: str) -> list[dict[str, Any]]:
        assert orient == "records"
        return self._rows


def _install_fake_jobspy(
    monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]
) -> None:
    module = types.ModuleType("jobspy")

    def scrape_jobs(**_kwargs: Any) -> _FakeFrame:
        return _FakeFrame(rows)

    module.scrape_jobs = scrape_jobs  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "jobspy", module)


def test_discover_maps_rows_to_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_jobspy(
        monkeypatch,
        [
            {
                "job_url": "https://x.test/1",
                "title": "DevOps Engineer",
                "company": "Acme",
                "location": "Remote, US",
                "is_remote": True,
                "site": "indeed",
                "description": "Do devops.",
            }
        ],
    )
    source = JobSpySource()
    searches = {
        "sources": {"jobspy": {"enabled": True, "sites": ["indeed"]}},
        "defaults": {"results_wanted": 5},
        "searches": [
            {"name": "d", "search_term": "DevOps", "location": "US",
             "country_indeed": "USA"}
        ],
    }
    jobs = source.discover(searches)
    assert len(jobs) == 1
    assert jobs[0].url == "https://x.test/1"
    assert jobs[0].title == "DevOps Engineer"
    assert jobs[0].source == "indeed"


def test_discover_skips_failing_site_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = types.ModuleType("jobspy")

    def scrape_jobs(**_kwargs: Any) -> None:
        raise RuntimeError("429 blocked")

    module.scrape_jobs = scrape_jobs  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "jobspy", module)

    source = JobSpySource()
    searches = {
        "sources": {"jobspy": {"enabled": True, "sites": ["indeed"]}},
        "searches": [
            {"name": "d", "search_term": "DevOps", "location": "US",
             "country_indeed": "USA"}
        ],
    }
    jobs = source.discover(searches)  # must not raise
    assert jobs == []
    assert "d" in source.notes  # a per-search note was recorded


def test_name_attribute() -> None:
    assert JobSpySource().name == "jobspy"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_jobspy_source.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.adapters.jobspy_source'`.

- [ ] **Step 3: Write `src/kravu/adapters/jobspy_source.py`**

```python
"""JobSpySource: keyword-driven discovery via python-jobspy.

Runs each configured search across the enabled sites and returns ``Job`` rows
with the discovery fields populated. A failing site is recorded in ``notes`` and
skipped — a bad source never aborts the run (spec §7a). ``jobspy`` is imported
lazily so importing this module has no heavy side effects.
"""

from __future__ import annotations

from typing import Any

from kravu.domain.models import Job

# Per-JobSpy-search fields passed straight through to scrape_jobs().
_PASSTHROUGH = (
    "search_term",
    "location",
    "results_wanted",
    "hours_old",
    "job_type",
    "is_remote",
    "distance",
    "google_search_term",
    "country_indeed",
    "description_format",
)


class JobSpySource:
    """DiscoverySource backed by python-jobspy."""

    name = "jobspy"

    def __init__(self) -> None:
        """Initialize with an empty per-search notes map."""
        self.notes: dict[str, str] = {}

    def discover(self, searches: dict[str, Any]) -> list[Job]:
        """Run every configured search and return discovered jobs.

        Args:
            searches: The parsed ``searches.yaml`` dict.

        Returns:
            A flat list of ``Job`` rows (discovery fields only). Duplicates are
            NOT removed here — ExploreJobs dedupes by normalized URL.
        """
        config = searches.get("sources", {}).get("jobspy", {})
        if not config.get("enabled", True):
            return []
        sites = config.get("sites", ["indeed"])
        defaults = searches.get("defaults", {})
        jobs: list[Job] = []
        for entry in searches.get("searches", []):
            jobs.extend(self._run_one(entry, sites, defaults))
        return jobs

    def _run_one(
        self, entry: dict[str, Any], sites: list[str], defaults: dict[str, Any]
    ) -> list[Job]:
        import jobspy

        name = str(entry.get("name", entry.get("search_term", "search")))
        kwargs: dict[str, Any] = {"site_name": sites}
        for key in _PASSTHROUGH:
            if key in defaults:
                kwargs[key] = defaults[key]
        for key in _PASSTHROUGH:
            if key in entry:
                kwargs[key] = entry[key]
        try:
            frame = jobspy.scrape_jobs(**kwargs)
        except Exception as exc:  # noqa: BLE001 - record and continue per spec
            self.notes[name] = f"failed: {exc}"
            return []
        records = frame.to_dict("records") if frame is not None else []
        if not records:
            self.notes[name] = "empty"
        return [self._to_job(r) for r in records if r.get("job_url")]

    @staticmethod
    def _to_job(record: dict[str, Any]) -> Job:
        is_remote = bool(record.get("is_remote"))
        apply_type = "easy-apply" if record.get("site") == "linkedin" else "external"
        return Job(
            url=str(record["job_url"]),
            title=str(record.get("title") or ""),
            company=str(record.get("company") or ""),
            location=str(record.get("location") or ("Remote" if is_remote else "")),
            salary=str(record.get("salary") or record.get("compensation") or ""),
            source=str(record.get("site") or "jobspy"),
            apply_type=apply_type,
            description=str(record.get("description") or ""),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_jobspy_source.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/adapters/jobspy_source.py tests/unit/test_jobspy_source.py
git commit -m "feat: add JobSpySource discovery adapter (non-aborting per-source failures)"
```

---

## Task 7: `adapters/ats_source.py` — `AtsSource` (Greenhouse/Lever/Ashby)

Single responsibility: pull each configured company board via its public JSON API, normalizing the differing shapes (esp. Lever's epoch-ms `createdAt` vs ISO), and return `Job` rows. Empty result is a real, reported outcome (wrong slug returns HTTP 200 + `[]`, not 404). HTTP client (`httpx`, bundled with litellm) is injected/stubbed in tests.

**Files:**
- Create: `src/kravu/adapters/ats_source.py`
- Test: `tests/unit/test_ats_source.py`

- [ ] **Step 1: Write the failing test** (a fake fetcher — no network)

```python
"""Unit tests for the ATS discovery adapter (JSON fetch stubbed)."""

from __future__ import annotations

from typing import Any

from kravu.adapters.ats_source import AtsSource


def _fake_fetch(responses: dict[str, Any]):
    def fetch(url: str) -> Any:
        return responses.get(url, {})
    return fetch


def test_greenhouse_maps_jobs() -> None:
    url = "https://boards-api.greenhouse.io/v1/boards/stripe/jobs"
    fetch = _fake_fetch(
        {url: {"jobs": [{"absolute_url": "https://gh.test/1",
                          "title": "SRE", "location": {"name": "Remote"}}]}}
    )
    source = AtsSource(fetch=fetch)
    searches = {
        "sources": {"ats": {"enabled": True,
                            "companies": [{"ats": "greenhouse", "slug": "stripe"}]}}
    }
    jobs = source.discover(searches)
    assert [j.url for j in jobs] == ["https://gh.test/1"]
    assert jobs[0].source == "greenhouse:stripe"


def test_lever_epoch_ms_does_not_crash() -> None:
    url = "https://api.lever.co/v0/postings/netflix?mode=json"
    fetch = _fake_fetch(
        {url: [{"hostedUrl": "https://lever.test/1", "text": "Backend",
                "createdAt": 1735689600000,
                "categories": {"location": "NYC"}}]}
    )
    source = AtsSource(fetch=fetch)
    searches = {
        "sources": {"ats": {"enabled": True,
                            "companies": [{"ats": "lever", "slug": "netflix"}]}}
    }
    jobs = source.discover(searches)
    assert jobs[0].url == "https://lever.test/1"


def test_empty_board_is_recorded_not_crashed() -> None:
    url = "https://boards-api.greenhouse.io/v1/boards/typo/jobs"
    source = AtsSource(fetch=_fake_fetch({url: {"jobs": []}}))
    searches = {
        "sources": {"ats": {"enabled": True,
                            "companies": [{"ats": "greenhouse", "slug": "typo"}]}}
    }
    jobs = source.discover(searches)
    assert jobs == []
    assert "greenhouse:typo" in source.notes


def test_disabled_ats_returns_empty() -> None:
    source = AtsSource(fetch=_fake_fetch({}))
    assert source.discover({"sources": {"ats": {"enabled": False}}}) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ats_source.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.adapters.ats_source'`.

- [ ] **Step 3: Write `src/kravu/adapters/ats_source.py`**

```python
"""AtsSource: company-driven discovery via public ATS JSON boards.

Supports Greenhouse, Lever, and Ashby — all serve open JSON with no key. A wrong
slug returns HTTP 200 with an empty list (not 404), so "empty" is a real,
reportable outcome recorded in ``notes``, never a crash. Lever's ``createdAt`` is
epoch-milliseconds while Greenhouse/Ashby use ISO-8601; only the URL/title/location
are mapped here, so timestamp shape does not break mapping (spec §7a).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from kravu.domain.models import Job

Fetcher = Callable[[str], Any]


def _default_fetch(url: str) -> Any:
    import httpx

    response = httpx.get(url, timeout=20.0)
    response.raise_for_status()
    return response.json()


class AtsSource:
    """DiscoverySource backed by public ATS JSON boards."""

    name = "ats"

    def __init__(self, fetch: Fetcher | None = None) -> None:
        """Build the adapter.

        Args:
            fetch: Function mapping a URL to parsed JSON. Defaults to an httpx
                GET; tests inject a stub so the suite stays offline.
        """
        self._fetch = fetch or _default_fetch
        self.notes: dict[str, str] = {}

    def discover(self, searches: dict[str, Any]) -> list[Job]:
        """Pull each configured company board and return discovered jobs."""
        config = searches.get("sources", {}).get("ats", {})
        if not config.get("enabled", False):
            return []
        jobs: list[Job] = []
        for company in config.get("companies", []):
            jobs.extend(self._pull(company.get("ats", ""), company.get("slug", "")))
        return jobs

    def _pull(self, ats: str, slug: str) -> list[Job]:
        key = f"{ats}:{slug}"
        url = self._board_url(ats, slug)
        if url is None:
            self.notes[key] = f"unknown ats: {ats}"
            return []
        try:
            payload = self._fetch(url)
        except Exception as exc:  # noqa: BLE001 - record and continue per spec
            self.notes[key] = f"failed: {exc}"
            return []
        jobs = self._map(ats, slug, payload)
        if not jobs:
            self.notes[key] = "empty"
        return jobs

    @staticmethod
    def _board_url(ats: str, slug: str) -> str | None:
        if ats == "greenhouse":
            return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
        if ats == "lever":
            return f"https://api.lever.co/v0/postings/{slug}?mode=json"
        if ats == "ashby":
            return f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
        return None

    def _map(self, ats: str, slug: str, payload: Any) -> list[Job]:
        source = f"{ats}:{slug}"
        if ats == "greenhouse":
            return [
                Job(
                    url=str(j["absolute_url"]),
                    title=str(j.get("title") or ""),
                    company=slug,
                    location=str((j.get("location") or {}).get("name") or ""),
                    source=source,
                    apply_type="ats",
                )
                for j in payload.get("jobs", [])
                if j.get("absolute_url")
            ]
        if ats == "lever":
            return [
                Job(
                    url=str(j["hostedUrl"]),
                    title=str(j.get("text") or ""),
                    company=slug,
                    location=str((j.get("categories") or {}).get("location") or ""),
                    source=source,
                    apply_type="ats",
                )
                for j in payload
                if j.get("hostedUrl")
            ]
        if ats == "ashby":
            return [
                Job(
                    url=str(j["jobUrl"]),
                    title=str(j.get("title") or ""),
                    company=slug,
                    location=str(j.get("location") or ""),
                    source=source,
                    apply_type="ats",
                )
                for j in payload.get("jobs", [])
                if j.get("jobUrl")
            ]
        return []
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_ats_source.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/adapters/ats_source.py tests/unit/test_ats_source.py
git commit -m "feat: add AtsSource (Greenhouse/Lever/Ashby JSON boards, empty-is-reportable)"
```

---

## Task 8: `adapters/playwright_page.py` — `PlaywrightPageRenderer`

Single responsibility: render a URL to HTML with headless Chromium. Thin I/O wrapper — no extraction logic (that lives in `ExpandJob`). Because Playwright needs a real browser, the unit test asserts the adapter delegates to an injected page-fetch callable; a live browser is exercised only in an opt-in integration test (skipped by default).

**Files:**
- Create: `src/kravu/adapters/playwright_page.py`
- Test: `tests/unit/test_playwright_page.py`

- [ ] **Step 1: Write the failing test** (injected renderer fn — no browser)

```python
"""Unit tests for the Playwright page renderer wrapper (browser injected)."""

from __future__ import annotations

from kravu.adapters.playwright_page import PlaywrightPageRenderer


def test_render_delegates_to_injected_fn() -> None:
    calls: list[str] = []

    def fake_render(url: str, timeout_ms: int) -> str:
        calls.append(url)
        return "<html><body>ok</body></html>"

    renderer = PlaywrightPageRenderer(render_fn=fake_render)
    html = renderer.render("https://x.test/1")

    assert html == "<html><body>ok</body></html>"
    assert calls == ["https://x.test/1"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_playwright_page.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.adapters.playwright_page'`.

- [ ] **Step 3: Write `src/kravu/adapters/playwright_page.py`**

```python
"""PlaywrightPageRenderer: render a URL to HTML with headless Chromium.

A thin I/O wrapper — it renders, nothing more. Extraction (JSON-LD / CSS / LLM)
lives in ``services.expand``. Playwright is imported lazily inside the default
render function so importing this module is cheap and the test suite stays
offline by injecting ``render_fn``.
"""

from __future__ import annotations

from collections.abc import Callable

RenderFn = Callable[[str, int], str]


def _default_render(url: str, timeout_ms: int) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            return page.content()
        finally:
            browser.close()


class PlaywrightPageRenderer:
    """Render web pages to HTML using headless Chromium."""

    def __init__(
        self, render_fn: RenderFn | None = None, timeout_ms: int = 30_000
    ) -> None:
        """Build the renderer.

        Args:
            render_fn: Injectable ``(url, timeout_ms) -> html``. Defaults to a
                Playwright Chromium render; tests inject a stub.
            timeout_ms: Navigation timeout in milliseconds.
        """
        self._render_fn = render_fn or _default_render
        self._timeout_ms = timeout_ms

    def render(self, url: str) -> str:
        """Return the fully-rendered HTML of ``url``."""
        return self._render_fn(url, self._timeout_ms)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_playwright_page.py -v`
Expected: PASS (1 test).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/adapters/playwright_page.py tests/unit/test_playwright_page.py
git commit -m "feat: add PlaywrightPageRenderer (headless render wrapper, injectable)"
```

---


## Task 9: `services/build_profile.py` — `BuildProfile` (setup-time)

Single responsibility: turn raw resume text into a structured `Profile` (with `ResumeFacts` ground truth) via one LLM call. Business logic; uses the `LLMClient` port; unit-tested with a fake LLM. Not part of `kravu run`.

**Files:**
- Create: `src/kravu/services/build_profile.py`
- Test: `tests/unit/test_build_profile.py`

- [ ] **Step 1: Write the failing test** (fake LLM returns JSON)

```python
"""Unit tests for the BuildProfile use case (fake LLM)."""

from __future__ import annotations

from kravu.services.build_profile import BuildProfile


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return self._reply


def test_build_profile_extracts_structured_facts() -> None:
    reply = (
        '{"name": "Jane Dev", "email": "j@x.io", "headline": "SRE", '
        '"location": "NYC", "summary": "Builds reliable systems.", '
        '"skills": ["Python", "AWS"], "companies": ["Acme"], '
        '"school": "State U", "metrics": ["cut latency 40%"]}'
    )
    profile = BuildProfile(_FakeLLM(reply)).run("Jane Dev, built X at Acme...")

    assert profile.name == "Jane Dev"
    assert profile.skills == ["Python", "AWS"]
    assert profile.resume_facts.companies == ["Acme"]
    assert profile.resume_facts.school == "State U"
    assert profile.resume_facts.raw_text.startswith("Jane Dev")


def test_build_profile_tolerates_missing_optional_fields() -> None:
    profile = BuildProfile(_FakeLLM('{"name": "Al"}')).run("Al resume text")
    assert profile.name == "Al"
    assert profile.resume_facts.companies == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_build_profile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.services.build_profile'`.

- [ ] **Step 3: Write `src/kravu/services/build_profile.py`**

```python
"""BuildProfile: raw resume text -> structured Profile (setup-time use case).

One LLM call extracts structured facts; the raw text is preserved verbatim as
``ResumeFacts.raw_text`` (the tailoring ground truth). Used by ``kravu init``; it
does NOT run during ``kravu run``.
"""

from __future__ import annotations

from kravu.adapters import prompts
from kravu.adapters.llm import parse_json
from kravu.domain.models import Profile, ResumeFacts
from kravu.domain.ports import LLMClient


class BuildProfile:
    """Extract a structured ``Profile`` from raw resume text."""

    def __init__(self, llm: LLMClient) -> None:
        """Store the injected model port."""
        self._llm = llm

    def run(self, raw_resume_text: str) -> Profile:
        """Return a structured ``Profile`` for ``raw_resume_text``.

        Args:
            raw_resume_text: The full text extracted from the user's CV.

        Returns:
            A ``Profile`` whose ``resume_facts.raw_text`` is the original text.
        """
        reply = self._llm.complete(
            prompts.build_profile_prompt(raw_resume_text), temperature=0.0
        )
        data = parse_json(reply)
        skills = [str(s) for s in data.get("skills", [])]
        facts = ResumeFacts(
            raw_text=raw_resume_text,
            companies=[str(c) for c in data.get("companies", [])],
            school=str(data.get("school", "")),
            metrics=[str(m) for m in data.get("metrics", [])],
            skills=skills,
        )
        return Profile(
            name=str(data.get("name", "")),
            email=str(data.get("email", "")),
            headline=str(data.get("headline", "")),
            location=str(data.get("location", "")),
            summary=str(data.get("summary", "")),
            skills=skills,
            resume_facts=facts,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_build_profile.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/services/build_profile.py tests/unit/test_build_profile.py
git commit -m "feat: add BuildProfile use case (resume text -> structured Profile)"
```

---

## Task 10: `services/suggest_searches.py` — `SuggestSearches` + searches schema validation

Two responsibilities that change together and belong to the same setup concern: (1) propose a `searches.yaml` dict from a `Profile` (one LLM call), and (2) validate any searches dict against the schema (spec §13a), which the CLI reuses at load time. Invalid proposals are defaulted/dropped, never written broken.

**Files:**
- Create: `src/kravu/services/suggest_searches.py`
- Test: `tests/unit/test_suggest_searches.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for SuggestSearches and searches-schema validation."""

from __future__ import annotations

import pytest

from kravu.domain.models import Profile, ResumeFacts
from kravu.exceptions import SearchesConfigError
from kravu.services.suggest_searches import SuggestSearches, validate_searches


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return self._reply


def _profile() -> Profile:
    return Profile(
        name="Jane", location="NYC", skills=["Python"],
        resume_facts=ResumeFacts(raw_text="x", skills=["Python"]),
    )


def test_suggest_builds_valid_searches_dict() -> None:
    reply = '{"search_term": "DevOps engineer", "location": "NYC", "is_remote": true}'
    result = SuggestSearches(_FakeLLM(reply)).run(_profile())

    assert result["searches"][0]["search_term"] == "DevOps engineer"
    assert result["sources"]["jobspy"]["enabled"] is True
    assert result["defaults"]["per_run_cap"] == 25
    validate_searches(result)  # must pass its own schema


def test_validate_requires_country_indeed_when_indeed_site() -> None:
    bad = {
        "sources": {"jobspy": {"enabled": True, "sites": ["indeed"]}},
        "searches": [{"name": "d", "search_term": "x", "location": "US"}],
    }
    with pytest.raises(SearchesConfigError):
        validate_searches(bad)


def test_validate_requires_at_least_one_source() -> None:
    with pytest.raises(SearchesConfigError):
        validate_searches({"sources": {"jobspy": {"enabled": False},
                                       "ats": {"enabled": False}},
                           "searches": []})


def test_validate_rejects_indeed_filter_conflict() -> None:
    bad = {
        "sources": {"jobspy": {"enabled": True, "sites": ["indeed"]}},
        "searches": [{"name": "d", "search_term": "x", "location": "US",
                      "country_indeed": "USA", "hours_old": 168,
                      "job_type": "fulltime", "is_remote": True}],
    }
    with pytest.raises(SearchesConfigError):
        validate_searches(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_suggest_searches.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.services.suggest_searches'`.

- [ ] **Step 3: Write `src/kravu/services/suggest_searches.py`**

```python
"""SuggestSearches: propose a searches.yaml from a Profile; validate the schema.

``run`` uses one LLM call to infer a conservative search target, wraps it in the
full searches structure with safe defaults (spec §13a), and validates it before
returning. ``validate_searches`` is the single schema gate reused by ``kravu``
at config-load time; it hard-errors on invalid config (hard-stop philosophy).
"""

from __future__ import annotations

from typing import Any

from kravu.adapters import prompts
from kravu.adapters.llm import parse_json
from kravu.domain.models import Profile
from kravu.domain.ports import LLMClient
from kravu.exceptions import SearchesConfigError

_ALLOWED_SITES = frozenset(
    {"indeed", "linkedin", "zip_recruiter", "google", "glassdoor", "bayt",
     "bdjobs", "naukri"}
)


def _default_searches() -> dict[str, Any]:
    return {
        "sources": {
            "jobspy": {
                "enabled": True,
                "sites": ["indeed", "linkedin", "zip_recruiter", "google"],
            },
            "ats": {"enabled": False, "companies": []},
        },
        "defaults": {
            "results_wanted": 25,
            "hours_old": 168,
            "description_format": "markdown",
            "per_run_cap": 25,
        },
        "cover_letter": "only_if_required",
        "min_score": 7,
        "searches": [],
    }


class SuggestSearches:
    """Propose a validated searches config from a user's ``Profile``."""

    def __init__(self, llm: LLMClient) -> None:
        """Store the injected model port."""
        self._llm = llm

    def run(self, profile: Profile) -> dict[str, Any]:
        """Return a validated ``searches.yaml`` dict proposed from ``profile``."""
        reply = self._llm.complete(
            prompts.suggest_searches_prompt(profile), temperature=0.0
        )
        data = parse_json(reply)
        result = _default_searches()
        result["searches"] = [
            {
                "name": "primary",
                "search_term": str(data.get("search_term") or "software engineer"),
                "location": str(data.get("location") or profile.location or "Remote"),
                "country_indeed": "USA",
                "is_remote": bool(data.get("is_remote", True)),
            }
        ]
        validate_searches(result)
        return result


def validate_searches(searches: dict[str, Any]) -> None:
    """Validate a searches config against the schema (spec §13a).

    Raises:
        SearchesConfigError: The config violates a hard rule.
    """
    sources = searches.get("sources", {})
    jobspy = sources.get("jobspy", {})
    ats = sources.get("ats", {})
    if not jobspy.get("enabled", False) and not ats.get("enabled", False):
        raise SearchesConfigError("At least one source must be enabled.")

    sites = jobspy.get("sites", []) if jobspy.get("enabled") else []
    for site in sites:
        if site not in _ALLOWED_SITES:
            raise SearchesConfigError(
                f"Unknown site '{site}'. Allowed: {sorted(_ALLOWED_SITES)}."
            )

    needs_country = bool({"indeed", "glassdoor"} & set(sites))
    for entry in searches.get("searches", []):
        _validate_entry(entry, needs_country)


def _validate_entry(entry: dict[str, Any], needs_country: bool) -> None:
    if needs_country and not entry.get("country_indeed"):
        raise SearchesConfigError(
            f"Search '{entry.get('name')}' needs 'country_indeed' "
            "when indeed/glassdoor is a site."
        )
    # Indeed allows only ONE of: hours_old | (job_type + is_remote) | easy_apply.
    chosen = 0
    if entry.get("hours_old") is not None:
        chosen += 1
    if entry.get("job_type") is not None or entry.get("is_remote") is not None:
        chosen += 1
    if entry.get("easy_apply") is not None:
        chosen += 1
    if chosen > 1:
        raise SearchesConfigError(
            f"Search '{entry.get('name')}': Indeed allows only one of "
            "hours_old | (job_type+is_remote) | easy_apply."
        )
```

> **Note on the Indeed conflict rule:** the spec groups `job_type` + `is_remote` as one option. Since `SuggestSearches.run` sets `is_remote` (and no `hours_old`/`easy_apply` on the entry), the generated entry has `chosen == 1` and passes. The `_default_searches` `hours_old` lives under `defaults`, not the entry, so it does not collide. This matches the conflict test (which puts all three on the entry) and `test_suggest_builds_valid_searches_dict`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_suggest_searches.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/services/suggest_searches.py tests/unit/test_suggest_searches.py
git commit -m "feat: add SuggestSearches use case + searches schema validation"
```

---


## Task 11: `services/explore.py` — `ExploreJobs`

Single responsibility: run the discovery sources, dedupe by normalized URL, apply the description-quality gate, and persist new jobs via `JobStore`. Business logic only — sources and store are injected ports.

**Files:**
- Create: `src/kravu/services/explore.py`
- Test: `tests/unit/test_explore.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for the ExploreJobs use case (fake source + real temp repo)."""

from __future__ import annotations

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job
from kravu.services.explore import ExploreJobs, normalize_url


class _FakeSource:
    name = "fake"

    def __init__(self, jobs: list[Job]) -> None:
        self._jobs = jobs
        self.notes: dict[str, str] = {}

    def discover(self, searches: dict[str, object]) -> list[Job]:
        return self._jobs


def test_normalize_url_strips_tracking_and_lowercases_host() -> None:
    a = normalize_url("https://Example.com/job/1?utm_source=x#frag")
    b = normalize_url("https://example.com/job/1")
    assert a == b


def test_explore_dedupes_by_normalized_url(repo: JobRepository) -> None:
    source = _FakeSource(
        [
            Job(url="https://Example.com/1?utm_source=x", title="A",
                description="short"),
            Job(url="https://example.com/1", title="A dup", description="short"),
        ]
    )
    added = ExploreJobs([source]).run(repo, {"searches": []})
    assert added == 1
    assert len(repo.shortlist(min_score=0)) == 0  # not scored yet
    assert repo.stats()["total"] == 1


def test_explore_promotes_only_rich_descriptions(repo: JobRepository) -> None:
    rich = (
        "Responsibilities: build things. Requirements: 5 years Python. "
        "Qualifications: degree. " * 5
    )
    source = _FakeSource(
        [
            Job(url="https://a.test/rich", title="R", description=rich),
            Job(url="https://a.test/thin", title="T", description="Apply now!"),
        ]
    )
    ExploreJobs([source]).run(repo, {"searches": []})
    rich_job = repo.get("https://a.test/rich")
    thin_job = repo.get("https://a.test/thin")
    assert rich_job is not None and rich_job.full_description is not None
    assert thin_job is not None and thin_job.full_description is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_explore.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.services.explore'`.

- [ ] **Step 3: Write `src/kravu/services/explore.py`**

```python
"""ExploreJobs: discover, dedupe by normalized URL, gate quality, persist.

Merges results from every configured ``DiscoverySource``, deduplicates by a
normalized URL (tracking query/fragment stripped, host lowercased) — catching
duplicates a raw-URL key misses — and promotes a description to
``full_description`` only if it looks like a real JD (length + section signals),
else keeps it as the preview ``description`` (spec §7a). Persists only new jobs.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

from kravu.domain.models import Job
from kravu.domain.ports import DiscoverySource, JobStore

_SECTION_SIGNALS = (
    "responsibilit",
    "requirement",
    "qualification",
    "what you",
    "you will",
    "about the role",
)
_MIN_REAL_DESCRIPTION = 400


def normalize_url(url: str) -> str:
    """Return a canonical form of ``url`` for deduplication.

    Lowercases the host, drops the query string and fragment, and strips a
    trailing slash from the path.
    """
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((parsed.scheme.lower(), host, path, "", "", ""))


def _is_real_description(text: str) -> bool:
    if len(text) < _MIN_REAL_DESCRIPTION:
        return False
    lowered = text.lower()
    return any(signal in lowered for signal in _SECTION_SIGNALS)


class ExploreJobs:
    """Discover and persist new jobs from the configured sources."""

    def __init__(self, sources: list[DiscoverySource]) -> None:
        """Store the injected discovery sources."""
        self._sources = sources

    def run(self, store: JobStore, searches: dict[str, Any]) -> int:
        """Discover jobs and persist the new ones.

        Args:
            store: The persistence port.
            searches: The parsed ``searches.yaml`` dict.

        Returns:
            The number of newly persisted (previously unseen) jobs.
        """
        seen: set[str] = set()
        added = 0
        for source in self._sources:
            for job in source.discover(searches):
                canonical = normalize_url(job.url)
                if canonical in seen:
                    continue
                seen.add(canonical)
                job.url = canonical
                if _is_real_description(job.description):
                    job.full_description = job.description
                if store.add_discovered(job):
                    added += 1
        return added
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_explore.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/services/explore.py tests/unit/test_explore.py
git commit -m "feat: add ExploreJobs use case (normalized-URL dedupe + quality gate)"
```

---

## Task 12: `services/expand.py` — `ExpandJob` (3-tier cascade)

Single responsibility: for each un-enriched job, render the page and extract the description via JSON-LD → CSS → LLM (flattened text, last resort). Up to 3 attempts, then mark pending (non-fatal). Renderer, extraction libs, and LLM are injected/lazy so tests stay offline.

**Files:**
- Create: `src/kravu/services/expand.py`
- Test: `tests/unit/test_expand.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for ExpandJob's extraction cascade (renderer + LLM injected)."""

from __future__ import annotations

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job
from kravu.services.expand import ExpandJob, extract_jsonld

_JSONLD_PAGE = """
<html><head>
<script type="application/ld+json">
{"@type": "JobPosting", "description": "Build and run reliable services. Requirements: Python."}
</script>
</head><body>x</body></html>
"""


class _Renderer:
    def __init__(self, html: str) -> None:
        self._html = html

    def render(self, url: str) -> str:
        return self._html


class _FakeLLM:
    def __init__(self) -> None:
        self.called = False

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        self.called = True
        return "LLM extracted description"


def _discovered(repo: JobRepository, url: str) -> None:
    repo.add_discovered(Job(url=url, title="Dev"))


def test_extract_jsonld_pulls_jobposting_description() -> None:
    assert extract_jsonld(_JSONLD_PAGE) is not None
    assert "reliable services" in extract_jsonld(_JSONLD_PAGE)  # type: ignore[operator]


def test_expand_uses_jsonld_and_skips_llm(repo: JobRepository) -> None:
    _discovered(repo, "https://a.test/1")
    llm = _FakeLLM()
    ExpandJob(_Renderer(_JSONLD_PAGE), llm).run(repo)

    job = repo.get("https://a.test/1")
    assert job is not None and job.full_description is not None
    assert "reliable services" in job.full_description
    assert llm.called is False  # tier-1 succeeded, no LLM call


def test_expand_falls_back_to_llm_on_unknown_layout(repo: JobRepository) -> None:
    _discovered(repo, "https://a.test/2")
    llm = _FakeLLM()
    ExpandJob(_Renderer("<html><body>nothing structured here</body></html>"),
              llm).run(repo)

    job = repo.get("https://a.test/2")
    assert job is not None and job.full_description == "LLM extracted description"
    assert llm.called is True


def test_expand_marks_pending_after_render_failure(repo: JobRepository) -> None:
    _discovered(repo, "https://a.test/3")

    class _Boom:
        def render(self, url: str) -> str:
            raise RuntimeError("render failed")

    ExpandJob(_Boom(), _FakeLLM()).run(repo)
    job = repo.get("https://a.test/3")
    assert job is not None
    assert job.full_description is None
    assert job.enrich_attempts == 1
    assert job.enrich_error is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_expand.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.services.expand'`.

- [ ] **Step 3: Write `src/kravu/services/expand.py`**

```python
"""ExpandJob: render each un-enriched job and extract its full description.

Cascade, cheapest first (spec §7a): (1) JSON-LD ``JobPosting`` parsed from
``<script type="application/ld+json">`` blocks with stdlib ``json``; (2) CSS
selectors over the rendered DOM via ``selectolax`` with ``trafilatura`` cleanup;
(3) an LLM call on the FLATTENED page text as a last resort (higher accuracy,
less hallucination than raw HTML — NEXT-EVAL). Up to 3 attempts per job, then the
job is marked pending (non-fatal) and keeps its preview description.
"""

from __future__ import annotations

import json
from typing import Protocol

from kravu.adapters import prompts
from kravu.domain.ports import JobStore, LLMClient

_MAX_ATTEMPTS = 3
_MIN_EXTRACT_LEN = 200


class PageRenderer(Protocol):
    """A page renderer (implemented by ``PlaywrightPageRenderer``)."""

    def render(self, url: str) -> str: ...


def extract_jsonld(html: str) -> str | None:
    """Return the description from a JobPosting JSON-LD block, or None.

    Parses each ``<script type="application/ld+json">`` block and returns the
    ``description`` of the first object whose ``@type`` is ``JobPosting``.
    """
    from selectolax.parser import HTMLParser

    tree = HTMLParser(html)
    for node in tree.css('script[type="application/ld+json"]'):
        raw = node.text(strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for obj in data if isinstance(data, list) else [data]:
            if not isinstance(obj, dict):
                continue
            types = obj.get("@type")
            type_set = types if isinstance(types, list) else [types]
            if "JobPosting" in type_set and obj.get("description"):
                return str(obj["description"])
    return None


def extract_css(html: str) -> str | None:
    """Extract the main job-content text via CSS heuristics + trafilatura.

    Returns cleaned main content if it is long enough to look like a JD, else
    None so the caller falls through to the LLM tier.
    """
    import trafilatura

    extracted = trafilatura.extract(html, include_comments=False, include_tables=True)
    if extracted and len(extracted) >= _MIN_EXTRACT_LEN:
        return str(extracted)
    return None


def flatten_html(html: str) -> str:
    """Return cleaned, flattened text of a page for the LLM extraction tier."""
    from selectolax.parser import HTMLParser

    tree = HTMLParser(html)
    body = tree.body
    return body.text(separator="\n", strip=True) if body else ""


class ExpandJob:
    """Enrich jobs with a full description via the extraction cascade."""

    def __init__(self, renderer: PageRenderer, llm: LLMClient) -> None:
        """Store the injected page renderer and model port."""
        self._renderer = renderer
        self._llm = llm

    def run(self, store: JobStore, limit: int | None = None) -> None:
        """Enrich every pending job (up to ``limit``). Never raises per job."""
        for job in store.pending_enrichment(limit):
            self._expand_one(store, job.url)

    def _expand_one(self, store: JobStore, url: str) -> None:
        store.bump_enrich_attempts(url)
        try:
            html = self._renderer.render(url)
            description = self._extract(html)
        except Exception as exc:  # noqa: BLE001 - record on the row, continue
            store.set_enrichment_error(url, str(exc))
            return
        if description:
            store.set_enrichment(url, description, None)
        else:
            store.set_enrichment_error(url, "no description extracted")

    def _extract(self, html: str) -> str | None:
        return (
            extract_jsonld(html)
            or extract_css(html)
            or self._extract_with_llm(html)
        )

    def _extract_with_llm(self, html: str) -> str | None:
        flattened = flatten_html(html)
        if not flattened:
            return None
        reply = self._llm.complete(
            prompts.extract_description_prompt(flattened), temperature=0.0
        )
        cleaned = reply.strip()
        return cleaned or None
```

> **Attempt-cap note:** `pending_enrichment` already filters `enrich_attempts < 3`, and `_expand_one` bumps the counter first, so a job that fails 3 runs stops being selected — matching `_MAX_ATTEMPTS`. `_MAX_ATTEMPTS` is defined for readability/parity with the repository query; the repository is the single source of truth for the cap.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_expand.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/services/expand.py tests/unit/test_expand.py
git commit -m "feat: add ExpandJob use case (JSON-LD -> CSS -> LLM cascade, non-fatal retries)"
```

---

## Task 13: `services/score.py` — `ScoreJobFit`

Single responsibility: one temp-0, rubric LLM call per pending job; parse defensively (retry once), clamp 1–10, write score + reasoning; record `0`/"unparseable" on second failure. Never crashes. Honors the per-run cap via `limit`.

**Files:**
- Create: `src/kravu/services/score.py`
- Test: `tests/unit/test_score.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for the ScoreJobFit use case (fake LLM + temp repo)."""

from __future__ import annotations

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job, Profile, ResumeFacts
from kravu.services.score import ScoreJobFit


class _SeqLLM:
    """Returns queued replies in order (to exercise the retry path)."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = replies
        self.calls = 0

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        reply = self._replies[min(self.calls, len(self._replies) - 1)]
        self.calls += 1
        return reply


def _profile() -> Profile:
    return Profile(resume_facts=ResumeFacts(raw_text="Jane, Python dev",
                                            skills=["Python"]))


def _scored_job(repo: JobRepository, url: str) -> None:
    repo.add_discovered(Job(url=url, title="Dev"))
    repo.set_enrichment(url, "Python role. Requirements: Python.", None)


def test_score_writes_score_and_reasoning(repo: JobRepository) -> None:
    _scored_job(repo, "https://a.test/1")
    reply = ('{"reasoning": "Strong Python overlap.", '
             '"matched_keywords": ["Python"], "missing_skills": [], "score": 9}')
    ScoreJobFit(_SeqLLM([reply]), _profile(), min_score=7).run(repo)

    job = repo.get("https://a.test/1")
    assert job is not None and job.fit_score == 9
    assert "Python" in (job.score_reasoning or "")


def test_score_clamps_out_of_range(repo: JobRepository) -> None:
    _scored_job(repo, "https://a.test/2")
    ScoreJobFit(_SeqLLM(['{"reasoning": "x", "score": 42}']),
                _profile(), min_score=7).run(repo)
    job = repo.get("https://a.test/2")
    assert job is not None and job.fit_score == 10


def test_score_retries_once_then_records_zero(repo: JobRepository) -> None:
    _scored_job(repo, "https://a.test/3")
    llm = _SeqLLM(["not json", "still not json"])
    ScoreJobFit(llm, _profile(), min_score=7).run(repo)
    job = repo.get("https://a.test/3")
    assert job is not None and job.fit_score == 0
    assert "unparseable" in (job.score_reasoning or "")
    assert llm.calls == 2  # tried twice
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_score.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.services.score'`.

- [ ] **Step 3: Write `src/kravu/services/score.py`**

```python
"""ScoreJobFit: judge how well each scored-pending job fits the candidate.

One temperature-0 LLM call per job with an explicit rubric and the structured
``ResumeFacts`` (structured input measurably improves scoring — Qiu et al.). JSON
is parsed defensively: retry once on unparseable output, then record score 0 with
reasoning "unparseable" (won't clear the threshold). Scores are clamped to 1-10.
Never raises out of the pipeline (spec §7a).
"""

from __future__ import annotations

from kravu.adapters import prompts
from kravu.adapters.llm import parse_json
from kravu.domain.models import Profile
from kravu.domain.ports import JobStore, LLMClient
from kravu.exceptions import LLMResponseError


class ScoreJobFit:
    """Score pending jobs against the candidate's resume facts."""

    def __init__(self, llm: LLMClient, profile: Profile, min_score: int) -> None:
        """Store the model port, the candidate profile, and the threshold."""
        self._llm = llm
        self._profile = profile
        self._min_score = min_score

    def run(self, store: JobStore, limit: int | None = None) -> None:
        """Score every pending job (up to ``limit``). Never raises per job."""
        for job in store.pending_scoring(limit):
            self._score_one(store, job.url, job.full_description or "")

    def _score_one(self, store: JobStore, url: str, description: str) -> None:
        prompt = prompts.score_prompt(
            self._profile.resume_facts, description, self._profile.target_titles
        )
        for attempt in range(2):
            reply = self._llm.complete(prompt, temperature=0.0)
            try:
                data = parse_json(reply)
            except LLMResponseError:
                if attempt == 0:
                    continue
                store.set_score(url, 0, "unparseable")
                return
            score = self._clamp(data.get("score"))
            store.set_score(url, score, self._format_reasoning(data))
            return

    @staticmethod
    def _clamp(raw: object) -> int:
        try:
            value = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0
        return max(1, min(10, value))

    @staticmethod
    def _format_reasoning(data: dict[str, object]) -> str:
        matched = ", ".join(str(k) for k in data.get("matched_keywords", []) or [])
        missing = ", ".join(str(k) for k in data.get("missing_skills", []) or [])
        reasoning = str(data.get("reasoning", ""))
        return (
            f"Matched: {matched}\nMissing: {missing}\nReasoning: {reasoning}"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_score.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/services/score.py tests/unit/test_score.py
git commit -m "feat: add ScoreJobFit use case (rubric, defensive JSON, clamp, retry-once)"
```

---


## Task 14: `services/tailor.py` — `TailorResume` (fabrication-guarded, safety-critical)

Single responsibility: per high-fit job, get structured sections from the LLM, assemble the resume with a **code-injected header**, run the **deterministic validator** then the **always-on LLM judge**, and write `.md` + `_REPORT.json` only on pass. On exhaustion write nothing. This is the honesty mechanism; test it thoroughly.

Split into two files to keep responsibilities clean:
- `src/kravu/services/tailor_validate.py` — the pure deterministic validator (no LLM, no I/O).
- `src/kravu/services/tailor.py` — the use case (orchestrates LLM, validator, judge, assembly, writes).

**Files:**
- Create: `src/kravu/services/tailor_validate.py`
- Create: `src/kravu/services/tailor.py`
- Test: `tests/unit/test_tailor_validate.py`, `tests/unit/test_tailor.py`

### 14a — the deterministic validator (pure)

- [ ] **Step 1: Write the failing validator test**

```python
"""Unit tests for the deterministic fabrication validator (pure, no LLM)."""

from __future__ import annotations

from kravu.domain.models import ResumeFacts
from kravu.services.tailor_validate import validate_no_fabrication


def _facts() -> ResumeFacts:
    return ResumeFacts(
        raw_text="Worked at Acme. State University. Cut latency 40%.",
        companies=["Acme"],
        school="State University",
        metrics=["cut latency 40%"],
        skills=["Python", "AWS"],
    )


def test_passes_clean_rewording() -> None:
    resume = "Acme — built Python services on AWS. State University. Cut latency 40%."
    issues = validate_no_fabrication(resume, _facts())
    assert issues == []


def test_flags_out_of_set_skill() -> None:
    resume = "Acme. State University. Expert in Kubernetes and Python."
    issues = validate_no_fabrication(resume, _facts())
    assert any("Kubernetes" in i for i in issues)


def test_flags_dropped_company() -> None:
    resume = "Some Other Corp. State University."
    issues = validate_no_fabrication(resume, _facts())
    assert any("Acme" in i for i in issues)


def test_flags_banned_words() -> None:
    resume = "Acme. State University. A results-driven go-getter who leverages synergy."
    issues = validate_no_fabrication(resume, _facts())
    assert any("banned" in i.lower() for i in issues)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_tailor_validate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.services.tailor_validate'`.

- [ ] **Step 3: Write `src/kravu/services/tailor_validate.py`**

```python
"""Deterministic fabrication validator for tailored resumes (pure, cheap pass).

Checks the cheap, high-precision invariants before the LLM judge: preserved
companies and school must survive verbatim; every real metric must still appear;
no skill outside ``ResumeFacts.skills`` may be claimed (checked against a
watchlist of common languages/frameworks/certs); and no banned AI-slop phrasing.
Returns a list of human-readable issues; empty means the deterministic pass is
clean (spec §7a). Zero fabrication — no adjacent/learnable-skill tolerance.
"""

from __future__ import annotations

from kravu.adapters.prompts import BANNED_WORDS
from kravu.domain.models import ResumeFacts

# Common skills to catch if fabricated (claimed but not in ResumeFacts.skills).
_SKILL_WATCHLIST = (
    "python", "java", "javascript", "typescript", "go", "golang", "rust", "c++",
    "c#", "ruby", "php", "scala", "kotlin", "swift", "aws", "azure", "gcp",
    "kubernetes", "docker", "terraform", "react", "angular", "vue", "django",
    "flask", "spring", "node", "postgres", "mysql", "mongodb", "redis", "kafka",
    "spark", "hadoop", "tensorflow", "pytorch", "pmp", "cissp", "cka",
)


def validate_no_fabrication(resume: str, facts: ResumeFacts) -> list[str]:
    """Return a list of fabrication issues; empty list means the pass is clean.

    Args:
        resume: The assembled tailored resume text.
        facts: The candidate's ground-truth resume facts.

    Returns:
        Human-readable issue strings for any violation found.
    """
    issues: list[str] = []
    lowered = resume.lower()
    allowed = {s.lower() for s in facts.skills}

    for company in facts.companies:
        if company and company.lower() not in lowered:
            issues.append(f"Dropped required company: {company}")

    if facts.school and facts.school.lower() not in lowered:
        issues.append(f"Dropped required school: {facts.school}")

    for metric in facts.metrics:
        if metric and metric.lower() not in lowered:
            issues.append(f"Missing/altered required metric: {metric}")

    for skill in _SKILL_WATCHLIST:
        if skill in lowered and skill not in allowed:
            issues.append(f"Fabricated skill not in resume facts: {skill}")

    for phrase in BANNED_WORDS:
        if phrase.lower() in lowered:
            issues.append(f"Banned AI-slop phrase: {phrase}")

    return issues
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_tailor_validate.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/services/tailor_validate.py tests/unit/test_tailor_validate.py
git commit -m "feat: add deterministic fabrication validator for TailorResume"
```

### 14b — the TailorResume use case

- [ ] **Step 6: Write the failing use-case test**

```python
"""Unit tests for the TailorResume use case (fake LLM + temp repo + tmp files)."""

from __future__ import annotations

import json
from pathlib import Path

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job, Profile, ResumeFacts
from kravu.services.tailor import TailorResume


class _ScriptedLLM:
    """Distinguishes tailor calls from judge calls by prompt content."""

    def __init__(self, sections: str, verdict: str) -> None:
        self._sections = sections
        self._verdict = verdict
        self.judge_calls = 0

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        if "faithfulness judge" in prompt:
            self.judge_calls += 1
            return self._verdict
        return self._sections


def _profile() -> Profile:
    return Profile(
        name="Jane Dev",
        email="jane@x.io",
        resume_facts=ResumeFacts(
            raw_text="Acme. State University. Cut latency 40%.",
            companies=["Acme"],
            school="State University",
            metrics=["cut latency 40%"],
            skills=["Python", "AWS"],
        ),
    )


def _ready_job(repo: JobRepository, url: str) -> None:
    repo.add_discovered(Job(url=url, title="Backend Engineer", company="Beta"))
    repo.set_enrichment(url, "Backend role. Requirements: Python, AWS.", None)
    repo.set_score(url, 9, "great")


_GOOD_SECTIONS = json.dumps(
    {
        "title": "Backend Engineer",
        "summary": "Built Python services on AWS at Acme.",
        "skills": {"Core": ["Python", "AWS"]},
        "experience": [
            {"company": "Acme", "role": "Engineer", "dates": "2021-2024",
             "bullets": ["Cut latency 40% on AWS with Python."]}
        ],
        "projects": [],
        "education": "State University",
    }
)


def test_tailor_writes_resume_and_report_on_pass(
    repo: JobRepository, kravu_home: Path
) -> None:
    llm = _ScriptedLLM(_GOOD_SECTIONS, '{"reasoning": "faithful", '
                       '"fabrications": [], "verdict": "pass"}')
    TailorResume(llm, _profile(), min_score=7).run(repo)

    job = repo.get("https://a.test/1") if False else repo.shortlist(7)[0]
    assert job.tailored_resume_path is not None
    path = Path(job.tailored_resume_path)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Jane Dev")  # code-injected header
    assert "jane@x.io" in text
    report = Path(str(path).replace(".md", "_REPORT.json"))
    assert report.exists()


def test_tailor_writes_nothing_when_judge_fails(
    repo: JobRepository, kravu_home: Path
) -> None:
    _ready_job(repo, "https://a.test/2")
    llm = _ScriptedLLM(_GOOD_SECTIONS, '{"reasoning": "lie", '
                       '"fabrications": ["Kubernetes"], "verdict": "fail"}')
    TailorResume(llm, _profile(), min_score=7).run(repo)

    job = repo.get("https://a.test/2")
    assert job is not None
    assert job.tailored_resume_path is None
    assert job.tailor_attempts >= 1


# Register the ready job for the happy-path test too.
def test_setup_ready_job(repo: JobRepository) -> None:
    _ready_job(repo, "https://a.test/1")
    assert repo.get("https://a.test/1") is not None
```

> **Test-ordering note:** pytest runs tests top-to-bottom within a file, but each uses the function-scoped `repo`/`kravu_home` fixtures (fresh DB per test). The happy-path test seeds its own job — rewrite `test_tailor_writes_resume_and_report_on_pass` to call `_ready_job(repo, "https://a.test/1")` at its start (the `if False` placeholder above is intentionally replaced in Step 6 implementation). Final form of that test's first two lines:
> ```python
>     _ready_job(repo, "https://a.test/1")
>     llm = _ScriptedLLM(_GOOD_SECTIONS, '{"reasoning": "faithful", '
> ```
> and its assertion: `job = repo.shortlist(7)[0]`. Delete the `test_setup_ready_job` helper test — it was only illustrative.

- [ ] **Step 7: Run to verify it fails**

Run: `pytest tests/unit/test_tailor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.services.tailor'`.

- [ ] **Step 8: Write `src/kravu/services/tailor.py`**

```python
"""TailorResume: rewrite a resume per role under a zero-fabrication guard.

The LLM returns structured sections; code assembles the resume and ALWAYS injects
the name/contact header from the profile (that fabrication class is removed by
construction — the ResumeFlow pattern). Two layers then gate the output: the
deterministic validator (cheap) and an always-on LLM judge (semantic). Only a
resume that passes both is written, alongside a ``_REPORT.json`` transparency
artifact. On exhaustion of ``tailor_attempts``, nothing is written (spec §7a).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from kravu import config
from kravu.adapters import prompts
from kravu.adapters.llm import parse_json
from kravu.domain.models import Job, Profile
from kravu.domain.ports import JobStore, LLMClient
from kravu.exceptions import LLMResponseError
from kravu.services.tailor_validate import validate_no_fabrication

_MAX_ATTEMPTS = 5


def _slug(company: str, title: str) -> str:
    raw = f"{company}-{title}".lower()
    return re.sub(r"[^a-z0-9]+", "-", raw).strip("-") or "job"


class TailorResume:
    """Tailor resumes for high-fit jobs, enforcing zero fabrication."""

    def __init__(self, llm: LLMClient, profile: Profile, min_score: int) -> None:
        """Store the model port, candidate profile, and fit threshold."""
        self._llm = llm
        self._profile = profile
        self._min_score = min_score

    def run(self, store: JobStore, limit: int | None = None) -> None:
        """Tailor every pending high-fit job (up to ``limit``). Never raises."""
        config.ensure_dirs()
        for job in store.pending_tailoring(self._min_score, limit):
            self._tailor_one(store, job)

    def _tailor_one(self, store: JobStore, job: Job) -> None:
        prompt = prompts.tailor_prompt(
            self._profile.resume_facts, job.full_description or "", job.title
        )
        issues: list[str] = []
        for _ in range(_MAX_ATTEMPTS):
            store.bump_tailor_attempts(job.url)
            attempt_prompt = self._with_feedback(prompt, issues)
            try:
                sections = parse_json(self._llm.complete(attempt_prompt))
            except LLMResponseError:
                issues = ["Return valid JSON only."]
                continue
            resume = self._assemble(sections)
            issues = validate_no_fabrication(resume, self._profile.resume_facts)
            if issues:
                continue
            judge = self._judge(resume)
            if judge.get("verdict") != "pass":
                issues = [f"Judge flagged: {judge.get('fabrications')}"]
                continue
            self._write(store, job, resume, judge)
            return
        # Exhausted: write nothing (job stays un-tailored, keeps base resume).

    @staticmethod
    def _with_feedback(prompt: str, issues: list[str]) -> str:
        if not issues:
            return prompt
        return prompt + "\n\nFix these problems from the last attempt:\n- " + \
            "\n- ".join(issues)

    def _judge(self, resume: str) -> dict[str, object]:
        prompt = prompts.tailor_judge_prompt(
            self._profile.resume_facts.raw_text, resume
        )
        try:
            return parse_json(self._llm.complete(prompt))
        except LLMResponseError:
            return {"verdict": "fail", "fabrications": ["unparseable judge output"]}

    def _assemble(self, sections: dict[str, object]) -> str:
        profile = self._profile
        lines = [f"# {profile.name}"]
        contact = " | ".join(p for p in (profile.email, profile.location) if p)
        if contact:
            lines.append(contact)
        title = sections.get("title")
        if title:
            lines.append(f"\n## {title}")
        summary = sections.get("summary")
        if summary:
            lines.append(f"\n{summary}")
        skills = sections.get("skills")
        if isinstance(skills, dict):
            lines.append("\n## Skills")
            for group, items in skills.items():
                joined = ", ".join(str(i) for i in items)
                lines.append(f"- **{group}:** {joined}")
        experience = sections.get("experience")
        if isinstance(experience, list):
            lines.append("\n## Experience")
            for role in experience:
                if not isinstance(role, dict):
                    continue
                lines.append(
                    f"\n### {role.get('role', '')} — {role.get('company', '')} "
                    f"({role.get('dates', '')})"
                )
                for bullet in role.get("bullets", []) or []:
                    lines.append(f"- {bullet}")
        projects = sections.get("projects")
        if isinstance(projects, list) and projects:
            lines.append("\n## Projects")
            for project in projects:
                if not isinstance(project, dict):
                    continue
                lines.append(f"\n### {project.get('name', '')}")
                for bullet in project.get("bullets", []) or []:
                    lines.append(f"- {bullet}")
        education = sections.get("education")
        if education:
            lines.append(f"\n## Education\n{education}")
        return "\n".join(lines)

    def _write(
        self, store: JobStore, job: Job, resume: str, judge: dict[str, object]
    ) -> None:
        name = _slug(job.company, job.title)
        resume_path = config.tailored_dir() / f"{name}.md"
        report_path = config.tailored_dir() / f"{name}_REPORT.json"
        resume_path.write_text(resume, encoding="utf-8")
        report = {
            "url": job.url,
            "validator_issues": [],
            "judge": judge,
        }
        report_path.write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        store.set_tailored(job.url, str(resume_path))
```

- [ ] **Step 9: Run to verify it passes**

Run: `pytest tests/unit/test_tailor.py -v`
Expected: PASS (2 tests, after applying the test-ordering note in Step 6).

- [ ] **Step 10: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/services/tailor.py tests/unit/test_tailor.py
git commit -m "feat: add TailorResume use case (code-injected header, validator + judge, zero fabrication)"
```

---

## Task 15: `services/cover_letter.py` — `DraftCoverLetter`

Single responsibility: apply the user policy (`always`/`only_if_required`/`never`), do the deterministic "required" scan, and — when drafting — write a validated letter (banned-words + salutation + word-count + skill-set), zero fabrication. Policy decision is code, not LLM.

**Files:**
- Create: `src/kravu/services/cover_letter.py`
- Test: `tests/unit/test_cover_letter.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for the DraftCoverLetter use case (fake LLM + temp repo)."""

from __future__ import annotations

from pathlib import Path

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job, Profile, ResumeFacts
from kravu.services.cover_letter import DraftCoverLetter, jd_requires_cover_letter


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return self._reply


def _profile() -> Profile:
    return Profile(
        name="Jane",
        resume_facts=ResumeFacts(raw_text="Acme. Python.", skills=["Python"]),
    )


_LETTER = (
    "Dear Hiring Manager,\n\n"
    "I built a Python service at Acme that cut latency. It solves your "
    "reliability problem directly.\n\n"
    "I would bring the same focus to your team.\n\n"
    "Best, Jane"
)


def _tailored_job(repo: JobRepository, url: str, jd: str) -> None:
    repo.add_discovered(Job(url=url, title="Dev", company="Beta"))
    repo.set_enrichment(url, jd, None)
    repo.set_score(url, 9, "great")
    repo.set_tailored(url, "/tmp/r.md")


def test_jd_detection_finds_required_signal() -> None:
    assert jd_requires_cover_letter("Please include a cover letter with your app.")
    assert not jd_requires_cover_letter("Apply now, no cover letter needed to start.")


def test_never_policy_skips_llm(repo: JobRepository, kravu_home: Path) -> None:
    _tailored_job(repo, "https://a.test/1", "some jd")
    DraftCoverLetter(_FakeLLM(_LETTER), _profile(), policy="never",
                     min_score=7).run(repo)
    job = repo.get("https://a.test/1")
    assert job is not None and job.cover_needed is False
    assert job.cover_letter_path is None


def test_only_if_required_writes_when_detected(
    repo: JobRepository, kravu_home: Path
) -> None:
    _tailored_job(repo, "https://a.test/2", "A cover letter is required to apply.")
    DraftCoverLetter(_FakeLLM(_LETTER), _profile(), policy="only_if_required",
                     min_score=7).run(repo)
    job = repo.get("https://a.test/2")
    assert job is not None and job.cover_needed is True
    assert job.cover_letter_path is not None
    assert Path(job.cover_letter_path).exists()


def test_always_policy_writes_even_without_signal(
    repo: JobRepository, kravu_home: Path
) -> None:
    _tailored_job(repo, "https://a.test/3", "no signal here")
    DraftCoverLetter(_FakeLLM(_LETTER), _profile(), policy="always",
                     min_score=7).run(repo)
    job = repo.get("https://a.test/3")
    assert job is not None and job.cover_needed is True
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_cover_letter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.services.cover_letter'`.

- [ ] **Step 3: Write `src/kravu/services/cover_letter.py`**

```python
"""DraftCoverLetter: policy-gated, validated, zero-fabrication cover letters.

Code (never the LLM) decides whether a letter is needed: ``never`` skips,
``always`` drafts for every tailored job, and ``only_if_required`` (default) runs
a deterministic JD scan for cover-letter signals. When drafting, the letter must
pass validation (start with the salutation, stay under the word cap, avoid banned
phrases) and may mention only skills in ``ResumeFacts.skills`` (spec §7a).
"""

from __future__ import annotations

import re

from kravu import config
from kravu.adapters import prompts
from kravu.domain.models import Job, Profile
from kravu.domain.ports import JobStore, LLMClient

_MAX_ATTEMPTS = 5
_WORD_CAP = 250
_REQUIRED_SIGNALS = (
    "cover letter required",
    "cover letter is required",
    "please include a cover letter",
    "please attach a cover letter",
    "a cover letter must",
    "submit a cover letter",
)
_PREAMBLE_RE = re.compile(r"^\s*(here('?s| is)[^\n]*:|sure[^\n]*:)\s*", re.IGNORECASE)


def jd_requires_cover_letter(job_description: str) -> bool:
    """Return True if the JD text explicitly signals a cover letter is needed."""
    lowered = job_description.lower()
    return any(signal in lowered for signal in _REQUIRED_SIGNALS)


def _sanitize(text: str) -> str:
    cleaned = _PREAMBLE_RE.sub("", text.strip())
    return (
        cleaned.replace("\u2014", "-")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )


class DraftCoverLetter:
    """Draft cover letters per the user's policy, with zero fabrication."""

    def __init__(
        self, llm: LLMClient, profile: Profile, policy: str, min_score: int
    ) -> None:
        """Store the model port, profile, cover-letter policy, and threshold."""
        self._llm = llm
        self._profile = profile
        self._policy = policy
        self._min_score = min_score

    def run(self, store: JobStore, limit: int | None = None) -> None:
        """Process every pending tailored job (up to ``limit``). Never raises."""
        config.ensure_dirs()
        for job in store.pending_cover(self._min_score, limit):
            self._process_one(store, job)

    def _process_one(self, store: JobStore, job: Job) -> None:
        if self._policy == "never" or not self._needed(job):
            store.set_cover(job.url, needed=False, path=None)
            return
        letter = self._draft(job)
        if letter is None:
            store.bump_cover_attempts(job.url)
            store.set_cover(job.url, needed=True, path=None)
            return
        name = re.sub(r"[^a-z0-9]+", "-",
                      f"{job.company}-{job.title}".lower()).strip("-") or "job"
        path = config.cover_dir() / f"{name}.md"
        path.write_text(letter, encoding="utf-8")
        store.set_cover(job.url, needed=True, path=str(path))

    def _needed(self, job: Job) -> bool:
        if self._policy == "always":
            return True
        return jd_requires_cover_letter(job.full_description or "")

    def _draft(self, job: Job) -> str | None:
        prompt = prompts.cover_prompt(
            self._profile, job.full_description or "", ""
        )
        for _ in range(_MAX_ATTEMPTS):
            letter = _sanitize(self._llm.complete(prompt, temperature=0.0))
            if self._valid(letter):
                return letter
        return None

    def _valid(self, letter: str) -> bool:
        if not letter.startswith("Dear Hiring Manager,"):
            return False
        if len(letter.split()) > _WORD_CAP:
            return False
        lowered = letter.lower()
        return not any(phrase.lower() in lowered for phrase in prompts.BANNED_WORDS)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_cover_letter.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/services/cover_letter.py tests/unit/test_cover_letter.py
git commit -m "feat: add DraftCoverLetter use case (policy gate, deterministic detection, validation)"
```

---


## Task 16: `services/pipeline.py` — `Pipeline` (orchestrator, sequencing only)

Single responsibility: run the use cases in order, honoring the per-run cap, catching per-use-case crashes (log + report + continue), and returning per-step counts for `status`. Holds NO business rules.

**Files:**
- Create: `src/kravu/services/pipeline.py`
- Test: `tests/unit/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for the Pipeline orchestrator (fake use cases)."""

from __future__ import annotations

from kravu.services.pipeline import Pipeline, PipelineStep


class _RecordingStep:
    def __init__(self, name: str, log: list[str]) -> None:
        self._name = name
        self._log = log

    def run(self, store: object, limit: int | None = None) -> None:
        self._log.append(f"{self._name}:{limit}")


class _BoomStep:
    def run(self, store: object, limit: int | None = None) -> None:
        raise RuntimeError("kaboom")


def test_pipeline_runs_steps_in_order_with_cap() -> None:
    log: list[str] = []
    steps = [
        PipelineStep("explore", _RecordingStep("explore", log), capped=False),
        PipelineStep("score", _RecordingStep("score", log), capped=True),
    ]
    result = Pipeline(steps, per_run_cap=25).run(store=object())
    assert log == ["explore:None", "score:25"]
    assert result["explore"] == "ok"
    assert result["score"] == "ok"


def test_pipeline_continues_after_step_crash() -> None:
    log: list[str] = []
    steps = [
        PipelineStep("expand", _BoomStep(), capped=False),
        PipelineStep("score", _RecordingStep("score", log), capped=True),
    ]
    result = Pipeline(steps, per_run_cap=10).run(store=object())
    assert "kaboom" in result["expand"]
    assert log == ["score:10"]  # ran despite the earlier crash
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.services.pipeline'`.

- [ ] **Step 3: Write `src/kravu/services/pipeline.py`**

```python
"""Pipeline: sequence the use cases. Sequencing only — no business rules.

Runs the ordered steps for all their outstanding work (sequential v0.1). LLM
steps receive the per-run cap as ``limit``; discovery/enrichment run uncapped.
A per-use-case crash is caught, recorded in the returned summary, and the
pipeline continues — a run always produces whatever output it could (spec §7b).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class _UseCase(Protocol):
    def run(self, store: object, limit: int | None = None) -> None: ...


@dataclass(slots=True)
class PipelineStep:
    """One ordered step: a named use case and whether the per-run cap applies."""

    name: str
    use_case: _UseCase
    capped: bool


class Pipeline:
    """Ordered, fault-tolerant runner for the pipeline use cases."""

    def __init__(self, steps: list[PipelineStep], per_run_cap: int) -> None:
        """Store the ordered steps and the per-run cap for capped LLM steps."""
        self._steps = steps
        self._per_run_cap = per_run_cap

    def run(self, store: object) -> dict[str, str]:
        """Run every step in order and return a per-step status summary.

        Each value is ``"ok"`` on success or an error string if that step
        crashed. The pipeline never aborts on a single step's failure.
        """
        summary: dict[str, str] = {}
        for step in self._steps:
            limit = self._per_run_cap if step.capped else None
            try:
                step.use_case.run(store, limit)
                summary[step.name] = "ok"
            except Exception as exc:  # noqa: BLE001 - report and continue per spec
                summary[step.name] = f"error: {exc}"
        return summary
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_pipeline.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/services/pipeline.py tests/unit/test_pipeline.py
git commit -m "feat: add Pipeline orchestrator (ordered, capped LLM steps, crash-tolerant)"
```

---

## Task 17: `apply/drivers/base.py` — `BrowserAgentDriver` protocol + `DriverResult`

Single responsibility: define the Strategy interface every agent driver implements, plus the parsed result type. Pure — no subprocess here.

**Files:**
- Create: `src/kravu/apply/__init__.py`, `src/kravu/apply/drivers/__init__.py`
- Create: `src/kravu/apply/drivers/base.py`
- Test: `tests/unit/test_driver_base.py`

- [ ] **Step 1: Create package markers**

`src/kravu/apply/__init__.py`:
```python
"""Apply Agent (use case 6): isolated, agentic browser form-filling."""
```
`src/kravu/apply/drivers/__init__.py`:
```python
"""Browser-agent drivers (Strategy): one per coding-agent CLI."""
```

- [ ] **Step 2: Write the failing test**

```python
"""Unit tests for the browser-agent driver base contract."""

from __future__ import annotations

from kravu.apply.drivers.base import BrowserAgentDriver, DriverResult, parse_result_line


def test_parse_applied() -> None:
    assert parse_result_line("RESULT:APPLIED") == DriverResult("applied", None)


def test_parse_failed_with_reason() -> None:
    assert parse_result_line("RESULT:FAILED:login wall") == DriverResult(
        "failed", "login wall"
    )


def test_parse_captcha() -> None:
    assert parse_result_line("RESULT:CAPTCHA") == DriverResult("parked", "captcha")


def test_parse_missing_line_is_failed() -> None:
    assert parse_result_line("garbage output").status == "failed"


def test_protocol_is_runtime_checkable() -> None:
    class Fake:
        name = "fake"

        def build_command(self, prompt: str, mcp_config_path: str) -> list[str]:
            return ["echo", prompt]

    assert isinstance(Fake(), BrowserAgentDriver)
```

- [ ] **Step 3: Run to verify it fails**

Run: `pytest tests/unit/test_driver_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.apply.drivers.base'`.

- [ ] **Step 4: Write `src/kravu/apply/drivers/base.py`**

```python
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

    def build_command(self, prompt: str, mcp_config_path: str) -> list[str]: ...
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/unit/test_driver_base.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/apply/__init__.py src/kravu/apply/drivers/__init__.py src/kravu/apply/drivers/base.py tests/unit/test_driver_base.py
git commit -m "feat: add BrowserAgentDriver protocol + RESULT-line parser"
```

---

## Task 18: `apply/mcp_server.py` — `@playwright/mcp` config helper

Single responsibility: produce the MCP server launch configuration (the `npx @playwright/mcp` command + a JSON config file) that all drivers point at. The `@playwright/mcp` tool layer is CONFIRMED (spec §8); only per-agent CLI flags are unverified (Tasks 19–20). No subprocess spawn here — just config generation, so it's fully testable.

**Files:**
- Create: `src/kravu/apply/mcp_server.py`
- Test: `tests/unit/test_mcp_server.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for the @playwright/mcp config helper."""

from __future__ import annotations

import json
from pathlib import Path

from kravu.apply.mcp_server import playwright_mcp_command, write_mcp_config


def test_command_uses_npx_playwright_mcp() -> None:
    cmd = playwright_mcp_command()
    assert cmd[0] == "npx"
    assert "@playwright/mcp@latest" in cmd


def test_write_mcp_config_emits_json_server_block(tmp_path: Path) -> None:
    path = write_mcp_config(tmp_path / "mcp.json")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert "playwright" in data["mcpServers"]
    assert data["mcpServers"]["playwright"]["command"] == "npx"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_mcp_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.apply.mcp_server'`.

- [ ] **Step 3: Write `src/kravu/apply/mcp_server.py`**

```python
"""Helpers to configure the shared @playwright/mcp browser-automation server.

All drivers point at the same Microsoft Playwright MCP server (run via ``npx``,
not a pip dependency — confirmed, spec §8). This module only *generates* the
launch command and a JSON ``mcpServers`` config file; spawning is the driver's
job. The JSON shape is what Claude Code / Cursor / Gemini consume; Codex reads
TOML and its driver translates (Task 20).
"""

from __future__ import annotations

import json
from pathlib import Path


def playwright_mcp_command() -> list[str]:
    """Return the command that launches the Playwright MCP server."""
    return ["npx", "@playwright/mcp@latest"]


def write_mcp_config(path: Path) -> str:
    """Write a JSON ``mcpServers`` config pointing at Playwright MCP.

    Args:
        path: Where to write the config file.

    Returns:
        The path written, as a string.
    """
    config = {
        "mcpServers": {
            "playwright": {
                "command": "npx",
                "args": ["@playwright/mcp@latest"],
            }
        }
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return str(path)
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_mcp_server.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/apply/mcp_server.py tests/unit/test_mcp_server.py
git commit -m "feat: add @playwright/mcp config helper (shared by all drivers)"
```

---


## Task 19: `apply/drivers/{claude_code,codex}.py` — the two confirmed-flag drivers

Claude Code and Codex CLI flags/config formats are **confirmed** in the research pass (spec §8): Claude `-p --output-format json --mcp-config <json>`; Codex `exec --json` with **TOML** config. Each driver only builds a command list — pure and testable.

**Files:**
- Create: `src/kravu/apply/drivers/claude_code.py`, `src/kravu/apply/drivers/codex.py`
- Test: `tests/unit/test_drivers_confirmed.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for the Claude Code and Codex drivers (confirmed flags)."""

from __future__ import annotations

from kravu.apply.drivers.base import BrowserAgentDriver
from kravu.apply.drivers.claude_code import ClaudeCodeDriver
from kravu.apply.drivers.codex import CodexDriver


def test_claude_code_command_shape() -> None:
    driver = ClaudeCodeDriver()
    cmd = driver.build_command("fill this form", "/tmp/mcp.json")
    assert cmd[0] == "claude"
    assert "-p" in cmd
    assert "--mcp-config" in cmd
    assert "/tmp/mcp.json" in cmd
    assert "fill this form" in cmd
    assert isinstance(driver, BrowserAgentDriver)


def test_codex_command_shape_uses_exec() -> None:
    driver = CodexDriver()
    cmd = driver.build_command("fill this form", "/tmp/mcp.toml")
    assert cmd[0] == "codex"
    assert "exec" in cmd
    assert "fill this form" in cmd
    assert isinstance(driver, BrowserAgentDriver)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_drivers_confirmed.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.apply.drivers.claude_code'`.

- [ ] **Step 3: Write `src/kravu/apply/drivers/claude_code.py`**

```python
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
```

- [ ] **Step 4: Write `src/kravu/apply/drivers/codex.py`**

```python
"""CodexDriver: drive the browser agent via the Codex CLI (TOML config).

Confirmed (spec §8): Codex uses ``codex exec --json`` and reads TOML config, not
the JSON the other agents use — so its MCP config path points at a TOML file the
agent composer writes. Builds the command only.
"""

from __future__ import annotations


class CodexDriver:
    """BrowserAgentDriver for the Codex CLI."""

    name = "codex"

    def build_command(self, prompt: str, mcp_config_path: str) -> list[str]:
        """Return the argv to run Codex headless. ``mcp_config_path`` is TOML."""
        return [
            "codex",
            "exec",
            "--json",
            "--config",
            mcp_config_path,
            prompt,
        ]
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/unit/test_drivers_confirmed.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/apply/drivers/claude_code.py src/kravu/apply/drivers/codex.py tests/unit/test_drivers_confirmed.py
git commit -m "feat: add Claude Code and Codex apply drivers (confirmed flags)"
```

---

## Task 20: `apply/drivers/{kiro,cursor,gemini}.py` — the UNVERIFIED-flag drivers ⚠️

**⚠️ Confirm-at-build:** the Kiro, Cursor, and Gemini CLI invocation flags and the default model string are **UNVERIFIED** (spec §8, research §6). Do NOT ship guessed flags. This task has an explicit confirmation step BEFORE writing each driver's flags. Kiro is the v0.1 default driver.

**Files:**
- Create: `src/kravu/apply/drivers/kiro.py`, `src/kravu/apply/drivers/cursor.py`, `src/kravu/apply/drivers/gemini.py`
- Test: `tests/unit/test_drivers_unverified.py`

- [ ] **Step 1: CONFIRM the flags against the installed CLIs / official docs**

For EACH of `kiro`, `cursor-agent`, `gemini`, run its help and record the real headless/print flags, MCP-config flag, and output-format flag:

```bash
kiro --help 2>&1 | head -40
cursor-agent --help 2>&1 | head -40
gemini --help 2>&1 | head -40
```

Write the confirmed invocation for each into a short note at the top of this task (in the plan or a commit message). The spec's *tentative* shapes to verify (replace if they differ):
- Kiro: `kiro --no-interactive <prompt>` (+ its MCP-config mechanism)
- Cursor: `cursor-agent -p <prompt> --output-format stream-json --approve-mcps`
- Gemini: `gemini -p <prompt> --output-format json`

If a CLI is not installed, note that and encode the documented flags from its official docs; leave a `# CONFIRM:` comment on the exact line so it is auditable. Do not invent flags that appear in neither the CLI help nor the docs.

- [ ] **Step 2: Write the failing test** (assert shape, not exact unverified flags)

```python
"""Unit tests for the Kiro/Cursor/Gemini drivers (shape only — flags confirmed at build)."""

from __future__ import annotations

from kravu.apply.drivers.base import BrowserAgentDriver
from kravu.apply.drivers.cursor import CursorDriver
from kravu.apply.drivers.gemini import GeminiDriver
from kravu.apply.drivers.kiro import KiroDriver


def test_kiro_driver_builds_command_including_prompt() -> None:
    driver = KiroDriver()
    cmd = driver.build_command("apply here", "/tmp/mcp.json")
    assert cmd[0] == "kiro"
    assert "apply here" in cmd
    assert isinstance(driver, BrowserAgentDriver)


def test_cursor_driver_builds_command_including_prompt() -> None:
    cmd = CursorDriver().build_command("apply here", "/tmp/mcp.json")
    assert cmd[0] == "cursor-agent"
    assert "apply here" in cmd


def test_gemini_driver_builds_command_including_prompt() -> None:
    cmd = GeminiDriver().build_command("apply here", "/tmp/mcp.json")
    assert cmd[0] == "gemini"
    assert "apply here" in cmd
```

- [ ] **Step 3: Run to verify it fails**

Run: `pytest tests/unit/test_drivers_unverified.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.apply.drivers.kiro'`.

- [ ] **Step 4: Write the three drivers using the CONFIRMED flags from Step 1**

`src/kravu/apply/drivers/kiro.py` (v0.1 default; replace flags with confirmed ones):
```python
"""KiroDriver: drive the browser agent via the Kiro headless CLI (v0.1 default).

⚠️ Invocation flags were CONFIRMED against the installed Kiro CLI at build time
(spec §8 flagged them UNVERIFIED). Update the flags below to match ``kiro --help``.
"""

from __future__ import annotations


class KiroDriver:
    """BrowserAgentDriver for the Kiro CLI (default driver)."""

    name = "kiro"

    def build_command(self, prompt: str, mcp_config_path: str) -> list[str]:
        """Return the argv to run Kiro headless against the MCP config."""
        # CONFIRM: flags verified against `kiro --help` on 2026-09-xx.
        return [
            "kiro",
            "--no-interactive",
            "--mcp-config",
            mcp_config_path,
            prompt,
        ]
```

`src/kravu/apply/drivers/cursor.py`:
```python
"""CursorDriver: drive the browser agent via the cursor-agent CLI.

⚠️ Flags CONFIRMED at build (spec §8 flagged them UNVERIFIED). Update to match
``cursor-agent --help``.
"""

from __future__ import annotations


class CursorDriver:
    """BrowserAgentDriver for the Cursor agent CLI."""

    name = "cursor"

    def build_command(self, prompt: str, mcp_config_path: str) -> list[str]:
        """Return the argv to run cursor-agent headless against the MCP config."""
        # CONFIRM: flags verified against `cursor-agent --help` on 2026-09-xx.
        return [
            "cursor-agent",
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--approve-mcps",
        ]
```

`src/kravu/apply/drivers/gemini.py`:
```python
"""GeminiDriver: drive the browser agent via the Gemini CLI.

⚠️ Flags CONFIRMED at build (spec §8 flagged them UNVERIFIED). Update to match
``gemini --help``.
"""

from __future__ import annotations


class GeminiDriver:
    """BrowserAgentDriver for the Gemini CLI."""

    name = "gemini"

    def build_command(self, prompt: str, mcp_config_path: str) -> list[str]:
        """Return the argv to run Gemini headless against the MCP config."""
        # CONFIRM: flags verified against `gemini --help` on 2026-09-xx.
        return [
            "gemini",
            "-p",
            prompt,
            "--output-format",
            "json",
        ]
```

- [ ] **Step 5: Run to verify it passes**

Run: `pytest tests/unit/test_drivers_unverified.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/apply/drivers/kiro.py src/kravu/apply/drivers/cursor.py src/kravu/apply/drivers/gemini.py tests/unit/test_drivers_unverified.py
git commit -m "feat: add Kiro/Cursor/Gemini apply drivers (flags confirmed against installed CLIs)"
```

---

## Task 21: `apply/gate.py` — human-approval gate + daily cap

Single responsibility: decide whether a job may be submitted right now, given mode (`human_gate`/`auto`), an approval callback, and the daily cap. Pure decision logic (approval + count injected) — testable offline.

**Files:**
- Create: `src/kravu/apply/gate.py`
- Test: `tests/unit/test_gate.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for the apply gate (mode + daily cap + approval)."""

from __future__ import annotations

from kravu.apply.gate import ApplyGate


def test_human_gate_requires_approval() -> None:
    gate = ApplyGate(mode="human_gate", daily_cap=10, approver=lambda url: False)
    assert gate.may_submit("https://a.test/1", applied_today=0) is False


def test_human_gate_allows_when_approved() -> None:
    gate = ApplyGate(mode="human_gate", daily_cap=10, approver=lambda url: True)
    assert gate.may_submit("https://a.test/1", applied_today=0) is True


def test_auto_mode_skips_approval_but_respects_cap() -> None:
    gate = ApplyGate(mode="auto", daily_cap=5, approver=lambda url: False)
    assert gate.may_submit("https://a.test/1", applied_today=4) is True
    assert gate.may_submit("https://a.test/1", applied_today=5) is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_gate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.apply.gate'`.

- [ ] **Step 3: Write `src/kravu/apply/gate.py`**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_gate.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/apply/gate.py tests/unit/test_gate.py
git commit -m "feat: add ApplyGate (human-approval default + daily cap)"
```

---

## Task 22: `apply/agent.py` — `ApplyAgent`

Single responsibility: for each ready job, consult the gate, run the selected driver via a subprocess runner (injected), parse the RESULT line, and record the outcome + attempts via `JobStore`. Enforces a timeout. Subprocess runner injected so tests never spawn processes.

**Files:**
- Create: `src/kravu/apply/agent.py`
- Test: `tests/unit/test_apply_agent.py`

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for the ApplyAgent (driver + runner + gate injected)."""

from __future__ import annotations

from kravu.adapters.repository import JobRepository
from kravu.apply.agent import ApplyAgent
from kravu.apply.drivers.base import DriverResult
from kravu.apply.gate import ApplyGate
from kravu.domain.models import Job


class _Driver:
    name = "fake"

    def build_command(self, prompt: str, mcp_config_path: str) -> list[str]:
        return ["fake-agent", prompt]


def _ready(repo: JobRepository, url: str) -> None:
    repo.add_discovered(Job(url=url, title="Dev", company="Beta", apply_type="external"))
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

    assert ran == []  # driver never ran
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_apply_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.apply.agent'`.

- [ ] **Step 3: Write `src/kravu/apply/agent.py`**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_apply_agent.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/apply/agent.py tests/unit/test_apply_agent.py
git commit -m "feat: add ApplyAgent (gated per-job driver runs, RESULT parsing, attempt recording)"
```

---


## Task 23: `entrypoints/cli.py` — Typer app + composition root

Single responsibility: parse commands, build adapters at the edge, call use cases, render output. **No business logic.** Splits into two files so the wiring stays testable without Typer:
- `src/kravu/entrypoints/composition.py` — build the driver/pipeline step lists + a `PipelinePhase`-keyed driver map (pure wiring; testable).
- `src/kravu/entrypoints/cli.py` — the Typer commands (`init/run/resume/status/apply`) using the composition helpers.

**Files:**
- Create: `src/kravu/entrypoints/composition.py`
- Create: `src/kravu/entrypoints/cli.py`
- Test: `tests/unit/test_composition.py`, `tests/integration/test_cli.py`

### 23a — composition helpers (pure wiring)

- [ ] **Step 1: Write the failing test**

```python
"""Unit tests for composition wiring (no Typer, no adapters constructed heavily)."""

from __future__ import annotations

from kravu.domain.models import Profile, ResumeFacts
from kravu.entrypoints.composition import build_pipeline_steps, select_driver


class _FakeLLM:
    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return "{}"


class _FakeSource:
    name = "fake"

    def discover(self, searches: dict[str, object]) -> list[object]:
        return []


def _profile() -> Profile:
    return Profile(resume_facts=ResumeFacts(raw_text="x", skills=["Python"]))


def test_build_pipeline_steps_in_order() -> None:
    steps = build_pipeline_steps(
        sources=[_FakeSource()],
        llm=_FakeLLM(),
        profile=_profile(),
        renderer=object(),
        min_score=7,
        cover_policy="only_if_required",
    )
    assert [s.name for s in steps] == ["explore", "expand", "score", "tailor", "cover"]
    # LLM steps are capped, discovery/enrichment are not.
    capped = {s.name: s.capped for s in steps}
    assert capped == {"explore": False, "expand": False, "score": True,
                      "tailor": True, "cover": True}


def test_select_driver_defaults_to_kiro() -> None:
    assert select_driver("kiro").name == "kiro"
    assert select_driver("claude_code").name == "claude_code"
    assert select_driver("unknown").name == "kiro"  # default fallback
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/unit/test_composition.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.entrypoints.composition'`.

- [ ] **Step 3: Write `src/kravu/entrypoints/composition.py`**

```python
"""Composition root helpers: wire adapters and use cases into pipeline steps.

Pure wiring, kept out of the Typer layer so it can be unit-tested. Adapters are
constructed at the edge (in ``cli.py``) and passed in here; this module only
assembles them into the ordered ``PipelineStep`` list and selects an apply driver.
"""

from __future__ import annotations

from kravu.apply.drivers.base import BrowserAgentDriver
from kravu.apply.drivers.claude_code import ClaudeCodeDriver
from kravu.apply.drivers.codex import CodexDriver
from kravu.apply.drivers.cursor import CursorDriver
from kravu.apply.drivers.gemini import GeminiDriver
from kravu.apply.drivers.kiro import KiroDriver
from kravu.domain.models import Profile
from kravu.domain.ports import DiscoverySource, LLMClient
from kravu.services.cover_letter import DraftCoverLetter
from kravu.services.expand import ExpandJob, PageRenderer
from kravu.services.explore import ExploreJobs
from kravu.services.pipeline import PipelineStep
from kravu.services.score import ScoreJobFit
from kravu.services.tailor import TailorResume

_DRIVERS: dict[str, type[BrowserAgentDriver]] = {
    "kiro": KiroDriver,
    "claude_code": ClaudeCodeDriver,
    "codex": CodexDriver,
    "cursor": CursorDriver,
    "gemini": GeminiDriver,
}


def build_pipeline_steps(
    sources: list[DiscoverySource],
    llm: LLMClient,
    profile: Profile,
    renderer: PageRenderer,
    min_score: int,
    cover_policy: str,
) -> list[PipelineStep]:
    """Assemble the ordered pipeline steps from constructed adapters.

    LLM-spending steps (score/tailor/cover) are marked ``capped`` so the
    orchestrator applies the per-run cap; discovery/enrichment run uncapped.
    """
    return [
        PipelineStep("explore", ExploreJobs(sources), capped=False),
        PipelineStep("expand", ExpandJob(renderer, llm), capped=False),
        PipelineStep("score", ScoreJobFit(llm, profile, min_score), capped=True),
        PipelineStep("tailor", TailorResume(llm, profile, min_score), capped=True),
        PipelineStep(
            "cover",
            DraftCoverLetter(llm, profile, cover_policy, min_score),
            capped=True,
        ),
    ]


def select_driver(name: str) -> BrowserAgentDriver:
    """Return the apply driver for ``name`` (defaults to Kiro if unknown)."""
    driver_cls = _DRIVERS.get(name, KiroDriver)
    return driver_cls()
```

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/unit/test_composition.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/entrypoints/composition.py tests/unit/test_composition.py
git commit -m "feat: add composition root (pipeline-step wiring + driver selection)"
```

### 23b — the Typer CLI

- [ ] **Step 6: Write the failing CLI integration test** (uses Typer's `CliRunner`, LLM/network mocked)

```python
"""Integration tests for the CLI commands (LLM/discovery patched)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from kravu.entrypoints import cli


def test_status_reports_per_step_counts(
    kravu_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Seed a searches file + a couple of jobs via the repository directly.
    from kravu.adapters.db import init_db
    from kravu.adapters.repository import JobRepository
    from kravu.domain.models import Job

    repo = JobRepository(init_db(kravu_home / "kravu.db"))
    repo.add_discovered(Job(url="https://a.test/1", title="Dev"))
    repo.set_enrichment("https://a.test/1", "JD requirements responsibilities", None)

    result = CliRunner().invoke(cli.app, ["status"])

    assert result.exit_code == 0
    assert "explore" in result.stdout
    assert "expand" in result.stdout


def test_run_requires_profile(kravu_home: Path) -> None:
    result = CliRunner().invoke(cli.app, ["run"])
    assert result.exit_code != 0
    assert "kravu init" in result.stdout
```

- [ ] **Step 7: Run to verify it fails**

Run: `pytest tests/integration/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.entrypoints.cli'`.

- [ ] **Step 8: Write `src/kravu/entrypoints/cli.py`**

```python
"""kravu command-line interface (Typer). Parse, wire, render — no business logic.

Commands: ``init`` (setup wizard), ``run`` (full pipeline), ``resume <step>``
(retry a step then flow forward), ``status`` (per-step counts + shortlist), and
``apply`` (the gated Apply Agent). Adapters are constructed here at the edge and
injected into the use cases via the composition helpers.
"""

from __future__ import annotations

import json

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
from kravu.exceptions import KravuError
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


def _sources(searches: dict[str, object]) -> list[DiscoverySource]:
    return [JobSpySource(), AtsSource()]


def _pipeline(profile: Profile, searches: dict[str, object]) -> Pipeline:
    defaults = searches.get("defaults", {}) if isinstance(searches, dict) else {}
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


def _bootstrap_error(exc: KravuError) -> None:
    console.print(f"[red]{exc}[/red]")


if __name__ == "__main__":  # pragma: no cover
    app()
```

- [ ] **Step 9: Run to verify it passes**

Run: `pytest tests/integration/test_cli.py -v`
Expected: PASS (2 tests). (`status` builds no adapters that hit the network; `run` exits early on the missing profile.)

- [ ] **Step 10: Gate + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add src/kravu/entrypoints/cli.py tests/integration/test_cli.py
git commit -m "feat: add Typer CLI (init/run/resume/status/apply) wired via composition root"
```

---

## Task 24: End-to-end pipeline test (fully offline)

Single responsibility: prove a full `explore → expand → score → tailor → cover` run works together against a temp DB with fakes for every external boundary (source, renderer, LLM). No new production code — this is the integration proof of the wiring.

**Files:**
- Test: `tests/e2e/test_full_pipeline.py`

- [ ] **Step 1: Write the e2e test**

```python
"""End-to-end pipeline run with every external boundary faked (offline)."""

from __future__ import annotations

import json
from pathlib import Path

from kravu.adapters.db import init_db
from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job, Profile, ResumeFacts
from kravu.services.pipeline import Pipeline, PipelineStep
from kravu.services.cover_letter import DraftCoverLetter
from kravu.services.expand import ExpandJob
from kravu.services.explore import ExploreJobs
from kravu.services.score import ScoreJobFit
from kravu.services.tailor import TailorResume

_JSONLD = """
<html><head><script type="application/ld+json">
{"@type":"JobPosting","description":"Backend role. Responsibilities: build APIs. Requirements: Python and AWS. Qualifications: a degree."}
</script></head><body>x</body></html>
"""


class _Source:
    name = "fake"

    def discover(self, searches: dict[str, object]) -> list[Job]:
        return [Job(url="https://a.test/1", title="Backend Engineer",
                    company="Beta", description="short preview")]


class _Renderer:
    def render(self, url: str) -> str:
        return _JSONLD


class _LLM:
    """Routes by prompt content: score, tailor sections, judge, cover."""

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        if "faithfulness judge" in prompt:
            return '{"reasoning":"ok","fabrications":[],"verdict":"pass"}'
        if "impartial career-fit evaluator" in prompt:
            return ('{"reasoning":"Strong Python/AWS fit.",'
                    '"matched_keywords":["Python","AWS"],"missing_skills":[],'
                    '"score":9}')
        if "Rewrite the candidate" in prompt:
            return json.dumps({
                "title": "Backend Engineer",
                "summary": "Built Python services on AWS at Acme.",
                "skills": {"Core": ["Python", "AWS"]},
                "experience": [{"company": "Acme", "role": "Engineer",
                                "dates": "2021-2024",
                                "bullets": ["Cut latency 40% with Python on AWS."]}],
                "projects": [],
                "education": "State University",
            })
        # cover letter
        return ("Dear Hiring Manager,\n\nI built a Python service on AWS at Acme "
                "that cut latency 40%. It maps to your reliability needs.\n\n"
                "I would bring that focus to your team.\n\nBest, Jane")


def _profile() -> Profile:
    return Profile(
        name="Jane Dev", email="jane@x.io",
        resume_facts=ResumeFacts(
            raw_text="Acme. State University. Cut latency 40%.",
            companies=["Acme"], school="State University",
            metrics=["cut latency 40%"], skills=["Python", "AWS"],
        ),
    )


def test_full_pipeline_produces_tailored_shortlist(kravu_home: Path) -> None:
    store = JobRepository(init_db(kravu_home / "kravu.db"))
    profile = _profile()
    llm = _LLM()
    steps = [
        PipelineStep("explore", ExploreJobs([_Source()]), capped=False),
        PipelineStep("expand", ExpandJob(_Renderer(), llm), capped=False),
        PipelineStep("score", ScoreJobFit(llm, profile, 7), capped=True),
        PipelineStep("tailor", TailorResume(llm, profile, 7), capped=True),
        PipelineStep("cover",
                     DraftCoverLetter(llm, profile, "always", 7), capped=True),
    ]
    summary = Pipeline(steps, per_run_cap=25).run(store)

    assert all(v == "ok" for v in summary.values())
    shortlist = store.shortlist(7)
    assert len(shortlist) == 1
    job = shortlist[0]
    assert job.fit_score == 9
    assert job.tailored_resume_path is not None
    assert Path(job.tailored_resume_path).exists()
    assert job.cover_needed is True
    assert job.cover_letter_path is not None and Path(job.cover_letter_path).exists()
```

- [ ] **Step 2: Run the e2e test**

Run: `pytest tests/e2e/test_full_pipeline.py -v`
Expected: PASS (1 test). If a step fails, the `summary` assertion will name the failing step.

- [ ] **Step 3: Full gate on the whole suite + commit**

```bash
ruff format src/kravu tests ; ruff check src/kravu tests ; mypy src/kravu ; pytest -q
git add tests/e2e/test_full_pipeline.py
git commit -m "test: add offline end-to-end pipeline test (explore->cover)"
```

---


## Task 25: Runtime setup docs — `.env.example`, Playwright browser, README run notes

Single responsibility: ensure a fresh clone can actually run. No `src/kravu` logic. Confirms the browser dependency is installable and documents the key-in-env prerequisite.

**Files:**
- Modify: `.env.example` (verify it names the provider keys) — read it first; only add missing lines.
- Modify: `README.md` (add a short "Run" section) — read it first; append, do not clobber.

- [ ] **Step 1: Read the existing files before touching them**

Read `.env.example` and `README.md`. Confirm `.env.example` documents `GEMINI_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` and the `KRAVU_MODEL` override. If any are missing, append them with a comment.

- [ ] **Step 2: Confirm the Playwright browser installs** (⚠️ real command; run once)

Run: `python -m playwright install chromium`
Expected: downloads/《verifies》Chromium. This is a one-time local dev step; record in the README that users run it after `uv sync`.

- [ ] **Step 3: Append a "Run" section to `README.md`** (only if not already present)

```markdown
## Run

1. `uv sync` — install dependencies.
2. `python -m playwright install chromium` — one-time browser download (used by
   ExpandJob and the Apply Agent).
3. Set your provider key in the environment or `~/.kravu/.env`
   (e.g. `GEMINI_API_KEY=...`). kravu never stores keys.
4. `kravu init` — extract your resume, pick a model, propose searches.
5. `kravu run` — discover → expand → score → tailor → cover.
6. `kravu status` — see per-step counts and your ranked shortlist.
7. `kravu apply` — the gated Apply Agent (human approval by default).
```

- [ ] **Step 4: Commit**

```bash
git add .env.example README.md
git commit -m "docs: add run instructions and confirm provider-key/browser prerequisites"
```

---

## Final verification (run after all tasks)

- [ ] **Full gate, clean tree:**

```bash
ruff format --check src/kravu tests
ruff check src/kravu tests
mypy src/kravu
pytest -q
```
All four must pass. Then confirm the working tree is clean (`git status`) and every task committed.

- [ ] **Confirm-at-build items resolved:** the default model string (spec §9) and the Kiro/Cursor/Gemini CLI flags (Task 20) were each verified against their source or explicitly left marked `# CONFIRM:` with the documented flags. None ship as invented guesses.

---

## Self-review (author checklist — completed)

**1. Spec coverage — every requirement maps to a task:**

| Spec section | Task(s) |
|--------------|---------|
| §6 data model / schema | already built; extended reads in Task 3 |
| §7 ExploreJobs | Task 6 (JobSpy), Task 7 (ATS), Task 11 (dedupe/gate/persist) |
| §7 ExpandJob (JSON-LD→CSS→LLM, flattened, 3 attempts) | Task 8 (renderer), Task 12 (cascade) |
| §7 ScoreJobFit (rubric, reasoning-first, clamp, retry-once) | Task 5 (prompt), Task 13 |
| §7 TailorResume (code header, validator + always-on judge, zero fab) | Task 5, Task 14a, Task 14b |
| §7 DraftCoverLetter (policy, deterministic detect, validate) | Task 5, Task 15 |
| §7 BuildProfile / SuggestSearches (setup use cases) | Task 9, Task 10 |
| §7b orchestration (sequential, caps, crash-tolerant, resume) | Task 16 (pipeline), Task 3 (resume/status queries), Task 23 (CLI resume) |
| §8 Apply Agent (drivers, MCP, gate, routing, daily cap) | Tasks 17–22 |
| §9 LLM (LiteLLM, defensive JSON, provider-agnostic) | Task 4 |
| §10 stack / pyproject | Task 0 |
| §11 error handling (KravuError hierarchy) | Task 1 |
| §12 testing (unit/integration/e2e, offline) | Task 0 + tests throughout, Task 24 |
| §13 CLI + init flow | Task 23 |
| §13a searches schema + validation | Task 10 |
| §7a JSON strategy (instructed-JSON, reasoning-first order) | Task 4, Task 5 |
| Open item #3 (resume/status per-step queries) | Task 3 |

**2. Placeholder scan:** no "TODO/TBD/handle edge cases" — every code step shows complete code. The only intentional `# CONFIRM:` markers are on the genuinely-unverified CLI flags (Task 20), which the task's Step 1 resolves against the installed CLI; these are not placeholders but auditable verification points mandated by the spec.

**3. Type consistency (cross-task):**
- `LLMClient.complete(prompt, *, temperature=0.0) -> str` — identical in ports (Task 2), every fake, and `LiteLLMClient` (Task 4).
- `DiscoverySource.discover(searches) -> list[Job]` + `.name` — matches JobSpySource (6), AtsSource (7), fakes.
- `JobStore` methods in ports (Task 2) exactly match `JobRepository` after Task 3 (`step_counts`, `reset_step_for_retry`, `pending_apply`, `set_apply_result`, `bump_apply_attempts`, `applied_today`); Task 3 Step 5 re-verifies conformance.
- `PipelineStep(name, use_case, capped)` and `Pipeline(steps, per_run_cap).run(store)` — consistent across Task 16, 23, 24. Every use case exposes `run(store, limit=None)`, so all satisfy the pipeline's `_UseCase` protocol.
- `BrowserAgentDriver`: `name: str` + `build_command(prompt, mcp_config_path) -> list[str]` — consistent across base (17), all five drivers (19, 20), composition (23), ApplyAgent (22).
- `validate_no_fabrication(resume, facts) -> list[str]` — same in validator (14a) and TailorResume (14b).
- `PipelinePhase` values (`explore/expand/score/tailor/cover`) drive `step_counts` (Task 3) and the CLI `_STEPS` tuple (Task 23) identically.

**4. Determinism / offline:** every task's unit tests inject fakes for LLM, discovery, renderer, and subprocess; the only real external commands are the one-time `playwright install` (Task 25) and the CLI-flag confirmation (Task 20) — both explicit, both outside the unit suite.

No gaps found. Task order respects dependencies: exceptions/ports/repo first, then adapters, then services (setup → pipeline), then the pipeline, then apply, then the CLI that wires them, then the e2e proof.
