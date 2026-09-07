"""Unit tests for prompt builders — assert structure, order, and guards."""

from __future__ import annotations

from kravu.adapters import prompts
from kravu.domain.models import Profile, ResumeFacts


def _profile() -> Profile:
    return Profile(
        name="Jane Dev",
        skills=["Python", "AWS"],
        resume_facts=ResumeFacts(
            raw_text="Built X at Acme.",
            companies=["Acme"],
            school="State University",
            metrics=["cut latency 40%"],
            skills=["Python", "AWS"],
        ),
    )


def test_score_prompt_lists_score_key_last() -> None:
    text = prompts.score_prompt(_profile().resume_facts, "JD text", ["Backend"])
    assert text.index('"reasoning"') < text.index('"score"')
    assert "1" in text and "10" in text


def test_tailor_prompt_forbids_fabrication_and_new_skills() -> None:
    text = prompts.tailor_prompt(_profile().resume_facts, "JD text", "Backend Engineer")
    assert "Python" in text and "AWS" in text
    assert "never" in text.lower() or "do not" in text.lower()


def test_judge_prompt_includes_exemplar_fabrication() -> None:
    text = prompts.tailor_judge_prompt("original resume", "tailored resume")
    assert "example" in text.lower() or "exemplar" in text.lower()
    assert text.index('"reasoning"') < text.index('"verdict"')


def test_cover_prompt_requires_salutation_and_word_limit() -> None:
    text = prompts.cover_prompt(_profile(), "JD text", "tailored resume")
    assert "Dear Hiring Manager" in text
    assert "250" in text


def test_extract_prompt_uses_flattened_text_label() -> None:
    text = prompts.extract_description_prompt("flattened page text")
    assert "flattened page text" in text


def test_banned_words_are_present() -> None:
    assert isinstance(prompts.BANNED_WORDS, tuple)
    assert len(prompts.BANNED_WORDS) > 0
