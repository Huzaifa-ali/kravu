# kravu — Stack & Coding Conventions

## Stack

- **Language:** Python 3.11+
- **Packaging:** `uv`, src-layout, `pyproject.toml`
- **CLI:** Typer + Rich
- **Storage:** SQLite (stdlib `sqlite3`, WAL mode) behind the repository interface;
  Postgres is a future swap, not a v1 dependency.
- **LLM:** LiteLLM (one interface, any provider)
- **Discovery:** JobSpy (`python-jobspy`) — multi-board, no API key
- **Detail fetch (ExpandJob):** httpx; parsing via selectolax / trafilatura, LLM fallback
- **Config:** PyYAML + python-dotenv; `profile.json` for user data
- **Browser agent (later phase):** Playwright + `@playwright/mcp`, pluggable driver

## Conventions

Full coding standards live in `.kiro/steering/coding-standards.md` (binding).
Highlights:

- **Type hints everywhere.** `from __future__ import annotations` at the top.
- **Docstrings** (Google style) on modules and public functions.
- **No secrets in code.** All keys via environment / `.env`.
- **Parameterized SQL only.** Never string-interpolate user/data values into SQL.
- **Errors are explicit.** A stage that fails one job records the error on that
  job's row and continues; it does not crash the whole run.
- **Idempotent stages.** Re-running a stage must be safe (overwrite/skip, never
  duplicate). This is why discovery dedupes by URL (the primary key).

## Testing (TDD)

- Tests live under `tests/`, mirroring `src/kravu/`.
- Write the failing test first, then the minimal implementation.
- LLM and network calls are mocked in unit tests — tests must run offline and
  deterministically. No real API calls in the test suite.
- Runner: `pytest`. Lint/format: `ruff`. Types: `mypy`.

## Commits

- Small, frequent, conventional commits (`feat:`, `fix:`, `test:`, `docs:`,
  `refactor:`, `chore:`).
- One logical change per commit.
