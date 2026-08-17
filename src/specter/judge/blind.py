"""Blind the judge (CLAUDE.md Amendment 2 mitigation 2, M9): strip anything
that could leak which agent/model/tier produced a `CasePacket` before it
reaches `rubric_judge.py`. A real `CasePacket` already carries no such field
(verified against `data/cases/*.json`) — `blind_case` exists to guard against
a *future* field leaking provenance, so it asserts rather than trusting the
current shape.
"""

from __future__ import annotations

from specter.core.contracts import BlindedCase, CasePacket
from specter.core.errors import SpecterError

_BANNED_SUBSTRINGS = ("gpt", "agent", "tier", "model")


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
        if substring in string.lower()
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
