"""Offline tests for the Skeptic Agent's evidence builder — no LLM call. The
live agent call is exercised by hand via scripts/48_smoke_judgement_agents.py.
"""

from __future__ import annotations

from specter.agents.skeptic import build_evidence


def test_build_evidence_carries_signals_and_enforcement_context() -> None:
    graph_findings = {
        "signals": [{"signal_type": "address_degree", "value": 8.0}],
        "narration": "shares an address with several other providers.",
        "community_context": "no community on record.",
    }
    enforcement_findings = {
        "matches": ["CASE-1"],
        "typologies": ["durable medical equipment billing fraud"],
    }
    bundle = build_evidence("9030000000", graph_findings, enforcement_findings)
    assert bundle.provider_npi == "9030000000"
    assert bundle.evidence["fired_signals"] == graph_findings["signals"]
    assert bundle.evidence["enforcement_matches"] == ["CASE-1"]


def test_build_evidence_handles_no_findings() -> None:
    bundle = build_evidence("9030000000", {}, {})
    assert bundle.evidence["fired_signals"] == []
    assert bundle.evidence["enforcement_matches"] == []
