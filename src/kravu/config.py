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
from pathlib import Path
from typing import Any

APP_NAME = "kravu"


def app_home() -> Path:
    """Root directory for all kravu runtime data."""
    override = os.environ.get("KRAVU_HOME")
    return Path(override).expanduser() if override else Path.home() / f".{APP_NAME}"


# Derived paths -------------------------------------------------------------

def db_path() -> Path:
    return app_home() / "kravu.db"


def profile_path() -> Path:
    return app_home() / "profile.json"


def searches_path() -> Path:
    return app_home() / "searches.yaml"


def tailored_dir() -> Path:
    return app_home() / "tailored"


def cover_dir() -> Path:
    return app_home() / "cover_letters"


def log_dir() -> Path:
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


DEFAULTS: dict[str, Any] = {
    "model": "gemini/gemini-2.0-flash",
    "min_score": 7,
}


def model() -> str:
    return os.environ.get("KRAVU_MODEL") or DEFAULTS["model"]


def min_score() -> int:
    raw = os.environ.get("KRAVU_MIN_SCORE")
    try:
        return int(raw) if raw else DEFAULTS["min_score"]
    except ValueError:
        return DEFAULTS["min_score"]


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
    return model().startswith("ollama/")


# User files ----------------------------------------------------------------

def load_profile() -> dict:
    """Load ``profile.json``; raise a clear error if the user hasn't run init."""
    p = profile_path()
    if not p.exists():
        raise FileNotFoundError(
            f"No profile found at {p}. Run `kravu init` first."
        )
    return json.loads(p.read_text(encoding="utf-8"))


def load_searches() -> dict:
    """Load ``searches.yaml``; return an empty dict if absent."""
    import yaml

    p = searches_path()
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
