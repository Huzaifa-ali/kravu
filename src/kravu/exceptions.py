"""Typed exception hierarchy for kravu.

Every error kravu raises deliberately is a ``KravuError`` subclass with an
actionable message (tell the user what to do). Per-job pipeline failures are
recorded on the job row instead of raised; these exceptions are for
configuration, setup, and hard-stop conditions.
"""

from __future__ import annotations


class KravuError(Exception):
    """Base class for all deliberate kravu errors."""


class ConfigError(KravuError):
    """Configuration or environment is invalid or incomplete."""


class SearchesConfigError(ConfigError):
    """``searches.yaml`` failed schema validation."""


class ProfileNotFoundError(KravuError):
    """No profile exists yet — the user must run ``kravu init``."""


class MissingKeyError(ConfigError):
    """A key-requiring provider is selected but its env var is absent."""


class LLMResponseError(KravuError):
    """The LLM returned output that could not be parsed/validated."""


class EnrichmentError(KravuError):
    """A job page could not be rendered or its description extracted."""


class FabricationError(KravuError):
    """Tailoring/cover output failed the anti-fabrication guard."""


class DiscoveryError(KravuError):
    """A discovery source failed in a way worth reporting to the user."""


class ApplyError(KravuError):
    """The Apply Agent failed to run or record a result."""
