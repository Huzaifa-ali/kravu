"""Unit tests for the browser-agent driver base contract."""

from __future__ import annotations

from kravu.apply.drivers.base import BrowserAgentDriver, DriverResult, parse_result_line


def test_parse_applied() -> None:
    assert parse_result_line("RESULT:APPLIED") == DriverResult("applied", None)


def test_parse_failed_with_reason() -> None:
    assert parse_result_line("RESULT:FAILED:login wall") == DriverResult(
        "failed", "login wall"
    )


def test_parse_captcha() -> None:
    assert parse_result_line("RESULT:CAPTCHA") == DriverResult("parked", "captcha")


def test_parse_missing_line_is_failed() -> None:
    assert parse_result_line("garbage output").status == "failed"


def test_parse_uses_last_result_line() -> None:
    # Reverse scan: the agent's final RESULT line wins over earlier ones.
    output = "progress...\nRESULT:FAILED:old\nmore\nRESULT:APPLIED"
    assert parse_result_line(output) == DriverResult("applied", None)


def test_protocol_is_runtime_checkable() -> None:
    class Fake:
        name = "fake"

        def build_command(self, prompt: str, mcp_config_path: str) -> list[str]:
            return ["echo", prompt]

    assert isinstance(Fake(), BrowserAgentDriver)
