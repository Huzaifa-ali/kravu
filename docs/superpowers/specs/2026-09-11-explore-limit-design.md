# Explore Limit, Attempt Budgets, and `country` — Design

**Date:** 2026-09-11
**Branch:** `feat/explore-limit`
**Status:** approved design → implementation plan

## Goal

Give a run a single, honest, user-facing number — `limit` — that says how many
jobs it explores and processes. Keep attempt/retry budgets as named internal
constants in `config.py`. Use a generic `country` field on each search, with the
JobSpy adapter supplying the board-specific request parameter it needs.

## The contract (source of truth)

- `searches.yaml` exposes **one** business number: `limit`.
- User sets `limit: 100` → explore admits up to **100 new (deduped) jobs** into
  the pipeline this run. `limit` is the **overall run total**, independent of how
  many sources or sites are configured (never per-source, never per-site).
- **Every downstream step processes that full set.** There is no per-step
  business cap. If 90% survive scoring, apply operates on those ~90. The funnel
  narrows by real outcomes (fit score, cover policy), not by a throttle.
- `limit` also bounds how many results each board is asked for, so a run can
  actually reach the number the user set (a board's own default fetch is small
  and would otherwise starve `limit`).
- **Attempt budgets are internal constants** in `config.py`, not user config.
  They are per-phase (see below) and never appear in `searches.yaml` or env.
- Each search entry has a generic **`country`** field, always required. The
  JobSpy adapter uses it to supply the country request parameter that Indeed and
  Glassdoor require.
- `hours_old` and `description_format` remain genuine search parameters, carried
  per search / per run as today.
- **Progress bar:** flat (no hierarchy). The explore bar's total is `limit`, and
  it advances once per newly persisted job — an honest denominator.

## Resulting `searches.yaml`

```yaml
limit: 100
cover_letter: only_if_required
min_score: 7

searches:
- name: primary
  search_term: AI Engineer
  location: Remote
  country: USA
  is_remote: true

sources:
  jobspy:
    enabled: true
    sites: [indeed, linkedin]
  ats:
    enabled: false
    companies: []
```

## Behavior details

### `limit` is the overall run total

`limit` is the **total number of jobs a run admits, independent of how many
sources or sites are configured.** `limit: 100` means 100 jobs this run — never
per-source, never per-site.

Enforcement is **gather-then-cap** (no source is privileged by position):
`ExploreJobs.run` gathers results from **all** enabled sources, dedupes the full
union by normalized URL, then admits the **first `limit`** new jobs. Iteration
order within the gathered union is deterministic, so the outcome is reproducible;
no source wins simply because it ran first. Idempotent: jobs not admitted this
run are not persisted and are rediscovered next run.

The explore progress total is `limit`; `advance` is called once per **newly
persisted** job (so the bar reflects real intake, not source ticks).

### `limit` bounds each board's fetch

A board's own default fetch is small and would starve `limit`. So `limit` is
threaded to the discovery sources as the per-board fetch ceiling: each enabled
board is asked for **up to `limit`** results. This is *not* "limit per board" —
it is an upper request bound so a single productive board can fill the whole
`limit` when other boards return empty or are blocked. Over-fetching across
several boards is harmless: `ExploreJobs` dedupes the union and enforces the real
overall `limit` when persisting.

To pass `limit` cleanly, the `DiscoverySource` port carries it as an explicit
argument:

```python
def discover(self, searches: dict[str, object], limit: int) -> list[Job]: ...
```

Both adapters (`JobSpySource`, `AtsSource`) and every test fake implement this
signature. `JobSpySource` uses `limit` as the per-board fetch count. `AtsSource`
pulls its configured company boards in order and returns at most `limit` jobs.
The overall cap is still enforced by `ExploreJobs` after dedup, but every source
honors `limit` itself rather than returning whole boards.

### `country` on a search entry

Each search entry carries a generic `country` field (e.g. `USA`). `JobSpySource`
reads `country` and supplies it as the country request parameter that JobSpy's
Indeed and Glassdoor scrapers require. `country` is **always required** on a
search entry; `validate_searches` raises `SearchesConfigError` naming `country`
when it is missing.

### Downstream steps process all pending work

`Pipeline` sequences the steps and threads the progress reporter; it holds no
run cap. Explore is the only step that receives `limit`. `expand`, `score`,
`tailor`, and `cover` each process every pending row the store returns for them.

### Attempt budgets (internal, per-phase)

Retry budgets live as named constants in `config.py` and back the repository's
`pending_*` retry gates. They are per-phase:

```python
ENRICH_MAX_ATTEMPTS = 3
TAILOR_MAX_ATTEMPTS = 5
COVER_MAX_ATTEMPTS = 5
APPLY_MAX_ATTEMPTS = 3
```

Tailor and cover allow more attempts than enrich and apply because the
no-fabrication guards (`principles.md` §"Never fabricate") can legitimately
reject and retry a generation several times before it passes. The repository
references these constants in `pending_enrichment`, `pending_tailoring`,
`pending_cover`, and `pending_apply` instead of inline numbers.

## Files touched

| File | Change |
|------|--------|
| `domain/ports.py` | `DiscoverySource.discover` gains a `limit: int` argument. |
| `services/explore.py` | `run(store, searches, limit, *, progress)`; gather all enabled sources with `limit`, dedupe, admit up to `limit` new jobs; progress total = `limit`, advance per persisted job. |
| `adapters/jobspy_source.py` | `discover(searches, limit)`; use `limit` as the per-board fetch count; read each search entry's `country` and supply it as JobSpy's country request parameter. |
| `adapters/ats_source.py` | `discover(searches, limit)`; pull company boards in order, return at most `limit` jobs. |
| `services/pipeline.py` | `Pipeline(steps)` holds no cap; steps run their pending work; `PipelineStep` has no `capped` field. |
| `entrypoints/composition.py` | Build steps without a cap; explore step carries `limit`. |
| `config.py` | Add `ENRICH_MAX_ATTEMPTS=3`, `TAILOR_MAX_ATTEMPTS=5`, `COVER_MAX_ATTEMPTS=5`, `APPLY_MAX_ATTEMPTS=3`; add `limit()` resolution (`KRAVU_LIMIT` env, default 100). |
| `adapters/repository.py` | `pending_enrichment`/`pending_tailoring`/`pending_cover`/`pending_apply` reference the `config` attempt constants. |
| `services/suggest_searches.py` | Generated config uses `limit`, `country`; `_default_searches` has no `defaults` throttle block; `_validate_entry` requires `country`. |
| `entrypoints/cli.py` | Resolve `limit` from `searches.yaml`/env; build the pipeline and pass `limit` to explore. |
| `.kravu/searches.yaml` | New shape (above). |
| `tests/unit/test_explore*.py` | Overall-cap test; single-source-fills-limit test. |
| `tests/unit/test_config_*.py` | `limit()` resolution; attempt constants. |
| `tests/unit/test_pipeline.py`, `test_progress.py` | `Pipeline(steps)` signature; explore total = `limit`; no `capped`. |
| `tests/unit/test_jobspy_source.py`, `test_jobspy_multisite.py` | `discover(searches, limit)`; `country` field; fetch count = `limit`. |
| `tests/unit/test_suggest_searches.py`, `test_config_save.py` | New config shape; `country`; no throttle block. |
| `tests/e2e/test_full_pipeline.py` | `Pipeline(steps)` + explore `limit` wiring. |
| `.kiro/steering/*`, `README.md` | Describe the single `limit`, per-phase attempt constants, and `country`. Remove the outdated migration note in `component-design.md`. |

## Testing strategy (TDD)

- **Explore overall cap:** two enabled sources returning more than `limit` unique
  jobs combined → exactly `limit` persisted; surplus not. Deterministic
  (gather-then-cap).
- **Single source fills limit:** one productive board asked for `limit` fills the
  whole `limit`.
- **ATS honors limit:** `AtsSource.discover(searches, limit)` returns at most
  `limit` jobs across its configured boards.
- **Fetch ceiling:** `JobSpySource.discover(searches, limit)` asks each board for
  `limit` results (assert the fetch kwarg equals `limit`).
- **Progress:** explore reports `start:explore:<limit>` and advances once per
  persisted job.
- **Attempt constants:** `config.ENRICH_MAX_ATTEMPTS == 3`,
  `TAILOR_MAX_ATTEMPTS == 5`, `COVER_MAX_ATTEMPTS == 5`, `APPLY_MAX_ATTEMPTS == 3`;
  each `pending_*` gate excludes a job at its budget and includes one below it.
- **`country`:** `suggest_searches` emits `country`; `validate_searches` raises
  naming `country` when absent; `JobSpySource` supplies it to the scraper.
- **Pipeline:** `Pipeline(steps)` runs each step over its pending work; explore
  receives `limit`.
- All unit tests offline and deterministic; LLM and network mocked.

## Out of scope

- Progress hierarchy / per-source live counts.
- Any change to `hours_old`, `description_format`, cover policy, `min_score`.
- ATS enablement behavior (off by default).
- Country inference (it stays explicit and required).
