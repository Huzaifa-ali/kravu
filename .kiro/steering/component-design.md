# kravu — Component Design

This document defines **what each component is for, what each file contains, and
where the business logic lives.** It is binding.

kravu follows the **standard layered layout from _Architecture Patterns with
Python_ (Cosmic Python)** — `domain` / `services` / `adapters` / `entrypoints` —
the recognized reference structure for a responsibility-organized Python app.
We apply it pragmatically (no dogmatic ceremony), organized **by layer** because
kravu is a single cohesive domain (the job pipeline), not a multi-feature backend.

## The one rule (dependency direction)

> **Business logic never depends on infrastructure.** Dependencies point inward:
> `entrypoints → services → domain`, with `adapters` implementing `domain` ports.

The rule is mechanical and testable — decide where code lives by what it imports:

| If a file imports... | it belongs in... |
|----------------------|------------------|
| `typer`, `rich` (the CLI) | `entrypoints/` |
| `sqlite3`, `litellm`, `httpx`, `jobspy` (external tools) | `adapters/` |
| only `domain/` (models + ports) | `services/` |
| nothing outside the standard library | `domain/` |

## Layers

| Layer | Package | Purpose | May import |
|-------|---------|---------|------------|
| **Entrypoints** (driving adapters) | `entrypoints/` | Turn user commands into calls; render output. No business logic. | services, config, Typer, Rich |
| **Services** (use cases) | `services/` | **All business logic.** One unit = one business operation. Orchestrates ports. | domain |
| **Domain** | `domain/` | Pure business objects + the port protocols. No side effects. | stdlib only |
| **Adapters** (driven adapters) | `adapters/` | Concrete infrastructure: DB, LLM, HTTP, JobSpy. Implement domain ports. | anything external |
| **Cross-cutting** | `config.py`, `exceptions.py` | Config (12-factor env), error types. | as needed |

## Standard terminology (binding — used in code and docs)

We use recognized software-architecture nouns, not casual coinages:

| Concept | Standard term | Basis |
|---------|---------------|-------|
| The whole system | **Pipeline** | Pipes-and-Filters |
| Steps 1–5 collectively | **the workflow** (deterministic) | Anthropic agent taxonomy: workflow vs agent |
| One unit of business logic | **Use Case** (`ScoreJob`, `TailorResume`) | Clean Architecture |
| The sequencer | **Pipeline / Orchestrator** | — |
| Step 6 | **Apply Agent** (a Browser Agent) | agent taxonomy |
| Swappable LLM for step 6 | **Agent Driver** (Strategy) | GoF Strategy |
| Persistence contract | **Repository** (`JobStore` port) | Fowler PoEAA |
| LLM/DB/HTTP concretions | **Adapters** | Ports & Adapters |

We do NOT use the word "stage" in code. It may appear only informally in prose to
describe pipeline flow. The units are **Use Cases**.

## Where the business logic resides — explicitly

**In `services/`.** Each unit is a **Use Case** named as a verb-noun business
operation:

- `services/discover.py` → `DiscoverJobs` — turn a search into jobs; **dedupe rule**.
- `services/enrich.py` → `EnrichJob` — extract full description; fallback strategy.
- `services/score.py` → `ScoreJob` — judge fit (prompt shape, parsing, threshold).
- `services/tailor.py` → `TailorResume` — rewrite resume for a role, **no fabrication**.
- `services/cover_letter.py` → `WriteCoverLetter` — whether a role needs a letter, and write it.
- `services/pipeline.py` → `Pipeline` — the orchestrator: run the use cases in
  order. Sequencing only — it holds no business rules itself.

Business logic does NOT live in entrypoints (parse/render only), the pipeline
(sequencing only), domain models (pure data), or adapters (dumb I/O).

## Ports & Adapters (dependency inversion)

Services depend on **protocols** in `domain/ports.py`, never on concretions:

- `JobStore` — persistence port. Implemented by `adapters.repository.JobRepository`
  (SQLite). A future `PostgresJobRepository` implements the same port.
- `LLMClient` — model port (`complete(prompt) -> str`). Implemented by
  `adapters.llm.LiteLLMClient`. Tests use a `FakeLLMClient`.
- `DiscoverySource` — job-source port. Implemented by `adapters.jobspy_source`;
  a future Apify adapter implements the same port.

**Injection:** adapters are constructed at the edge (in `entrypoints/cli.py`, or a
small composition step) and passed into services. Services never construct their
own adapters — this keeps the core infra-free and unit-testable with fakes.

## File layout (v0.1 target)

```
src/kravu/
├── __init__.py            version
├── config.py              paths, env loading, profile/searches loading, defaults (12-factor)
├── exceptions.py          KravuError hierarchy
├── domain/
│   ├── __init__.py
│   ├── models.py          Profile, Job, ScoreResult, Stage enum. Pure data.
│   └── ports.py           Protocols: JobStore, LLMClient, DiscoverySource.
├── services/
│   ├── __init__.py
│   ├── pipeline.py        Orchestrator: ordered use-case execution. No business rules.
│   ├── discover.py        DiscoverJobs
│   ├── enrich.py          EnrichJob
│   ├── score.py           ScoreJob
│   ├── tailor.py          TailorResume
│   └── cover_letter.py    WriteCoverLetter
├── adapters/
│   ├── __init__.py
│   ├── db.py              SQLite engine + schema (connection, WAL).
│   ├── repository.py      JobRepository  → implements JobStore. All SQL here.
│   ├── llm.py             LiteLLMClient  → implements LLMClient. Provider-agnostic.
│   ├── prompts.py         Prompt templates for score/tailor/cover. Low-slop, no fabrication.
│   └── jobspy_source.py   JobSpy adapter → implements DiscoverySource.
└── entrypoints/
    ├── __init__.py
    └── cli.py             Typer app: init / run / status. Wires adapters, calls pipeline, renders.

tests/
├── conftest.py            shared fixtures (temp DB, fakes)
├── unit/                  domain + services with fakes — offline, deterministic
├── integration/          adapters against a temp SQLite / mocked HTTP
└── e2e/                   a full pipeline run end-to-end
```

## SRP checklist (applied to every file)

For each file you must answer in one sentence: *what is this responsible for?*
If the answer needs "and", split it. Concretely:
- A service does business logic and orchestrates its ports — it does not open DB
  connections, build LLM clients, or format CLI output.
- An adapter does I/O — it holds no business rules.
- `domain/models.py` holds data shapes — no DB, no network, no prompts.

## Data flow (one run)

```
entrypoints/cli.py :: run()
  → build adapters (JobRepository, LiteLLMClient, JobSpySource) + load Profile
  → services/pipeline.py :: run(use_cases, store, llm, source, profile, min_score)
       for use_case in [DiscoverJobs, EnrichJob, ScoreJob, TailorResume, WriteCoverLetter]:
           use_case.run(...)      # reads pending rows via JobStore,
                                   # applies business logic (maybe via LLMClient),
                                   # writes results back via JobStore
  → cli renders shortlist from store.shortlist(min_score)
```

## Migration note (from the earlier draft)

The earlier draft used `storage/`, `core/`, `stages/`. This is superseded by the
standard layout above. The plan will relocate:
`storage/*` → `adapters/{db,repository}.py`; `models.py` → `domain/models.py`;
add `domain/ports.py`, `exceptions.py`; new units live in `services/`; CLI in
`entrypoints/`. The underlying design (blackboard DB, repository, ports,
determinism) is unchanged — only the packaging vocabulary is aligned to the standard.
```
