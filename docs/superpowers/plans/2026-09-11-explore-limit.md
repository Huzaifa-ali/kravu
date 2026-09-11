# Explore Limit, Attempt Budgets, and `country` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `limit` the single user-facing number for how many jobs a run explores and processes; keep attempt budgets as named internal constants; use a generic required `country` field per search.

**Architecture:** `limit` is threaded from `searches.yaml` → CLI → `ExploreJobs` → each `DiscoverySource.discover(searches, limit)`. Explore gathers all enabled sources, dedupes by normalized URL, and admits up to `limit` new jobs. The `Pipeline` holds no cap; downstream steps drain their pending work. Attempt budgets move to `config.py` constants referenced by the repository. `country` replaces the board-named field in user config; the JobSpy adapter supplies JobSpy's required country request parameter from it.

**Tech Stack:** Python 3.11+, pytest, ruff, mypy (strict). Tests offline/deterministic; JobSpy and network mocked.

**Spec:** `docs/superpowers/specs/2026-09-11-explore-limit-design.md`

**Working branch:** `feat/explore-limit`

---

## Task 1: Attempt-budget constants in `config.py`

**Files:**
- Modify: `src/kravu/config.py` (add constants near `APP_NAME`)
- Test: `tests/unit/test_config_attempts.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_config_attempts.py`:

```python
"""Unit tests: per-phase attempt budgets are named constants in config."""

from __future__ import annotations

from kravu import config


def test_attempt_budgets_are_defined() -> None:
    assert config.ENRICH_MAX_ATTEMPTS == 3
    assert config.TAILOR_MAX_ATTEMPTS == 5
    assert config.COVER_MAX_ATTEMPTS == 5
    assert config.APPLY_MAX_ATTEMPTS == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_config_attempts.py -v`
Expected: FAIL with `AttributeError: module 'kravu.config' has no attribute 'ENRICH_MAX_ATTEMPTS'`

- [ ] **Step 3: Add the constants**

In `src/kravu/config.py`, directly below `APP_NAME = "kravu"`:

```python
APP_NAME = "kravu"

# Per-phase retry budgets for the blackboard's pending_* gates. Tailor and cover
# allow more attempts than enrich and apply because the no-fabrication guards
# (principles.md) can legitimately reject and retry a generation several times.
ENRICH_MAX_ATTEMPTS = 3
TAILOR_MAX_ATTEMPTS = 5
COVER_MAX_ATTEMPTS = 5
APPLY_MAX_ATTEMPTS = 3

# Default number of jobs a run explores and processes when neither searches.yaml
# nor KRAVU_LIMIT specifies one.
DEFAULT_LIMIT = 100
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_config_attempts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kravu/config.py tests/unit/test_config_attempts.py
git commit -m "feat: add per-phase attempt-budget constants and default limit to config"
```

---

## Task 2: Repository references the attempt constants

**Files:**
- Modify: `src/kravu/adapters/repository.py` (`pending_enrichment` ~line 106, `pending_tailoring`, `pending_cover`, `pending_apply`)
- Test: `tests/integration/test_repository_attempts.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/integration/test_repository_attempts.py`:

```python
"""Repository retry gates honor the config attempt budgets."""

from __future__ import annotations

import inspect

from kravu import config
from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job


def _job(url: str) -> Job:
    return Job(url=url, title="Dev")


def test_pending_gates_use_config_constants() -> None:
    src = inspect.getsource(JobRepository)
    assert "config.ENRICH_MAX_ATTEMPTS" in src
    assert "config.TAILOR_MAX_ATTEMPTS" in src
    assert "config.COVER_MAX_ATTEMPTS" in src
    assert "config.APPLY_MAX_ATTEMPTS" in src


def test_enrichment_excludes_job_at_budget(repo: JobRepository) -> None:
    repo.add_discovered(_job("https://a.test/enrich"))
    for _ in range(config.ENRICH_MAX_ATTEMPTS):
        repo.bump_enrich_attempts("https://a.test/enrich")
    assert repo.pending_enrichment() == []


def test_enrichment_includes_job_below_budget(repo: JobRepository) -> None:
    repo.add_discovered(_job("https://a.test/enrich2"))
    for _ in range(config.ENRICH_MAX_ATTEMPTS - 1):
        repo.bump_enrich_attempts("https://a.test/enrich2")
    assert len(repo.pending_enrichment()) == 1


def test_tailoring_excludes_job_at_budget(repo: JobRepository) -> None:
    url = "https://a.test/tailor"
    repo.add_discovered(_job(url))
    repo.set_enrichment(url, "Python role. Requirements: Python.", None)
    repo.set_score(url, 9, "great")
    for _ in range(config.TAILOR_MAX_ATTEMPTS):
        repo.bump_tailor_attempts(url)
    assert repo.pending_tailoring(min_score=7) == []
```

The behavior tests pass against the current literals (3 and 5); the
`test_pending_gates_use_config_constants` test is the one that fails now and
drives routing the literals through config without changing behavior.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/integration/test_repository_attempts.py::test_pending_gates_use_config_constants -v`
Expected: FAIL — the repository source still has inline `< 3` / `< 5` literals.

- [ ] **Step 3: Route the literals through config**

In `src/kravu/adapters/repository.py`, add the import at the top (with the other first-party imports):

```python
from kravu import config
```

Then replace the inline attempt literals. `pending_enrichment`:

```python
        sql = (
            "SELECT * FROM jobs "
            "WHERE full_description IS NULL "
            f"AND COALESCE(enrich_attempts, 0) < {config.ENRICH_MAX_ATTEMPTS}"
        )
```

`pending_tailoring` (replace `< 5`):

```python
            f"AND COALESCE(tailor_attempts, 0) < {config.TAILOR_MAX_ATTEMPTS} "
```

`pending_cover` (replace `< 5`):

```python
            f"AND COALESCE(cover_attempts, 0) < {config.COVER_MAX_ATTEMPTS} "
```

`pending_apply` (replace `< 3`):

```python
            f"AND COALESCE(apply_attempts, 0) < {config.APPLY_MAX_ATTEMPTS} "
```

These are static, code-controlled integer interpolations (allowed by coding-standards.md: the only permitted SQL interpolation exception, same as the existing `LIMIT {int(limit)}`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/integration/test_repository_attempts.py -v`
Expected: PASS (all, including the source-inspection test)

- [ ] **Step 5: Commit**

```bash
git add src/kravu/adapters/repository.py tests/integration/test_repository_attempts.py
git commit -m "refactor: route repository retry gates through config attempt constants"
```

---

## Task 3: `config.limit()` resolution

**Files:**
- Modify: `src/kravu/config.py` (add `limit()` after `min_score()`)
- Test: `tests/unit/test_config_limit.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_config_limit.py`:

```python
"""Unit tests: run limit resolves from KRAVU_LIMIT with a safe default."""

from __future__ import annotations

import pytest

from kravu import config


def test_limit_reads_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_LIMIT", "42")
    assert config.limit() == 42


def test_limit_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KRAVU_LIMIT", raising=False)
    assert config.limit() == config.DEFAULT_LIMIT


def test_limit_defaults_on_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_LIMIT", "not-a-number")
    assert config.limit() == config.DEFAULT_LIMIT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_config_limit.py -v`
Expected: FAIL with `AttributeError: module 'kravu.config' has no attribute 'limit'`

- [ ] **Step 3: Add `limit()`**

In `src/kravu/config.py`, immediately after the `min_score()` function:

```python
def limit() -> int:
    """The number of jobs a run explores and processes, from ``KRAVU_LIMIT``.

    Unlike model/min_score, a run limit is always safe to default, so an unset or
    non-integer value falls back to ``DEFAULT_LIMIT`` rather than raising.
    (``searches.yaml`` may carry a ``limit`` key that overrides this per run.)
    """
    raw = os.environ.get("KRAVU_LIMIT")
    if not raw:
        return DEFAULT_LIMIT
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_LIMIT
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_config_limit.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kravu/config.py tests/unit/test_config_limit.py
git commit -m "feat: add config.limit() resolving KRAVU_LIMIT with a safe default"
```

---

## Task 4: `DiscoverySource` port gains `limit`

**Files:**
- Modify: `src/kravu/domain/ports.py` (`DiscoverySource.discover`)
- Test: covered by adapter tests in Tasks 5–6; add a port-shape check here.
- Test: `tests/unit/test_ports_discovery.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ports_discovery.py`:

```python
"""The DiscoverySource port takes searches and a run limit."""

from __future__ import annotations

import inspect

from kravu.domain.ports import DiscoverySource


def test_discover_signature_has_limit() -> None:
    sig = inspect.signature(DiscoverySource.discover)
    assert "limit" in sig.parameters
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_ports_discovery.py -v`
Expected: FAIL — `discover` has no `limit` parameter.

- [ ] **Step 3: Update the port**

In `src/kravu/domain/ports.py`, change the `DiscoverySource.discover` signature and docstring:

```python
    def discover(self, searches: dict[str, object], limit: int) -> list[Job]:
        """Run the configured searches and return up to ``limit`` discovered jobs."""
        ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_ports_discovery.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kravu/domain/ports.py tests/unit/test_ports_discovery.py
git commit -m "feat: DiscoverySource.discover takes a run limit"
```

---

## Task 5: `JobSpySource` uses `limit` as fetch count and reads `country`

**Files:**
- Modify: `src/kravu/adapters/jobspy_source.py` (`discover`, `_run_one_site`, `_PASSTHROUGH`)
- Test: `tests/unit/test_jobspy_source.py` (rewrite the two search dicts + add fetch/country assertions), `tests/unit/test_jobspy_multisite.py` (`_searches` helper)

- [ ] **Step 1: Write the failing tests**

Rewrite `tests/unit/test_jobspy_source.py` search dicts to drop `defaults.results_wanted` and use `country`, and assert the adapter passes `limit` as `results_wanted` and forwards `country` as `country_indeed`. Replace the whole file body below the imports/helpers with:

```python
def _capture_jobspy(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Install a fake jobspy that records the kwargs of the last scrape call."""
    module = types.ModuleType("jobspy")
    captured: dict[str, Any] = {}

    def scrape_jobs(**kwargs: Any) -> _FakeFrame:
        captured.update(kwargs)
        return _FakeFrame(rows)

    module.scrape_jobs = scrape_jobs  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "jobspy", module)
    return captured


def _searches() -> dict[str, Any]:
    return {
        "sources": {"jobspy": {"enabled": True, "sites": ["indeed"]}},
        "searches": [
            {"name": "d", "search_term": "DevOps", "location": "US", "country": "USA"}
        ],
    }


def test_discover_maps_rows_to_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_jobspy(
        monkeypatch,
        [
            {
                "job_url": "https://x.test/1",
                "title": "DevOps Engineer",
                "company": "Acme",
                "location": "Remote, US",
                "is_remote": True,
                "site": "indeed",
                "description": "Do devops.",
            }
        ],
    )
    jobs = JobSpySource().discover(_searches(), limit=5)
    assert len(jobs) == 1
    assert jobs[0].url == "https://x.test/1"
    assert jobs[0].source == "indeed"


def test_discover_uses_limit_as_fetch_count(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_jobspy(monkeypatch, [])
    JobSpySource().discover(_searches(), limit=37)
    assert captured["results_wanted"] == 37


def test_discover_forwards_country(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _capture_jobspy(monkeypatch, [])
    JobSpySource().discover(_searches(), limit=5)
    assert captured["country_indeed"] == "USA"


def test_discover_skips_failing_site_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    module = types.ModuleType("jobspy")

    def scrape_jobs(**_kwargs: Any) -> None:
        raise RuntimeError("429 blocked")

    module.scrape_jobs = scrape_jobs  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "jobspy", module)

    source = JobSpySource()
    jobs = source.discover(_searches(), limit=5)
    assert jobs == []
    assert ("d", "indeed") in source.notes


def test_name_attribute() -> None:
    assert JobSpySource().name == "jobspy"
```

In `tests/unit/test_jobspy_multisite.py`, change `_searches` to drop `defaults` and use `country`, and update the two `discover(...)` call sites to pass `limit`:

```python
def _searches(sites: list[str]) -> dict[str, Any]:
    return {
        "sources": {"jobspy": {"enabled": True, "sites": sites}},
        "searches": [
            {
                "name": "primary",
                "search_term": "AI Engineer",
                "location": "Remote",
                "country": "USA",
            }
        ],
    }
```

Update each call: `source.discover(_searches([...]), limit=5)` in
`test_one_failing_site_does_not_lose_the_others`,
`test_per_site_notes_record_outcomes`, `test_unknown_site_is_noted_and_skipped`,
and `test_disabled_jobspy_returns_empty`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_jobspy_source.py tests/unit/test_jobspy_multisite.py -v`
Expected: FAIL — `discover()` takes no `limit`; `country_indeed`/`results_wanted` not derived.

- [ ] **Step 3: Update the adapter**

In `src/kravu/adapters/jobspy_source.py`:

Remove `"results_wanted"` and `"country_indeed"` from `_PASSTHROUGH` (they are now derived, not passed through verbatim):

```python
_PASSTHROUGH = (
    "search_term",
    "location",
    "hours_old",
    "job_type",
    "is_remote",
    "distance",
    "google_search_term",
    "description_format",
)
```

Change `discover` to accept `limit` and thread it:

```python
    def discover(self, searches: dict[str, Any], limit: int) -> list[Job]:
        """Run every configured search across every site and return jobs.

        Args:
            searches: The parsed ``searches.yaml`` dict.
            limit: Per-board fetch ceiling (results requested from each board).

        Returns:
            A flat list of ``Job`` rows (discovery fields only). Duplicates are
            NOT removed here — ExploreJobs dedupes by normalized URL.
        """
        config = searches.get("sources", {}).get("jobspy", {})
        if not config.get("enabled", True):
            return []
        sites = config.get("sites", ["indeed"])
        defaults = searches.get("defaults", {})
        jobs: list[Job] = []
        for entry in searches.get("searches", []):
            for site in sites:
                jobs.extend(self._run_one_site(entry, site, defaults, limit))
        return jobs
```

Change `_run_one_site` to accept `limit`, set `results_wanted=limit`, and map
`country` → JobSpy's `country_indeed` kwarg:

```python
    def _run_one_site(
        self,
        entry: dict[str, Any],
        site: str,
        defaults: dict[str, Any],
        limit: int,
    ) -> list[Job]:
        """Scrape a single site for one search; record the outcome, never raise."""
        name = str(entry.get("name", entry.get("search_term", "search")))
        key = (name, site)
        if site not in SUPPORTED_SITES:
            self.notes[key] = (
                f"unsupported site (choose from {', '.join(sorted(SUPPORTED_SITES))})"
            )
            return []

        import jobspy  # type: ignore[import-untyped]  # no stubs shipped

        kwargs: dict[str, Any] = {"site_name": [site], "results_wanted": limit}
        for source in (defaults, entry):
            for field in _PASSTHROUGH:
                if field in source:
                    kwargs[field] = source[field]
            if source.get("country") is not None:
                kwargs["country_indeed"] = source["country"]
        try:
            frame = jobspy.scrape_jobs(**kwargs)
        except Exception as exc:  # noqa: BLE001 - record and continue per spec
            self.notes[key] = f"failed: {exc}"
            return []
        records = frame.to_dict("records") if frame is not None else []
        jobs = [self._to_job(r) for r in records if r.get("job_url")]
        self.notes[key] = f"ok: {len(jobs)}" if jobs else "empty"
        return jobs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_jobspy_source.py tests/unit/test_jobspy_multisite.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kravu/adapters/jobspy_source.py tests/unit/test_jobspy_source.py tests/unit/test_jobspy_multisite.py
git commit -m "feat: JobSpySource fetches limit per board and reads country field"
```

---

## Task 6: `AtsSource` accepts and honors `limit`

**Files:**
- Modify: `src/kravu/adapters/ats_source.py` (`discover`)
- Test: `tests/unit/test_ats_source_limit.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ats_source_limit.py`:

```python
"""AtsSource honors the run limit across its configured boards."""

from __future__ import annotations

from typing import Any

from kravu.adapters.ats_source import AtsSource


def _greenhouse_payload(n: int) -> dict[str, Any]:
    return {
        "jobs": [
            {"absolute_url": f"https://gh.test/{i}", "title": f"Role {i}",
             "location": {"name": "Remote"}}
            for i in range(n)
        ]
    }


def test_ats_returns_at_most_limit() -> None:
    def fetch(url: str, body: Any = None) -> Any:
        return _greenhouse_payload(10)

    searches = {
        "sources": {
            "ats": {"enabled": True, "companies": [{"ats": "greenhouse", "slug": "acme"}]}
        }
    }
    jobs = AtsSource(fetch=fetch).discover(searches, limit=4)
    assert len(jobs) == 4


def test_ats_disabled_returns_empty() -> None:
    jobs = AtsSource(fetch=lambda *a, **k: {}).discover(
        {"sources": {"ats": {"enabled": False}}}, limit=5
    )
    assert jobs == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_ats_source_limit.py -v`
Expected: FAIL — `discover()` takes no `limit`.

- [ ] **Step 3: Update the adapter**

In `src/kravu/adapters/ats_source.py`, change `discover` to accept and apply `limit`:

```python
    def discover(self, searches: dict[str, Any], limit: int) -> list[Job]:
        """Pull each configured company board and return at most ``limit`` jobs."""
        config = searches.get("sources", {}).get("ats", {})
        if not config.get("enabled", False):
            return []
        jobs: list[Job] = []
        for company in config.get("companies", []):
            jobs.extend(self._pull(company))
            if len(jobs) >= limit:
                return jobs[:limit]
        return jobs[:limit]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_ats_source_limit.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kravu/adapters/ats_source.py tests/unit/test_ats_source_limit.py
git commit -m "feat: AtsSource accepts and honors the run limit"
```

---

## Task 7: `ExploreJobs` takes `limit`, gathers-then-caps

**Files:**
- Modify: `src/kravu/services/explore.py` (`run`)
- Test: `tests/unit/test_explore_limit.py` (create); update `tests/unit/test_progress.py::test_explore_reports_progress`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_explore_limit.py`:

```python
"""ExploreJobs enforces the overall run limit across all sources."""

from __future__ import annotations

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job
from kravu.services.explore import ExploreJobs


class _Source:
    def __init__(self, name: str, urls: list[str]) -> None:
        self.name = name
        self._urls = urls

    def discover(self, searches: dict[str, object], limit: int) -> list[Job]:
        return [Job(url=u, title="Dev", description="short") for u in self._urls]


def test_explore_admits_at_most_limit(repo: JobRepository) -> None:
    src_a = _Source("a", [f"https://a.test/{i}" for i in range(6)])
    src_b = _Source("b", [f"https://b.test/{i}" for i in range(6)])
    added = ExploreJobs([src_a, src_b]).run(repo, {"searches": []}, limit=4)
    assert added == 4
    assert repo.stats()["total"] == 4


def test_explore_dedupes_then_caps(repo: JobRepository) -> None:
    shared = ["https://x.test/1", "https://x.test/2"]
    src_a = _Source("a", shared)
    src_b = _Source("b", shared + ["https://x.test/3", "https://x.test/4"])
    added = ExploreJobs([src_a, src_b]).run(repo, {"searches": []}, limit=3)
    assert added == 3


def test_single_source_fills_limit(repo: JobRepository) -> None:
    src = _Source("a", [f"https://a.test/{i}" for i in range(10)])
    added = ExploreJobs([src]).run(repo, {"searches": []}, limit=5)
    assert added == 5
```

Also update `tests/unit/test_progress.py::test_explore_reports_progress`: the fake
source's `discover` gains `limit`, and the call passes `limit`, asserting the
start total equals the limit:

```python
def test_explore_reports_progress(repo: JobRepository) -> None:
    class _FakeSource:
        name = "fake"

        def discover(self, searches: dict[str, object], limit: int) -> list[Job]:
            return [Job(url="https://a.test/x", title="A", description="short")]

    reporter = _RecordingReporter()
    ExploreJobs([_FakeSource()]).run(repo, {"searches": []}, limit=10, progress=reporter)

    assert "start:explore:10" in reporter.events
    assert "finish:explore" in reporter.events
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_explore_limit.py tests/unit/test_progress.py::test_explore_reports_progress -v`
Expected: FAIL — `run()` has no `limit`; sources called without `limit`.

- [ ] **Step 3: Rewrite `ExploreJobs.run`**

In `src/kravu/services/explore.py`, replace the `run` method:

```python
    def run(
        self,
        store: JobStore,
        searches: dict[str, Any],
        limit: int,
        *,
        progress: ProgressReporter = NO_PROGRESS,
    ) -> int:
        """Discover jobs from all sources, dedupe, and persist up to ``limit`` new.

        Args:
            store: The persistence port.
            searches: The parsed ``searches.yaml`` dict.
            limit: The overall run cap — at most this many new jobs are admitted,
                regardless of how many sources or sites are configured.
            progress: Optional progress sink; total is ``limit``, advanced once
                per newly persisted job.

        Returns:
            The number of newly persisted (previously unseen) jobs (<= limit).
        """
        seen: set[str] = set()
        added = 0
        progress.start_step("explore", limit)
        for source in self._sources:
            if added >= limit:
                break
            for job in source.discover(searches, limit):
                if added >= limit:
                    break
                canonical = normalize_url(job.url)
                if canonical in seen:
                    continue
                seen.add(canonical)
                job.url = canonical
                if store.add_discovered(job):
                    added += 1
                    progress.advance("explore", job.title)
                    if _is_real_description(job.description):
                        store.set_enrichment(canonical, job.description, None)
        progress.finish_step("explore", f"{added} new jobs")
        return added
```

Note: `progress.start_step` no longer references `len(self._sources)`; the
`start_step("explore", ...)` at the top of the old body is removed by this
replacement.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_explore_limit.py tests/unit/test_progress.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kravu/services/explore.py tests/unit/test_explore_limit.py tests/unit/test_progress.py
git commit -m "feat: ExploreJobs enforces overall run limit (gather-then-cap)"
```

---

## Task 8: `Pipeline` drops the cap; `PipelineStep` drops `capped`

**Files:**
- Modify: `src/kravu/services/pipeline.py`
- Test: `tests/unit/test_pipeline.py` (rewrite), `tests/unit/test_progress.py` (pipeline pass-through tests)

- [ ] **Step 1: Rewrite the failing tests**

Replace `tests/unit/test_pipeline.py` body below imports:

```python
class _RecordingStep:
    def __init__(self, name: str, log: list[str]) -> None:
        self._name = name
        self._log = log

    def run(
        self,
        store: object,
        limit: int | None = None,
        *,
        progress: ProgressReporter = NO_PROGRESS,
    ) -> None:
        self._log.append(self._name)


class _BoomStep:
    def run(
        self,
        store: object,
        limit: int | None = None,
        *,
        progress: ProgressReporter = NO_PROGRESS,
    ) -> None:
        raise RuntimeError("kaboom")


def test_pipeline_runs_steps_in_order() -> None:
    log: list[str] = []
    steps = [
        PipelineStep("explore", _RecordingStep("explore", log)),
        PipelineStep("score", _RecordingStep("score", log)),
    ]
    result = Pipeline(steps).run(store=object())
    assert log == ["explore", "score"]
    assert result["explore"] == "ok"
    assert result["score"] == "ok"


def test_pipeline_continues_after_step_crash() -> None:
    log: list[str] = []
    steps = [
        PipelineStep("expand", _BoomStep()),
        PipelineStep("score", _RecordingStep("score", log)),
    ]
    result = Pipeline(steps).run(store=object())
    assert "kaboom" in result["expand"]
    assert log == ["score"]
```

In `tests/unit/test_progress.py`, update the two pipeline tests to drop `capped`
and `per_run_cap`:

```python
    steps = [
        PipelineStep("explore", _ProgressAwareStep("explore", seen)),
        PipelineStep("score", _ProgressAwareStep("score", seen)),
    ]
    Pipeline(steps).run(store=object(), progress=reporter)
```

and

```python
    steps = [PipelineStep("score", _ProgressAwareStep("score", seen))]
    result = Pipeline(steps).run(store=object())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_pipeline.py tests/unit/test_progress.py -v`
Expected: FAIL — `PipelineStep` still requires `capped`; `Pipeline` still requires `per_run_cap`.

- [ ] **Step 3: Rewrite `pipeline.py`**

Replace the module body (keeping the docstring updated to drop cap language):

```python
"""Pipeline: sequence the use cases. Sequencing only — no business rules.

Runs each ordered step over its outstanding work. A per-step crash is caught,
recorded in the returned summary, and the pipeline continues — a run always
produces whatever output it could (spec §7b).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from kravu.domain.ports import NO_PROGRESS, JobStore, ProgressReporter


class _UseCase(Protocol):
    def run(
        self,
        store: JobStore,
        limit: int | None = None,
        *,
        progress: ProgressReporter = ...,
    ) -> None: ...


@dataclass(slots=True)
class PipelineStep:
    """One ordered step: a named use case."""

    name: str
    use_case: _UseCase


class Pipeline:
    """Ordered, fault-tolerant runner for the pipeline use cases."""

    def __init__(self, steps: list[PipelineStep]) -> None:
        """Store the ordered steps."""
        self._steps = steps

    def run(
        self,
        store: JobStore,
        progress: ProgressReporter = NO_PROGRESS,
    ) -> dict[str, str]:
        """Run every step in order and return a per-step status summary.

        Each value is ``"ok"`` on success or an error string if that step
        crashed. The pipeline never aborts on a single step's failure. The
        optional ``progress`` reporter is threaded into every step.
        """
        summary: dict[str, str] = {}
        for step in self._steps:
            try:
                step.use_case.run(store, progress=progress)
                summary[step.name] = "ok"
            except Exception as exc:  # noqa: BLE001 - report and continue per spec
                summary[step.name] = f"error: {exc}"
        return summary
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_pipeline.py tests/unit/test_progress.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kravu/services/pipeline.py tests/unit/test_pipeline.py tests/unit/test_progress.py
git commit -m "refactor: Pipeline sequences steps without a run cap"
```

---

## Task 9: Composition wires `limit` into explore, drops `capped`

**Files:**
- Modify: `src/kravu/entrypoints/composition.py` (`_ExploreStep`, `build_pipeline_steps`)
- Test: `tests/unit/test_composition.py` (update), `tests/e2e/test_full_pipeline.py` (update)

- [ ] **Step 1: Update the failing tests**

In `tests/e2e/test_full_pipeline.py`:
- The `_Source.discover` fake gains `limit`:

```python
    def discover(self, searches: dict[str, object], limit: int) -> list[Job]:
```

- `build_pipeline_steps(...)` call gains `limit=25`:

```python
    steps = build_pipeline_steps(
        sources=[_Source()],
        llm=llm,
        profile=profile,
        renderer=_Renderer(),
        min_score=7,
        cover_policy="always",
        searches={"searches": []},
        limit=25,
    )
    summary = Pipeline(steps).run(store)
```

Read `tests/unit/test_composition.py` and update any `capped`/`per_run_cap`
references and the `build_pipeline_steps` call to pass `limit=25` and construct
`Pipeline(steps)`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_composition.py tests/e2e/test_full_pipeline.py -v`
Expected: FAIL — `build_pipeline_steps` has no `limit`; `PipelineStep`/`Pipeline` signatures changed.

- [ ] **Step 3: Rewrite `_ExploreStep` and `build_pipeline_steps`**

In `src/kravu/entrypoints/composition.py`, `_ExploreStep` captures `limit` and
uses it (no longer ignoring it):

```python
class _ExploreStep:
    """Adapt ExploreJobs to the pipeline's uniform ``run(store, ...)`` shape.

    ExploreJobs needs the searches config and the run limit, captured here so the
    step exposes the uniform ``run(store, limit=None, *, progress)`` signature the
    pipeline calls.
    """

    def __init__(
        self, explore: ExploreJobs, searches: dict[str, Any], limit: int
    ) -> None:
        """Capture the ExploreJobs use case, the searches config, and the limit."""
        self._explore = explore
        self._searches = searches
        self._limit = limit

    def run(
        self,
        store: JobStore,
        limit: int | None = None,
        *,
        progress: ProgressReporter = NO_PROGRESS,
    ) -> None:
        """Run discovery with the captured searches and limit."""
        self._explore.run(
            store, self._searches, self._limit, progress=progress
        )
```

Rewrite `build_pipeline_steps` to take `limit` and drop `capped`:

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
) -> list[PipelineStep]:
    """Assemble the ordered pipeline steps from constructed adapters.

    Explore admits up to ``limit`` new jobs; the remaining steps process all of
    their pending work.
    """
    return [
        PipelineStep(
            "explore", _ExploreStep(ExploreJobs(sources), searches, limit)
        ),
        PipelineStep("expand", ExpandJob(renderer, llm)),
        PipelineStep("score", ScoreJobFit(llm, profile, min_score)),
        PipelineStep("tailor", TailorResume(llm, profile, min_score)),
        PipelineStep(
            "cover", DraftCoverLetter(llm, profile, cover_policy, min_score)
        ),
    ]
```

Update the module docstring's paragraph about `_ExploreStep` ignoring `limit`
to state it now captures the run limit.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_composition.py tests/e2e/test_full_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kravu/entrypoints/composition.py tests/unit/test_composition.py tests/e2e/test_full_pipeline.py
git commit -m "feat: composition wires run limit into explore, drops capped flag"
```

---

## Task 10: CLI resolves `limit` and builds the pipeline

**Files:**
- Modify: `src/kravu/entrypoints/cli.py` (`_pipeline`, add `_resolve_limit`)
- Test: `tests/unit/test_cli_resolve_limit.py` (create)

- [ ] **Step 1: Write the failing test**

`_resolve_limit` is a pure function (searches dict → int), so it is unit-testable
without driving a full offline `run()`. Create `tests/unit/test_cli_resolve_limit.py`:

```python
"""CLI resolves the run limit from searches.yaml, else config default."""

from __future__ import annotations

import pytest

from kravu import config
from kravu.entrypoints.cli import _resolve_limit


def test_resolve_limit_prefers_searches_value() -> None:
    assert _resolve_limit({"limit": 42}) == 42


def test_resolve_limit_falls_back_to_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KRAVU_LIMIT", raising=False)
    assert _resolve_limit({}) == config.DEFAULT_LIMIT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_cli_resolve_limit.py -v`
Expected: FAIL with `ImportError: cannot import name '_resolve_limit'`

- [ ] **Step 3: Update `_pipeline` and add `_resolve_limit`**

In `src/kravu/entrypoints/cli.py`, add near `_resolve_min_score`:

```python
def _resolve_limit(searches: dict[str, Any]) -> int:
    """Run limit from ``searches.yaml`` if present, else ``KRAVU_LIMIT``/default."""
    if "limit" in searches:
        return int(searches["limit"])
    return config.limit()
```

Rewrite `_pipeline` to drop `per_run_cap`/`defaults` and pass `limit`:

```python
def _pipeline(
    profile: Profile, searches: dict[str, Any], sources: list[DiscoverySource]
) -> Pipeline:
    min_score = _resolve_min_score(searches)
    cover_policy = _resolve_cover_policy(searches)
    limit = _resolve_limit(searches)
    steps = build_pipeline_steps(
        sources=sources,
        llm=LiteLLMClient(),
        profile=profile,
        renderer=PlaywrightPageRenderer(),
        min_score=min_score,
        cover_policy=cover_policy,
        searches=searches,
        limit=limit,
    )
    return Pipeline(steps)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_cli_resolve_limit.py tests/integration -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kravu/entrypoints/cli.py tests/unit/test_cli_resolve_limit.py
git commit -m "feat: CLI resolves run limit and builds the uncapped pipeline"
```

---

## Task 11: `suggest_searches` generates the new config shape

**Files:**
- Modify: `src/kravu/services/suggest_searches.py` (`_default_searches`, `run`, `validate_searches`, `_validate_entry`)
- Test: `tests/unit/test_suggest_searches.py` (rewrite affected tests), `tests/unit/test_config_save.py` (update round-trip dict)

- [ ] **Step 1: Rewrite the failing tests**

In `tests/unit/test_suggest_searches.py`:

- Replace `test_suggest_builds_valid_searches_dict` assertion about `per_run_cap`:

```python
def test_suggest_builds_valid_searches_dict() -> None:
    reply = '{"search_term": "DevOps engineer", "location": "NYC", "is_remote": true}'
    result = SuggestSearches(_FakeLLM(reply)).run(_profile())

    assert result["searches"][0]["search_term"] == "DevOps engineer"
    assert result["searches"][0]["country"] == "USA"
    assert result["sources"]["jobspy"]["enabled"] is True
    assert result["limit"] == config.DEFAULT_LIMIT
    assert "defaults" not in result
    validate_searches(result)
```

Add `from kravu import config` to the imports.

- Rename/repoint `test_validate_requires_country_indeed_when_indeed_site` to
  `country`:

```python
def test_validate_requires_country_when_indeed_site() -> None:
    bad = {
        "sources": {"jobspy": {"enabled": True, "sites": ["indeed"]}},
        "searches": [{"name": "d", "search_term": "x", "location": "US"}],
    }
    with pytest.raises(SearchesConfigError):
        validate_searches(bad)
```

- In `test_validate_rejects_indeed_filter_conflict`, change `"country_indeed": "USA"`
  to `"country": "USA"`.

In `tests/unit/test_config_save.py`, update `test_save_searches_round_trips`:

```python
def test_save_searches_round_trips(kravu_home: Path) -> None:
    searches = {
        "sources": {"jobspy": {"enabled": True, "sites": ["indeed"]}},
        "limit": 100,
        "min_score": 7,
        "searches": [
            {"name": "primary", "search_term": "DevOps", "country": "USA"}
        ],
    }

    config.ensure_dirs()
    config.save_searches(searches)

    assert config.searches_path().exists()
    loaded = config.load_searches()
    assert loaded["searches"][0]["search_term"] == "DevOps"
    assert loaded["min_score"] == 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_suggest_searches.py tests/unit/test_config_save.py -v`
Expected: FAIL — generation still emits `defaults`/`country_indeed`; validation still checks `country_indeed`.

- [ ] **Step 3: Rewrite `suggest_searches.py`**

Replace `_default_searches`:

```python
def _default_searches() -> dict[str, Any]:
    return {
        "sources": {
            "jobspy": {
                "enabled": True,
                "sites": list(DEFAULT_SITES),
            },
            "ats": {"enabled": False, "companies": []},
        },
        "limit": config.DEFAULT_LIMIT,
        "cover_letter": "only_if_required",
        "min_score": 7,
        "searches": [],
    }
```

Add `from kravu import config` to the imports.

In `run`, change the generated entry field name:

```python
        result["searches"] = [
            {
                "name": "primary",
                "search_term": str(data.get("search_term") or "software engineer"),
                "location": str(data.get("location") or profile.location or "Remote"),
                "country": "USA",
                "is_remote": bool(data.get("is_remote", True)),
            }
        ]
```

In `validate_searches`, rename the local flag and pass-through:

```python
    needs_country = bool({"indeed", "glassdoor"} & set(sites))
    for entry in searches.get("searches", []):
        _validate_entry(entry, needs_country)
```

In `_validate_entry`, use `country`:

```python
def _validate_entry(entry: dict[str, Any], needs_country: bool) -> None:
    if needs_country and not entry.get("country"):
        raise SearchesConfigError(
            f"Search '{entry.get('name')}' needs 'country' "
            "when indeed/glassdoor is a site."
        )
```

(Keep the rest of `_validate_entry` — the Indeed filter-conflict check — unchanged.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_suggest_searches.py tests/unit/test_config_save.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/kravu/services/suggest_searches.py tests/unit/test_suggest_searches.py tests/unit/test_config_save.py
git commit -m "feat: suggest_searches emits single limit and generic country"
```

---

## Task 12: Update the on-disk `searches.yaml`

**Files:**
- Modify: `.kravu/searches.yaml`

- [ ] **Step 1: Rewrite the file to the new shape**

Replace `.kravu/searches.yaml` with:

```yaml
# How many jobs to explore and process this run. The only number you set.
limit: 100

# Whether to draft cover letters: always | never | only_if_required
cover_letter: only_if_required

# Minimum fit score (1-10) for a job to make the shortlist / be applied to.
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
    sites:
    - indeed
    - linkedin
  ats:
    enabled: false
    companies: []
```

- [ ] **Step 2: Verify it loads and validates**

Run: `python -c "from kravu import config; from kravu.services.suggest_searches import validate_searches; validate_searches(config.load_searches()); print('ok')"`
Expected: `ok`

Note: `.kravu/` is gitignored, so this file is not committed. No commit step.

---

## Task 13: Full verification pass

**Files:** none (verification only)

- [ ] **Step 1: Run the whole suite**

Run: `python -m pytest -q`
Expected: all tests pass.

- [ ] **Step 2: Lint and format check**

Run: `python -m ruff format --check . ; python -m ruff check .`
Expected: no errors. If `ruff format --check` reports files, run `python -m ruff format .` and re-commit.

- [ ] **Step 3: Type check**

Run: `python -m mypy src/kravu`
Expected: no errors. In particular confirm `discover(searches, limit)` conformance across `JobSpySource`, `AtsSource`, and the port.

- [ ] **Step 4: Grep for leftover legacy identifiers**

Run: `python -m pytest -q` then search:
Search `per_run_cap`, `results_wanted`, `country_indeed`, `capped`, `MAX_ATTEMPTS` (bare) across `src/` and `tests/`.
Expected: `country_indeed` appears ONLY inside `jobspy_source.py` as the JobSpy scrape kwarg. No `per_run_cap`, no `results_wanted` in config/handling, no `capped` on `PipelineStep`. If any remain, fix and re-commit.

- [ ] **Step 5: Commit any format/fixups**

```bash
git add -A
git commit -m "chore: format and cleanup for explore-limit feature"
```

---

## Task 14: Update `.kiro` steering and README

**Files:**
- Modify: `.kiro/steering/stack.md`, `.kiro/steering/principles.md`, `.kiro/steering/component-design.md` (remove migration note), `.kiro/steering/architecture.md` (only if it references cap/knobs)
- Modify: `README.md`

- [ ] **Step 1: Update steering to the new contract**

- In whichever steering file documents discovery/dedupe/config, ensure it states:
  a run explores and processes up to `limit` jobs (single number); attempt budgets
  are internal per-phase constants in `config.py`; searches use a generic `country`.
- In `.kiro/steering/component-design.md`, **remove the "Migration note (from the
  earlier draft)" section entirely** (the `storage/`/`core/`/`stages/` paragraph).
- Scan all steering files for `per_run_cap`, `results_wanted`, `country_indeed`,
  and any "renamed/was/legacy" phrasing and remove/rewrite so no legacy references
  remain.

- [ ] **Step 2: Update README**

Update any `searches.yaml` example and prose in `README.md` to the new shape:
single `limit`, `country`, no `defaults`/`per_run_cap`/`results_wanted`. Remove any
mention of the old knobs.

- [ ] **Step 3: Verify no legacy references remain in docs**

Search `per_run_cap`, `results_wanted`, `country_indeed` across `README.md` and
`.kiro/`. Expected: none (except none at all in these files).

- [ ] **Step 4: Commit**

```bash
git add README.md .kiro
git commit -m "docs: update steering and README for single limit, internal attempts, country"
```

Note: `.kiro/` is gitignored (untracked). If the commit stages nothing under
`.kiro`, that is expected — the working-copy edits still stand; only `README.md`
is committed. Do not force-add ignored files.

---

## Task 15: Finish the branch

**Files:** none

- [ ] **Step 1: Final full verification**

Run: `python -m pytest -q ; python -m ruff check . ; python -m mypy src/kravu`
Expected: all green.

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin feat/explore-limit
```

Then open a PR (summary: single `limit`, per-phase attempt constants, generic
`country`; what was tested: full suite + ruff + mypy). Do not merge without user
approval.
