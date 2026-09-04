"""Database schema for kravu.

A single ``jobs`` table acts as a state machine: a row is created at discovery
and advances left-to-right as each stage fills in its columns. Pending work for
a stage is "rows where my input column is set but my output column is NULL".

All columns from every stage are declared up front so any stage can run
independently without migration-ordering headaches. ``ensure_columns`` adds any
columns introduced in later versions to an existing database.
"""

from __future__ import annotations

import sqlite3

CREATE_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    -- Discovery
    url                   TEXT PRIMARY KEY,
    title                 TEXT,
    company               TEXT,
    location              TEXT,
    salary                TEXT,
    source                TEXT,
    description           TEXT,
    discovered_at         TEXT,

    -- Enrichment
    full_description      TEXT,
    apply_url             TEXT,
    enriched_at           TEXT,
    enrich_error          TEXT,

    -- Scoring
    fit_score             INTEGER,
    score_reasoning       TEXT,
    scored_at             TEXT,

    -- Tailoring
    tailored_resume_path  TEXT,
    tailored_at           TEXT,
    tailor_attempts       INTEGER DEFAULT 0,

    -- Cover letter
    cover_letter_path     TEXT,
    cover_needed          INTEGER,
    cover_at              TEXT,
    cover_attempts        INTEGER DEFAULT 0
)
"""

# Columns that may need to be added to older databases: name -> SQL type.
_MIGRATION_COLUMNS: dict[str, str] = {
    # Reserved for future stages (e.g. apply). Kept here so upgrades are trivial.
}


def ensure_columns(conn: sqlite3.Connection) -> None:
    """Add any missing columns to an existing ``jobs`` table (forward migration)."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    for column, sql_type in _MIGRATION_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {sql_type}")
    conn.commit()
