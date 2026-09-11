<div align="center">

# kravu

***A local-first, open-source job-hunting pipeline.*** Point it at your resume and a
search, and it discovers matching roles, scores each one against your CV, and
hands you a tailored resume plus a ranked shortlist of the jobs actually worth
your time — so you spend your effort applying, not searching.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Lint: Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![CI](https://github.com/Huzaifa-ali/kravu/actions/workflows/ci.yml/badge.svg)](https://github.com/Huzaifa-ali/kravu/actions/workflows/ci.yml)
![Status: v0.1 dev](https://img.shields.io/badge/status-v0.1%20dev-orange.svg)

</div>

> kravu is a **co-pilot, not a spam-bot.** It prepares tailored materials and a
> ranked shortlist for you to review. Auto-apply is opt-in and human-gated by
> default — it never blasts applications.

---

## Why

Job hunting for engineers is mostly mechanical: find roles, read each JD, judge
fit, re-tailor the resume, repeat. kravu automates the mechanical 80% and leaves
the decisions — and the final send — to you.

## Features

- **Multi-board discovery** — Finds roles across job boards via JobSpy and, optionally, company ATS boards (Greenhouse, Lever, Ashby), deduped by normalized URL.
- **Target-aware fit scoring** — An LLM rates each job 1–10 against your actual resume facts with an explicit rubric; only high-fit roles move forward.
- **Per-role resume tailoring** — Rewrites your resume for each job and reorganizes and re-emphasizes your real experience, guarded so it **never fabricates** skills, employers, or metrics.
- **Conditional cover letters** — Drafts a targeted letter only when the role needs one (or always/never, your choice), with the same zero-fabrication guard.
- **Human-gated auto-apply** — An opt-in browser agent (`kravu apply`) fills applications and, by default, waits for your approval before submitting — with a daily cap.
- **Local-first and provider-agnostic** — One SQLite file, no server or account; any LLM via LiteLLM (Gemini free tier by default, or OpenAI / Anthropic / Ollama / Cohere).

<!-- TODO: add a terminal demo GIF of `kravu run` → `kravu status` here (asciinema/vhs, <5MB, centered) -->

## How it works

kravu is a **deterministic pipeline** of independent stages coordinated through a
local SQLite database (a blackboard). Each stage reads the rows that need its
work, does one thing, and writes its result back — so runs are idempotent and
resumable.

| Stage | What happens |
|-------|--------------|
| 1. **explore** | Find postings across boards (JobSpy + optional ATS), dedupe by normalized URL |
| 2. **expand**  | Render each job page and extract the full description (JSON-LD → CSS → LLM fallback) |
| 3. **score**    | LLM rates fit 1–10 against your profile; only jobs ≥ your threshold proceed |
| 4. **tailor**   | LLM rewrites your resume per job — reorganizes and emphasizes, never fabricates |
| 5. **cover**    | LLM writes a targeted cover letter (per your policy) |
| 6. **apply**    | *(opt-in)* A browser agent submits applications, human-approved by default |

Stages 1–5 run with `kravu run` and produce a ranked shortlist plus tailored
materials you review and send yourself. Stage 6 is a separate, explicit
`kravu apply` because it has real-world side effects.

The LLM is used only as a focused text function (score this / rewrite that), one
job per call with a small prompt — never a giant blob — so control flow stays
deterministic and drift-free. Within a stage, jobs are processed concurrently by
a bounded worker pool (see `KRAVU_WORKERS` below) to overlap the network and LLM
waits; the results are identical to a serial run. The single place that genuinely
needs open-ended reasoning, filling arbitrary web forms, is isolated in stage 6.

## Quick start

```bash
uv sync --extra dev                             # install dependencies
uv run python -m playwright install chromium    # one-time browser download
                                                #   (used by enrich + the Apply Agent)
```

Set your provider key in the environment or `~/.kravu/.env` (e.g.
`GEMINI_API_KEY=...`) — **kravu never stores keys.** Then:

```bash
uv run kravu init      # extract your resume, pick a model, propose searches
uv run kravu run       # explore → expand → score → tailor → cover
uv run kravu status    # per-step counts + your ranked shortlist
```

## Commands

| Command | What it does |
|---------|--------------|
| `kravu init` | One-time setup: read your resume, pick a provider/model, propose searches |
| `kravu run` | Run the full pipeline over all outstanding work (idempotent, safe to re-run). `--workers N` sets per-step concurrency |
| `kravu resume <step>` | Retry the failed/pending jobs at a step (`explore`\|`expand`\|`score`\|`tailor`\|`cover`), then continue forward (`--workers N` supported) |
| `kravu status` | Per-step counts (done / pending) plus your ranked shortlist |
| `kravu clean` | Reset the workspace: clear all jobs, tailored resumes, cover letters, and logs (asks first; keeps your profile, searches, and keys) |
| `kravu apply` | Run the gated Apply Agent over ready jobs — human-approval by default (`--auto` to opt in, `--daily-cap N`) |

## Configuration

- **Model** — set `KRAVU_MODEL` (e.g. `gemini/gemma-4-26b-a4b-it`,
  `ollama/qwen3.5:4b`, `anthropic/claude-sonnet-5`, `gpt-6-astra`). Passed straight
  to LiteLLM; override freely. See [`.env.example`](.env.example).
- **Provider key** — set the variable your model needs (`GEMINI_API_KEY`,
  `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, …). Local Ollama models need no key.
- **Searches** — `~/.kravu/searches.yaml` (created by `kravu init`) defines your
  keyword searches, sources, fit threshold, cover-letter policy, and `limit` — the
  number of jobs a run explores and processes.
- **Workers** — `KRAVU_WORKERS` (default 4) sets how many jobs each step processes
  concurrently; `--workers N` on `kravu run`/`resume` overrides it, as does a
  `workers:` key in `searches.yaml`. Keep it modest on free LLM tiers (e.g. Gemini
  free ~15 requests/min).
- **Data** — everything lives under `~/.kravu/` (SQLite DB, profile, tailored
  materials). Override the location with `KRAVU_HOME`.

## Security & honesty

These are enforced guarantees, not aspirations:

- **Never fabricates.** Tailoring may reorder, reframe, and re-emphasize your real
  resume, but a code-injected header plus a deterministic validator **and** an
  always-on LLM judge block any invented skill, employer, date, degree, or metric.
  If the guard can't be satisfied, kravu writes nothing rather than emit fabricated
  material.
- **Human-gated by default.** Auto-submission is opt-in; the default prepares and
  queues applications for your approval, and a daily cap limits volume. kravu is a
  co-pilot, not a spam-bot.
- **Never stores your keys.** API keys stay in your environment / `.env`; kravu
  reads the provider/model only and hard-stops with an actionable message if a
  required key is missing.
- **Local-first.** Your data stays in a single local SQLite file — no server, no
  account, no cloud dependency.

## Development

```bash
uv sync --extra dev
uv run ruff format --check src/kravu tests   # formatting
uv run ruff check src/kravu tests            # lint
uv run mypy src/kravu                        # type check (strict)
uv run pytest                                # tests (offline, no real LLM/network)
```

The codebase follows a `domain` / `services` / `adapters` / `entrypoints` layout
(business logic in `services/`, infrastructure behind ports). This same gate runs
in CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) on every push and
pull request across Python 3.11 and 3.12; contributions should keep it green. See
[`docs/`](docs/) for the design spec and implementation plan.

## Roadmap

- **v0.1** *(current)* — explore → expand → score → tailor → cover, plus the
  human-gated Apply Agent. Each step processes jobs concurrently (bounded worker
  pool, `KRAVU_WORKERS`).
- **v0.2** — PDF rendering of materials; richer `status`; broader ATS apply support.
- **v0.3+** — streaming (cross-stage/overlapping) pipeline execution; scheduled runs.

## License

Released under the [MIT License](LICENSE).
