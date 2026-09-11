"""JobRepository: the only place that runs SQL against the jobs table.

Use cases depend on this interface, not on SQLite. Swapping to Postgres later means
writing another implementation with the same methods — no use-case code changes.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from kravu import config
from kravu.adapters.db import get_connection
from kravu.domain.models import Job, PipelinePhase

# Columns that map 1:1 between the Job dataclass and the jobs table.
_JOB_COLUMNS = (
    "url",
    "title",
    "company",
    "location",
    "salary",
    "source",
    "apply_type",
    "description",
    "discovered_at",
    "full_description",
    "apply_url",
    "enriched_at",
    "enrich_error",
    "enrich_attempts",
    "fit_score",
    "score_reasoning",
    "scored_at",
    "tailored_resume_path",
    "tailored_at",
    "tailor_attempts",
    "cover_letter_path",
    "cover_needed",
    "cover_at",
    "cover_attempts",
    "apply_status",
    "applied_at",
    "apply_error",
    "apply_attempts",
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _row_to_job(row: sqlite3.Row) -> Job:
    data = {k: row[k] for k in row.keys() if k in _JOB_COLUMNS}
    # SQLite stores booleans as ints; normalize cover_needed back to bool/None.
    if data.get("cover_needed") is not None:
        data["cover_needed"] = bool(data["cover_needed"])
    return Job(**data)


class JobRepository:
    """CRUD + per-use-case queries for jobs. Construct once per thread."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        """Bind to an existing connection or acquire the thread-local one."""
        self._conn = conn or get_connection()

    # -- Discovery ----------------------------------------------------------

    def add_discovered(self, job: Job) -> bool:
        """Insert a newly discovered job.

        Returns False if the URL already exists (deduplication by URL, the
        natural primary key).
        """
        try:
            self._conn.execute(
                """
                INSERT INTO jobs (url, title, company, location, salary, source,
                                  apply_type, description, discovered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.url,
                    job.title,
                    job.company,
                    job.location,
                    job.salary,
                    job.source,
                    job.apply_type,
                    job.description,
                    job.discovered_at or _now(),
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # duplicate URL — already discovered

    # -- Enrichment ---------------------------------------------------------

    def pending_enrichment(self, limit: int | None = None) -> list[Job]:
        """Jobs still needing enrichment (no full description, under retry budget)."""
        # A job needs enrichment if it has no full description yet and hasn't
        # exhausted its retry budget (3 attempts). This makes ExpandJob retryable
        # across runs: pending jobs are picked up again until they succeed or hit 3.
        sql = (
            "SELECT * FROM jobs "
            "WHERE full_description IS NULL "
            f"AND COALESCE(enrich_attempts, 0) < {config.ENRICH_MAX_ATTEMPTS}"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [_row_to_job(r) for r in self._conn.execute(sql)]

    def set_enrichment(
        self, url: str, full_description: str, apply_url: str | None
    ) -> None:
        """Store the enrichment result and clear any prior error."""
        self._conn.execute(
            """
            UPDATE jobs SET full_description = ?, apply_url = ?, enriched_at = ?,
                            enrich_error = NULL
            WHERE url = ?
            """,
            (full_description, apply_url, _now(), url),
        )
        self._conn.commit()

    def bump_enrich_attempts(self, url: str) -> None:
        """Increment the enrichment retry counter for a job."""
        self._conn.execute(
            "UPDATE jobs SET enrich_attempts = COALESCE(enrich_attempts, 0) + 1 "
            "WHERE url = ?",
            (url,),
        )
        self._conn.commit()

    def set_enrichment_error(self, url: str, error: str) -> None:
        """Record the latest enrichment error without marking the job enriched."""
        # Record the latest error; do NOT set enriched_at — the job stays pending
        # (retryable) until full_description is set or attempts reach 3.
        self._conn.execute(
            "UPDATE jobs SET enrich_error = ? WHERE url = ?",
            (error[:500], url),
        )
        self._conn.commit()

    # -- Scoring ------------------------------------------------------------

    def pending_scoring(self, limit: int | None = None) -> list[Job]:
        """Enriched jobs that have not yet been scored."""
        sql = (
            "SELECT * FROM jobs "
            "WHERE full_description IS NOT NULL AND fit_score IS NULL"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [_row_to_job(r) for r in self._conn.execute(sql)]

    def set_score(self, url: str, score: int, reasoning: str) -> None:
        """Store a job's fit score and reasoning."""
        self._conn.execute(
            "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ? "
            "WHERE url = ?",
            (score, reasoning, _now(), url),
        )
        self._conn.commit()

    # -- Tailoring ----------------------------------------------------------

    def pending_tailoring(self, min_score: int, limit: int | None = None) -> list[Job]:
        """High-fit, enriched jobs awaiting a tailored resume (under retry budget)."""
        sql = (
            "SELECT * FROM jobs "
            "WHERE fit_score >= ? AND full_description IS NOT NULL "
            "AND tailored_resume_path IS NULL "
            f"AND COALESCE(tailor_attempts, 0) < {config.TAILOR_MAX_ATTEMPTS} "
            "ORDER BY fit_score DESC"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [_row_to_job(r) for r in self._conn.execute(sql, (min_score,))]

    def set_tailored(self, url: str, resume_path: str) -> None:
        """Record the path to a job's tailored resume."""
        self._conn.execute(
            "UPDATE jobs SET tailored_resume_path = ?, tailored_at = ? WHERE url = ?",
            (resume_path, _now(), url),
        )
        self._conn.commit()

    def bump_tailor_attempts(self, url: str) -> None:
        """Increment the tailoring retry counter for a job."""
        self._conn.execute(
            "UPDATE jobs SET tailor_attempts = COALESCE(tailor_attempts, 0) + 1 "
            "WHERE url = ?",
            (url,),
        )
        self._conn.commit()

    # -- Cover letter -------------------------------------------------------

    def pending_cover(self, min_score: int, limit: int | None = None) -> list[Job]:
        """Tailored jobs awaiting a cover-letter decision (under retry budget)."""
        sql = (
            "SELECT * FROM jobs "
            "WHERE tailored_resume_path IS NOT NULL "
            "AND cover_at IS NULL "
            f"AND COALESCE(cover_attempts, 0) < {config.COVER_MAX_ATTEMPTS} "
            "ORDER BY fit_score DESC"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [_row_to_job(r) for r in self._conn.execute(sql, ())]

    def set_cover(self, url: str, needed: bool, path: str | None) -> None:
        """Record the cover-letter decision and path for a job."""
        self._conn.execute(
            "UPDATE jobs SET cover_needed = ?, cover_letter_path = ?, cover_at = ? "
            "WHERE url = ?",
            (1 if needed else 0, path, _now(), url),
        )
        self._conn.commit()

    def bump_cover_attempts(self, url: str) -> None:
        """Increment the cover-letter retry counter for a job."""
        self._conn.execute(
            "UPDATE jobs SET cover_attempts = COALESCE(cover_attempts, 0) + 1 "
            "WHERE url = ?",
            (url,),
        )
        self._conn.commit()

    # -- Reads / reporting --------------------------------------------------

    def shortlist(self, min_score: int) -> list[Job]:
        """High-fit jobs, best first — the user-facing result of a run."""
        rows = self._conn.execute(
            "SELECT * FROM jobs WHERE fit_score >= ? ORDER BY fit_score DESC, company",
            (min_score,),
        )
        return [_row_to_job(r) for r in rows]

    def get(self, url: str) -> Job | None:
        """Fetch a single job by URL, or None if not found."""
        row = self._conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
        return _row_to_job(row) if row else None

    def clear_all(self) -> int:
        """Delete every job row and reclaim space. Returns the number removed.

        Backs ``kravu clean``: a full reset of the blackboard so the pipeline can
        be re-run from scratch. Idempotent — clearing an empty table returns 0.
        """
        count = int(self._conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0])
        self._conn.execute("DELETE FROM jobs")
        self._conn.commit()
        self._conn.execute("VACUUM")
        return count

    def stats(self) -> dict[str, int]:
        """Return counts of jobs at each pipeline phase."""
        c = self._conn

        def one(sql: str) -> int:
            return int(c.execute(sql).fetchone()[0])

        return {
            "total": one("SELECT COUNT(*) FROM jobs"),
            "enriched": one(
                "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL"
            ),
            "scored": one("SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL"),
            "tailored": one(
                "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL"
            ),
            "cover": one("SELECT COUNT(*) FROM jobs WHERE cover_at IS NOT NULL"),
        }

    # -- Apply (use case 6) -------------------------------------------------

    def pending_apply(self, min_score: int, limit: int | None = None) -> list[Job]:
        """Tailored, high-fit jobs not yet applied and under the attempt cap."""
        sql = (
            "SELECT * FROM jobs "
            "WHERE tailored_resume_path IS NOT NULL "
            "AND fit_score >= ? "
            "AND (apply_status IS NULL OR apply_status IN ('failed', 'pending')) "
            f"AND COALESCE(apply_attempts, 0) < {config.APPLY_MAX_ATTEMPTS} "
            "ORDER BY fit_score DESC"
        )
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [_row_to_job(r) for r in self._conn.execute(sql, (min_score,))]

    def set_apply_result(self, url: str, status: str, error: str | None) -> None:
        """Record an apply outcome. ``status`` is applied|failed|parked|pending."""
        applied_at = _now() if status == "applied" else None
        self._conn.execute(
            "UPDATE jobs SET apply_status = ?, applied_at = ?, apply_error = ? "
            "WHERE url = ?",
            (status, applied_at, (error or "")[:500] or None, url),
        )
        self._conn.commit()

    def bump_apply_attempts(self, url: str) -> None:
        """Increment the apply attempt counter for a job."""
        self._conn.execute(
            "UPDATE jobs SET apply_attempts = COALESCE(apply_attempts, 0) + 1 "
            "WHERE url = ?",
            (url,),
        )
        self._conn.commit()

    def applied_today(self) -> int:
        """Count submissions recorded today (UTC) — used for the daily cap."""
        today = _now()[:10]
        row = self._conn.execute(
            "SELECT COUNT(*) FROM jobs "
            "WHERE apply_status = 'applied' AND substr(applied_at, 1, 10) = ?",
            (today,),
        ).fetchone()
        return int(row[0])

    # -- Resume / status reporting -----------------------------------------

    def reset_step_for_retry(self, phase: str) -> int:
        """Clear a step's error/attempt state so its pending jobs re-run.

        For ``expand`` this zeroes ``enrich_attempts`` and clears
        ``enrich_error`` on jobs still lacking a ``full_description``. For the
        LLM steps it zeroes the matching ``*_attempts`` counter on jobs that
        have not produced their output yet. ``explore`` is a no-op (discovery is
        re-run wholesale). Returns the number of rows reset.
        """
        resets: dict[str, str] = {
            "expand": (
                "UPDATE jobs SET enrich_attempts = 0, enrich_error = NULL "
                "WHERE full_description IS NULL"
            ),
            "score": (
                "UPDATE jobs SET fit_score = NULL, score_reasoning = NULL "
                "WHERE fit_score IS NULL AND full_description IS NOT NULL"
            ),
            "tailor": (
                "UPDATE jobs SET tailor_attempts = 0 WHERE tailored_resume_path IS NULL"
            ),
            "cover": (
                "UPDATE jobs SET cover_attempts = 0 "
                "WHERE cover_at IS NULL AND tailored_resume_path IS NOT NULL"
            ),
        }
        sql = resets.get(phase)
        if sql is None:
            return 0
        cursor = self._conn.execute(sql)
        self._conn.commit()
        return int(cursor.rowcount)

    def step_counts(self, min_score: int) -> dict[str, dict[str, int]]:
        """Per-phase done/pending counts for ``kravu status``.

        Each phase reports how many jobs have completed it (``done``) and how
        many are still eligible for it (``pending``). This tells the user which
        step to ``resume``.
        """
        c = self._conn

        def one(sql: str, params: tuple[object, ...] = ()) -> int:
            return int(c.execute(sql, params).fetchone()[0])

        total = one("SELECT COUNT(*) FROM jobs")
        counts = {
            PipelinePhase.EXPLORE.value: {"done": total, "pending": 0},
            PipelinePhase.EXPAND.value: {
                "done": one(
                    "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL"
                ),
                "pending": one(
                    "SELECT COUNT(*) FROM jobs WHERE full_description IS NULL "
                    f"AND COALESCE(enrich_attempts, 0) < {config.ENRICH_MAX_ATTEMPTS}"
                ),
            },
            PipelinePhase.SCORE.value: {
                "done": one("SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL"),
                "pending": one(
                    "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL "
                    "AND fit_score IS NULL"
                ),
            },
            PipelinePhase.TAILOR.value: {
                "done": one(
                    "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL"
                ),
                "pending": one(
                    "SELECT COUNT(*) FROM jobs WHERE fit_score >= ? "
                    "AND tailored_resume_path IS NULL "
                    f"AND COALESCE(tailor_attempts, 0) < {config.TAILOR_MAX_ATTEMPTS}",
                    (min_score,),
                ),
            },
            PipelinePhase.COVER.value: {
                "done": one("SELECT COUNT(*) FROM jobs WHERE cover_at IS NOT NULL"),
                "pending": one(
                    "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL "
                    "AND cover_at IS NULL "
                    f"AND COALESCE(cover_attempts, 0) < {config.COVER_MAX_ATTEMPTS}"
                ),
            },
        }
        return counts
