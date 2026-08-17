"""Blind the judge (CLAUDE.md Amendment 2 mitigation 2, M9): strip anything
that could leak which agent/model/tier produced a `CasePacket` before it
reaches `rubric_judge.py`. A real `CasePacket` already carries no such field
(verified against `data/cases/*.json`) — `blind_case` exists to guard against
a *future* field leaking provenance, so it asserts rather than trusting the
current shape.

**`_BENIGN_COMPOUND_RE` (M9, live finding).** A bare substring check on
"agent"/"model"/"tier" false-positives on ordinary English healthcare/
business usage that has nothing to do with AI provenance — confirmed live
on the very first real judge run twice in a row: "registered-agent style
address" (a real shell-company fraud typology — this system specifically
investigates shell-provider patterns, so this vocabulary will recur, not a
one-off) and "billing agents" (a routine mention of third-party billing
services in a benign explanation). A guard that hard-fails on ordinary
domain vocabulary would make the judge unusable for exactly the cases it
exists to grade. Known-benign `<qualifier> agent(s)/model(s)/tier(s)`
compounds are stripped before the substring scan runs, so a genuine
standalone "agent"/"model"/"tier" mention (e.g. "the agent observed",
"the model produced", "escalated to a higher tier") still raises — those
have no natural qualifier in front of them. Extend the qualifier lists below
if a future run surfaces another legitimate collision; do not weaken the
check for a bare, unqualified occurrence of a banned word.
"""

from __future__ import annotations

import re

from specter.core.contracts import BlindedCase, CasePacket
from specter.core.errors import SpecterError

_BANNED_SUBSTRINGS = ("gpt", "agent", "tier", "model")
_AGENT_QUALIFIERS = ("registered", "billing", "insurance", "claims", "collection")
_MODEL_QUALIFIERS = ("business", "care", "practice", "reimbursement", "staffing", "ownership")
_TIER_QUALIFIERS = ("provider", "network", "pricing", "service", "reimbursement")
_BENIGN_RE = re.compile(
    r"\b(?:"
    + "|".join(re.escape(q) for q in _AGENT_QUALIFIERS)
    + r")[- ]agents?\b"
    + r"|\b(?:"
    + "|".join(re.escape(q) for q in _MODEL_QUALIFIERS)
    + r")[- ]models?\b"
    + r"|\b(?:"
    + "|".join(re.escape(q) for q in _TIER_QUALIFIERS)
    + r")[- ]tiers?\b",
    re.IGNORECASE,
)


class ProvenanceLeakError(SpecterError):
    """A string value inside the case dump case-insensitively contains
    "gpt"/"agent"/"tier"/"model" — the judge would no longer be blind.
    """


def _walk_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for k, v in value.items():
            strings.append(k)
            strings.extend(_walk_strings(v))
        return strings
    if isinstance(value, list):
        strings = []
        for item in value:
            strings.extend(_walk_strings(item))
        return strings
    return []


def blind_case(case: CasePacket) -> BlindedCase:
    dump = case.model_dump(mode="json")
    leaked = [
        (string, substring)
        for string in _walk_strings(dump)
        for substring in _BANNED_SUBSTRINGS
        if substring in _BENIGN_RE.sub("", string).lower()
    ]
    if leaked:
        raise ProvenanceLeakError(
            f"CasePacket for {case.provider_npi} leaks provenance: {leaked}"
        )
    return BlindedCase(
        provider_npi=case.provider_npi,
        narrative=case.narrative,
        signals=case.signals,
        enforcement_matches=case.enforcement_matches,
        legal_status_per_match=case.legal_status_per_match,
        counter_evidence=case.counter_evidence,
        citation_report=case.citation_report,
        created_at=case.created_at,
    )
