"""Unit tests for the resume-text reader adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from kravu.adapters.resume_reader import read_resume_text
from kravu.exceptions import ConfigError


def test_read_plain_text_file(tmp_path: Path) -> None:
    cv = tmp_path / "cv.txt"
    cv.write_text("Jane Dev\nBuilt X at Acme.", encoding="utf-8")
    assert read_resume_text(cv) == "Jane Dev\nBuilt X at Acme."


def test_read_markdown_file(tmp_path: Path) -> None:
    cv = tmp_path / "cv.md"
    cv.write_text("# Jane\n\n- Python", encoding="utf-8")
    assert read_resume_text(cv).startswith("# Jane")


def test_missing_file_raises_config_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        read_resume_text(tmp_path / "nope.txt")


def test_empty_file_raises_config_error(tmp_path: Path) -> None:
    cv = tmp_path / "empty.txt"
    cv.write_text("   \n\t", encoding="utf-8")
    with pytest.raises(ConfigError):
        read_resume_text(cv)


def test_unsupported_format_raises_actionable_error(tmp_path: Path) -> None:
    # An unsupported extension must fail with an actionable message naming the
    # supported formats, never silently return garbage.
    cv = tmp_path / "resume.rtf"
    cv.write_text("some rtf", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        read_resume_text(cv)
    assert ".pdf" in str(exc.value)
