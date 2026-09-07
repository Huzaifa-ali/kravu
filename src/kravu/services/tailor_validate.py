"""Deterministic fabrication validator for tailored resumes (pure, cheap pass).

Checks the cheap, high-precision invariants before the LLM judge: preserved
companies and school must survive verbatim; every real metric must still appear;
no skill outside ``ResumeFacts.skills`` may be claimed (checked against a
watchlist of common languages/frameworks/certs); and no banned AI-slop phrasing.
Returns a list of human-readable issues; empty means the deterministic pass is
clean (spec §7a). Zero fabrication — no adjacent/learnable-skill tolerance.
"""

from __future__ import annotations

from kravu.adapters.prompts import BANNED_WORDS
from kravu.domain.models import ResumeFacts

# Common skills to catch if fabricated (claimed but not in ResumeFacts.skills).
_SKILL_WATCHLIST = (
    "python",
    "java",
    "javascript",
    "typescript",
    "go",
    "golang",
    "rust",
    "c++",
    "c#",
    "ruby",
    "php",
    "scala",
    "kotlin",
    "swift",
    "aws",
    "azure",
    "gcp",
    "kubernetes",
    "docker",
    "terraform",
    "react",
    "angular",
    "vue",
    "django",
    "flask",
    "spring",
    "node",
    "postgres",
    "mysql",
    "mongodb",
    "redis",
    "kafka",
    "spark",
    "hadoop",
    "tensorflow",
    "pytorch",
    "pmp",
    "cissp",
    "cka",
)


def validate_no_fabrication(resume: str, facts: ResumeFacts) -> list[str]:
    """Return a list of fabrication issues; empty list means the pass is clean.

    Args:
        resume: The assembled tailored resume text.
        facts: The candidate's ground-truth resume facts.

    Returns:
        Human-readable issue strings for any violation found.
    """
    issues: list[str] = []
    lowered = resume.lower()
    allowed = {s.lower() for s in facts.skills}

    for company in facts.companies:
        if company and company.lower() not in lowered:
            issues.append(f"Dropped required company: {company}")

    if facts.school and facts.school.lower() not in lowered:
        issues.append(f"Dropped required school: {facts.school}")

    for metric in facts.metrics:
        if metric and metric.lower() not in lowered:
            issues.append(f"Missing/altered required metric: {metric}")

    for skill in _SKILL_WATCHLIST:
        index = lowered.find(skill)
        if index != -1 and skill not in allowed:
            # Report the skill as it appears in the resume (preserves casing).
            claimed = resume[index : index + len(skill)]
            issues.append(f"Fabricated skill not in resume facts: {claimed}")

    for phrase in BANNED_WORDS:
        if phrase.lower() in lowered:
            issues.append(f"Banned AI-slop phrase: {phrase}")

    return issues
