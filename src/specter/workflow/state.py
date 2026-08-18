"""Deterministic orchestration primitives (plan §10, M6): cohort selection,
entity-resolution candidate pairing, and case scoring. No LLM call anywhere
in this module — CLAUDE.md hard rule 8: scoring is deterministic code, never
an agent.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from neo4j import Driver

from specter.core.contracts import CaseScore
from specter.core.enums import LegalStatus, MatchDecision, PriorityTier
from specter.tools.graph_tools import find_shared_attribute_peers

logger = structlog.get_logger(__name__)

_CONFLICTING_DECISIONS = {MatchDecision.HUMAN_REVIEW, MatchDecision.REJECT}
_STRONG_LEGAL_STATUSES = {
    LegalStatus.CHARGED,
    LegalStatus.CONVICTED,
    LegalStatus.SETTLED,
    LegalStatus.EXCLUDED,
}


def cohort_select(
    driver: Driver, taxonomy_prefix: str, states: list[str], limit: int | None = None
) -> list[str]:
    """`config/screening.yaml`'s `cohort` block, as Cypher. Sorted by npi so
    the cohort — and any `limit` slice of it — is reproducible run to run.

    `p.data_origin = 'public'` is explicit, not incidental (BUILD_MILESTONES.md
    debt D-17). Synthetic scenario providers (S01-S10) carry no `HAS_TAXONOMY`
    edge today, so this filter is currently redundant with that gap — but a
    live production screening cohort must never depend on an accident of the
    synthetic loader to keep synthetic providers out. Anything that needs a
    synthetic scenario queries by `scenario_id` directly (M3/M5/M9's own smoke
    scripts and `scripts/50_judge.py` already do this), never through this
    taxonomy-based cohort path.
    """
    query = """
        MATCH (p:Provider)-[:HAS_TAXONOMY]->(t:Taxonomy)
        WHERE t.code STARTS WITH $prefix AND p.state IN $states
          AND p.data_origin = 'public'
        RETURN DISTINCT p.npi AS npi
        ORDER BY npi
    """
    if limit is not None:
        query += " LIMIT $limit"
    with driver.session() as session:
        records = session.run(query, prefix=taxonomy_prefix, states=states, limit=limit).data()
    return [r["npi"] for r in records]


def build_candidate_pairs(driver: Driver, npis: list[str]) -> list[tuple[str, str]]:
    """Per cohort NPI, union its address/phone/officer peers into candidate
    pairs for the entity-resolution fan-out (BUILD_MILESTONES.md M6 Step 4).
    `npi` (first element) is always the cohort member driving the query;
    `candidate_npi` may or may not itself be in the cohort. Self-matches are
    already excluded by `find_shared_attribute_peers`'s own Cypher.

    Logged, not capped (BUILD_MILESTONES.md M6 Traps: a cohort where many
    providers share one address is a real finding worth a config cap, not
    something to guess a limit for in advance).
    """
    pairs: list[tuple[str, str]] = []
    for npi in npis:
        seen: set[str] = set()
        for attribute in ("address", "phone", "officer"):
            for peer in find_shared_attribute_peers(driver, npi, attribute):
                if peer.peer_npi not in seen:
                    seen.add(peer.peer_npi)
                    pairs.append((npi, peer.peer_npi))
    logger.info("workflow.candidate_pairs", cohort_size=len(npis), pair_count=len(pairs))
    return pairs


class ScoringService:
    """Plan §10's five-dimension deterministic scorer plus the escalation
    gate. `confidence_adjustment` (the Skeptic's bounded `[-0.4, 0.0]`
    discount, CLAUDE.md hard rule 8) is folded into `evidence_quality` only —
    no other dimension reads anything the Skeptic produced.

    `signals`/`entity_adjudications` are `AgentRunResult.output`-shaped
    dicts (already JSON-mode-dumped), same convention `skeptic.py`/
    `case_reporter.py` use — not parsed Pydantic objects.
    """

    def __init__(
        self,
        signal_families: dict[str, list[str]],
        min_independent_signal_families: int,
        evidence_freshness_days: int,
    ) -> None:
        self._families = signal_families
        self._min_families = min_independent_signal_families
        self._freshness_days = evidence_freshness_days

    def _fired_families(self, signal_types: set[str]) -> list[str]:
        return sorted(
            family for family, members in self._families.items() if signal_types & set(members)
        )

    def _family_fraction(self, family: str, signal_types: set[str]) -> float:
        members = self._families.get(family, [])
        if not members:
            return 0.0
        return len(signal_types & set(members)) / len(members)

    def _freshness_ok(self, signals: list[dict[str, Any]]) -> bool:
        if not signals:
            return True
        now = datetime.now(UTC)
        for signal in signals:
            detected_at = signal["detected_at"]
            if isinstance(detected_at, str):
                detected_at = datetime.fromisoformat(detected_at)
            if (now - detected_at).days > self._freshness_days:
                return False
        return True

    def score(
        self,
        npi: str,
        signals: list[dict[str, Any]],
        enforcement_findings: dict[str, Any],
        entity_adjudications: list[dict[str, Any]],
        confidence_adjustment: float,
    ) -> CaseScore:
        signal_types = {s["signal_type"] for s in signals}
        fired_families = self._fired_families(signal_types)
        family_count = len(fired_families)

        conflict_count = sum(
            1 for a in entity_adjudications if a["decision"] in _CONFLICTING_DECISIONS
        )
        identity_integrity = max(0.0, 1.0 - 0.5 * conflict_count)

        network_association = self._family_fraction("network_anomaly", signal_types)
        corporate_complexity = self._family_fraction("address_anomaly", signal_types)

        adverse_fraction = self._family_fraction("adverse_history", signal_types)
        legal_statuses = enforcement_findings.get("legal_status_per_match", [])
        has_strong_match = any(
            entry["legal_status"] in _STRONG_LEGAL_STATUSES for entry in legal_statuses
        )
        adverse_history = min(1.0, adverse_fraction + (0.3 if has_strong_match else 0.0))

        evidence_quality = min(1.0, max(0.0, 1.0 + confidence_adjustment))

        has_gov_source = bool(enforcement_findings.get("matches")) or any(
            s["signal_type"] in self._families.get("adverse_history", []) for s in signals
        )
        has_strong_quant_anomaly = any(
            s["value"] >= 2 * s["threshold"] for s in signals if s["threshold"] > 0
        )
        freshness_ok = self._freshness_ok(signals)

        reasons: list[str] = []
        if family_count < self._min_families:
            reasons.append(
                f"only {family_count}/{self._min_families} required independent "
                "signal families fired"
            )
        if not (has_gov_source or has_strong_quant_anomaly):
            reasons.append("no authoritative government source or strong quantitative anomaly")
        if conflict_count:
            reasons.append(f"{conflict_count} unresolved entity-match conflict(s)")
        if not freshness_ok:
            reasons.append(f"evidence older than {self._freshness_days} days")

        if not reasons:
            priority_tier = PriorityTier.HIGH_PRIORITY
            reasons = ["meets all four escalation-gate conditions (plan §10)"]
        elif family_count >= 1 or enforcement_findings.get("matches"):
            priority_tier = PriorityTier.STANDARD
        else:
            priority_tier = PriorityTier.LOW

        return CaseScore(
            provider_npi=npi,
            identity_integrity=identity_integrity,
            network_association=network_association,
            adverse_history=adverse_history,
            evidence_quality=evidence_quality,
            corporate_complexity=corporate_complexity,
            fired_signal_families=fired_families,
            independent_signal_family_count=family_count,
            priority_tier=priority_tier,
            escalation_gate_reasons=reasons,
        )
