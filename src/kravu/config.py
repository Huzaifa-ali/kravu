"""Configuration, paths, and environment loading for kravu.

kravu is local-first: all runtime data lives under a single app directory
(``~/.kravu`` by default, overridable with ``KRAVU_HOME``). Configuration comes
from environment variables (optionally via a ``.env`` file) and two user files:

    profile.json   — the user's CV facts, contact info, and targets
    searches.yaml  — what jobs to look for

Nothing here imports heavy dependencies at module load; helpers import lazily.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kravu.exceptions import ConfigError

APP_NAME = "kravu"


def app_home() -> Path:
    """Root directory for all kravu runtime data.

    Defaults to a ``.kravu`` directory inside the repository (anchored to this
    source file, so it resolves the same regardless of the current working
    directory). Override with the ``KRAVU_HOME`` environment variable — e.g. to
    keep runtime data outside the repo or to isolate a test run.
    """
    override = os.environ.get("KRAVU_HOME")
    if override:
        return Path(override).expanduser()
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / f".{APP_NAME}"


# Derived paths -------------------------------------------------------------


def db_path() -> Path:
    """Path to the SQLite database file."""
    return app_home() / "kravu.db"


def profile_path() -> Path:
    """Path to the user's ``profile.json``."""
    return app_home() / "profile.json"


def searches_path() -> Path:
    """Path to the user's ``searches.yaml``."""
    return app_home() / "searches.yaml"


def tailored_dir() -> Path:
    """Directory for tailored resumes."""
    return app_home() / "tailored"


def cover_dir() -> Path:
    """Directory for generated cover letters."""
    return app_home() / "cover_letters"


def log_dir() -> Path:
    """Directory for log files."""
    return app_home() / "logs"


def ensure_dirs() -> None:
    """Create all runtime directories. Idempotent."""
    for d in (app_home(), tailored_dir(), cover_dir(), log_dir()):
        d.mkdir(parents=True, exist_ok=True)


# Environment / settings ----------------------------------------------------


def load_env() -> None:
    """Load ``.env`` from the app home and the current directory, if present."""
    from dotenv import load_dotenv

    env_file = app_home() / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    load_dotenv()  # also pick up a .env in the CWD as a fallback


# Valid cover-letter policies. The configured values live in the environment:
#   KRAVU_MODEL, KRAVU_MIN_SCORE, KRAVU_COVER_LETTER (see .env.example).
_VALID_COVER_POLICIES = frozenset({"always", "only_if_required", "never"})


def model() -> str:
    """The configured LLM model identifier, from ``KRAVU_MODEL``.

    kravu is provider-agnostic and never hardcodes a model. The value must be set
    in the environment (or ``~/.kravu/.env`` / project ``.env``); ``kravu init``
    writes it for you.

    Raises:
        ConfigError: ``KRAVU_MODEL`` is not set.
    """
    value = os.environ.get("KRAVU_MODEL")
    if not value:
        raise ConfigError(
            "KRAVU_MODEL is not set. Run `kravu init` to choose a model, or set "
            "KRAVU_MODEL in your environment / .env (see .env.example for options)."
        )
    return value


def min_score() -> int:
    """The minimum fit score for shortlisting, from ``KRAVU_MIN_SCORE``.

    Raises:
        ConfigError: ``KRAVU_MIN_SCORE`` is unset or not a valid integer.
    """
    raw = os.environ.get("KRAVU_MIN_SCORE")
    if not raw:
        raise ConfigError(
            "KRAVU_MIN_SCORE is not set. Run `kravu init`, or set KRAVU_MIN_SCORE "
            "in your environment / .env (see .env.example)."
        )
    try:
        return int(raw)
    except ValueError:
        raise ConfigError(f"KRAVU_MIN_SCORE must be an integer, got {raw!r}.") from None


def cover_letter_default() -> str:
    """The cover-letter policy, from ``KRAVU_COVER_LETTER``.

    One of ``always`` | ``only_if_required`` | ``never``. (``searches.yaml`` may
    also carry a ``cover_letter`` key that overrides this per run.)

    Raises:
        ConfigError: ``KRAVU_COVER_LETTER`` is unset or not a valid policy.
    """
    raw = (os.environ.get("KRAVU_COVER_LETTER") or "").strip()
    if not raw:
        raise ConfigError(
            "KRAVU_COVER_LETTER is not set. Run `kravu init`, or set "
            "KRAVU_COVER_LETTER in your environment / .env (see .env.example)."
        )
    if raw not in _VALID_COVER_POLICIES:
        raise ConfigError(
            f"KRAVU_COVER_LETTER must be one of {sorted(_VALID_COVER_POLICIES)}, "
            f"got {raw!r}."
        )
    return raw


def has_llm_key() -> bool:
    """True if any known provider key is present in the environment."""
    keys = (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "COHERE_API_KEY",
    )
    if any(os.environ.get(k) for k in keys):
        return True
    # Local providers (Ollama) need no key.
    return (os.environ.get("KRAVU_MODEL") or "").startswith("ollama/")


@dataclass(frozen=True, slots=True)
class ModelOption:
    """A selectable provider/model shown by ``kravu init`` (spec §9)."""

    model: str  # the KRAVU_MODEL string passed to LiteLLM
    label: str  # human-readable menu label
    env_key: str | None  # required env var, or None for local (Ollama)


# Provider/model options offered by `init` (spec §9). Model strings move often and
# are all overridable via KRAVU_MODEL; the default is first.
_MODEL_OPTIONS: tuple[ModelOption, ...] = (
    ModelOption(
        "gemini/gemma-4-26b-a4b-it",
        "Gemini — Gemma 4 26B (default, smaller/faster)",
        "GEMINI_API_KEY",
    ),
    ModelOption(
        "gemini/gemma-4-31b-it", "Gemini — Gemma 4 31B (larger)", "GEMINI_API_KEY"
    ),
    ModelOption(
        "gemini/gemini-2.5-flash",
        "Gemini — 2.5 Flash (most reliable free tier)",
        "GEMINI_API_KEY",
    ),
    ModelOption("ollama/qwen3.5:4b", "Ollama — Qwen (small, local)", None),
    ModelOption("ollama/qwen3.8:27b", "Ollama — Qwen (latest, local)", None),
    ModelOption(
        "anthropic/claude-sonnet-5", "Anthropic — Claude Sonnet 5", "ANTHROPIC_API_KEY"
    ),
    ModelOption("gpt-6-astra", "OpenAI — GPT-6 Astra", "OPENAI_API_KEY"),
)

# Fallback provider-prefix -> env var, for models typed/overridden outside the menu.
_PROVIDER_KEYS: tuple[tuple[str, str], ...] = (
    ("gemini/", "GEMINI_API_KEY"),
    ("anthropic/", "ANTHROPIC_API_KEY"),
    ("openai/", "OPENAI_API_KEY"),
    ("gpt-", "OPENAI_API_KEY"),
    ("cohere/", "COHERE_API_KEY"),
)


def model_options() -> list[ModelOption]:
    """Return the selectable provider/model options (default first)."""
    return list(_MODEL_OPTIONS)


def required_key_for(model_string: str) -> str | None:
    """Return the env var a model needs, or None if it needs none (Ollama/local).

    Args:
        model_string: A ``KRAVU_MODEL`` value (menu choice or manual override).

    Returns:
        The required environment variable name, or ``None`` for local models.
    """
    if model_string.startswith("ollama/"):
        return None
    for option in _MODEL_OPTIONS:
        if option.model == model_string:
            return option.env_key
    for prefix, env_key in _PROVIDER_KEYS:
        if model_string.startswith(prefix):
            return env_key
    return None


def key_present_for_model(model_string: str) -> bool:
    """True if the env var a model requires is set (always True for local models).

    Google accepts either ``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``; either satisfies
    a Gemini model.
    """
    required = required_key_for(model_string)
    if required is None:
        return True
    if os.environ.get(required):
        return True
    if required == "GEMINI_API_KEY" and os.environ.get("GOOGLE_API_KEY"):
        return True
    return False


# User files ----------------------------------------------------------------


def load_profile() -> dict[str, Any]:
    """Load ``profile.json``; raise a clear error if the user hasn't run init."""
    p = profile_path()
    if not p.exists():
        raise FileNotFoundError(f"No profile found at {p}. Run `kravu init` first.")
    data: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    return data


def load_searches() -> dict[str, Any]:
    """Load ``searches.yaml``; return an empty dict if absent."""
    import yaml

    p = searches_path()
    if not p.exists():
        return {}
    result: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return result


def profile_exists() -> bool:
    """True if a ``profile.json`` has already been written."""
    return profile_path().exists()


def searches_exist() -> bool:
    """True if a ``searches.yaml`` has already been written."""
    return searches_path().exists()


def save_profile(profile: Any) -> None:
    """Write a ``Profile`` to ``profile.json`` (setup-time; used by ``init``).

    The JSON shape mirrors what ``load_profile`` reads back, including the nested
    ``resume_facts`` block (the tailoring ground truth).

    Args:
        profile: A ``kravu.domain.models.Profile`` instance.
    """
    facts = profile.resume_facts
    data = {
        "name": profile.name,
        "email": profile.email,
        "headline": profile.headline,
        "location": profile.location,
        "summary": profile.summary,
        "skills": list(profile.skills),
        "resume_facts": {
            "raw_text": facts.raw_text,
            "companies": list(facts.companies),
            "school": facts.school,
            "metrics": list(facts.metrics),
            "skills": list(facts.skills),
        },
        "target_titles": list(profile.target_titles),
        "target_locations": list(profile.target_locations),
    }
    ensure_dirs()
    profile_path().write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def save_searches(searches: dict[str, Any]) -> None:
    """Write a searches config to ``searches.yaml`` (setup-time; used by ``init``).

    Args:
        searches: A validated searches dict (see ``SuggestSearches`` / spec §13a).
    """
    import yaml

    ensure_dirs()
    searches_path().write_text(
        yaml.safe_dump(searches, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def set_model_in_env_file(model_string: str) -> Path:
    """Persist ``KRAVU_MODEL`` to ``~/.kravu/.env`` so later runs pick it up.

    Rewrites an existing ``KRAVU_MODEL=`` line if present, otherwise appends one.
    The key itself is never written here — kravu never stores API keys (spec §9).

    Args:
        model_string: The chosen ``KRAVU_MODEL`` value.

    Returns:
        The path to the ``.env`` file that was written.
    """
    ensure_dirs()
    env_file = app_home() / ".env"
    line = f"KRAVU_MODEL={model_string}"
    if env_file.exists():
        kept = [
            existing
            for existing in env_file.read_text(encoding="utf-8").splitlines()
            if not existing.strip().startswith("KRAVU_MODEL=")
        ]
        kept.append(line)
        env_file.write_text("\n".join(kept) + "\n", encoding="utf-8")
    else:
        env_file.write_text(line + "\n", encoding="utf-8")
    return env_file
