"""Prompt builders for kravu's LLM calls (pure functions, no I/O).

Every reasoning-bearing prompt asks for JSON with the reasoning/analysis fields
BEFORE the score/verdict field — constraining a model to answer before reasoning
degrades reasoning quality (Tam et al., arXiv 2408.02442). JSON here is for
reliable parsing, not grounding; grounding for tailoring comes from the validator
and judge (spec §7a).
"""

from __future__ import annotations

from kravu.domain.models import Profile, ResumeFacts

# Generic AI-slop phrasing the tailor/cover validators reject. A writing-quality
# measure (recruiters skip generic AI phrasing), NOT a claim to defeat AI-text
# detectors, which are unreliable in practice (spec §7a).
BANNED_WORDS: tuple[str, ...] = (
    "leverage",
    "synergy",
    "spearheaded",
    "results-driven",
    "detail-oriented",
    "go-getter",
    "team player",
    "think outside the box",
    "passionate about",
    "dynamic professional",
    "proven track record",
    "seamlessly",
    "cutting-edge",
    "best-in-class",
)

_RUBRIC = (
    "Score on this rubric: 9-10 strong fit, 7-8 good fit, 5-6 moderate, "
    "3-4 weak, 1-2 poor."
)


def score_prompt(
    facts: ResumeFacts, job_description: str, target_titles: list[str]
) -> str:
    """Build the ScoreJobFit prompt (temperature 0, rubric, reasoning-first JSON)."""
    targets = ", ".join(target_titles) if target_titles else "(none stated)"
    return (
        "You are an impartial career-fit evaluator judging how well a candidate "
        "fits ONE job, FOR THE CANDIDATE'S benefit.\n\n"
        f"{_RUBRIC}\n\n"
        f"Candidate target roles: {targets}\n\n"
        "CANDIDATE RESUME FACTS:\n"
        f"Skills: {', '.join(facts.skills)}\n"
        f"Companies: {', '.join(facts.companies)}\n"
        f"Education: {facts.school}\n"
        f"Metrics: {'; '.join(facts.metrics)}\n"
        f"Full resume text:\n{facts.raw_text}\n\n"
        "JOB DESCRIPTION:\n"
        f"{job_description[:6000]}\n\n"
        "Return ONLY a JSON object with EXACTLY these keys in THIS ORDER "
        "(reason before you commit to a number):\n"
        '{"reasoning": "<2-3 sentences>", "matched_keywords": ["..."], '
        '"missing_skills": ["..."], "score": <integer 1-10>}'
    )


def tailor_prompt(facts: ResumeFacts, job_description: str, target_role: str) -> str:
    """Build the TailorResume prompt: structured sections, zero fabrication."""
    return (
        "Rewrite the candidate's resume to target the role below. You may "
        "reorder, reframe, reword, drop, and re-emphasize freely.\n\n"
        "ABSOLUTE RULES — you must NEVER do any of these:\n"
        "- Invent or add any skill not in the ALLOWED SKILLS list.\n"
        "- Invent or change any company, job title, school, degree, date, or "
        "metric.\n"
        "- Claim adjacent or 'learnable' skills the candidate does not have.\n\n"
        f"ALLOWED SKILLS (the ONLY skills you may mention): {', '.join(facts.skills)}\n"
        f"COMPANIES (must all survive, unchanged): {', '.join(facts.companies)}\n"
        f"EDUCATION (must survive, unchanged): {facts.school}\n"
        f"METRICS (must survive, unchanged): {'; '.join(facts.metrics)}\n"
        f"ORIGINAL RESUME:\n{facts.raw_text}\n\n"
        f"TARGET ROLE: {target_role}\n"
        f"JOB DESCRIPTION:\n{job_description[:6000]}\n\n"
        "Return ONLY a JSON object with these keys (do NOT include a name or "
        "contact header — that is added by code):\n"
        '{"title": "<headline>", "summary": "<2-3 sentences>", '
        '"skills": {"<group>": ["..."]}, '
        '"experience": [{"company": "...", "role": "...", "dates": "...", '
        '"bullets": ["..."]}], '
        '"projects": [{"name": "...", "bullets": ["..."]}], '
        '"education": "<text>"}'
    )


def tailor_judge_prompt(original_resume: str, tailored_resume: str) -> str:
    """Build the always-on fabrication judge prompt (reasoning-first verdict).

    Reference-free LLM-as-judge for faithfulness (FaithJudge, arXiv 2505.04847);
    the few-shot exemplar fabrications sharpen it.
    """
    return (
        "You are a strict faithfulness judge. Compare a TAILORED resume against "
        "the ORIGINAL. Legitimate reordering/rewording/re-emphasis is FINE. Your "
        "job is to catch FABRICATION: any skill, employer, title, date, degree, "
        "or metric in the tailored version that is not supported by the "
        "original.\n\n"
        "Example fabrications (all FAIL):\n"
        '- Original: "Python, SQL"; Tailored claims "Kubernetes" -> fabricated skill.\n'
        '- Original: "Acme 2021-2023"; Tailored says "Acme 2019-2023" -> '
        "altered dates.\n"
        '- Original: "reduced cost"; Tailored says "reduced cost 60%" -> '
        "invented metric.\n\n"
        f"ORIGINAL RESUME:\n{original_resume}\n\n"
        f"TAILORED RESUME:\n{tailored_resume}\n\n"
        "Return ONLY a JSON object with keys in THIS ORDER:\n"
        '{"reasoning": "<what you checked>", "fabrications": ["..."], '
        '"verdict": "pass" | "fail"}'
    )


def cover_prompt(profile: Profile, job_description: str, tailored_resume: str) -> str:
    """Build the DraftCoverLetter prompt: 3 short paras, <250 words, eng voice."""
    facts = profile.resume_facts
    return (
        "Write a cover letter for the candidate targeting the job below.\n\n"
        "RULES:\n"
        "- Exactly 3 short paragraphs, UNDER 250 words total.\n"
        '- Start with the exact line "Dear Hiring Manager,".\n'
        "- Engineering voice: open with something the candidate BUILT that solves "
        "the employer's problem; every sentence carries a number, tool, or "
        "outcome.\n"
        f"- Mention ONLY skills in this list: {', '.join(facts.skills)}. If the job "
        "asks for tools the candidate lacks, write about the WORK, not the tools.\n"
        "- Never invent employers, titles, dates, degrees, or metrics.\n\n"
        f"CANDIDATE:\n{profile.compact_summary()}\n"
        f"TAILORED RESUME:\n{tailored_resume}\n\n"
        f"JOB DESCRIPTION:\n{job_description[:6000]}\n\n"
        "Return ONLY the letter text (no preamble, no 'Here is the letter')."
    )


def extract_description_prompt(flattened_text: str) -> str:
    """Build the ExpandJob tier-3 extraction prompt (fed FLATTENED text, not HTML).

    Flattened input yields higher extraction accuracy and less hallucination
    (NEXT-EVAL, arXiv 2505.17125).
    """
    return (
        "Below is the flattened, cleaned text of a job posting page. Extract the "
        "full job description (responsibilities, requirements, qualifications). "
        "Return ONLY the description text, nothing else.\n\n"
        "flattened page text:\n"
        f"{flattened_text[:12000]}"
    )


def build_profile_prompt(raw_resume_text: str) -> str:
    """Build the BuildProfile extraction prompt (raw CV text -> structured facts)."""
    return (
        "Extract structured facts from the resume below. Do NOT invent anything; "
        "copy only what is present.\n\n"
        f"RESUME:\n{raw_resume_text}\n\n"
        "Return ONLY a JSON object:\n"
        '{"name": "...", "email": "...", "headline": "...", "location": "...", '
        '"summary": "...", "skills": ["..."], "companies": ["..."], '
        '"school": "...", "metrics": ["..."]}'
    )


def suggest_searches_prompt(profile: Profile) -> str:
    """Build the SuggestSearches prompt (Profile -> proposed search targets)."""
    return (
        "Propose conservative job-search targets for this candidate. Infer target "
        "roles and seniority from their resume; propose a CONSERVATIVE location "
        "(their resume location or 'Remote').\n\n"
        f"CANDIDATE:\n{profile.compact_summary()}\n\n"
        "Return ONLY a JSON object:\n"
        '{"search_term": "<primary role query>", "location": "<location>", '
        '"is_remote": <true|false>}'
    )
