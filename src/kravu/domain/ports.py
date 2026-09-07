"""Port protocols the services depend on (dependency inversion).

Services import these protocols, never concrete adapters. Adapters in
``kravu.adapters`` implement them; tests provide fakes. All protocols are
``runtime_checkable`` so tests can assert conformance structurally.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from kravu.domain.models import Job


@runtime_checkable
class JobStore(Protocol):
    """Persistence contract for the jobs blackboard.

    Implemented by ``kravu.adapters.repository.JobRepository`` (SQLite). A future
    Postgres implementation would satisfy the same protocol.
    """

    def add_discovered(self, job: Job) -> bool:
        """Insert a newly discovered job; False if the URL already exists."""
        ...

    def pending_enrichment(self, limit: int | None = None) -> list[Job]:
        """Return jobs still needing enrichment (under retry budget)."""
        ...

    def set_enrichment(
        self, url: str, full_description: str, apply_url: str | None
    ) -> None:
        """Store an enrichment result and clear any prior error."""
        ...

    def bump_enrich_attempts(self, url: str) -> None:
        """Increment the enrichment retry counter for a job."""
        ...

    def set_enrichment_error(self, url: str, error: str) -> None:
        """Record the latest enrichment error without marking it enriched."""
        ...

    def pending_scoring(self, limit: int | None = None) -> list[Job]:
        """Return enriched jobs that have not yet been scored."""
        ...

    def set_score(self, url: str, score: int, reasoning: str) -> None:
        """Store a job's fit score and reasoning."""
        ...

    def pending_tailoring(self, min_score: int, limit: int | None = None) -> list[Job]:
        """Return high-fit jobs awaiting a tailored resume."""
        ...

    def set_tailored(self, url: str, resume_path: str) -> None:
        """Record the path to a job's tailored resume."""
        ...

    def bump_tailor_attempts(self, url: str) -> None:
        """Increment the tailoring retry counter for a job."""
        ...

    def pending_cover(self, min_score: int, limit: int | None = None) -> list[Job]:
        """Return tailored jobs awaiting a cover-letter decision."""
        ...

    def set_cover(self, url: str, needed: bool, path: str | None) -> None:
        """Record the cover-letter decision and path for a job."""
        ...

    def bump_cover_attempts(self, url: str) -> None:
        """Increment the cover-letter retry counter for a job."""
        ...

    def shortlist(self, min_score: int) -> list[Job]:
        """Return high-fit jobs, best first — the result of a run."""
        ...

    def get(self, url: str) -> Job | None:
        """Fetch a single job by URL, or None if not found."""
        ...

    def stats(self) -> dict[str, int]:
        """Return counts of jobs at each pipeline phase."""
        ...

    def step_counts(self, min_score: int) -> dict[str, dict[str, int]]:
        """Return per-phase done/pending/error counts for reporting."""
        ...

    def reset_step_for_retry(self, phase: str) -> int:
        """Clear a phase's results so it reruns; return rows affected."""
        ...

    def pending_apply(self, min_score: int, limit: int | None = None) -> list[Job]:
        """Return high-fit jobs awaiting an apply attempt."""
        ...

    def set_apply_result(self, url: str, status: str, error: str | None) -> None:
        """Record the outcome of an apply attempt for a job."""
        ...

    def bump_apply_attempts(self, url: str) -> None:
        """Increment the apply retry counter for a job."""
        ...

    def applied_today(self) -> int:
        """Return the count of jobs applied to today (rate limiting)."""
        ...


@runtime_checkable
class LLMClient(Protocol):
    """Provider-agnostic model port.

    ``complete`` returns the model's raw text. Callers parse/validate defensively
    (JSON is instructed, not guaranteed — see spec §7a/§9).
    """

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        """Return the model's raw text completion for a prompt."""
        ...


@runtime_checkable
class DiscoverySource(Protocol):
    """A source of job postings (JobSpy, ATS boards, ...).

    ``discover`` runs the configured searches and returns ``Job`` rows (only the
    discovery fields populated).
    """

    name: str

    def discover(self, searches: dict[str, object]) -> list[Job]:
        """Run the configured searches and return discovered jobs."""
        ...
