"""LiteLLMClient: the provider-agnostic model adapter, plus defensive JSON parse.

LiteLLM gives one interface to any provider; the model string comes from
``config.model()`` (never hardcoded). JSON is *instructed, not guaranteed*:
``response_format`` support is provider-dependent and some providers silently
return prose. Callers therefore parse with ``parse_json`` and retry once before
falling to their documented failure path (spec §7a, §9).
"""

from __future__ import annotations

import json
import re
from typing import Any

from kravu import config
from kravu.exceptions import LLMResponseError

_FENCE_RE = re.compile(r"```(?:json)?\s*(?P<body>.*?)\s*```", re.DOTALL)


def parse_json(text: str) -> dict[str, Any]:
    """Extract the first JSON object from possibly-noisy LLM text.

    Tries, in order: the whole string, any fenced code block, then the first
    balanced ``{...}`` span. Raises ``LLMResponseError`` if none parse.

    Args:
        text: Raw model output.

    Returns:
        The parsed JSON object as a dict.

    Raises:
        LLMResponseError: No parseable JSON object was found.
    """
    for candidate in _json_candidates(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise LLMResponseError("No parseable JSON object in model output.")


def _json_candidates(text: str) -> list[str]:
    candidates = [text.strip()]
    for match in _FENCE_RE.finditer(text):
        candidates.append(match.group("body").strip())
    span = _first_balanced_object(text)
    if span is not None:
        candidates.append(span)
    return candidates


def _first_balanced_object(text: str) -> str | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


class LiteLLMClient:
    """LLMClient backed by LiteLLM. One small, single-job call per invocation."""

    def __init__(self, model: str | None = None) -> None:
        """Build a client. ``model`` defaults to ``config.model()``."""
        self._model = model or config.model()

    def complete(self, prompt: str, *, temperature: float = 0.0) -> str:
        """Return the model's completion text for a single-message prompt.

        Args:
            prompt: The full instruction (already includes any JSON directive).
            temperature: Sampling temperature; 0.0 for deterministic calls.

        Returns:
            The model's raw text output.

        Raises:
            LLMResponseError: The provider returned no usable content.
        """
        import litellm

        response = litellm.completion(
            model=self._model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError("Empty or malformed LLM response.") from exc
        if not content:
            raise LLMResponseError("LLM returned no content.")
        return str(content)
