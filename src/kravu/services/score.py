"""ScoreJobFit: judge how well each scored-pending job fits the candidate.

One temperature-0 LLM call per job with an explicit rubric and the structured
``ResumeFacts`` (structured input measurably improves scoring — Qiu et al.). JSON
is parsed defensively: retry once on unparseable output, then record score 0 with
reasoning "unparseable" (won't clear the threshold). Scores are clamped to 1-10.
Never raises out of the pipeline (spec §7a).
"""

from __future__ import annotations

from kravu.adapters import prompts
from kravu.adapters.llm import parse_json
from kravu.domain.models import Profile
from kravu.domain.ports import JobStore, LLMClient
from kravu.exceptions import LLMResponseError


class ScoreJobFit:
    """Score pending jobs against the candidate's resume facts."""

    def __init__(self, llm: LLMClient, profile: Profile, min_score: int) -> None:
        """Store the model port, the candidate profile, and the threshold."""
        self._llm = llm
        self._profile = profile
        self._min_score = min_score

    def run(self, store: JobStore, limit: int | None = None) -> None:
        """Score every pending job (up to ``limit``). Never raises per job."""
        for job in store.pending_scoring(limit):
            self._score_one(store, job.url, job.full_description or "")

    def _score_one(self, store: JobStore, url: str, description: str) -> None:
        prompt = prompts.score_prompt(
            self._profile.resume_facts, description, self._profile.target_titles
        )
        for attempt in range(2):
            reply = self._llm.complete(prompt, temperature=0.0)
            try:
                data = parse_json(reply)
            except LLMResponseError:
                if attempt == 0:
                    continue
                store.set_score(url, 0, "unparseable")
                return
            score = self._clamp(data.get("score"))
            store.set_score(url, score, self._format_reasoning(data))
            return

    @staticmethod
    def _clamp(raw: object) -> int:
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            return 0
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return 0
        return max(1, min(10, value))

    @staticmethod
    def _format_reasoning(data: dict[str, object]) -> str:
        matched = ", ".join(str(k) for k in _as_list(data.get("matched_keywords")))
        missing = ", ".join(str(k) for k in _as_list(data.get("missing_skills")))
        reasoning = str(data.get("reasoning", ""))
        return f"Matched: {matched}\nMissing: {missing}\nReasoning: {reasoning}"


def _as_list(value: object) -> list[object]:
    """Coerce a JSON field into a list of items (empty when absent/not a list)."""
    return list(value) if isinstance(value, (list, tuple)) else []
