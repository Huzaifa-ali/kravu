"""Unit tests for ExpandJob's extraction cascade (renderer + LLM injected)."""

from __future__ import annotations

from kravu.adapters.repository import JobRepository
from kravu.domain.models import Job
from kravu.services.expand import ExpandJob, extract_jsonld

_JSONLD_PAGE = """
<html><head>
<script type="application/ld+json">
{"@type": "JobPosting", "description": "Build and run reliable services. Requirements: Python."}
</script>
</head><body>x</body></html>
"""


class _Renderer:
    def __init__(self, html: str) -> None:
        self._html = html

    def render(self, url: str) -> str:
        return self._html


class _FakeLLM:
    def __init__(self) -> None:
        self.called = False

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        self.called = True
        return "LLM extracted description"


def _discovered(repo: JobRepository, url: str) -> None:
    repo.add_discovered(Job(url=url, title="Dev"))


def test_extract_jsonld_pulls_jobposting_description() -> None:
    result = extract_jsonld(_JSONLD_PAGE)
    assert result is not None
    assert "reliable services" in result


def test_expand_uses_jsonld_and_skips_llm(repo: JobRepository) -> None:
    _discovered(repo, "https://a.test/1")
    llm = _FakeLLM()
    ExpandJob(_Renderer(_JSONLD_PAGE), llm).run(repo)

    job = repo.get("https://a.test/1")
    assert job is not None and job.full_description is not None
    assert "reliable services" in job.full_description
    assert llm.called is False


def test_expand_falls_back_to_llm_on_unknown_layout(repo: JobRepository) -> None:
    _discovered(repo, "https://a.test/2")
    llm = _FakeLLM()
    ExpandJob(_Renderer("<html><body>nothing structured here</body></html>"), llm).run(
        repo
    )

    job = repo.get("https://a.test/2")
    assert job is not None and job.full_description == "LLM extracted description"
    assert llm.called is True


def test_expand_marks_pending_after_render_failure(repo: JobRepository) -> None:
    _discovered(repo, "https://a.test/3")

    class _Boom:
        def render(self, url: str) -> str:
            raise RuntimeError("render failed")

    ExpandJob(_Boom(), _FakeLLM()).run(repo)
    job = repo.get("https://a.test/3")
    assert job is not None
    assert job.full_description is None
    assert job.enrich_attempts == 1
    assert job.enrich_error is not None
