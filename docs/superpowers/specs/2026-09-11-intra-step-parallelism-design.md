# kravu — Intra-Step Parallelism (Design)

**Date:** 2026-09-11
**Status:** Approved for planning
**Scope:** Speed up a pipeline run by processing jobs concurrently *within* each
LLM/network use case, built incrementally and tested per step. Cross-step
streaming is explicitly out of scope (deferred to a later, separate effort).

---

## 1. Problem

A `kravu run` is slow because every per-job use case processes jobs strictly one
at a time. `ScoreJobFit`, `DraftCoverLetter`, `TailorResume`, and `ExpandJob`
each iterate `for job in jobs:` and block on a network or LLM round-trip per job.
For N jobs at ~t seconds each, wall-clock cost is ~N·t — and the thread spends
almost all of that time *waiting* on I/O, not computing.

Despite an earlier impression that the pipeline "contains streaming and
parallelism," it does not: all four use cases are serial loops, `LiteLLMClient`
makes a single blocking call, and the `Pipeline` runs steps in strict order. What
*does* already exist is the enabler — `adapters/db.py` uses thread-local,
WAL-mode SQLite connections and documents itself as "safe for parallel workers."
The groundwork is present but unused.

## 2. Goal & non-goals

**Goal.** Reduce run wall-clock time by overlapping the I/O wait across jobs
inside each per-job step, with a bounded, configurable worker count. Every change
lands as one small, independently tested, independently committable slice.

**Non-goals.**
- Cross-step streaming (a job flowing into `score` the instant it is enriched).
  This is a `Pipeline` redesign and belongs to a separate project.
- Parallelizing `explore` (discovery is a handful of source calls, not per-job
  work).
- A token-bucket rate limiter or provider backoff/retry. Deferred unless measured
  429s justify it (see §7).
- Any change to the apply agent (stage 6).

## 3. Why threads

The slow work is I/O-bound (network page renders and LLM round-trips). Python
releases the GIL during blocking I/O, so a thread pool overlaps the waiting —
which is where essentially all the time goes. `concurrent.futures.ThreadPoolExecutor`
is the canonical tool. Processes would add serialization overhead for no benefit
on I/O-bound work.

The binding constraint is **not** CPU but the LLM provider's request rate (e.g.
Gemini free tier ≈ 15 requests/min). Therefore the worker count is a small,
bounded, configurable knob — never unbounded.

## 4. Design

### 4.1 One shared helper (single responsibility)

A new module `services/parallel.py` exposes exactly one function:

```python
def run_parallel(
    items: list[T],
    work: Callable[[T], None],
    *,
    workers: int,
    on_done: Callable[[T], None] | None = None,
) -> None:
    """Apply `work(item)` across `items` with a bounded thread pool.

    Calls `on_done(item)` once per completed item (for progress). `workers <= 1`
    runs serially with no pool — behaviourally identical to a plain for-loop.
    A worker exception is contained per item (logged/re-raised defensively) and
    never aborts the batch: consistent with the pipeline's fault-tolerance rule.
    On `KeyboardInterrupt`, stop submitting, cancel pending futures, let in-flight
    ones finish, and re-raise (so Ctrl+C still stops the run — see §4.9).
    """
```

Responsibility, in one sentence: *apply a unit of work across items with bounded
concurrency, reporting each completion.* It knows nothing about jobs, LLMs, or
the store.

Key behaviours:
- `workers <= 1` → straight serial loop (no executor). This makes the serial path
  the default and the exact baseline for tests.
- `workers > 1` → `ThreadPoolExecutor(max_workers=workers)`, `submit` per item,
  `as_completed` to invoke `on_done` as each finishes (good progress UX).
- Contract: `work` is expected to handle and record its own per-job errors (the
  existing `_..._one` methods already do — they write the error to the job row
  and return). The helper adds defence-in-depth: it still wraps each
  `future.result()` so that if an *unexpected* exception ever escapes `work`, that
  one item is logged and skipped rather than aborting the whole batch. This
  preserves the pipeline's "one job's failure never stops the run" rule.

`T` is a `TypeVar` bound only by what `work`/`on_done` accept; in every kravu use
case `items` is a `list[Job]`.

### 4.2 Use-case adoption

Each per-job use case replaces its `for job in jobs:` loop with a call to
`run_parallel`, passing a `work` closure that calls its existing `_..._one` method
(with a per-thread store from the factory — §4.5) and `progress.advance` as
`on_done`. The per-job methods (`_score_one`, `_expand_one`, `_tailor_one`,
`_process_one`) are **unchanged** — only the iteration and the store they write
through change. Each use case gains two keyword-only constructor arguments,
`workers` and `store_factory` (injected at composition; see the note after the
example for their defaults).

Example (`score`):

```python
def run(self, store, limit=None, *, progress=NO_PROGRESS):
    jobs = store.pending_scoring(limit)          # main-thread read
    progress.start_step("score", len(jobs))
    run_parallel(
        jobs,
        lambda job: self._score_one(
            self._store_factory(),               # this worker thread's own store
            job.url, job.full_description or "",
        ),
        workers=self._workers,
        on_done=lambda job: progress.advance("score", job.company),
    )
    progress.finish_step("score")
```

The `workers` and `store_factory` arguments are **keyword-only with defaults**
(`workers: int = 1`, `store_factory: StoreFactory | None = None`) so existing
tests and the composition root that construct these use cases positionally keep
working; when the factory is absent the use case falls back to the passed-in
`store` and runs serially (`workers=1`), i.e. exactly today's behaviour.

### 4.3 Thread-safe progress

`RichProgressReporter.advance()` mutates Rich state and is not thread-safe. Fix:
serialize `advance` (and `start_step`/`finish_step`) behind a `threading.Lock`
inside `RichProgressReporter`. `NullProgressReporter` needs no change. The lock is
an entrypoint-layer concern; the domain `ProgressReporter` protocol is unchanged.

### 4.4 The knob

- `config.workers()` reads `KRAVU_WORKERS`, **defaulting to 4** (follows the
  existing `limit()` pattern: unset or non-integer falls back to the default,
  never raises).
- A `--workers` option on `run` and `resume` overrides the env value for one run.
- `searches.yaml` may carry an optional `workers:` key, resolved the same way
  `min_score` / `limit` are (`_resolve_*` helpers in `cli.py`).
- This is a concurrency setting, not a provider setting — it stays fully
  provider-agnostic.

### 4.5 Concurrency and the store (the critical correctness point)

**A SQLite connection may only be used by the thread that created it.** This is a
hard rule of Python's `sqlite3` (it raises `ProgrammingError: SQLite objects
created in a thread can only be used in that same thread`); "one connection per
thread" is the standard, ecosystem-wide answer (SQLAlchemy solves it with a
thread-local session factory — `ScopedSession`; kravu's `adapters/db.py` already
implements the same thread-local idea).

The current wiring **defeats** that mechanism under parallelism: `cli.py` builds
`store = JobRepository()` **once, on the main thread**, and `JobRepository.__init__`
calls `get_connection()` eagerly and caches it in `self._conn`. If that single
`store` is shared into worker threads, every worker writes through a connection
owned by the main thread → error / data race. The thread-local cache in `db.py`
only helps if **each worker thread constructs its own `JobRepository`** (so it
calls `get_connection()` from its own thread and gets its own connection).

**Resolution — inject a store factory (chosen; option b).** The parallelized use
cases receive a `store_factory: Callable[[], JobStore]` instead of (or in addition
to) a single `store`. Inside `work(job)`, the use case obtains a
thread-appropriate store via the factory; because `db.py` caches one connection
per thread, each worker thread ends up with exactly one connection and reuses it
across the jobs it handles.

- The default factory (wired in `cli.py`) is simply `JobRepository` — i.e.
  `store_factory = JobRepository`. Called on a worker thread, it acquires that
  thread's own connection.
- Services still never *name* a concrete adapter: they call the injected factory.
  This keeps the "adapters are built at the edge and injected" rule intact
  (component-design steering) — the factory is the injected dependency.
- Reads that happen on the main thread before/after the parallel section (e.g.
  `store.pending_scoring(...)`, `progress` sizing) keep using the main-thread
  store. Only the per-job `work` uses the per-thread store from the factory.

Rejected alternatives: (a) constructing `JobRepository()` directly inside the use
case — smaller, but the service then reaches for a concrete adapter, bending the
DI rule; (c) a single DB-owning thread fed by a queue — serializes all writes and
defeats the speedup. The factory (b) is the minimal change that keeps both
correctness and the architecture rules.

### 4.6 Composition & data flow

```
entrypoints/cli.py         resolves workers (flag > searches.yaml > KRAVU_WORKERS > 4),
                           wraps RichProgressReporter with a lock,
                           passes store_factory=JobRepository into composition
        │
composition.build_pipeline_steps(..., workers=workers, store_factory=...)
                           injects workers + store_factory into each use case
        │
services/pipeline.py       UNCHANGED — still runs steps in order, barrier between them
        │
services/{score,cover,tailor,expand}.py
                           main-thread read (pending_*), then
                           run_parallel(jobs, work, workers=self._workers, ...)
                           where work(job) uses self._store_factory() for its writes
        │
services/parallel.py       bounded ThreadPoolExecutor, as_completed, on_done per completion
        │
adapters/repository.py     UNCHANGED CODE — but now CONSTRUCTED PER WORKER THREAD
                           via the factory, so each thread gets its own WAL connection
adapters/llm.py            UNCHANGED — each thread calls .complete() independently
```

The repository's *code* does not change; what changes is that it is now
**constructed per worker thread** rather than once and shared. That distinction is
the whole point of this section.

### 4.7 `expand` needs a renderer factory too (same shape, slice 5)

`ExpandJob` receives a `PageRenderer`, and `cli.py` builds one
`PlaywrightPageRenderer` at the edge and injects it — so under parallel `expand`,
all workers would share one renderer instance. The default render function opens
its own `sync_playwright()` per call, but Playwright's sync API is not designed to
be driven from multiple threads through a shared object, and any stateful injected
renderer would be unsafe to share.

Resolution mirrors the store: `ExpandJob` takes a **`renderer_factory:
Callable[[], PageRenderer]`** (default wired in `cli.py` as
`PlaywrightPageRenderer`), and each worker obtains its own renderer via the
factory inside `work(job)`. If per-thread Playwright launches prove too heavy,
`expand` may ship with a smaller default worker count than the LLM steps (§9). This
makes slice 5 explicitly larger than the LLM slices: helper adoption **plus** a
renderer factory.

### 4.8 Not breaking existing wiring & tests

Two existing tests pin signatures that this change touches, so the additions must
be backward-compatible:
- `tests/e2e/test_full_pipeline.py` and `tests/unit/test_composition.py` call
  `build_pipeline_steps(...)` with a fixed keyword set. New parameters
  (`workers`, `store_factory`, `renderer_factory`) must be **keyword-only with
  defaults** so these calls keep compiling and running unchanged (default =
  serial, `workers=1`).
- `tests/unit/test_progress.py` asserts exact `advance` counts (e.g. `== 2`). The
  thread-safe-progress lock (§4.3) must not change how many times `advance` is
  called — these tests are the regression guard that it doesn't.

## 4.9 Error handling & retries under parallelism

kravu has **two distinct retry mechanisms**, at different scopes. Parallelism
affects them differently, and it is important not to conflate them.

**(1) In-call retries — the `for attempt in range(N)` loop inside a `_..._one`
method.** `score` retries JSON parsing up to twice; `tailor` loops
`TAILOR_MAX_ATTEMPTS` over draft→validate→judge; `cover` loops on validation.
This logic lives entirely within one job's work function. Under parallelism it is
**unchanged and self-contained**: each worker runs one job's `_..._one` top to
bottom, including that job's own retry loop. Thread A retrying job-1 never
interacts with thread B running job-2 — no shared state.

**(2) Cross-run attempt counters — the `*_attempts` DB columns.** The `pending_*`
queries gate on `COALESCE(attempts,0) < MAX`, and the `_..._one` methods call
`bump_*_attempts(url)` (an `UPDATE ... SET x = COALESCE(x,0)+1 WHERE url=?`). This
is what makes a step retryable *across runs*. Under parallelism this remains
**correct, and correct precisely because of the store factory (§4.5)**:
- Each job's URL appears exactly once in the `pending_*` list and is submitted to
  the pool exactly once, so exactly one worker ever touches a given row's counter.
- Each worker uses its **own connection** (from the factory), and the increment
  targets a distinct primary key, so there is no lost-update race; WAL commits
  each `UPDATE` atomically.
- (Had we shared one connection across threads — the rejected design — concurrent
  `UPDATE`s would have been a genuine hazard. The counter's integrity is a direct
  payoff of the store-factory decision.)

Note the per-step asymmetry (unchanged, just documented): `tailor` bumps its
counter **inside** its attempt loop (one call can consume several attempts),
`expand` bumps **once per call**, and `score` does not use a persisted counter at
all (it retries in-call only). All three are safe because each is confined to one
worker per job.

**Behavioural change on interruption (must be understood).** In a serial run,
Ctrl+C leaves untouched jobs with pristine counters. In a parallel run, up to
`workers` jobs are *in flight* at the interrupt; each may have already bumped its
counter without writing a result. Those jobs return on the next run with an
attempt already consumed but no output — which is **correct** (the attempt was
spent) but means an interrupted parallel run can burn up to `workers` extra
attempts versus a clean serial stop. With budgets of 3–5 this is harmless; it is
called out so it is not mistaken for a bug.

**`KeyboardInterrupt` and the pool.** The serial pipeline lets Ctrl+C propagate to
stop the run (`pipeline.py` re-raises it). `run_parallel` must preserve that: on
`KeyboardInterrupt` it stops submitting new items, cancels not-yet-started
futures, lets in-flight futures finish (they cannot be force-killed mid-I/O), and
re-raises so the existing CLI handling (`_run_pipeline_with_progress` → exit 130)
still fires. This is an explicit requirement on the helper, tested with a `work`
fn that raises `KeyboardInterrupt`.

## 5. Determinism & principles

Parallelism changes *when* work happens, never *what* the outcome is:
- Each job's result is written independently to its own DB row. Completion order
  does not affect the final state (idempotent stages — architecture steering).
- The LLM still never controls flow. The control flow (which steps run, over
  which pending rows) stays deterministic pure Python. Only the I/O wait overlaps.
- Per-job failure is still recorded on that row and the run continues; a batch is
  never aborted by one job.
- YAGNI: one ~20-line helper, one config knob, one CLI flag. No new framework, no
  speculative rate-limiter.

## 6. Testing strategy (per slice)

Concurrency is tested deterministically by exploiting `workers=1` as an exact
serial baseline and asserting order-independent results:

1. **Helper unit tests** (`tests/unit/test_parallel.py`):
   - `workers=1` and `workers=4` produce identical side effects (assert on the
     *set/dict* of recorded work, never on order).
   - `on_done` is called exactly once per item.
   - One item raising does not prevent the others from completing.
   - `KeyboardInterrupt` from a `work` call stops new submissions and re-raises
     (Ctrl+C still stops the run — §4.9).
   - A concurrency probe: a `work` fn that sleeps briefly and records max
     in-flight count proves `>1` runs concurrently when `workers>1`.
2. **Per use-case tests**: parametrize each adopted use case at `workers=1` and
   `workers=4` with the existing `FakeLLMClient` / fake renderer; assert the same
   store writes (scores, tailored paths, cover decisions) regardless of worker
   count. For `tailor`, additionally assert the zero-fabrication guard still
   holds under parallelism, and that a job's `tailor_attempts` counter is bumped
   the same number of times at `workers=1` and `workers=4` (retry integrity).
   - **Store constraint in tests (important):** the current `repo` fixture yields
     a real `JobRepository` bound to one connection created on the fixture's
     (main) thread — so running a use case at `workers>1` against it directly
     would hit the very cross-thread error described in §4.5. Tests therefore pass
     a **store factory** too: either `store_factory=JobRepository` (each worker
     opens its own connection to the shared temp DB file — WAL makes concurrent
     writes safe), or a purpose-built thread-safe in-memory fake store. Assertions
     read back through the main-thread `repo` after the parallel section
     completes. This keeps tests offline, deterministic, and order-independent.
3. **Progress thread-safety**: assert `advance` is called the right number of
   times under `workers>1` (lock prevents lost updates).

All unit tests remain offline and deterministic (no real network/LLM).

## 7. Rate limits (deferred mitigation)

With a modest default (4 workers) and free-tier providers, transient 429s are
possible but bounded. The intentional plan:
- Ship bounded workers first; measure.
- **Only if** real 429s appear, add exponential-backoff-with-jitter retry on 429
  at the adapter layer (`LiteLLMClient`) — the standard, least-invasive fix.
- A token-bucket limiter is heavier and stays out unless the backoff proves
  insufficient.

This keeps us from building rate-limit machinery nobody has yet needed.

## 8. Incremental rollout (each = one commit + tests)

| # | Slice | Rationale | Verification |
|---|-------|-----------|--------------|
| 1 | `services/parallel.py` helper + `StoreFactory` type + thread-safe `RichProgressReporter` | Foundation; nothing wired | Helper unit tests; progress lock test |
| 2 | Adopt in **`score`** (inject `workers` + `store_factory`; wire `store_factory=JobRepository` in composition/CLI) | Simplest: one LLM call, no browser; first real store-per-thread use | Parametrized workers=1/4 identical scores; no cross-thread error |
| 3 | Adopt in **`cover`** | Same shape as score | Parametrized workers=1/4 identical decisions |
| 4 | Adopt in **`tailor`** | More parts (draft+judge+retry) but self-contained | Parametrized + fabrication guard intact |
| 5 | Adopt in **`expand`** (+ renderer factory — see §4.7) | **Last** — Playwright thread-safety is the one unknown; needs a *renderer factory* so each worker gets its own renderer, mirroring the store factory | Test + explicit Playwright concurrency check |
| 6 | `--workers` flag + `config.workers()` + optional `searches.yaml` key | Expose the knob once steps support it | CLI + config unit tests |

The `store_factory` plumbing lands in slice 2 (with `score`, the first
parallelized step) rather than slice 1, so the foundation slice stays pure
infrastructure with no wiring.

`explore` stays serial throughout.

## 9. Risks

- **Cross-thread SQLite use (§4.5).** The current single shared `JobRepository`
  is unsafe under threads. Mitigated by the store-factory: each worker constructs
  its own repository → its own WAL connection. This is the single most important
  correctness item and is addressed from the first parallelized slice.
- **Playwright thread-safety (slice 5).** A single shared renderer is not safe to
  drive from multiple threads. Mitigation: a renderer factory (§4.7) so each
  worker gets its own renderer. This is why `expand` is sequenced last and gets a
  dedicated concurrency check; if per-thread launches prove costly, `expand` can
  ship with a lower default worker count than the LLM steps.
- **Free-tier 429s.** Mitigated by the modest default and the deferred-backoff
  plan (§7).
- **Progress races.** Mitigated by the lock (§4.3), covered by a test.
- **Connection accumulation.** Each worker thread caches a connection for the run
  via `db.py`'s thread-local map. The pool is bounded (≤ workers), lives only for
  the run, and is released at process exit — acceptable; no explicit teardown
  needed for a CLI run.

## 10. Success criteria

- Measurable wall-clock reduction on `score`/`tailor`/`cover`/`expand` at
  `workers=4` vs `workers=1` on a representative batch.
- Identical pipeline outputs at any worker count (proven by parametrized tests).
- `mypy` (strict, configured in `pyproject.toml`), `ruff format --check`,
  `ruff check`, and the full `pytest` suite pass on Python 3.11 and 3.12 (the CI
  matrix), run via `uv run`.
- No change to determinism, fault-tolerance, or the no-fabrication guarantees.
