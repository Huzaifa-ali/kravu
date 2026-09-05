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
  `ExploreJobs`, `ExpandJob`, `ScoreJobFit`, `TailorResume`, `DraftCoverLetter`.
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
                                          ExploreJobs → ExpandJob → ScoreJobFit
                                          → TailorResume → DraftCoverLetter
   each use case: read pending rows via JobStore → apply logic (maybe via
   LLMClient) → write results back  ──▶  SQLite jobs table (blackboard)
```

## 6. Data model

Single `jobs` table as a state machine, keyed by `url` (natural dedupe key). A row
is created by `ExploreJobs` and advances as each use case fills its columns.
Pending work for a use case = "input column set AND output column NULL". Columns
grouped by use case: discovery, enrichment, scoring, tailoring, cover.

Domain dataclasses (`domain/models.py`): `Profile` (with `resume_facts` as ground
truth and `compact_summary()` for prompts), `Job`, `ScoreResult`, and the
`PipelinePhase` enum (identifies each use case for orchestration/reporting).

## 7. The use cases (1–5, v0.1)

1. **ExploreJobs** — JobSpy across boards for the configured searches; insert new
   jobs; dedupe by URL.
2. **ExpandJob** — fetch each job's full description (httpx + parse; LLM
   fallback for unknown layouts). Record per-job errors; never crash the run.
3. **ScoreJobFit** — one focused LLM call per job: compact profile + this JD → fit
   1–10 + reasoning. Only jobs ≥ `min_score` proceed.
4. **TailorResume** — one LLM call per high-fit job: rewrite the resume for the
   role. Constrained to `resume_facts`; never fabricates. Writes a tailored file.
5. **DraftCoverLetter** — conditional: decide if the role needs a cover letter;
   if so, write a targeted one; otherwise mark not-needed.

Output: `kravu status` shows a ranked shortlist — high-fit jobs, best first, with
paths to tailored materials and the "why you fit" reasoning.

**Setup-time use cases (not part of the pipeline):**
- **BuildProfile** (`services/build_profile.py`) — takes raw resume text + the
  `LLMClient` and returns a structured `Profile` (keeping the raw text as
  `resume_facts`). Used by `kravu init`.
- **SuggestSearches** (`services/suggest_searches.py`) — takes the `Profile` + the
  `LLMClient` and proposes a `searches.yaml` (inferred target roles/seniority, and
  a conservative location). Output is validated against the searches schema (§13a)
  before saving; invalid proposals are defaulted/corrected, never written broken.
  Used by `kravu init`.

Both are use cases (business logic, testable with a fake LLM), kept out of the CLI,
but they do **not** run during `kravu run`.

## 7a. Use-case contracts

Precise input/output for each pipeline use case. LLM calls return **strict JSON**
(via LiteLLM's JSON/response-format support) so parsing is deterministic, not
regex-scraped from prose. Each contract lists: input, output, DB writes, failure.

### ExpandJob
- **Input:** a `Job` with `url` (and preview `description`), no `full_description`.
- **Behavior:** fetch the job page via httpx, then a 3-tier extraction cascade:
  (1) JSON-LD (`JobPosting` structured data via trafilatura),
  (2) targeted CSS selectors (selectolax) for known layouts,
  (3) trafilatura main-content extraction as a general fallback.
  Stop at the first tier that yields a non-trivial description (≥ a min length).
- **Output / DB:** on success → `full_description`, `apply_url` (if found),
  `enriched_at`. On failure (all tiers empty, HTTP error, timeout) → `enrich_error`
  set, `enriched_at` set; the job is skipped by later use cases. **No LLM call**
  in v0.1 (LLM-assisted extraction is a possible later enhancement, not default).
- **Give-up rule:** one attempt; a recorded `enrich_error` is terminal for v0.1.

### ScoreJobFit
- **Input:** `Profile.compact_summary()` + the job's `full_description`.
- **LLM output (strict JSON):** `{"score": <int 1-10>, "reasoning": <str>,
  "missing_skills": [<str>, ...]}` → maps to `ScoreResult`.
- **DB:** `fit_score` = score, `score_reasoning` = reasoning, `scored_at`.
  (`missing_skills` folded into reasoning text for v0.1; not a separate column.)
- **Threshold:** only jobs with `fit_score >= min_score` proceed to TailorResume.
- **Robustness:** if the model returns an out-of-range or unparseable score, retry
  once with a stricter instruction; on second failure record score `0` +
  reasoning "unparseable" (the job simply won't clear the threshold). Never crash.

### TailorResume  (fabrication-guarded — safety-critical)
- **Input:** `Profile.resume_facts` (ground truth) + `full_description`.
- **LLM output (strict JSON):** `{"tailored_resume": <str>,
  "claims": [<str>, ...]}` — the rewrite, plus the list of concrete factual claims
  (employers, titles, dates, metrics, skills) the rewrite asserts.
- **Fabrication guard (two layers):**
  1. **Prompt constraint:** the model is instructed it may reorder, re-emphasize,
     and rephrase, but must use ONLY facts present in `resume_facts`; inventing
     anything is forbidden.
  2. **Post-generation verification:** kravu checks each returned `claim` is
     grounded in `resume_facts`. v0.1 uses a deterministic check — key tokens of a
     claim (company names, numbers/metrics, degree/title terms) must appear in
     `resume_facts` (normalized). Any claim that isn't grounded ⇒ the tailoring is
     **rejected**: bump `tailor_attempts`, retry once with the offending claim
     called out; if it fails again, **do not write a tailored file** and leave the
     job un-tailored (it still appears in the shortlist with the original resume).
- **DB:** on success → `tailored_resume_path`, `tailored_at`. On repeated failure →
  `tailor_attempts` incremented, no path written.
- This makes "never fabricate" (principles.md) an *enforced mechanism*, not just a
  prompt request.

### DraftCoverLetter  (conditional)
- **Input:** `Profile` + `full_description` (+ the tailored resume if present).
- **Need decision (LLM, strict JSON):** `{"needed": <bool>, "reason": <str>,
  "cover_letter": <str|null>}`. The model decides `needed` from signals in the JD
  (explicit "cover letter required/optional", application form expectations); if
  `needed` is false, `cover_letter` is null.
- **DB:** `cover_needed` = needed; if needed → write file, set `cover_letter_path`;
  always set `cover_at`. `bump cover_attempts` on failure (cap enforced by repo).
- Same fabrication discipline as TailorResume applies to any factual claims.

### Output format (v0.1)
- Tailored resumes and cover letters are written as **Markdown** (`.md`) under
  `~/.kravu/tailored/` and `~/.kravu/cover_letters/`, named by a slug of
  company+title. **PDF rendering is v0.2** (per roadmap), so v0.1 output is
  review-and-send Markdown/text the user can convert or paste.

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
- **Open item — apply-site targeting:** *which* sites/ATSes the Apply Agent submits
  to (e.g. Workday portals, direct career pages, greenhouse/lever), how to classify
  manual-only ATSes, and which to block, is an open design question to be settled
  when this phase is built. This is distinct from discovery `sites` (§13a).

## 9. LLM usage, providers & memory

- **LiteLLM**; model chosen via `KRAVU_MODEL`. Each call is small, single-job,
  structured. No conversation history accumulates; no external memory framework
  (Mem0/Letta/Zep). Durable memory is the DB.
- **kravu never handles API keys.** Keys are the user's responsibility, set in the
  environment (or `~/.kravu/.env`) *before* using kravu — standard 12-factor. `init`
  selects the *provider/model*; it never prompts for or stores a key.
- **Provider/model options** (defaults current as of 2026-09-04; model strings move
  frequently — all overridable via `KRAVU_MODEL`):

| Provider (in `init`) | `KRAVU_MODEL` | Key (hard-stop if missing) | Note |
|----------------------|---------------|----------------------------|------|
| **Gemini — Gemma 4 31B (default)** | `gemini/gemma-4-31b` | `GEMINI_API_KEY` | ⚠️ hosted model string UNVERIFIED — confirm in Google AI Studio; override if it differs |
| Ollama — Qwen (small) | `ollama/qwen3.5:4b` | none (local) | ~3.4GB, runs on modest hardware |
| Ollama — Qwen (latest) | `ollama/qwen3.8:27b` | none (local) | ~18GB, needs a strong GPU |
| Anthropic | `anthropic/claude-sonnet-5` | `ANTHROPIC_API_KEY` | |
| OpenAI | `gpt-6-astra` | `OPENAI_API_KEY` | |

- **Preflight (hard-stop):** when a key-requiring provider is selected, kravu checks
  the matching env var. If absent, it stops with an actionable message naming the
  exact variable to set — it does **not** prompt for the key. Local (Ollama)
  providers need no key.

## 10. Technology stack & versions

Latest stable from PyPI as of 2026-09-04. Pinning strategy: compatible-release
ranges (`>=x,<next-major`); `uv.lock` captures exact resolved versions.

**Runtime (v0.1 workflow):**

| Package | Version | Used by |
|---------|---------|---------|
| `python-jobspy` | 1.1.82 | ExploreJobs |
| `litellm` | 1.99.0 | ScoreJobFit / TailorResume / DraftCoverLetter |
| `typer` | 0.27.2 | entrypoints/cli |
| `rich` | 15.0.0 | CLI output |
| `httpx` | 0.28.1 | ExpandJob (fetch) |
| `selectolax` | 0.4.11 | ExpandJob (HTML/CSS parse) |
| `trafilatura` | 2.2.0 | ExpandJob (content/JSON-LD extraction) |
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

## 13. CLI surface & the `init` flow (v0.1)

**Prerequisite (user, before kravu):** set your provider API key in the
environment or `~/.kravu/.env` (e.g. `GEMINI_API_KEY=...`). kravu never collects
keys. Local Ollama providers need no key. `.env.example` documents this.

**Commands:**
- `kravu init` — one-time setup wizard (details below).
- `kravu run [phases...]` — run the workflow (default: all use cases 1–5).
- `kravu status` — pipeline stats + ranked shortlist.

**`kravu init` flow:**

1. **Resume:** ask for a path to the user's CV (PDF/DOCX/TXT); extract raw text.
2. **Provider/model:** user picks from the table in §9 (default:
   `gemini/gemma-4-31b`). Write the chosen string to config as `KRAVU_MODEL`.
   **The key is never requested or stored.**
3. **Preflight (hard-stop):** verify the matching key env var exists for the chosen
   provider (skip for Ollama). If missing, print the exact variable to set and
   **stop** — do not continue, do not prompt for the key.
4. **Structure resume (`BuildProfile`):** one LLM call turns the raw resume text
   into a structured `Profile`; keep the raw text as `resume_facts` (ground truth).
5. **Suggest searches (`SuggestSearches`):** from the `Profile`, one LLM call
   proposes a `searches.yaml` (inferred target roles/seniority; conservative
   location). Validate against the schema (§13a) before proposing.
6. **Review both:** show the extracted `Profile` **and** the proposed searches;
   user chooses **keep** or **edit**; save `~/.kravu/profile.json` and
   `~/.kravu/searches.yaml`.
7. Done — instruct the user to run `kravu run`.

`init` is **safe to re-run**: if files exist, it asks overwrite/edit/keep rather
than clobbering. Setup uses two LLM calls (BuildProfile + SuggestSearches).
Business logic lives in those use cases, not in the CLI.

Note: because search targets are *inferred from a resume*, they can be wrong (e.g.
a user pivoting careers). Location especially is weak from a CV — `SuggestSearches`
proposes it conservatively (resume location or "Remote") and the review step (6)
must make it easy to correct.

## 13a. `searches.yaml` schema

One or more named searches. `ExploreJobs` runs each and dedupes results by URL.
Fields map directly onto JobSpy's `scrape_jobs()`; the YAML key `sites` maps to
JobSpy's `site_name`.

```yaml
# ~/.kravu/searches.yaml
defaults:                      # merged into every search unless overridden
  sites: [indeed, linkedin, zip_recruiter, google]
  results_wanted: 25
  hours_old: 168               # last 7 days
  description_format: markdown

searches:
  - name: devops-us            # kravu label (status/logs); not sent to JobSpy
    search_term: "DevOps engineer"
    location: "United States"
    country_indeed: USA        # REQUIRED when 'indeed' or 'glassdoor' is in sites
    is_remote: true
    # job_type: fulltime       # fulltime | parttime | contract | internship
    # distance: 50             # miles
    # google_search_term: "..."# recommended when 'google' is a site
```

**Field mapping / notes:**
- `sites` → JobSpy `site_name`. Allowed: indeed, linkedin, zip_recruiter, google,
  glassdoor, bayt, bdjobs, naukri.
- Passed through to JobSpy: `search_term`, `location`, `results_wanted`,
  `hours_old`, `job_type`, `is_remote`, `distance`, `google_search_term`,
  `country_indeed`, `description_format`.
- `name` is kravu-only.

**Validation (hard-error at load; consistent with the hard-stop philosophy):**
- If `indeed` or `glassdoor` is in `sites`, `country_indeed` is **required**.
- **Indeed** allows only ONE of: `hours_old` / (`job_type` + `is_remote`) /
  `easy_apply`. Conflicts are a hard error.
- **LinkedIn** allows only ONE of: `hours_old` / `easy_apply`.
- If `google` is a site and `google_search_term` is absent, kravu derives one from
  `search_term` + `location`.
- Safe defaults keep first runs small/fast (`results_wanted: 25`, `hours_old: 168`) —
  never a mass blast (co-pilot principle).

> **Deferred / open:** the `sites` here are *discovery* sources (where jobs are
> found). *Which sites kravu submits applications to* is a separate concern of the
> Apply Agent (use case 6) and is an open item — see §8. The two are not conflated.

## 14. Resolved decisions

- **License:** MIT. **Author:** Muhammad Huzaifa Ali (no email for now).
- **Package/command name:** `kravu`.
- **Unit terminology:** Use Case (option A), verb-noun class names.
- **Pinning:** compatible-release ranges; `uv.lock` for exact reproducibility.
- **API keys:** user-managed in the environment; kravu never collects/stores keys.
  `init` selects provider/model only, with a hard-stop preflight if the key is absent.
- **Default model:** `gemini/gemma-4-31b` (string unverified against the hosted API —
  flagged in §9; overridable via `KRAVU_MODEL`).

## 15. Roadmap (post-v0.1)

- v0.2: PDF rendering of materials; richer `status`.
- v0.3+: the Apply Agent (use case 6) — Playwright MCP + pluggable Agent Driver
  (one agent first), human-approval gate by default.

## 16. Note on already-written code

`domain/models.py`, `config.py`, `adapters/{db,repository}.py` exist and conform to
this spec and the steering. The implementation plan will add `exceptions.py`,
`domain/ports.py`, the `services/` use cases (incl. setup-time `BuildProfile` and
`SuggestSearches`), adapters (`llm`, `prompts`, `jobspy_source`), and
`entrypoints/cli.py`, wiring use cases to ports by injection.
