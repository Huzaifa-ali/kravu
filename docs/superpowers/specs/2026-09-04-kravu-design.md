# kravu — Design Spec

**Date:** 2026-09-04
**Status:** Draft for review

---

## 1. Summary

kravu is a local-first, open-source job-hunting pipeline. Given a user's resume
and a search target, it discovers matching roles, scores each against the CV,
tailors the resume per role, and produces a ranked shortlist with prepared
materials. It is a **co-pilot, not a spam-bot**: v0.1 prepares; it does not
auto-submit.

## 2. Goals and non-goals

**Goals (v0.1)**
- Turn a resume + a search into a ranked, tailored shortlist of good-fit jobs.
- Zero-friction: value from a resume + one free-tier LLM key + one command.
- Robust and low-risk: no browser automation, cannot get accounts banned.
- Provider-agnostic LLM; local SQLite storage.

**Non-goals (v0.1)**
- Autonomous form submission / auto-apply (deferred to a later opt-in phase).
- Postgres, multi-user, or hosted/service deployment.
- Harvesting private contact data or mass outreach.

## 3. Background & research

The design is grounded in study of the reference project and current practice:

- **ApplyPilot** (`Pickle-Pixel/ApplyPilot`, AGPL-3.0) — the closest mature
  reference. Its real structure (read from source): a CLI-fronted **deterministic
  pipeline** for stages 1–5 coordinated through a single SQLite `jobs` table
  (blackboard), plus a **separate agent** for auto-apply that shells out to the
  Claude Code CLI driving Playwright MCP. It is not multi-agent. Discovery uses
  **JobSpy**, not the LinkedIn API.
- **LinkedIn official API** — confirmed unsuitable: no public/self-serve people or
  company search; job-posting API is partner-gated and closed to new partners.
  Discovery therefore uses JobSpy (public job-board data).
- **Agent memory (2026)** — Mem0/Letta/Zep solve *cross-session fact
  accumulation* for conversational agents and add infra weight (vector/graph DBs).
  kravu's state is structured and tabular, so a relational DB is the correct store.
  The "lost in the middle" / context-drift problem is avoided by construction:
  each LLM call is small and operates on one job.
- **Headless agent CLIs** — for the later stage-6 driver layer, verified that
  Claude Code (`-p --mcp-config`), Codex (`exec --json`, TOML MCP config),
  Gemini CLI (`-p --output-format json`), Cursor (`-p --output-format
  stream-json --approve-mcps`), and Kiro (`--no-interactive`) all support headless
  execution + a custom MCP config. The pluggable-driver design is therefore
  feasible, but is explicitly out of scope for v0.1.

## 4. Architecture

**Classification:** CLI-fronted, database-coordinated deterministic pipeline
(stages 1–5). Stage 6 (agent-at-the-edge auto-apply) is a later phase.

**Patterns:** Pipes-and-Filters (stages), Blackboard (the DB), Repository
(storage access), Adapter/Strategy (LLM providers). See
`.kiro/steering/architecture.md` for the binding rules.

```
CLI (Typer)
  └─ pipeline.py  (deterministic orchestrator; plain Python, no LLM in control flow)
       stage 1 discover ─┐
       stage 2 enrich    │  each stage: read pending rows from DB → do work → write back
       stage 3 score     ├─▶  storage/repository.py  ──▶  SQLite jobs table (blackboard)
       stage 4 tailor    │
       stage 5 cover ────┘
  core/llm.py    (LiteLLM adapter — any provider; used only inside stages 3–5)
  core/prompts.py(low-slop prompt templates)
```

## 5. Data model

Single `jobs` table as a state machine, keyed by `url` (natural dedupe key). A row
is created at discovery and advances as each stage fills its columns. Pending work
for a stage = "input column set AND output column NULL". Columns grouped by stage:
discovery, enrichment, scoring, tailoring, cover. (See `storage/schema.py`.)

Dataclasses (`models.py`): `Profile` (with `resume_facts` as ground truth and a
`compact_summary()` for prompts), `Job`, `ScoreResult`, `Stage` enum.

## 6. The stages

1. **discover** — JobSpy across boards for the configured searches; insert new
   jobs, dedupe by URL.
2. **enrich** — fetch each job's full description (httpx + parse; LLM fallback for
   unknown layouts). Record per-job errors, don't crash the run.
3. **score** — one focused LLM call per job: compact profile + this JD → fit 1–10
   + reasoning. Only jobs ≥ `min_score` proceed.
4. **tailor** — one LLM call per high-fit job: rewrite the resume for the role.
   Constrained to `resume_facts`; never fabricates. Writes a tailored resume file.
5. **cover** — conditional: decide if the role needs a cover letter; if so, write
   a targeted one. Otherwise mark not-needed.

Output: `kravu status` / shortlist view — ranked high-fit jobs with paths to
tailored materials and the "why you fit" reasoning.

## 7. LLM usage & memory

- LiteLLM; model chosen via `KRAVU_MODEL` (default `gemini/gemini-2.0-flash`).
- Each call is small, single-job, structured. No conversation history is
  accumulated; no external memory framework. Durable memory is the DB.

## 8. Error handling

- Per-job errors are recorded on the row (`enrich_error`, attempt counters) and
  the run continues. Attempt caps prevent infinite retry loops.
- Missing profile/keys → clear, actionable CLI errors (run `kravu init`).

## 9. Testing

- TDD. Unit tests mock LLM and network; suite runs offline and deterministically.
- Storage tests use a temp SQLite file. Stage tests inject a fake repository and a
  fake LLM.

## 10. CLI surface (v0.1)

- `kravu init` — wizard: create `profile.json` (from a resume file), `searches.yaml`, `.env`.
- `kravu run [stages...]` — run the pipeline (default: all of 1–5).
- `kravu status` — pipeline stats + ranked shortlist.

## 11. Open decisions (to confirm during planning)

- **License:** MIT (max adoption) vs AGPL-3.0 (protects against closed SaaS
  clones). *Pending user decision.*
- **Author metadata** for `pyproject.toml`. *Pending user input.*

## 12. Roadmap (post-v0.1)

- v0.2: PDF rendering of materials; richer `status`/dashboard.
- v0.3+: opt-in stage-6 auto-apply — Playwright MCP + pluggable agent driver
  (start with one agent), human-approval gate by default.

## 13. Note on already-drafted code

`src/kravu/{__init__,models,config}.py` and `src/kravu/storage/*` were drafted
before this spec. They are to be **validated against this spec and the steering
files during planning**, not treated as final. Anything inconsistent is revised.
