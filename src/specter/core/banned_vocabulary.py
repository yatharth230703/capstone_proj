"""CLAUDE.md hard rule 9: banned output vocabulary, enforced by a regex
post-check — not only a prompt instruction. `case_reporter.py` (M5) raises
if `find_banned_phrases` returns anything non-empty.
"""

from __future__ import annotations

import re

BANNED_PHRASES: tuple[str, ...] = (
    "fraudulent",
    "criminal",
    "guilty",
    "proven",
    "confirmed fraud",
)

_BANNED_RE = re.compile(
    r"\b(" + "|".join(re.escape(phrase) for phrase in BANNED_PHRASES) + r")\b",
    re.IGNORECASE,
)


def find_banned_phrases(text: str) -> list[str]:
    """Case-insensitive, word-boundary matched — "guiltily" does not match
    "guilty" (no word boundary between its "y" and "i"), which is the
    intended behavior: a substring hit inside an unrelated word is not the
    same claim as the banned word itself.
    """
    return sorted({match.group(0).lower() for match in _BANNED_RE.finditer(text)})
