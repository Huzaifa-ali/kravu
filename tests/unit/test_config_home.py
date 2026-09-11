"""Unit tests for app_home() location resolution.

The app home defaults to an in-repo ``.kravu`` directory (anchored to the source
tree, so it is stable regardless of the current working directory) and remains
overridable by the ``KRAVU_HOME`` environment variable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from kravu import config


def test_app_home_honors_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KRAVU_HOME", "/tmp/custom-kravu")
    assert config.app_home() == Path("/tmp/custom-kravu")


def test_app_home_defaults_to_in_repo_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KRAVU_HOME", raising=False)
    home = config.app_home()
    # The default lives inside the repo, next to src/, named ".kravu".
    assert home.name == ".kravu"
    repo_root = Path(config.__file__).resolve().parents[2]
    assert home == repo_root / ".kravu"


def test_app_home_is_stable_across_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("KRAVU_HOME", raising=False)
    monkeypatch.chdir(tmp_path)  # running from an unrelated directory
    home = config.app_home()
    repo_root = Path(config.__file__).resolve().parents[2]
    assert home == repo_root / ".kravu"
