"""Unit tests for progress reporting (ProgressReporter port + instrumentation).

Covers the pure domain port and its no-op default, that each LLM/enrichment use
case reports start/advance/finish for the jobs it processes, and that the
Pipeline threads the reporter through to every step. Fakes only — offline and
deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job, Profile, ResumeFacts
from kravu.domain.ports import NO_PROGRESS, NullProgressReporter, ProgressReporter
from kravu.services.expand import ExpandJob
from kravu.services.explore import ExploreJobs
from kravu.services.pipeline import Pipeline, PipelineStep
from kravu.services.score import ScoreJobFit


@dataclass
class _RecordingReporter:
    """Captures the sequence of progress calls for assertions."""

    events: list[str] = field(default_factory=list)

    def start_step(self, name: str, total: int) -> None:
        self.events.append(f"start:{name}:{total}")

    def advance(self, name: str, detail: str = "") -> None:
        self.events.append(f"advance:{name}")

    def finish_step(self, name: str, note: str = "") -> None:
        self.events.append(f"finish:{name}")

    def _advances(self, name: str) -> int:
        return sum(1 for e in self.events if e == f"advance:{name}")


class _StubLLM:
    def __init__(self, reply: str) -> None:
        self._reply = reply

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return self._reply


class _StubRenderer:
    def render(self, url: str) -> str:
        return (
            '<html><body><script type="application/ld+json">'
            '{"@type": "JobPosting", "description": "A real job description here."}'
            "</script></body></html>"
        )


# --- Port + null reporter --------------------------------------------------


def test_null_progress_reporter_satisfies_port() -> None:
    assert isinstance(NullProgressReporter(), ProgressReporter)


def test_recording_reporter_satisfies_port() -> None:
    assert isinstance(_RecordingReporter(), ProgressReporter)


def test_null_progress_reporter_is_a_noop() -> None:
    reporter = NullProgressReporter()
    reporter.start_step("score", 3)
    reporter.advance("score", "Acme")
    reporter.finish_step("score")  # must not raise


# --- Use-case instrumentation ---------------------------------------------


def _profile() -> Profile:
    return Profile(
        resume_facts=ResumeFacts(raw_text="Jane, Python dev", skills=["Python"])
    )


def test_score_reports_progress_per_job(repo: JobRepository) -> None:
    for url in ("https://a.test/1", "https://a.test/2"):
        repo.add_discovered(Job(url=url, title="Dev"))
        repo.set_enrichment(url, "Python role. Requirements: Python.", None)
    reporter = _RecordingReporter()
    reply = '{"reasoning": "ok", "matched_keywords": [], "score": 8}'

    ScoreJobFit(_StubLLM(reply), _profile(), min_score=7).run(repo, progress=reporter)

    assert "start:score:2" in reporter.events
    assert reporter._advances("score") == 2
    assert "finish:score" in reporter.events


def test_expand_reports_progress_per_job(repo: JobRepository) -> None:
    for url in ("https://a.test/e1", "https://a.test/e2", "https://a.test/e3"):
        repo.add_discovered(Job(url=url, title="Dev", description="preview"))
    reporter = _RecordingReporter()

    ExpandJob(_StubRenderer(), _StubLLM("desc")).run(repo, progress=reporter)

    assert "start:expand:3" in reporter.events
    assert reporter._advances("expand") == 3
    assert "finish:expand" in reporter.events


def test_explore_reports_progress(repo: JobRepository) -> None:
    class _FakeSource:
        name = "fake"

        def discover(self, searches: dict[str, object], limit: int) -> list[Job]:
            return [Job(url="https://a.test/x", title="A", description="short")]

    reporter = _RecordingReporter()
    ExploreJobs([_FakeSource()]).run(
        repo, {"searches": []}, limit=10, progress=reporter
    )

    assert "start:explore:10" in reporter.events
    assert "finish:explore" in reporter.events


def test_use_cases_run_without_reporter(repo: JobRepository) -> None:
    """The progress arg is optional; existing call sites must keep working."""
    repo.add_discovered(Job(url="https://a.test/n", title="Dev"))
    repo.set_enrichment("https://a.test/n", "Python. Requirements: Python.", None)
    reply = '{"reasoning": "ok", "score": 8}'
    ScoreJobFit(_StubLLM(reply), _profile(), min_score=7).run(repo)  # no progress=


# --- Pipeline pass-through -------------------------------------------------


class _ProgressAwareStep:
    def __init__(self, name: str, seen: list[str]) -> None:
        self._name = name
        self._seen = seen

    def run(
        self,
        store: object,
        limit: int | None = None,
        *,
        progress: ProgressReporter = NO_PROGRESS,
    ) -> None:
        # Record whether the pipeline handed us the recording reporter.
        progress.advance(self._name, "seen")
        self._seen.append(self._name)


def test_pipeline_passes_reporter_to_every_step() -> None:
    seen: list[str] = []
    reporter = _RecordingReporter()
    steps = [
        PipelineStep("explore", _ProgressAwareStep("explore", seen)),
        PipelineStep("score", _ProgressAwareStep("score", seen)),
    ]
    Pipeline(steps).run(store=object(), progress=reporter)

    assert seen == ["explore", "score"]
    assert "advance:explore" in reporter.events
    assert "advance:score" in reporter.events


def test_pipeline_runs_without_reporter() -> None:
    """Reporter is optional; the existing run(store) signature still works."""
    seen: list[str] = []
    steps = [PipelineStep("score", _ProgressAwareStep("score", seen))]
    result = Pipeline(steps).run(store=object())
    assert result["score"] == "ok"
    assert seen == ["score"]
