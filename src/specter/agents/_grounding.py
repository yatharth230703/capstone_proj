"""Numeric-grounding check (CLAUDE.md hard rule 1): a number in agent output
that isn't in a tool result is a bug that fails the case. Generalized out of
`graph_investigation.py` (M3) so `case_reporter.py` (M5) doesn't copy-paste a
third implementation — BUILD_MILESTONES.md debt D-14.

`judge/deterministic_checks.py` (M9) will do the authoritative, retrospective
version of this same idea; this module is the pre-emptive, per-call version
agents run on their own output before returning it.
"""

from __future__ import annotations

import json
import re

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def numbers_in(text: str) -> set[str]:
    return set(_NUMBER_RE.findall(text))


def numeric_violations(claimed_texts: list[str], evidence: dict[str, object]) -> list[str]:
    """Every number in `claimed_texts` that doesn't appear anywhere in
    `evidence`'s rendered JSON. Empty means fully grounded.
    """
    grounded = numbers_in(json.dumps(evidence, sort_keys=True, default=str))
    claimed: set[str] = set()
    for text in claimed_texts:
        claimed |= numbers_in(text)
    return sorted(claimed - grounded)
