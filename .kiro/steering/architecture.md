# kravu — Architecture Principles

These rules govern all code in this project. They exist to keep kravu robust,
maintainable, and free of AI slop. Deviating from them requires an explicit,
documented reason.

## What kravu is

A **CLI-fronted, database-coordinated pipeline** (stages 1–5) with a **pluggable
browser agent isolated at the final stage** (stage 6, later phase). It is *not*
an agent or a multi-agent system for stages 1–5. It is a deterministic pipeline.

Classification, precisely:
- Stages 1–5 (discover → enrich → score → tailor → cover): a **deterministic
  pure-Python pipeline**. No LLM controls the flow.
- Stage 6 (apply): an **agent at the edge**, isolated because form-filling on
  arbitrary sites genuinely needs open-ended reasoning. Everything else does not.

## Core patterns (do not reinvent these)

- **Pipes and Filters** — each stage is one filter with a single responsibility.
- **Blackboard** — stages coordinate ONLY through the database. A stage reads the
  rows that need its work and writes its results back. Stages do not call each
  other directly.
- **Repository** — all SQL lives in `storage/repository.py`. Stages depend on the
  repository interface, never on raw SQL or the DB driver. This is what keeps
  SQLite swappable for Postgres later.
- **Adapter / Strategy** — LLM providers (and, later, browser-agent drivers) sit
  behind one interface. No provider name is hardcoded in stage logic.

## Determinism rule (the reason stages 1–5 are pure Python)

LLM calls introduce variance. We remove variance at the root by keeping the
pipeline's control flow deterministic. The LLM is used ONLY as a focused text
function inside a stage (score this / rewrite that), never to decide what runs
next. Each LLM call operates on ONE job with a SMALL, focused prompt — never a
giant blob — so we avoid context drift / "lost in the middle" by construction.

## Memory rule

- **Durable memory = the database.** Job state lives in SQLite. It survives
  restarts. Nothing important is held in an LLM's context between steps.
- **No external memory framework** (Mem0/Letta/Zep) in the core. Our state is
  structured and tabular; a relational DB is the correct store. Semantic/episodic
  memory is a possible future phase, not core.
- **Stage 6 delegates working memory to the driving agent** (Claude Code, Kiro,
  etc.). We do not hand-roll agent working-memory management.

## File and module discipline

- Small, focused files with one clear responsibility. If a file grows unwieldy,
  split by responsibility (not by technical layer).
- src-layout: all code under `src/kravu/`.
- A unit must be understandable without reading its internals, and its internals
  must be changeable without breaking consumers.
