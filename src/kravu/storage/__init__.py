"""Storage layer for kravu.

The database is the pipeline's *blackboard*: every stage reads the jobs that
need its work and writes its results back. The public surface is the
``JobRepository`` — stages never touch SQL directly, which keeps the storage
backend swappable (SQLite today, Postgres later) behind one interface.
"""

from kravu.storage.engine import get_connection, init_db
from kravu.storage.repository import JobRepository

__all__ = ["get_connection", "init_db", "JobRepository"]
