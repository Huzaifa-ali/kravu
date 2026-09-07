"""SuggestSearches: propose a searches.yaml from a Profile; validate the schema.

``run`` uses one LLM call to infer a conservative search target, wraps it in the
full searches structure with safe defaults (spec §13a), and validates it before
returning. ``validate_searches`` is the single schema gate reused by ``kravu``
at config-load time; it hard-errors on invalid config (hard-stop philosophy).
"""

from __future__ import annotations

from typing import Any

from kravu.adapters import prompts
from kravu.adapters.llm import parse_json
from kravu.domain.models import Profile
from kravu.domain.ports import LLMClient
from kravu.exceptions import SearchesConfigError

_ALLOWED_SITES = frozenset(
    {
        "indeed",
        "linkedin",
        "zip_recruiter",
        "google",
        "glassdoor",
        "bayt",
        "bdjobs",
        "naukri",
    }
)


def _default_searches() -> dict[str, Any]:
    return {
        "sources": {
            "jobspy": {
                "enabled": True,
                "sites": ["indeed", "linkedin", "zip_recruiter", "google"],
            },
            "ats": {"enabled": False, "companies": []},
        },
        "defaults": {
            "results_wanted": 25,
            "hours_old": 168,
            "description_format": "markdown",
            "per_run_cap": 25,
        },
        "cover_letter": "only_if_required",
        "min_score": 7,
        "searches": [],
    }


class SuggestSearches:
    """Propose a validated searches config from a user's ``Profile``."""

    def __init__(self, llm: LLMClient) -> None:
        """Store the injected model port."""
        self._llm = llm

    def run(self, profile: Profile) -> dict[str, Any]:
        """Return a validated ``searches.yaml`` dict proposed from ``profile``."""
        reply = self._llm.complete(
            prompts.suggest_searches_prompt(profile), temperature=0.0
        )
        data = parse_json(reply)
        result = _default_searches()
        result["searches"] = [
            {
                "name": "primary",
                "search_term": str(data.get("search_term") or "software engineer"),
                "location": str(data.get("location") or profile.location or "Remote"),
                "country_indeed": "USA",
                "is_remote": bool(data.get("is_remote", True)),
            }
        ]
        validate_searches(result)
        return result


def validate_searches(searches: dict[str, Any]) -> None:
    """Validate a searches config against the schema (spec §13a).

    Raises:
        SearchesConfigError: The config violates a hard rule.
    """
    sources = searches.get("sources", {})
    jobspy = sources.get("jobspy", {})
    ats = sources.get("ats", {})
    if not jobspy.get("enabled", False) and not ats.get("enabled", False):
        raise SearchesConfigError("At least one source must be enabled.")

    sites = jobspy.get("sites", []) if jobspy.get("enabled") else []
    for site in sites:
        if site not in _ALLOWED_SITES:
            raise SearchesConfigError(
                f"Unknown site '{site}'. Allowed: {sorted(_ALLOWED_SITES)}."
            )

    needs_country = bool({"indeed", "glassdoor"} & set(sites))
    for entry in searches.get("searches", []):
        _validate_entry(entry, needs_country)


def _validate_entry(entry: dict[str, Any], needs_country: bool) -> None:
    if needs_country and not entry.get("country_indeed"):
        raise SearchesConfigError(
            f"Search '{entry.get('name')}' needs 'country_indeed' "
            "when indeed/glassdoor is a site."
        )
    chosen = 0
    if entry.get("hours_old") is not None:
        chosen += 1
    if entry.get("job_type") is not None or entry.get("is_remote") is not None:
        chosen += 1
    if entry.get("easy_apply") is not None:
        chosen += 1
    if chosen > 1:
        raise SearchesConfigError(
            f"Search '{entry.get('name')}': Indeed allows only one of "
            "hours_old | (job_type+is_remote) | easy_apply."
        )
