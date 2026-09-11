# Intra-Step Parallelism Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Speed up a `kravu run` by processing jobs concurrently *within* each per-job step (score, cover, tailor, expand) using a bounded thread pool, built as independently-tested slices.

**Architecture:** One shared `run_parallel` helper wraps `concurrent.futures.ThreadPoolExecutor`; `workers=1` is an exact serial baseline. Because a SQLite connection may only be used by its creating thread, each worker builds its own `JobRepository` via an injected `store_factory` (kravu's `db.py` already caches one WAL connection per thread). `expand` additionally needs a `renderer_factory`. A `threading.Lock` makes `RichProgressReporter` thread-safe. Determinism is preserved: each job writes its own DB row, order-independent; the LLM never controls flow.

**Tech Stack:** Python 3.11+, `concurrent.futures`, stdlib `sqlite3` (WAL), Typer, Rich, pytest, `uv`, `ruff`, `mypy` (strict).

**Reference spec:** `docs/superpowers/specs/2026-09-11-intra-step-parallelism-design.md`

**Conventions (from steering):** `from __future__ import annotations` at top of every module; modern typing (`list[str]`, `X | None`); full type hints incl. `-> None`; Google-style docstrings; absolute imports (`from kravu...`); 88-char lines; TDD (failing test first). Run tooling via `uv run`.

---

## File Structure

| File | Responsibility | Task |
|------|----------------|------|
| `src/kravu/services/parallel.py` (create) | The `run_parallel` helper + `StoreFactory` type alias. Bounded concurrency, per-completion callback, `workers<=1` serial, `KeyboardInterrupt` handling. | 1 |
| `src/kravu/entrypoints/cli.py` (modify) | Add a `threading.Lock` to `RichProgressReporter`. Later: resolve `workers`, wire factories, add `--workers`. | 1, 6 |
| `src/kravu/services/score.py` (modify) | Parallelize the job loop via `run_parallel`; add `workers` + `store_factory` ctor args. | 2 |
| `src/kravu/entrypoints/composition.py` (modify) | Thread `workers` + `store_factory` (+ `renderer_factory`) into `build_pipeline_steps`. | 2, 5 |
| `src/kravu/services/cover_letter.py` (modify) | Same parallelization pattern as score. | 3 |
| `src/kravu/services/tailor.py` (modify) | Same pattern; verify attempt-counter integrity. | 4 |
| `src/kravu/services/expand.py` (modify) | Same pattern + `renderer_factory` per worker. | 5 |
| `src/kravu/config.py` (modify) | Add `workers()` reading `KRAVU_WORKERS` (default 4). | 6 |
| `tests/unit/test_parallel.py` (create) | Helper behaviour: serial==parallel, on_done once, error isolation, KeyboardInterrupt, concurrency probe. | 1 |
| `tests/unit/test_rich_progress_reporter.py` (modify) | Add a concurrency test for the progress lock. | 1 |
| `tests/unit/test_score_parallel.py` (create) | score identical at workers=1/4. | 2 |
| `tests/unit/test_cover_parallel.py` (create) | cover identical at workers=1/4. | 3 |
| `tests/unit/test_tailor_parallel.py` (create) | tailor identical at workers=1/4 + attempt integrity + no fabrication. | 4 |
| `tests/unit/test_expand_parallel.py` (create) | expand identical at workers=1/4 + renderer-per-worker. | 5 |
| `tests/unit/test_config_workers.py` (create) | `config.workers()` default and override. | 6 |
| `tests/unit/test_composition.py` (modify) | Assert new kwargs default safely. | 2, 6 |

**Backward-compat rule (spec §4.8):** every new constructor / `build_pipeline_steps` parameter is **keyword-only with a default**, so existing calls in `tests/e2e/test_full_pipeline.py` and `tests/unit/test_composition.py` keep working unchanged.

---

## Task 1: The `run_parallel` helper + thread-safe progress

**Files:**
- Create: `src/kravu/services/parallel.py`
- Modify: `src/kravu/entrypoints/cli.py` (`RichProgressReporter`, ~lines 118-170)
- Test: `tests/unit/test_parallel.py` (create), `tests/unit/test_rich_progress_reporter.py` (modify)

- [ ] **Step 1: Write the failing test for the helper**

Create `tests/unit/test_parallel.py`:

```python
"""Unit tests for run_parallel: the bounded-concurrency helper.

Offline and deterministic. Correctness is asserted order-independently (on sets),
so the same assertions hold at workers=1 (serial) and workers>1 (pooled).
"""

from __future__ import annotations

import threading
import time

import pytest

from kravu.services.parallel import run_parallel


@pytest.mark.parametrize("workers", [1, 4])
def test_run_parallel_applies_work_to_every_item(workers: int) -> None:
    seen: set[int] = set()
    lock = threading.Lock()

    def work(item: int) -> None:
        with lock:
            seen.add(item * 10)

    run_parallel([1, 2, 3, 4, 5], work, workers=workers)

    assert seen == {10, 20, 30, 40, 50}


@pytest.mark.parametrize("workers", [1, 4])
def test_run_parallel_calls_on_done_once_per_item(workers: int) -> None:
    done: list[int] = []
    lock = threading.Lock()

    def on_done(item: int) -> None:
        with lock:
            done.append(item)

    run_parallel([1, 2, 3], lambda _: None, workers=workers, on_done=on_done)

    assert sorted(done) == [1, 2, 3]


@pytest.mark.parametrize("workers", [1, 4])
def test_run_parallel_isolates_a_failing_item(workers: int) -> None:
    completed: set[int] = set()
    lock = threading.Lock()

    def work(item: int) -> None:
        if item == 3:
            raise ValueError("boom")
        with lock:
            completed.add(item)

    # One item raising must not abort the batch.
    run_parallel([1, 2, 3, 4], work, workers=workers)

    assert completed == {1, 2, 4}


def test_run_parallel_runs_concurrently_when_workers_gt_1() -> None:
    max_in_flight = 0
    in_flight = 0
    lock = threading.Lock()

    def work(_: int) -> None:
        nonlocal max_in_flight, in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1

    run_parallel(list(range(8)), work, workers=4)

    assert max_in_flight > 1  # proves real concurrency


def test_run_parallel_reraises_keyboard_interrupt() -> None:
    def work(item: int) -> None:
        if item == 1:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_parallel([1, 2, 3], work, workers=4)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_parallel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kravu.services.parallel'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/kravu/services/parallel.py`:

```python
"""run_parallel: apply a unit of work across items with bounded concurrency.

The single concurrency primitive for the pipeline's per-job steps. It knows
nothing about jobs, the store, or LLMs — a service passes a ``work`` callable and
a worker count. ``workers <= 1`` runs a plain serial loop (the exact baseline the
serial pipeline had, and the deterministic baseline tests compare against);
``workers > 1`` uses a bounded ``ThreadPoolExecutor``. I/O-bound work (network,
LLM) overlaps because Python releases the GIL while blocking on I/O.

A per-item exception is contained (logged, item skipped) so one failure never
aborts the batch — matching the pipeline's fault-tolerance rule. A
``KeyboardInterrupt`` propagates so Ctrl+C always stops a run.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import FIRST_EXCEPTION, ThreadPoolExecutor, wait
from typing import TypeVar

_LOGGER = logging.getLogger("kravu")

T = TypeVar("T")

# A zero-arg factory returning a fresh store bound to the calling thread. Defined
# here (rather than importing a concrete repository) so services stay infra-free.
StoreFactory = Callable[[], object]


def run_parallel(
    items: list[T],
    work: Callable[[T], None],
    *,
    workers: int,
    on_done: Callable[[T], None] | None = None,
) -> None:
    """Apply ``work(item)`` across ``items`` with a bounded thread pool.

    Args:
        items: The work items (a service passes its pending jobs).
        work: The per-item operation. Expected to record its own per-item errors;
            an unexpected escaping exception is logged and that item skipped.
        workers: Max concurrent workers. ``<= 1`` runs serially with no pool.
        on_done: Optional callback invoked once per completed item (progress).

    Raises:
        KeyboardInterrupt: Propagated so Ctrl+C stops the run; in-flight items are
            allowed to finish and pending ones are cancelled first.
    """
    if workers <= 1:
        _run_serial(items, work, on_done)
        return
    _run_pooled(items, work, workers, on_done)


def _run_serial(
    items: list[T],
    work: Callable[[T], None],
    on_done: Callable[[T], None] | None,
) -> None:
    for item in items:
        _do_one(item, work)
        if on_done is not None:
            on_done(item)


def _run_pooled(
    items: list[T],
    work: Callable[[T], None],
    workers: int,
    on_done: Callable[[T], None] | None,
) -> None:
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_do_one, item, work): item for item in items}
        try:
            for future in _as_they_complete(futures):
                item = futures[future]
                future.result()  # _do_one swallows work errors; guards the rest
                if on_done is not None:
                    on_done(item)
        except KeyboardInterrupt:
            for future in futures:
                future.cancel()  # drop not-yet-started work; in-flight finishes
            raise


def _as_they_complete(futures: dict[object, T]):  # type: ignore[type-arg]
    from concurrent.futures import as_completed

    return as_completed(futures)


def _do_one(item: T, work: Callable[[T], None]) -> None:
    """Run one item, containing any unexpected escaping exception."""
    try:
        work(item)
    except KeyboardInterrupt:
        raise
    except Exception:  # noqa: BLE001 - contain per item; never abort the batch
        _LOGGER.exception("run_parallel: unhandled error processing an item")
```

Note: `wait`/`FIRST_EXCEPTION` are imported for clarity but `as_completed` drives the loop; remove the unused import to satisfy ruff — see Step 4.

- [ ] **Step 4: Tidy imports and run tests to verify they pass**

Edit the import line in `src/kravu/services/parallel.py` to drop unused names:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
```

and change `_as_they_complete` usage to call `as_completed(futures)` directly, deleting the `_as_they_complete` helper:

```python
            for future in as_completed(futures):
```

Run: `uv run pytest tests/unit/test_parallel.py -v`
Expected: PASS (all 9 parametrized cases).

- [ ] **Step 5: Run ruff + mypy on the new module**

Run: `uv run ruff check src/kravu/services/parallel.py; uv run mypy src/kravu`
Expected: no errors. (If mypy flags the `dict[object, T]` future map, annotate as `dict[Future[None], T]` importing `Future` from `concurrent.futures`.)

- [ ] **Step 6: Write the failing progress-lock test**

Add to `tests/unit/test_rich_progress_reporter.py`:

```python
def test_advance_is_thread_safe_under_concurrent_calls() -> None:
    import threading

    from rich.progress import Progress

    with Progress(*_progress_columns(), auto_refresh=False) as progress:
        reporter = RichProgressReporter(progress)
        reporter.start_step("score", total=200)

        def hammer() -> None:
            for _ in range(100):
                reporter.advance("score", "x")

        threads = [threading.Thread(target=hammer) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        task = _task(progress, "score")
        assert task.completed == 200  # no lost updates
```

- [ ] **Step 7: Run it to verify it fails (or is flaky)**

Run: `uv run pytest tests/unit/test_rich_progress_reporter.py::test_advance_is_thread_safe_under_concurrent_calls -v`
Expected: FAIL or intermittent — `task.completed < 200` because Rich updates race without a lock.

- [ ] **Step 8: Add the lock to RichProgressReporter**

In `src/kravu/entrypoints/cli.py`, `RichProgressReporter.__init__` — add a lock:

```python
    def __init__(self, progress: Progress) -> None:
        """Store the live ``Progress`` instance and the per-step task registry."""
        self._progress = progress
        self._tasks: dict[str, TaskID] = {}
        self._lock = threading.Lock()
```

Wrap each method body's Rich mutation in `with self._lock:`. For `start_step`:

```python
    def start_step(self, name: str, total: int) -> None:
        """Add (or reset) a bar for ``name`` sized to ``total`` items."""
        _LOGGER.info("%s: starting (%d items)", name, total)
        with self._lock:
            self._tasks[name] = self._progress.add_task(
                f"{name}", total=max(total, 1), detail=""
            )
```

For `advance`:

```python
    def advance(self, name: str, detail: str = "") -> None:
        """Advance ``name`` by one item and show ``detail`` as the trailing label."""
        with self._lock:
            task_id = self._tasks.get(name)
            if task_id is None:
                return
            self._progress.update(task_id, advance=1, detail=detail)
```

For `finish_step`, wrap the task lookup + update in `with self._lock:` the same way.

Add the import at the top of `cli.py` (with the stdlib imports):

```python
import threading
```

- [ ] **Step 9: Run progress tests to verify pass**

Run: `uv run pytest tests/unit/test_rich_progress_reporter.py -v`
Expected: PASS (including the new concurrency test and the existing bar-honesty tests — the lock must not change `advance` counts).

- [ ] **Step 10: Full gate + commit**

Run: `uv run ruff format src/kravu tests; uv run ruff check src/kravu tests; uv run mypy src/kravu; uv run pytest`
Expected: all pass.

```bash
git add src/kravu/services/parallel.py src/kravu/entrypoints/cli.py tests/unit/test_parallel.py tests/unit/test_rich_progress_reporter.py
git commit -m "feat: add run_parallel helper and thread-safe progress reporter"
```

---

## Task 2: Parallelize `score` (+ wire store_factory)

**Files:**
- Modify: `src/kravu/services/score.py`
- Modify: `src/kravu/entrypoints/composition.py` (`build_pipeline_steps`)
- Modify: `src/kravu/entrypoints/cli.py` (`_pipeline` passes `store_factory` + `workers`)
- Test: `tests/unit/test_score_parallel.py` (create), `tests/unit/test_composition.py` (modify)

- [ ] **Step 1: Write the failing parallel-score test**

Create `tests/unit/test_score_parallel.py`:

```python
"""ScoreJobFit produces identical results serially and in parallel."""

from __future__ import annotations

import pytest

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job, Profile, ResumeFacts
from kravu.services.score import ScoreJobFit


class _StubLLM:
    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return '{"reasoning": "ok", "matched_keywords": [], "score": 8}'


def _profile() -> Profile:
    return Profile(
        resume_facts=ResumeFacts(raw_text="Jane, Python dev", skills=["Python"])
    )


@pytest.mark.parametrize("workers", [1, 4])
def test_score_identical_serial_and_parallel(repo: JobRepository, workers: int) -> None:
    urls = [f"https://a.test/{i}" for i in range(6)]
    for url in urls:
        repo.add_discovered(Job(url=url, title="Dev"))
        repo.set_enrichment(url, "Python role. Requirements: Python.", None)

    ScoreJobFit(
        _StubLLM(), _profile(), min_score=7,
        workers=workers, store_factory=JobRepository,
    ).run(repo)

    scored = {j.url: j.fit_score for j in repo.shortlist(min_score=1)}
    assert scored == {url: 8 for url in urls}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_score_parallel.py -v`
Expected: FAIL — `TypeError: ScoreJobFit.__init__() got an unexpected keyword argument 'workers'`.

- [ ] **Step 3: Add ctor args and parallelize the loop in `score.py`**

In `src/kravu/services/score.py`, update imports (add the helper + factory type):

```python
from kravu.services.parallel import StoreFactory, run_parallel
```

Replace `__init__` and `run`:

```python
    def __init__(
        self,
        llm: LLMClient,
        profile: Profile,
        min_score: int,
        *,
        workers: int = 1,
        store_factory: StoreFactory | None = None,
    ) -> None:
        """Store the model port, profile, threshold, and concurrency settings."""
        self._llm = llm
        self._profile = profile
        self._min_score = min_score
        self._workers = workers
        self._store_factory = store_factory

    def run(
        self,
        store: JobStore,
        limit: int | None = None,
        *,
        progress: ProgressReporter = NO_PROGRESS,
    ) -> None:
        """Score every pending job (up to ``limit``). Never raises per job."""
        jobs = store.pending_scoring(limit)
        progress.start_step("score", len(jobs))
        run_parallel(
            jobs,
            lambda job: self._score_one(
                self._store_for(store), job.url, job.full_description or ""
            ),
            workers=self._workers,
            on_done=lambda job: progress.advance("score", job.company),
        )
        progress.finish_step("score")

    def _store_for(self, fallback: JobStore) -> JobStore:
        """Return this worker thread's own store, or the shared one if serial."""
        if self._store_factory is None:
            return fallback
        store = self._store_factory()
        assert isinstance(store, JobStore)
        return store
```

`_score_one` is unchanged.

- [ ] **Step 4: Run the parallel-score test to verify pass**

Run: `uv run pytest tests/unit/test_score_parallel.py -v`
Expected: PASS at both `workers=1` and `workers=4`.

- [ ] **Step 5: Thread `workers` + `store_factory` through composition**

In `src/kravu/entrypoints/composition.py`, add imports:

```python
from kravu.services.parallel import StoreFactory
```

Update `build_pipeline_steps` signature (append keyword-only params with defaults):

```python
def build_pipeline_steps(
    sources: list[DiscoverySource],
    llm: LLMClient,
    profile: Profile,
    renderer: PageRenderer,
    min_score: int,
    cover_policy: str,
    searches: dict[str, Any],
    limit: int,
    *,
    workers: int = 1,
    store_factory: StoreFactory | None = None,
) -> list[PipelineStep]:
```

Change the `score` step construction to pass them:

```python
        PipelineStep(
            "score",
            ScoreJobFit(
                llm, profile, min_score,
                workers=workers, store_factory=store_factory,
            ),
        ),
```

(Leave expand/tailor/cover unchanged for now — they get their turn in later tasks.)

- [ ] **Step 6: Wire the CLI to pass a factory + resolved workers**

In `src/kravu/entrypoints/cli.py`, in `_pipeline(...)`, pass the factory and a worker count. For this task use a fixed `workers=config.workers()` — the `config.workers()` function is added in Task 6, so temporarily hardcode `workers=4` here and replace it in Task 6:

```python
    steps = build_pipeline_steps(
        sources=sources,
        llm=LiteLLMClient(),
        profile=profile,
        renderer=PlaywrightPageRenderer(),
        min_score=min_score,
        cover_policy=cover_policy,
        searches=searches,
        limit=limit,
        workers=4,  # TODO(Task 6): replace with resolved config.workers()
        store_factory=JobRepository,
    )
```

- [ ] **Step 7: Add a composition test for the safe defaults**

Add to `tests/unit/test_composition.py`:

```python
def test_build_pipeline_steps_defaults_are_serial_safe() -> None:
    # New concurrency kwargs must default so existing callers keep working.
    steps = build_pipeline_steps(
        sources=[_FakeSource()],
        llm=_FakeLLM(),
        profile=_profile(),
        renderer=_FakeRenderer(),
        min_score=7,
        cover_policy="never",
        searches={"searches": []},
        limit=10,
    )
    assert [s.name for s in steps] == ["explore", "expand", "score", "tailor", "cover"]
```

- [ ] **Step 8: Full gate + commit**

Run: `uv run ruff format src/kravu tests; uv run ruff check src/kravu tests; uv run mypy src/kravu; uv run pytest`
Expected: all pass (including existing e2e/composition tests, unchanged).

```bash
git add src/kravu/services/score.py src/kravu/entrypoints/composition.py src/kravu/entrypoints/cli.py tests/unit/test_score_parallel.py tests/unit/test_composition.py
git commit -m "feat: parallelize score with a per-thread store factory"
```

---

## Task 3: Parallelize `cover`

**Files:**
- Modify: `src/kravu/services/cover_letter.py`
- Modify: `src/kravu/entrypoints/composition.py` (cover step)
- Test: `tests/unit/test_cover_parallel.py` (create)

- [ ] **Step 1: Write the failing parallel-cover test**

Create `tests/unit/test_cover_parallel.py`:

```python
"""DraftCoverLetter produces identical results serially and in parallel."""

from __future__ import annotations

import pytest

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job, Profile, ResumeFacts
from kravu.services.cover_letter import DraftCoverLetter


def _profile() -> Profile:
    return Profile(
        name="Jane Dev", email="j@x.test",
        resume_facts=ResumeFacts(raw_text="Jane", skills=["Python"]),
    )


def _tailored(repo: JobRepository, url: str) -> None:
    repo.add_discovered(Job(url=url, title="Dev", company="Acme"))
    repo.set_enrichment(url, "A cover letter is required to apply.", None)
    repo.set_score(url, 9, "great")
    repo.set_tailored(url, "/tmp/resume.md")


@pytest.mark.parametrize("workers", [1, 4])
def test_cover_identical_serial_and_parallel(
    repo: JobRepository, kravu_home, workers: int
) -> None:
    urls = [f"https://a.test/{i}" for i in range(5)]
    for url in urls:
        _tailored(repo, url)

    DraftCoverLetter(
        _StubLLM(), _profile(), policy="only_if_required", min_score=7,
        workers=workers, store_factory=JobRepository,
    ).run(repo)

    decided = {j.url: j.cover_needed for j in repo.shortlist(min_score=1)}
    assert decided == {url: True for url in urls}


class _StubLLM:
    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return "Dear Hiring Manager,\n\nI am a Python developer. Regards, Jane"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_cover_parallel.py -v`
Expected: FAIL — unexpected keyword argument `workers`.

- [ ] **Step 3: Add ctor args and parallelize `cover_letter.py`**

Add import:

```python
from kravu.services.parallel import StoreFactory, run_parallel
```

Update `__init__` to accept the two keyword-only args and store them (mirror score exactly):

```python
    def __init__(
        self,
        llm: LLMClient,
        profile: Profile,
        policy: str,
        min_score: int,
        *,
        workers: int = 1,
        store_factory: StoreFactory | None = None,
    ) -> None:
        """Store model port, profile, policy, threshold, and concurrency settings."""
        self._llm = llm
        self._profile = profile
        self._policy = policy
        self._min_score = min_score
        self._workers = workers
        self._store_factory = store_factory
```

Replace the loop in `run`:

```python
        jobs = store.pending_cover(self._min_score, limit)
        progress.start_step("cover", len(jobs))
        run_parallel(
            jobs,
            lambda job: self._process_one(self._store_for(store), job),
            workers=self._workers,
            on_done=lambda job: progress.advance("cover", job.company),
        )
        progress.finish_step("cover")

    def _store_for(self, fallback: JobStore) -> JobStore:
        """Return this worker thread's own store, or the shared one if serial."""
        if self._store_factory is None:
            return fallback
        store = self._store_factory()
        assert isinstance(store, JobStore)
        return store
```

`_process_one` is unchanged.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_cover_parallel.py -v`
Expected: PASS at workers=1 and 4.

- [ ] **Step 5: Wire cover in composition**

In `build_pipeline_steps`, update the cover step:

```python
        PipelineStep(
            "cover",
            DraftCoverLetter(
                llm, profile, cover_policy, min_score,
                workers=workers, store_factory=store_factory,
            ),
        ),
```

- [ ] **Step 6: Full gate + commit**

Run: `uv run ruff format src/kravu tests; uv run ruff check src/kravu tests; uv run mypy src/kravu; uv run pytest`
Expected: all pass.

```bash
git add src/kravu/services/cover_letter.py src/kravu/entrypoints/composition.py tests/unit/test_cover_parallel.py
git commit -m "feat: parallelize cover-letter drafting"
```

---

## Task 4: Parallelize `tailor` (+ attempt-counter integrity)

**Files:**
- Modify: `src/kravu/services/tailor.py`
- Modify: `src/kravu/entrypoints/composition.py` (tailor step)
- Test: `tests/unit/test_tailor_parallel.py` (create)

- [ ] **Step 1: Write the failing parallel-tailor test**

Create `tests/unit/test_tailor_parallel.py`:

```python
"""TailorResume: identical results serially and in parallel; attempt integrity."""

from __future__ import annotations

import pytest

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job, Profile, ResumeFacts
from kravu.services.tailor import TailorResume

_SECTIONS = (
    '{"title": "Python Developer", "summary": "Python dev.",'
    ' "skills": {"Core": ["Python"]},'
    ' "experience": [{"role": "Dev", "company": "Acme", "dates": "2020",'
    ' "bullets": ["Built things with Python"]}]}'
)
_JUDGE = '{"verdict": "pass", "fabrications": []}'


class _StubLLM:
    """Returns tailor sections then a passing judge verdict, alternating."""

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return _JUDGE if "judge" in prompt.lower() else _SECTIONS


def _profile() -> Profile:
    return Profile(
        name="Jane Dev", email="j@x.test",
        resume_facts=ResumeFacts(
            raw_text="Acme. Python.", companies=["Acme"], skills=["Python"]
        ),
    )


def _scored(repo: JobRepository, url: str) -> None:
    repo.add_discovered(Job(url=url, title="Dev", company="Acme"))
    repo.set_enrichment(url, "Python role. Requirements: Python.", None)
    repo.set_score(url, 9, "great")


@pytest.mark.parametrize("workers", [1, 4])
def test_tailor_identical_serial_and_parallel(
    repo: JobRepository, kravu_home, workers: int
) -> None:
    urls = [f"https://a.test/{i}" for i in range(4)]
    for url in urls:
        _scored(repo, url)

    TailorResume(
        _StubLLM(), _profile(), min_score=7,
        workers=workers, store_factory=JobRepository,
    ).run(repo)

    tailored = {
        j.url: (j.tailored_resume_path is not None, j.tailor_attempts)
        for j in repo.shortlist(min_score=1)
    }
    # Every job tailored, and each consumed exactly one attempt (happy path).
    assert tailored == {url: (True, 1) for url in urls}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_tailor_parallel.py -v`
Expected: FAIL — unexpected keyword argument `workers`.

- [ ] **Step 3: Add ctor args and parallelize `tailor.py`**

Add import:

```python
from kravu.services.parallel import StoreFactory, run_parallel
```

Update `__init__`:

```python
    def __init__(
        self,
        llm: LLMClient,
        profile: Profile,
        min_score: int,
        *,
        workers: int = 1,
        store_factory: StoreFactory | None = None,
    ) -> None:
        """Store model port, profile, threshold, and concurrency settings."""
        self._llm = llm
        self._profile = profile
        self._min_score = min_score
        self._workers = workers
        self._store_factory = store_factory
```

Replace the loop in `run` (keep the `config.ensure_dirs()` call):

```python
        config.ensure_dirs()
        jobs = store.pending_tailoring(self._min_score, limit)
        progress.start_step("tailor", len(jobs))
        run_parallel(
            jobs,
            lambda job: self._tailor_one(self._store_for(store), job),
            workers=self._workers,
            on_done=lambda job: progress.advance("tailor", job.company),
        )
        progress.finish_step("tailor")

    def _store_for(self, fallback: JobStore) -> JobStore:
        """Return this worker thread's own store, or the shared one if serial."""
        if self._store_factory is None:
            return fallback
        store = self._store_factory()
        assert isinstance(store, JobStore)
        return store
```

`_tailor_one` (with its internal `bump_tailor_attempts` retry loop) is unchanged.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_tailor_parallel.py -v`
Expected: PASS at both worker counts, including `tailor_attempts == 1` per job (proves the per-job attempt counter is correct under concurrency — spec §4.9).

- [ ] **Step 5: Wire tailor in composition**

In `build_pipeline_steps`, update the tailor step:

```python
        PipelineStep(
            "tailor",
            TailorResume(
                llm, profile, min_score,
                workers=workers, store_factory=store_factory,
            ),
        ),
```

- [ ] **Step 6: Full gate + commit**

Run: `uv run ruff format src/kravu tests; uv run ruff check src/kravu tests; uv run mypy src/kravu; uv run pytest`
Expected: all pass.

```bash
git add src/kravu/services/tailor.py src/kravu/entrypoints/composition.py tests/unit/test_tailor_parallel.py
git commit -m "feat: parallelize resume tailoring"
```

---

## Task 5: Parallelize `expand` (+ renderer factory)

**Files:**
- Modify: `src/kravu/services/expand.py`
- Modify: `src/kravu/entrypoints/composition.py` (expand step + `renderer_factory` param)
- Modify: `src/kravu/entrypoints/cli.py` (`_pipeline` passes `renderer_factory`)
- Test: `tests/unit/test_expand_parallel.py` (create)

- [ ] **Step 1: Write the failing parallel-expand test**

Create `tests/unit/test_expand_parallel.py`:

```python
"""ExpandJob: identical results serially and in parallel; renderer per worker."""

from __future__ import annotations

import threading

import pytest

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job
from kravu.services.expand import ExpandJob

_JSONLD = (
    '<html><body><script type="application/ld+json">'
    '{"@type": "JobPosting", "description": "A real job description here."}'
    "</script></body></html>"
)


class _Renderer:
    def render(self, url: str) -> str:
        return _JSONLD


class _StubLLM:
    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return "unused"


class _RendererFactory:
    """Counts how many renderers were built, one per calling thread."""

    def __init__(self) -> None:
        self.threads: set[int] = set()
        self._lock = threading.Lock()

    def __call__(self) -> _Renderer:
        with self._lock:
            self.threads.add(threading.get_ident())
        return _Renderer()


@pytest.mark.parametrize("workers", [1, 4])
def test_expand_identical_serial_and_parallel(
    repo: JobRepository, workers: int
) -> None:
    urls = [f"https://a.test/{i}" for i in range(6)]
    for url in urls:
        repo.add_discovered(Job(url=url, title="Dev", description="preview"))

    factory = _RendererFactory()
    ExpandJob(
        _Renderer(), _StubLLM(),
        workers=workers, store_factory=JobRepository, renderer_factory=factory,
    ).run(repo)

    # Freshly-expanded jobs have no fit_score, so shortlist() (fit_score >= ?)
    # would exclude them — read each row directly instead.
    enriched = {
        url: (repo.get(url).full_description or "").strip()  # type: ignore[union-attr]
        for url in urls
    }
    assert enriched == {url: "A real job description here." for url in urls}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_expand_parallel.py -v`
Expected: FAIL — unexpected keyword argument `workers`.

- [ ] **Step 3: Add ctor args + renderer factory and parallelize `expand.py`**

Add import:

```python
from kravu.services.parallel import StoreFactory, run_parallel
```

Define a renderer-factory type near the top (after `PageRenderer`):

```python
from collections.abc import Callable

RendererFactory = Callable[[], PageRenderer]
```

Update `__init__`:

```python
    def __init__(
        self,
        renderer: PageRenderer,
        llm: LLMClient,
        *,
        workers: int = 1,
        store_factory: StoreFactory | None = None,
        renderer_factory: RendererFactory | None = None,
    ) -> None:
        """Store renderer/model ports and concurrency settings."""
        self._renderer = renderer
        self._llm = llm
        self._workers = workers
        self._store_factory = store_factory
        self._renderer_factory = renderer_factory
```

Replace the loop in `run`:

```python
        jobs = store.pending_enrichment(limit)
        progress.start_step("expand", len(jobs))
        run_parallel(
            jobs,
            lambda job: self._expand_one(
                self._store_for(store), self._renderer_for(), job.url
            ),
            workers=self._workers,
            on_done=lambda job: progress.advance("expand", job.company),
        )
        progress.finish_step("expand")

    def _store_for(self, fallback: JobStore) -> JobStore:
        if self._store_factory is None:
            return fallback
        store = self._store_factory()
        assert isinstance(store, JobStore)
        return store

    def _renderer_for(self) -> PageRenderer:
        return self._renderer_factory() if self._renderer_factory else self._renderer
```

Change `_expand_one` to take the renderer as a parameter (so each worker uses its own):

```python
    def _expand_one(
        self, store: JobStore, renderer: PageRenderer, url: str
    ) -> None:
        store.bump_enrich_attempts(url)
        try:
            html = renderer.render(url)
            description = self._extract(html)
        except Exception as exc:  # noqa: BLE001 - record on the row, continue
            store.set_enrichment_error(url, str(exc))
            return
        if description:
            store.set_enrichment(url, description, None)
        else:
            store.set_enrichment_error(url, "no description extracted")
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/unit/test_expand_parallel.py -v`
Expected: PASS at both worker counts.

- [ ] **Step 5: Add renderer_factory to composition and wire the CLI**

In `composition.py`, import the factory type:

```python
from kravu.services.expand import ExpandJob, PageRenderer, RendererFactory
```

Add a keyword-only param to `build_pipeline_steps` and pass it to expand:

```python
    *,
    workers: int = 1,
    store_factory: StoreFactory | None = None,
    renderer_factory: RendererFactory | None = None,
```

```python
        PipelineStep(
            "expand",
            ExpandJob(
                renderer, llm,
                workers=workers, store_factory=store_factory,
                renderer_factory=renderer_factory,
            ),
        ),
```

In `cli.py` `_pipeline`, pass `renderer_factory=PlaywrightPageRenderer`:

```python
        renderer_factory=PlaywrightPageRenderer,
```

- [ ] **Step 6: Full gate + commit**

Run: `uv run ruff format src/kravu tests; uv run ruff check src/kravu tests; uv run mypy src/kravu; uv run pytest`
Expected: all pass.

```bash
git add src/kravu/services/expand.py src/kravu/entrypoints/composition.py src/kravu/entrypoints/cli.py tests/unit/test_expand_parallel.py
git commit -m "feat: parallelize enrichment with a per-worker renderer factory"
```

---

## Task 6: The `--workers` knob (config + CLI)

**Files:**
- Modify: `src/kravu/config.py`
- Modify: `src/kravu/entrypoints/cli.py` (`_resolve_workers`, `run`/`resume` options, `_pipeline`)
- Test: `tests/unit/test_config_workers.py` (create)

- [ ] **Step 1: Write the failing config test**

Create `tests/unit/test_config_workers.py`:

```python
"""config.workers() reads KRAVU_WORKERS with a safe default of 4."""

from __future__ import annotations

import pytest

from kravu import config


def test_workers_defaults_to_4_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KRAVU_WORKERS", raising=False)
    assert config.workers() == 4


def test_workers_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_WORKERS", "8")
    assert config.workers() == 8


def test_workers_falls_back_on_garbage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_WORKERS", "notanumber")
    assert config.workers() == 4


def test_workers_floors_at_1(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_WORKERS", "0")
    assert config.workers() == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/unit/test_config_workers.py -v`
Expected: FAIL — `AttributeError: module 'kravu.config' has no attribute 'workers'`.

- [ ] **Step 3: Add `workers()` to `config.py`**

Add near `limit()`, plus a default constant near `DEFAULT_LIMIT`:

```python
# Default worker count for intra-step parallelism when KRAVU_WORKERS is unset.
# Modest by design: free-tier LLM providers cap requests per minute, so a small
# bound respects the rate limit while still overlapping I/O waits.
DEFAULT_WORKERS = 4
```

```python
def workers() -> int:
    """Number of concurrent workers per parallelized step, from ``KRAVU_WORKERS``.

    Always safe to default (like ``limit``): unset or non-integer falls back to
    ``DEFAULT_WORKERS``; values below 1 are floored to 1 (serial). A ``--workers``
    CLI option or a ``workers`` key in ``searches.yaml`` may override per run.
    """
    raw = os.environ.get("KRAVU_WORKERS")
    if not raw:
        return DEFAULT_WORKERS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_WORKERS
    return max(1, value)
```

- [ ] **Step 4: Run config test to verify pass**

Run: `uv run pytest tests/unit/test_config_workers.py -v`
Expected: PASS.

- [ ] **Step 5: Add resolution + `--workers` option in the CLI**

In `cli.py`, add a resolver next to `_resolve_limit`:

```python
def _resolve_workers(searches: dict[str, Any], override: int | None) -> int:
    """Workers from --workers, else searches.yaml, else KRAVU_WORKERS/default."""
    if override is not None:
        return max(1, override)
    if "workers" in searches:
        return max(1, int(searches["workers"]))
    return config.workers()
```

Change `_pipeline` to take a resolved worker count and use it (replace the Task-2 hardcoded `workers=4`):

```python
def _pipeline(
    profile: Profile,
    searches: dict[str, Any],
    sources: list[DiscoverySource],
    workers: int,
) -> Pipeline:
    ...
        workers=workers,
        store_factory=JobRepository,
        renderer_factory=PlaywrightPageRenderer,
    )
    return Pipeline(steps)
```

Add a `--workers` option to `run` and `resume` and thread it through. For `run`:

```python
@app.command()
def run(
    workers: int | None = typer.Option(
        None, help="Concurrent workers per step (default: KRAVU_WORKERS or 4)."
    ),
) -> None:
    ...
    resolved = _resolve_workers(searches, workers)
    summary = _run_pipeline_with_progress(
        _pipeline(profile, searches, sources, resolved), store
    )
```

Apply the same `workers` option + `_resolve_workers` + `_pipeline(..., resolved)` change to `resume`.

- [ ] **Step 6: Full gate + commit**

Run: `uv run ruff format src/kravu tests; uv run ruff check src/kravu tests; uv run mypy src/kravu; uv run pytest`
Expected: all pass.

```bash
git add src/kravu/config.py src/kravu/entrypoints/cli.py tests/unit/test_config_workers.py
git commit -m "feat: add --workers flag and KRAVU_WORKERS config knob"
```

- [ ] **Step 7: Update `.env.example` docs (no code)**

Add to `.env.example`:

```
# Concurrent workers per parallelized pipeline step (score/tailor/cover/expand).
# Default 4. Keep modest on free LLM tiers (e.g. Gemini free ~15 req/min).
KRAVU_WORKERS=4
```

```bash
git add .env.example
git commit -m "docs: document KRAVU_WORKERS in .env.example"
```

---

## Self-Review

**1. Spec coverage:**
- §4.1 helper → Task 1. §4.3 progress lock → Task 1. §4.5 store factory → Task 2 (+reused 3/4/5). §4.7 renderer factory → Task 5. §4.4/§4.8 knob + keyword-only defaults → Task 6 + composition tests. §4.9 retry/attempt integrity → Task 4 (attempt assertion), KeyboardInterrupt → Task 1 test. §6 testing (workers=1/4 parametrized) → Tasks 2-5. §10 gate commands → every task's final step. All covered.
- Deferred items (streaming, 429 backoff) correctly have NO tasks (out of scope per spec §2/§7).

**2. Placeholder scan:** The only intentional TODO is the Task-2 hardcoded `workers=4`, explicitly replaced in Task 6 Step 5 — flagged in-line, not a hidden gap. No other placeholders; every code step shows full code.

**3. Type consistency:** `StoreFactory` defined in `parallel.py` (Task 1), imported everywhere it's used. `RendererFactory` defined in `expand.py` (Task 5), imported by composition. `_store_for`/`_renderer_for` helper names consistent across score/cover/tailor/expand. `build_pipeline_steps` gains `workers`, `store_factory`, `renderer_factory` (keyword-only) consistently across Tasks 2/3/4/5/6. `config.workers()` / `DEFAULT_WORKERS` names match between Task 6 code and tests.

One consistency note fixed inline: expand's parallel test reads rows via
`repo.get(url)` (not `shortlist`, which excludes NULL-score rows), so the
assertion is correct for freshly-enriched jobs.
