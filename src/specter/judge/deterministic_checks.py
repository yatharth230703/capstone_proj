"""The three primary rubric criteria (CLAUDE.md Amendment 2 mitigation 1, M9)
— fully checkable in code, treated as authoritative. `JudgeReport.md` leads
with these; the LLM rubric judge's scores are reported underneath, explicitly
labelled secondary.

Each function reuses an existing pure-function/tool rather than
reimplementing the check: `check_citation_validity` reuses
`evidence_tools.validate_citations`, `check_numeric_grounding` reuses
`agents._grounding.numeric_violations`, `check_entity_existence` reuses
`evidence_tools._resolves_to_graph_node`'s label/key pattern directly.
"""

from __future__ import annotations

import re
from pathlib import Path

from neo4j import Driver

from specter.agents._grounding import numeric_violations
from specter.core.contracts import CasePacket
from specter.tools import evidence_tools

_NPI_RE = re.compile(r"\b\d{10}\b")
# `case_id`/`officer_id` are `sha256_text(...)[:24]` — 24 lowercase hex chars
# (graph/enforcement_loader.py, graph/loader.py; confirmed live pre-M8).
_HEX24_RE = re.compile(r"\b[0-9a-f]{24}\b")


def check_citation_validity(
    case: CasePacket, driver: Driver, evidence_dir: Path
) -> dict[str, bool]:
    """One boolean per claim: every `RiskSignal.source_ids` set, plus every
    enforcement-match citation (`graph:enforcement_case:<case_id>`), must
    resolve to a stored `EvidenceArtifact` or an existing graph node.
    """
    results: dict[str, bool] = {}
    for signal in case.signals:
        report = evidence_tools.validate_citations(signal.source_ids, driver, evidence_dir)
        results[f"signal:{signal.signal_type}"] = report.all_resolved
    for match in case.legal_status_per_match:
        source_id = f"graph:enforcement_case:{match.case_id}"
        report = evidence_tools.validate_citations([source_id], driver, evidence_dir)
        results[f"enforcement_match:{match.case_id}"] = report.all_resolved
    return results


def check_numeric_grounding(case: CasePacket) -> list[str]:
    """Every numeric literal in `narrative` must appear somewhere in the
    packet's own structured data. Empty list = fully grounded.
    """
    evidence = case.model_dump(mode="json", exclude={"narrative"})
    return numeric_violations([case.narrative], evidence)


def check_entity_existence(case: CasePacket, driver: Driver) -> dict[str, bool]:
    """Regex-extract every NPI-shaped and case/officer-id-shaped identifier
    out of `narrative` and check each against the graph, reusing
    `evidence_tools._resolves_to_graph_node`'s label/key mapping directly
    rather than reinventing the query shape. One boolean per extracted
    identifier — CLAUDE.md hard rule 2, no fabricated identifiers.
    """
    results: dict[str, bool] = {}
    for npi in sorted(set(_NPI_RE.findall(case.narrative))):
        results[f"npi:{npi}"] = evidence_tools._resolves_to_graph_node(
            driver, f"graph:provider:{npi}"
        )
    for hex_id in sorted(set(_HEX24_RE.findall(case.narrative))):
        matched = evidence_tools._resolves_to_graph_node(
            driver, f"graph:enforcement_case:{hex_id}"
        ) or evidence_tools._resolves_to_graph_node(driver, f"graph:officer:{hex_id}")
        results[f"id:{hex_id}"] = matched
    return results
