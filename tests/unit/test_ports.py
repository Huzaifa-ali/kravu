"""Unit tests for the domain port protocols."""

from __future__ import annotations

from kravu.domain.ports import DiscoverySource, JobStore, LLMClient


def test_job_repository_satisfies_job_store() -> None:
    from kravu.adapters.repository import JobRepository

    assert issubclass(JobRepository, JobStore)


def test_llm_client_is_runtime_checkable() -> None:
    class FakeLLM:
        def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
            return "{}"

    assert isinstance(FakeLLM(), LLMClient)


def test_discovery_source_is_runtime_checkable() -> None:
    class FakeSource:
        name = "fake"

        def discover(self, searches: dict[str, object]) -> list[object]:
            return []

    assert isinstance(FakeSource(), DiscoverySource)
