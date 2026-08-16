"""Offline tests for `core/banned_vocabulary.py` — CLAUDE.md hard rule 9,
enforced by regex, not just prompt instruction.
"""

from __future__ import annotations

import pytest

from specter.core.banned_vocabulary import BANNED_PHRASES, find_banned_phrases


@pytest.mark.parametrize("phrase", BANNED_PHRASES)
def test_each_banned_phrase_is_caught_case_insensitively(phrase: str) -> None:
    text = f"This case looks {phrase.upper()} based on the evidence."
    assert phrase in find_banned_phrases(text)


def test_clean_narrative_returns_empty() -> None:
    text = "The provider exhibits 3 independently observed indicators."
    assert find_banned_phrases(text) == []


def test_guiltily_does_not_false_match_guilty() -> None:
    # "guilty" isn't even a literal substring of "guiltily" ("guilt" + "ily",
    # not "guilty" + "ily") — asserted explicitly so a future stemming/fuzzy
    # match doesn't silently start flagging derived words.
    assert find_banned_phrases("the officer behaved guiltily around reporters.") == []


def test_word_boundary_still_matches_a_possessive_neighbor() -> None:
    # Apostrophe is not a word character, so \b still matches right up
    # against it — confirms the boundary check isn't over-aggressive.
    assert find_banned_phrases("that is the jury's guilty verdict.") == ["guilty"]


def test_multiple_banned_phrases_all_reported() -> None:
    found = find_banned_phrases("this looks fraudulent and the pattern seems criminal.")
    assert found == ["criminal", "fraudulent"]
