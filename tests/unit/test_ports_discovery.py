"""The DiscoverySource port takes searches and a run limit."""

from __future__ import annotations

import inspect

from kravu.domain.ports import DiscoverySource


def test_discover_signature_has_limit() -> None:
    sig = inspect.signature(DiscoverySource.discover)
    assert "limit" in sig.parameters
