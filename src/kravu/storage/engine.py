"""SQLite engine: connections and schema initialization.

Thread-local connections (safe for the parallel workers used in discovery /
enrichment) with WAL mode for concurrent readers. This module owns the
low-level DB concerns; ``schema.py`` owns the table definition and ``repository.py``
owns the queries.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from kravu import config
from kravu.storage.schema import CREATE_JOBS_TABLE, ensure_columns

_local = threading.local()


def get_connection(path: Path | str | None = None) -> sqlite3.Connection:
    """Return a thread-local, WAL-enabled SQLite connection.

    Each thread gets its own cached connection (SQLite connections are not safe
    to share across threads). Reused within the same thread.
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
