# kravu — Component Design

This document defines **what each component is for, what each file contains, and
where the business logic lives.** It is binding. It applies a *pragmatic* (loose)
Clean / Hexagonal architecture — we inherit the principles (modular, testable,
infra-independent core) without the dogmatic four-folder ceremony that makes
Python projects a nightmare to maintain.

## The one rule

> **Business logic never depends on infrastructure.**
> Stages (the core) know *what* to do. They reach the database and the LLM only
> through injected interfaces (ports). Swapping SQLite→Postgres or
> Gemini→OpenAI must not change a single line in a stage.

Dependencies point **inward**: CLI → pipeline → stages → (ports) → adapters.
Nothing in `stages/` or `models.py` imports `sqlite3`, `litellm`, `httpx`, or a
provider name.

## Layers (virtual — expressed as modules, not enforced folders)

| Layer | Module(s) | Purpose | May import |
|-------|-----------|---------|------------|
| **Interface** (driving adapter) | `cli.py` | Turn user commands into calls; render results. | pipeline, config, Rich |
| **Application** (orchestration) | `pipeline.py` | Run stages in dependency order, sequential. | stages, repository, config |
| **Domain logic** (the core) | `stages/*.py` | **All business logic lives here.** | models, ports (protocols) |
| **Domain models** | `models.py` | Pure data (`Profile`, `Job`, ...). No behavior with side effects. | stdlib only |
| **Ports** (interfaces) | `ports.py` | Protocols the core depends on (`LLMClient`, `JobStore`, `DiscoverySource`). | typing, models |
| **Infrastructure** (driven adapters) | `storage/`, `core/llm.py`, discovery/enrich fetchers | Concrete DB, LLM, HTTP, JobSpy. Implement ports. | anything external |
| **Cross-cutting** | `config.py`, `core/prompts.py`, `exceptions.py` | Config, prompt templates, error types. | as needed |

## Where the business logic resides — explicitly

**In the stages.** Each stage is a *service* that owns one business decision:

- `stages/discover.py` — how to turn a search into jobs; **dedupe rule**.
- `stages/enrich.py` — how to extract a full description; fallback strategy.
- `stages/score.py` — how to judge fit (prompt shape, score parsing, threshold).
- `stages/tailor.py` — how to rewrite a resume for a role **without fabricating**.
- `stages/cover.py` — whether a role needs a cover letter, and how to write it.

Business logic does NOT live in the CLI (that only parses/renders), in the
pipeline (that only sequences), in models (pure data), or in adapters (dumb I/O).

## Ports & Adapters (dependency inversion)

Stages depend on **protocols**, not concretions. Defined in `ports.py`:

- `JobStore` — the persistence port. Implemented by `storage.JobRepository`
  (SQLite). A future `PostgresJobRepository` implements the same port.
- `LLMClient` — the model port (`complete(prompt) -> str`). Implemented by
  `core.llm.LiteLLMClient`. Tests use a `FakeLLMClient`.
- `DiscoverySource` — the job-source port. Implemented by a JobSpy adapter; a
  future Apify adapter implements the same port.

**Injection:** adapters are constructed at the edge (in `cli.py` / a small
composition step) and passed into stages. Stages never construct their own
adapters. This is what makes every stage unit-testable with fakes and keeps the
core infra-free.

## What each file contains (v0.1 target layout)

```
src/kravu/
├── __init__.py          version
├── cli.py               Typer app: init / run / status. Wires adapters, calls pipeline, renders.
├── pipeline.py          Orchestrator: ordered stage execution, per-stage summary. No business rules.
├── models.py            Dataclasses: Profile, Job, ScoreResult, Stage. Pure data.
├── ports.py             Protocols: JobStore, LLMClient, DiscoverySource.
├── exceptions.py        KravuError hierarchy.
├── config.py            Paths, env loading, profile/searches loading, defaults.
├── core/
│   ├── llm.py           LiteLLMClient (implements LLMClient). Provider-agnostic.
│   └── prompts.py       Prompt templates for score/tailor/cover. Low-slop, no fabrication.
├── stages/
│   ├── base.py          Stage protocol/ABC: name, run(store, ...). Shared helpers.
│   ├── discover.py      DiscoverStage — uses DiscoverySource + JobStore.
│   ├── enrich.py        EnrichStage — fetch + parse full description.
│   ├── score.py         ScoreStage — LLMClient scores each job vs profile.
│   ├── tailor.py        TailorStage — LLMClient rewrites resume; fabrication guard.
│   └── cover.py         CoverStage — conditional cover letter.
├── discovery/
│   └── jobspy_source.py JobSpy adapter (implements DiscoverySource).
└── storage/
    ├── engine.py        SQLite connection/WAL.
    ├── schema.py        jobs table (state machine).
    └── repository.py    JobRepository (implements JobStore). All SQL here.
```

## SRP checklist (applied to every file)

For each file you must be able to answer in one sentence: *what is this
responsible for?* If the answer needs "and", split it. Concretely:
- A stage does business logic and orchestrates its ports — it does not open
  DB connections, build LLM clients, or format CLI output.
- An adapter does I/O — it holds no business rules.
- `models.py` holds data shapes — no DB, no network, no prompts.

## Data flow (one run)

```
cli.run()
  → build adapters (JobRepository, LiteLLMClient, JobSpySource) + load Profile
  → pipeline.run(stages, store, llm, source, profile, min_score)
       for stage in [discover, enrich, score, tailor, cover]:
           stage.run(...)                       # reads pending rows via JobStore,
                                                 # applies business logic (maybe via LLMClient),
                                                 # writes results back via JobStore
  → cli renders shortlist from store.shortlist(min_score)
```

## Note on the existing draft

`models.py`, `config.py`, `storage/*` already exist and conform. The additions
this doc mandates for the plan: introduce `ports.py` (protocols) and
`exceptions.py`, and ensure stages receive ports by injection rather than
importing adapters directly. The current `storage/__init__.py` re-exports concrete
classes — that's fine for the adapter package; stages still depend on the port.
```
