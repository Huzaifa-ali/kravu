# Contributing to kravu

Thanks for your interest in improving kravu. This guide covers how to set up a
development environment, the quality bar every change must meet, and how to
propose changes.

## Ground rules

- **kravu is a co-pilot, not a spam-bot.** Contributions must not add mass
  auto-submission, scraping of private personal data, or anything a reasonable
  maintainer would be embarrassed to defend. See [`README.md`](README.md#security--honesty).
- **Never weaken the anti-fabrication guarantees.** The tailoring and cover-letter
  paths must never invent skills, employers, dates, degrees, or metrics.
- **No secrets in code or tests.** API keys live in the environment; tests run
  fully offline with fakes — no real network or LLM calls.

## Development setup

kravu uses [uv](https://docs.astral.sh/uv/) for dependency management and Python 3.11+.

```bash
git clone https://github.com/<owner>/kravu.git
cd kravu
uv sync --extra dev                          # install runtime + dev dependencies
uv run python -m playwright install chromium # one-time browser download (for enrich + apply)
```

## The quality gate

Every change must keep the full gate green. CI runs the same checks on Python
3.11 and 3.12 for every push and pull request.

```bash
uv run ruff format --check src/kravu tests   # formatting
uv run ruff check src/kravu tests            # lint
uv run mypy src/kravu                        # type check (strict)
uv run pytest                                # tests (offline, deterministic)
```

Run `uv run ruff format src/kravu tests` to auto-fix formatting before committing.

## Coding standards

- **Test-driven.** Write a failing test first, then the minimal code to pass it.
  Tests mirror the source layout under `tests/` and use fakes for the LLM,
  network, and browser.
- **Type hints everywhere**, `from __future__ import annotations` at the top of
  every module, modern typing (`list[str]`, `X | None`), Google-style docstrings.
- **Absolute imports only** (`from kravu.services.score import ScoreJobFit`).
- **Parameterized SQL only**, and all SQL stays in `adapters/repository.py`.
- 88-column lines. Ruff (`format` + `check`) is the single source of truth.

Full standards live in [`.kiro/steering/coding-standards.md`](.kiro/steering/coding-standards.md).

## Architecture

kravu follows a layered `domain` / `services` / `adapters` / `entrypoints` layout
(Cosmic Python). Dependencies point inward: business logic lives in `services/`
and depends only on `domain/` ports; infrastructure (SQLite, LiteLLM, HTTP,
JobSpy, Playwright) lives in `adapters/` and implements those ports. Before
changing a component, read [`.kiro/steering/component-design.md`](.kiro/steering/component-design.md)
and the spec under [`docs/`](docs/).

## Commits and pull requests

- Use [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`). One logical change
  per commit.
- Keep pull requests focused. In the description, summarize the change, what you
  tested, and any follow-ups.
- Do not commit generated artifacts (`~/.kravu/` data, `*.db`, caches, `.venv/`) —
  `.gitignore` already excludes them.

## Reporting bugs and requesting features

Open an issue using the provided templates. For anything security-sensitive, see
[`SECURITY.md`](SECURITY.md) instead of filing a public issue.
