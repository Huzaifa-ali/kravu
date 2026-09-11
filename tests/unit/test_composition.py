"""Unit tests for composition wiring (no Typer, no heavy adapters)."""

from __future__ import annotations

from kravu.domain.models import Profile, ResumeFacts
from kravu.entrypoints.composition import build_pipeline_steps, select_driver


class _FakeLLM:
    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        return "{}"


class _FakeSource:
    name = "fake"

    def discover(self, searches: dict[str, object], limit: int) -> list[object]:
        return []


class _FakeRenderer:
    def render(self, url: str) -> str:
        return "<html></html>"


def _profile() -> Profile:
    return Profile(resume_facts=ResumeFacts(raw_text="x", skills=["Python"]))


def test_build_pipeline_steps_in_order() -> None:
    steps = build_pipeline_steps(
        sources=[_FakeSource()],
        llm=_FakeLLM(),
        profile=_profile(),
        renderer=_FakeRenderer(),
        min_score=7,
        cover_policy="only_if_required",
        searches={"searches": []},
        limit=25,
    )
    assert [s.name for s in steps] == ["explore", "expand", "score", "tailor", "cover"]


def test_explore_step_adapts_signature(repo) -> None:  # type: ignore[no-untyped-def]
    # The explore step must accept run(store, limit=None) and not crash when the
    # pipeline calls it — it internally calls ExploreJobs.run(store, searches, limit).
    steps = build_pipeline_steps(
        sources=[_FakeSource()],
        llm=_FakeLLM(),
        profile=_profile(),
        renderer=_FakeRenderer(),
        min_score=7,
        cover_policy="only_if_required",
        searches={"searches": []},
        limit=25,
    )
    explore_step = steps[0]
    explore_step.use_case.run(repo, None)  # must not raise


def test_build_pipeline_steps_defaults_are_serial_safe() -> None:
    steps = build_pipeline_steps(
        sources=[_FakeSource()],
        llm=_FakeLLM(),
        profile=_profile(),
        renderer=_FakeRenderer(),
        min_score=7,
        cover_policy="never",
        searches={"searches": []},
        limit=10,
    )
    assert [s.name for s in steps] == ["explore", "expand", "score", "tailor", "cover"]


def test_select_driver_defaults_to_kiro() -> None:
    assert select_driver("kiro").name == "kiro"
    assert select_driver("claude_code").name == "claude_code"
    assert select_driver("unknown").name == "kiro"
