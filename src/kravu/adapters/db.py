"""SQLite backing store: schema, connections, and initialization.

This adapter owns the low-level database concerns for kravu's blackboard: the
single ``jobs`` table (a state machine — a row is created at discovery and
advances as each service fills in its columns), thread-local WAL connections
(safe for parallel workers), and idempotent schema setup.

Queries live in ``adapters/repository.py``; this module only provides the
connection and the schema.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from kravu import config

# ---------------------------------------------------------------------------
# Schema — a single jobs table, all columns declared up front so any service
# can run independently without migration-ordering issues.
# ---------------------------------------------------------------------------

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

# Columns added after the initial schema: name -> SQL type. Applied by
# ``ensure_columns`` so upgrading an existing database is trivial.
_MIGRATION_COLUMNS: dict[str, str] = {}


def ensure_columns(conn: sqlite3.Connection) -> None:
    """Add any missing columns to an existing ``jobs`` table (forward migration)."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}
    for column, sql_type in _MIGRATION_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {sql_type}")
    conn.commit()


# ---------------------------------------------------------------------------
# Connections — thread-local, WAL-enabled.
# ---------------------------------------------------------------------------

_local = threading.local()


def get_connection(path: Path | str | None = None) -> sqlite3.Connection:
    """Return a thread-local, WAL-enabled SQLite connection.

    Each thread gets its own cached connection (SQLite connections are not safe
    to share across threads). Reused within the same thread.

    Args:
        path: Override the default database path (useful for tests).

    Returns:
        A configured ``sqlite3.Connection`` with a row factory.
    """
    resolved = str(path or config.db_path())

    if not hasattr(_local, "connections"):
        _local.connections = {}

    conn = _local.connections.get(resolved)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.ProgrammingError:
            pass  # connection was closed; recreate below

    Path(resolved).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(resolved, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    _local.connections[resolved] = conn
    return conn


def close_connection(path: Path | str | None = None) -> None:
    """Close and forget the current thread's connection for ``path``."""
    resolved = str(path or config.db_path())
    if hasattr(_local, "connections"):
        conn = _local.connections.pop(resolved, None)
        if conn is not None:
            conn.close()


def init_db(path: Path | str | None = None) -> sqlite3.Connection:
    """Create the schema if needed. Idempotent; safe to call on every startup."""
    conn = get_connection(path)
    conn.execute(CREATE_JOBS_TABLE)
    conn.commit()
    ensure_columns(conn)
    return conn
