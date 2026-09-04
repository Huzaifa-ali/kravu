# kravu — Coding Standards

Binding rules for all Python in this project. These are enforced by tooling where
possible and by review otherwise. When these conflict with a habit, these win.

## Tooling (single source of truth: `pyproject.toml`)

- **Format + lint:** [Ruff](https://docs.astral.sh/ruff/) — replaces black, isort,
  flake8. Run `ruff format` and `ruff check --fix`.
- **Type check:** mypy in `strict` mode over `src/kravu`.
- **Tests:** pytest.
- **Line length:** 88 characters.
- **Target:** Python 3.11+.

CI (and pre-commit, if installed) must pass: `ruff format --check`,
`ruff check`, `mypy src/kravu`, `pytest`.

## Language conventions

- **`from __future__ import annotations`** at the top of every module.
- **Modern typing syntax only:** `list[str]`, `dict[str, int]`, `X | None`.
  Do NOT import `List`, `Dict`, `Optional`, `Union` from `typing`.
- **Full type hints** on all function signatures (params and return), including
  `-> None`. Public data structures are typed dataclasses, not loose dicts.
- **Absolute imports only:** `from kravu.storage.repository import JobRepository`.
  No relative imports (`from ..storage import`).
- **Import order** (Ruff/isort enforces): future, stdlib, third-party, first-party
  (`kravu`), local. One import group per block, blank line between.

## Naming

- `snake_case` — functions, methods, variables, modules.
- `PascalCase` — classes, dataclasses, enums.
- `UPPER_SNAKE_CASE` — module-level constants.
- `_leading_underscore` — private/internal functions, attributes, module helpers.
- Names say what a thing IS or DOES; no abbreviations that aren't domain-standard
  (`url`, `db`, `llm` are fine; `desc`, `cfg`, `mgr` are not — write
  `description`, `config`, `manager`).

## Docstrings & comments

- **Google-style docstrings** on every public module, class, and function.
  A one-line summary; then `Args:`, `Returns:`, `Raises:` where they add value.
- Docstrings explain *what* and *why*; comments explain *why*, never *what* the
  code already says. Delete commented-out code — git remembers it.
- Module docstring states the module's single responsibility and its dependencies.

## Functions & structure

- One responsibility per function. If you need "and" to describe it, split it.
- Prefer pure functions; isolate side effects (DB writes, network, file I/O).
- Guard clauses / early returns over deep nesting (max ~3 levels).
- No function longer than it needs to be; if it doesn't fit on a screen, question it.
- Files have one clear responsibility; split by responsibility when they grow.

## Errors

- Define a typed hierarchy in `kravu/exceptions.py` (base `KravuError`, then
  specific subclasses like `ProfileNotFoundError`, `EnrichmentError`).
- Raise specific exceptions with actionable messages (tell the user what to do).
- **Never** bare `except:` or `except Exception: pass`. Catch the narrowest type;
  if you must catch broadly, log and re-raise or record the error on the job row.
- A per-job failure in a stage is recorded on that row and the run continues; it
  does not raise out of the pipeline.

## SQL & data safety

- Parameterized queries only. Never f-string user/data values into SQL.
  (Static, code-controlled `LIMIT` interpolation is the only allowed exception.)
- All SQL lives in `storage/repository.py`. Stages never see SQL.

## Configuration & secrets

- No secrets, keys, or absolute machine paths in code. Everything via env / `.env`
  / the `config` module.
- No hardcoded LLM provider or model in stage logic — always via `config.model()`.

## Tests (see also stack.md)

- TDD: failing test first, minimal code to pass, then refactor.
- Tests mirror source layout under `tests/`.
- No real network or LLM calls in unit tests — inject fakes/mocks. The suite runs
  offline and is deterministic.
- Test behavior and public interfaces, not private internals. Name tests
  `test_<unit>_<behavior>_<expected>`.

## Comments on AI-generated code

This is an AI-assisted project. Every generated change must still obey these
standards. "The model wrote it" is not an exemption. If generated code adds
unrequested abstraction, config, or stages, remove it (see principles.md: low slop).
