"""Unit tests for the apply gate (mode + daily cap + approval)."""

from __future__ import annotations

from kravu.apply.gate import ApplyGate


def test_human_gate_requires_approval() -> None:
    gate = ApplyGate(mode="human_gate", daily_cap=10, approver=lambda url: False)
    assert gate.may_submit("https://a.test/1", applied_today=0) is False


def test_human_gate_allows_when_approved() -> None:
    gate = ApplyGate(mode="human_gate", daily_cap=10, approver=lambda url: True)
    assert gate.may_submit("https://a.test/1", applied_today=0) is True


def test_auto_mode_skips_approval_but_respects_cap() -> None:
    gate = ApplyGate(mode="auto", daily_cap=5, approver=lambda url: False)
    assert gate.may_submit("https://a.test/1", applied_today=4) is True
    assert gate.may_submit("https://a.test/1", applied_today=5) is False
