# kravu — Specification

**Date:** 2026-09-04
**Status:** Draft for review
**Steering:** This spec is written against the binding steering documents in
`.kiro/steering/` (`stack.md`, `coding-standards.md`, `architecture.md`,
`principles.md`, `component-design.md`). Where this spec and steering overlap,
steering governs; this spec adds the concrete specification.

---

## 1. Summary

kravu is a local-first, open-source job-hunting **pipeline**. Given a user's
resume and a search target, it discovers matching roles, scores each against the
CV, tailors the resume per role, and produces a ranked shortlist with prepared
materials. It is a **co-pilot, not a spam-bot**: v0.1 prepares; it does not
auto-submit.

## 2. Terminology (standard, binding)

We use recognized software-architecture terms, not casual labels:

- **Pipeline** — the whole system (Pipes-and-Filters).
- **Workflow** — the deterministic phase (use cases 1–5). Per the standard
  workflow-vs-agent distinction: a workflow runs predetermined steps; an agent
  directs its own process.
- **Use Case** — one unit of business logic (Clean Architecture), named verb-noun:
  `SourceJobs`, `FetchJobDetails`, `ScoreJobFit`, `TailorResume`, `DraftCoverLetter`.
- **Pipeline (Orchestrator)** — sequences the use cases; holds no business rules.
- **Apply Agent** — use case 6, a **Browser Agent** (autonomous, deferred phase).
- **Agent Driver** — the swappable LLM/coding-agent that powers the Apply Agent
  (Strategy pattern).
- **Repository** — the persistence contract (`JobStore` port); **Adapters** — the
  concrete infrastructure (SQLite, LiteLLM, HTTP, JobSpy).

"Stage" is not used in code; it may appear informally in prose only.

## 3. Goals and non-goals

**Goals (v0.1)**
- Turn a resume + a search into a ranked, tailored shortlist of good-fit jobs.
- Zero-friction: value from a resume + one free-tier LLM key + one command.
- Robust and low-risk: no browser automation, cannot get accounts banned.
- Provider-agnostic LLM; local SQLite storage.

**Non-goals (v0.1)**
- The Apply Agent (use case 6) — designed here but deferred to a later phase.
- Postgres, multi-user, or hosted/service deployment.
- Harvesting private contact data or mass outreach.

## 4. The deterministic workflow vs. the agent (why the split)

The core design decision: **use cases 1–5 are a deterministic workflow (pure
Python, no LLM in control flow); use case 6 is an agent.** The reason is variance
control. LLM-directed control flow introduces non-determinism ("drift"). We remove
variance at the root by keeping the workflow deterministic and using the LLM only
as a focused text function inside a use case (score this / rewrite that) — one job
per call, small prompt, so no context drift by construction. The single place that
genuinely needs open-ended reasoning — filling arbitrary web forms — is isolated
as the Apply Agent, where variance is expected and contained.

## 5. Architecture

CLI-fronted, database-coordinated deterministic **workflow** (use cases 1–5), with
an isolated **agent** at use case 6 (deferred). Patterns: Pipes-and-Filters,
Blackboard (the DB), Repository, Ports-and-Adapters (pragmatic hexagonal —
business logic in `services/`, infrastructure behind injected ports). Standard
Cosmic Python layout: `domain` / `services` / `adapters` / `entrypoints`. Full
component responsibilities and file layout: `.kiro/steering/component-design.md`.

```
entrypoints/cli.py   (Typer)  →  services/pipeline.py (Orchestrator)
   builds adapters, loads Profile        runs use cases in order:
                                          SourceJobs → FetchJobDetails → ScoreJobFit
                                          → TailorResume → DraftCoverLetter
   each use case: read pending rows via JobStore → apply logic (maybe via
   LLMClient) → write results back  ──▶  SQLite jobs table (blackboard)
```

## 6. Data model

Single `jobs` table as a state machine, keyed by `url` (natural dedupe key). A row
is created by `SourceJobs` and advances as each use case fills its columns.
Pending work for a use case = "input column set AND output column NULL". Columns
grouped by use case: discovery, enrichment, scoring, tailoring, cover.

Domain dataclasses (`domain/models.py`): `Profile` (with `resume_facts` as ground
truth and `compact_summary()` for prompts), `Job`, `ScoreResult`, and the
`PipelinePhase` enum (identifies each use case for orchestration/reporting).

## 7. The use cases (1–5, v0.1)

1. **SourceJobs** — JobSpy across boards for the configured searches; insert new
   jobs; dedupe by URL.
2. **FetchJobDetails** — fetch each job's full description (httpx + parse; LLM
   fallback for unknown layouts). Record per-job errors; never crash the run.
3. **ScoreJobFit** — one focused LLM call per job: compact profile + this JD → fit
   1–10 + reasoning. Only jobs ≥ `min_score` proceed.
4. **TailorResume** — one LLM call per high-fit job: rewrite the resume for the
   role. Constrained to `resume_facts`; never fabricates. Writes a tailored file.
5. **DraftCoverLetter** — conditional: decide if the role needs a cover letter;
   if so, write a targeted one; otherwise mark not-needed.

Output: `kravu status` shows a ranked shortlist — high-fit jobs, best first, with
paths to tailored materials and the "why you fit" reasoning.

## 8. Use case 6 — the Apply Agent (designed, deferred)

Autonomous browser agent that fills and (optionally) submits an application form.
Isolated because arbitrary web forms need open-ended reasoning. **Deferred to a
later phase; not a v0.1 runtime dependency.** Design:

- **Browser:** Playwright drives a real Chrome/Chromium.
- **Tool protocol:** `@playwright/mcp` (Microsoft's Playwright MCP server) exposes
  browser actions (navigate, snapshot, click, type, upload) as MCP tools.
- **Agent Driver (pluggable):** a coding agent drives the browser via its headless
  CLI and manages its own memory/context. Verified invocations:
  Claude Code (`claude -p --mcp-config`, JSON config),
  Codex (`codex exec --json`, **TOML** config),
  Gemini CLI (`gemini -p --output-format json`),
  Cursor (`cursor-agent -p --output-format stream-json --approve-mcps`),
  Kiro (`kiro --no-interactive`). Config format differs per agent (Codex=TOML,
  others=JSON) — encapsulated in each driver.
- **Result protocol:** the agent prints an agent-independent final line
  (`RESULT:APPLIED` / `RESULT:FAILED:<reason>` / `RESULT:CAPTCHA`), which the
  runner parses.
- **Process control:** Python `subprocess` runner spawns browser + agent per job,
  captures output, enforces timeout, records outcome + attempts to the DB.
- **Safety:** **human-approval gate is the default** (prepare + queue; user
  approves before submit). Auto-submit is opt-in.
- **Memory:** delegated to the driving agent. kravu builds no working-memory layer.

## 9. LLM usage & memory

- LiteLLM; model via `KRAVU_MODEL` (default `gemini/gemini-2.0-flash`).
- Each call is small, single-job, structured. No conversation history accumulates;
  no external memory framework (Mem0/Letta/Zep). Durable memory is the DB.

## 10. Technology stack & versions

Latest stable from PyPI as of 2026-09-04. Pinning strategy: compatible-release
ranges (`>=x,<next-major`); `uv.lock` captures exact resolved versions.

**Runtime (v0.1 workflow):**

| Package | Version | Used by |
|---------|---------|---------|
| `python-jobspy` | 1.1.82 | SourceJobs |
| `litellm` | 1.99.0 | ScoreJobFit / TailorResume / DraftCoverLetter |
| `typer` | 0.27.2 | entrypoints/cli |
| `rich` | 15.0.0 | CLI output |
| `httpx` | 0.28.1 | FetchJobDetails (fetch) |
| `selectolax` | 0.4.11 | FetchJobDetails (HTML/CSS parse) |
| `trafilatura` | 2.2.0 | FetchJobDetails (content/JSON-LD extraction) |
| `pyyaml` | 6.0.3 | searches.yaml |
| `python-dotenv` | 1.2.3 | .env loading |

**Dev/tooling:** `pytest` 9.1.1, `ruff` 0.16.6, `mypy` 2.3.1.
**Build backend:** `hatchling` 1.32.0.
**Deferred (use case 6, later phase):** Playwright + `@playwright/mcp` (npx) + the
chosen agent CLI — not in v0.1 `dependencies`.

**`pyproject.toml` shape (PEP 621, src-layout):**

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
    "httpx>=0.28,<1",
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
```

## 11. Error handling

- Per-job errors are recorded on the row (`enrich_error`, attempt counters) and the
  run continues. Attempt caps prevent infinite retry loops.
- Missing profile/keys → clear, actionable CLI errors (run `kravu init`).
- Typed exception hierarchy in `kravu/exceptions.py` (`KravuError` base).

## 12. Testing

- TDD. Unit tests mock LLM and network; the suite runs offline and
  deterministically. Layout: `tests/{unit,integration,e2e}` with shared
  `conftest.py` (temp SQLite, fakes).
- Use cases are tested with a fake `JobStore` and a fake `LLMClient`.

## 13. CLI surface (v0.1)

- `kravu init` — wizard: create `profile.json` (from a resume file),
  `searches.yaml`, `.env`.
- `kravu run [phases...]` — run the workflow (default: all use cases 1–5).
- `kravu status` — pipeline stats + ranked shortlist.

## 14. Resolved decisions

- **License:** MIT. **Author:** Muhammad Huzaifa Ali (no email for now).
- **Package/command name:** `kravu`.
- **Unit terminology:** Use Case (option A), verb-noun class names.
- **Pinning:** compatible-release ranges; `uv.lock` for exact reproducibility.

## 15. Roadmap (post-v0.1)

- v0.2: PDF rendering of materials; richer `status`.
- v0.3+: the Apply Agent (use case 6) — Playwright MCP + pluggable Agent Driver
  (one agent first), human-approval gate by default.

## 16. Note on already-written code

`domain/models.py`, `config.py`, `adapters/{db,repository}.py` exist and conform to
this spec and the steering. The implementation plan will add `exceptions.py`,
`domain/ports.py`, the `services/` use cases, adapters (`llm`, `prompts`,
`jobspy_source`), and `entrypoints/cli.py`, wiring use cases to ports by injection.
