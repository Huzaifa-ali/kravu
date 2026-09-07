"""Unit tests for the kravu exception hierarchy."""

from __future__ import annotations

import pytest

from kravu.exceptions import (
    ConfigError,
    EnrichmentError,
    FabricationError,
    KravuError,
    LLMResponseError,
    ProfileNotFoundError,
    SearchesConfigError,
)


def test_all_kravu_errors_subclass_base() -> None:
    for cls in (
        ConfigError,
        SearchesConfigError,
        ProfileNotFoundError,
        LLMResponseError,
        EnrichmentError,
        FabricationError,
    ):
        assert issubclass(cls, KravuError)


def test_kravu_error_carries_message() -> None:
    err = ProfileNotFoundError("Run `kravu init` first.")
    assert str(err) == "Run `kravu init` first."


def test_kravu_error_is_exception() -> None:
    with pytest.raises(KravuError):
        raise LLMResponseError("bad json")
