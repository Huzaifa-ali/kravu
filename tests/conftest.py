"""Shared pytest fixtures: an isolated on-disk SQLite DB and reusable fakes."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from kravu.adapters.db import close_connection, init_db
from kravu.adapters.repository import JobRepository


@pytest.fixture()
def kravu_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point kravu at a throwaway home directory for the duration of a test."""
    monkeypatch.setenv("KRAVU_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture()
def repo(kravu_home: Path) -> Iterator[JobRepository]:
    """A JobRepository backed by a fresh temp database."""
    db_file = kravu_home / "kravu.db"
    conn = init_db(db_file)
    yield JobRepository(conn)
    close_connection(db_file)
