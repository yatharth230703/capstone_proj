"""Offline tests for the Case Reporter Agent's evidence builder and citation
collection — no LLM call. The live agent call (including the banned-
vocabulary/numeric-grounding/citation checks running against a real
narrative) is exercised by hand via scripts/48_smoke_judgement_agents.py.
"""

from __future__ import annotations

from specter.agents.case_reporter import _collect_source_ids, build_evidence


def test_build_evidence_includes_signal_count_for_numeric_grounding() -> None:
    graph_findings = {
        "signals": [
            {"signal_type": "address_degree", "value": 8.0, "source_ids": ["graph:address:x"]},
            {"signal_type": "phone_degree", "value": 5.0, "source_ids": ["graph:phone:y"]},
        ],
        "narration": "n",
        "community_context": "c",
    }
    enforcement_findings = {"matches": [], "legal_status_per_match": []}
    bundle = build_evidence("9050000000", graph_findings, enforcement_findings, {})
    assert bundle.evidence["signal_count"] == 2
    assert bundle.evidence["fired_signals"] == graph_findings["signals"]


def test_collect_source_ids_dedupes_signals_and_enforcement_matches() -> None:
    graph_findings = {
        "signals": [
            {"signal_type": "address_degree", "source_ids": ["graph:address:x", "art1"]},
            {"signal_type": "phone_degree", "source_ids": ["graph:address:x"]},
        ]
    }
    enforcement_findings = {"matches": ["CASE-1", "CASE-2"]}
    ids = _collect_source_ids(graph_findings, enforcement_findings)
    assert ids == [
        "art1",
        "graph:address:x",
        "graph:enforcement_case:CASE-1",
        "graph:enforcement_case:CASE-2",
    ]


def test_collect_source_ids_empty_when_no_findings() -> None:
    assert _collect_source_ids({}, {}) == []
