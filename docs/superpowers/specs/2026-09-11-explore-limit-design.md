# Explore Limit + Internal Attempts + Generic `country` — Design

**Date:** 2026-09-11
**Branch:** `feat/explore-limit`
**Status:** approved design → implementation plan

## Goal

Make the number of jobs a run handles a single, honest, user-facing number
(`limit`). Remove the internal throttle knobs (`per_run_cap`, `results_wanted`)
from user config, move the retry budget into `config.py` as an internal constant,
and rename the board-coupled `country_indeed` search field to a generic `country`.

## Problem

The current design has three related problems:

1. **Explore is uncapped, downstream is capped.** `per_run_cap` (default 100)
   gates the LLM/render steps (`expand`, `score`, `tailor`, `cover`) but *not*
   `explore` (built `capped=False`, and `_ExploreStep` ignores `limit`). So a run
   can discover ~200 jobs (1 search × 2 sites × `results_wanted: 100`) yet only
   process 100 — the surplus silently becomes backlog. The number the user cares
   about (how many jobs enter the pipeline) is unbounded and unpredictable.

2. **Two confusingly-named internal knobs leak into business meaning.**
   `results_wanted` (JobSpy per-board fetch hint) and `per_run_cap` (LLM spend
   throttle) both default to 100, both live under `defaults:`, and neither is a
   concept the user should reason about. Using `per_run_cap` to bound intake turns
   an internal throttle into a business rule — the wrong place for it.

3. **`country_indeed` is board-coupled naming.** It reads as "a setting only for
   Indeed." The concept (which country to search) is generic; only the name (and
   the fact JobSpy's API calls it `country_indeed`) is board-specific. That
   adapter detail leaked into the user's config vocabulary.

## The contract (source of truth)

- `searches.yaml` exposes **one** business number: `limit`.
- User sets `limit: 100` → explore admits up to **100 new (deduped) jobs** into
  the pipeline this run.
- **Every downstream step processes that full set** — no per-step business cap.
  If 90% survive scoring, apply operates on those ~90. The funnel narrows by real
  outcomes (fit score, cover policy), never by a hidden throttle.
- `limit` **also drives how many JobSpy fetches per board internally**, so a run
  can actually reach the number the user set (JobSpy's own default fetch is ~15,
  which would starve `limit: 100`).
- **Retry/attempt budget** is an internal constant in `config.py`
  (`MAX_ATTEMPTS = 3`), replacing the scattered hardcoded `< 3`. Not in yaml/env.
- The search field **`country_indeed` is renamed to `country`**; the JobSpy
  adapter translates `country` → JobSpy's `country_indeed` param internally.
  `country` is **always required** on a search entry (validation + error message
  use `country`).
- `hours_old` and `description_format` are **unchanged** (they are genuine search
  params, fine as they are).
- **Progress bar:** no hierarchy for now. The explore bar simply gets an honest
  denominator (`limit`) instead of `len(sources)`. That fixes the `0/2` confusion
  (`0/1` when only JobSpy is enabled is a non-issue because the total is now
  `limit`, not the source count).

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

### Explore cap enforcement (deterministic)

`ExploreJobs.run` accepts a `limit`. It counts only **newly persisted** jobs and
stops admitting once `added == limit`. Order is deterministic: source order
(JobSpy first, then ATS if enabled), then discovery order within a source.
Dedup by normalized URL still applies before counting. Idempotent: jobs not
admitted this run are simply not persisted and are rediscovered next run.

The explore progress total is `limit`; `advance` is called once per **newly
persisted** job (so the bar reflects real intake, not source ticks).

### JobSpy fetch count from `limit`

`JobSpySource.discover` receives the run `limit` and uses it as the per-search /
per-site fetch count (replacing the `results_wanted` passthrough). It fetches up
to `limit` per board so the deduped union can reach `limit`. Over-fetch across
multiple sites is fine — `ExploreJobs` dedupes and caps at persist time.

### Downstream steps uncapped

`Pipeline` no longer holds a `per_run_cap`. Explore is the only step that takes a
`limit`; `expand`/`score`/`tailor`/`cover` process all their pending rows. The
`capped` flag on `PipelineStep` is removed.

### Attempts constant

`config.MAX_ATTEMPTS = 3` is the single retry budget. `repository.py`'s
`pending_enrichment` (and any other `< 3` retry gate) references it instead of a
literal. Behavior is unchanged (still 3); the value just has one home.

## Files touched

| File | Change |
|------|--------|
| `services/explore.py` | Accept `limit`; admit up to `limit` new jobs (deterministic); progress total = `limit`, advance per persisted job; pass fetch count to sources. |
| `adapters/jobspy_source.py` | Fetch count from `limit` (drop `results_wanted` passthrough); map `country` → `country_indeed`. |
| `services/pipeline.py` | Remove `per_run_cap` and `capped`; explore carries `limit`; downstream uncapped. |
| `entrypoints/composition.py` | Drop `capped`; explore step carries `limit`; wire fetch count. |
| `config.py` | Add `MAX_ATTEMPTS = 3`; add `limit` resolution (`KRAVU_LIMIT` env fallback + default); remove `per_run_cap`/`results_wanted` defaults. |
| `adapters/repository.py` | Replace hardcoded `< 3` with `config.MAX_ATTEMPTS`. |
| `services/suggest_searches.py` | `country_indeed` → `country` in generation + `_validate_entry`. |
| `entrypoints/cli.py` | Resolve `limit`; feed explore; drop `per_run_cap` wiring. |
| `.kravu/searches.yaml` | New shape (above). |
| `tests/**` | Explore-cap test; attempts-constant test; update pipeline/progress/jobspy/config/suggest tests to new contract. |
| `.kiro/steering/*` + `README.md` | Update to reflect single `limit`, internal attempts, `country`. |

## Testing strategy (TDD)

- **Explore cap:** given sources returning more than `limit` unique jobs, exactly
  `limit` are persisted; the surplus is not. Deterministic by source order.
- **Explore reaches limit across sites:** dedup union caps at `limit`.
- **Progress:** explore reports `start:explore:<limit>` and advances once per
  persisted job.
- **Attempts constant:** `config.MAX_ATTEMPTS == 3`; `pending_enrichment` respects
  it (a job with `MAX_ATTEMPTS` attempts is excluded).
- **country rename:** `suggest_searches` emits `country`; `_validate_entry`
  requires `country` and its error message names `country`; JobSpy maps `country`
  → `country_indeed`.
- **Pipeline:** no `per_run_cap`; downstream steps process all pending.
- All unit tests offline/deterministic; LLM + network mocked.

## Out of scope

- Progress hierarchy / per-source live counts (deferred).
- Any change to `hours_old`, `description_format`, cover policy, min_score.
- ATS enablement behavior (still off by default).
- Non-US country inference (country stays explicit and required).
