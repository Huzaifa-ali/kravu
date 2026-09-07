"""JobRepository: the only place that runs SQL against the jobs table.

Use cases depend on this interface, not on SQLite. Swapping to Postgres later means
writing another implementation with the same methods — no use-case code changes.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from kravu.domain.models import Job
from kravu.adapters.db import get_connection

# Columns that map 1:1 between the Job dataclass and the jobs table.
_JOB_COLUMNS = (
    "url", "title", "company", "location", "salary", "source", "apply_type",
    "description", "discovered_at",
    "full_description", "apply_url", "enriched_at", "enrich_error", "enrich_attempts",
    "fit_score", "score_reasoning", "scored_at",
    "tailored_resume_path", "tailored_at", "tailor_attempts",
    "cover_letter_path", "cover_needed", "cover_at", "cover_attempts",
    "apply_status", "applied_at", "apply_error", "apply_attempts",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_job(row: sqlite3.Row) -> Job:
    data = {k: row[k] for k in row.keys() if k in _JOB_COLUMNS}
    # SQLite stores booleans as ints; normalize cover_needed back to bool/None.
    if data.get("cover_needed") is not None:
        data["cover_needed"] = bool(data["cover_needed"])
    return Job(**data)


class JobRepository:
    """CRUD + per-use-case queries for jobs. Construct once per thread."""

    def __init__(self, conn: sqlite3.Connection | None = None) -> None:
        self._conn = conn or get_connection()

    # -- Discovery ----------------------------------------------------------

    def add_discovered(self, job: Job) -> bool:
        """Insert a newly discovered job. Returns False if the URL already exists
        (deduplication by URL, the natural primary key)."""
        try:
            self._conn.execute(
                """
                INSERT INTO jobs (url, title, company, location, salary, source,
                                  apply_type, description, discovered_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.url, job.title, job.company, job.location, job.salary,
                    job.source, job.apply_type, job.description,
                    job.discovered_at or _now(),
                ),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # duplicate URL — already discovered

    # -- Enrichment ---------------------------------------------------------

    def pending_enrichment(self, limit: int | None = None) -> list[Job]:
        # A job needs enrichment if it has no full description yet and hasn't
        # exhausted its retry budget (3 attempts). This makes ExpandJob retryable
        # across runs: pending jobs are picked up again until they succeed or hit 3.
        sql = ("SELECT * FROM jobs "
               "WHERE full_description IS NULL AND COALESCE(enrich_attempts, 0) < 3")
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [_row_to_job(r) for r in self._conn.execute(sql)]

    def set_enrichment(self, url: str, full_description: str,
                       apply_url: str | None) -> None:
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
        self._conn.execute(
            "UPDATE jobs SET enrich_attempts = COALESCE(enrich_attempts, 0) + 1 WHERE url = ?",
            (url,),
        )
        self._conn.commit()

    def set_enrichment_error(self, url: str, error: str) -> None:
        # Record the latest error; do NOT set enriched_at — the job stays pending
        # (retryable) until full_description is set or attempts reach 3.
        self._conn.execute(
            "UPDATE jobs SET enrich_error = ? WHERE url = ?",
            (error[:500], url),
        )
        self._conn.commit()

    # -- Scoring ------------------------------------------------------------

    def pending_scoring(self, limit: int | None = None) -> list[Job]:
        sql = ("SELECT * FROM jobs "
               "WHERE full_description IS NOT NULL AND fit_score IS NULL")
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [_row_to_job(r) for r in self._conn.execute(sql)]

    def set_score(self, url: str, score: int, reasoning: str) -> None:
        self._conn.execute(
            "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ? WHERE url = ?",
            (score, reasoning, _now(), url),
        )
        self._conn.commit()

    # -- Tailoring ----------------------------------------------------------

    def pending_tailoring(self, min_score: int, limit: int | None = None) -> list[Job]:
        sql = ("SELECT * FROM jobs "
               "WHERE fit_score >= ? AND full_description IS NOT NULL "
               "AND tailored_resume_path IS NULL "
               "AND COALESCE(tailor_attempts, 0) < 5 "
               "ORDER BY fit_score DESC")
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [_row_to_job(r) for r in self._conn.execute(sql, (min_score,))]

    def set_tailored(self, url: str, resume_path: str) -> None:
        self._conn.execute(
            "UPDATE jobs SET tailored_resume_path = ?, tailored_at = ? WHERE url = ?",
            (resume_path, _now(), url),
        )
        self._conn.commit()

    def bump_tailor_attempts(self, url: str) -> None:
        self._conn.execute(
            "UPDATE jobs SET tailor_attempts = COALESCE(tailor_attempts, 0) + 1 WHERE url = ?",
            (url,),
        )
        self._conn.commit()

    # -- Cover letter -------------------------------------------------------

    def pending_cover(self, min_score: int, limit: int | None = None) -> list[Job]:
        sql = ("SELECT * FROM jobs "
               "WHERE tailored_resume_path IS NOT NULL "
               "AND cover_at IS NULL "
               "AND COALESCE(cover_attempts, 0) < 5 "
               "ORDER BY fit_score DESC")
        if limit:
            sql += f" LIMIT {int(limit)}"
        return [_row_to_job(r) for r in self._conn.execute(sql, ())]

    def set_cover(self, url: str, needed: bool, path: str | None) -> None:
        self._conn.execute(
            "UPDATE jobs SET cover_needed = ?, cover_letter_path = ?, cover_at = ? WHERE url = ?",
            (1 if needed else 0, path, _now(), url),
        )
        self._conn.commit()

    def bump_cover_attempts(self, url: str) -> None:
        self._conn.execute(
            "UPDATE jobs SET cover_attempts = COALESCE(cover_attempts, 0) + 1 WHERE url = ?",
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
        row = self._conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
        return _row_to_job(row) if row else None

    def stats(self) -> dict[str, int]:
        c = self._conn
        one = lambda sql: c.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "total": one("SELECT COUNT(*) FROM jobs"),
            "enriched": one("SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL"),
            "scored": one("SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL"),
            "tailored": one("SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL"),
            "cover": one("SELECT COUNT(*) FROM jobs WHERE cover_at IS NOT NULL"),
        }
