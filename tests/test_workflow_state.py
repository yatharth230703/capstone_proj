"""Tests for `workflow/state.py` (M6, plan §10). `cohort_select`/
`build_candidate_pairs` are Neo4j-backed (same skip-if-unreachable pattern as
`test_graph_investigation.py`); `ScoringService` is pure Python — fed
synthetic `AgentRunResult.output`-shaped dicts, no Neo4j or LLM needed.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from neo4j import Driver, GraphDatabase

from specter.core.enums import PriorityTier
from specter.settings import get_settings
from specter.workflow.state import ScoringService, build_candidate_pairs, cohort_select

_FAMILIES = {
    "address_anomaly": ["address_degree", "enumeration_burst", "address_churn"],
    "network_anomaly": ["phone_degree", "officer_degree", "geographic_spread"],
    "adverse_history": ["exclusion_proximity", "community_exclusion_density", "phoenix_pattern"],
}


@pytest.fixture(scope="module")
def driver() -> Iterator[Driver]:
    settings = get_settings()
    drv = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value())
    )
    try:
        drv.verify_connectivity()
    except Exception:
        pytest.skip("Neo4j not reachable — start it with `docker compose up -d`")
    with drv.session() as session:
        record = session.run(
            "MATCH (p:Provider) WHERE p.scenario_id = 'S03' RETURN count(p) AS c"
        ).single()
    if record is None or record["c"] == 0:
        pytest.skip("Synthetic scenarios not loaded — run scripts/20_build_graph.py first")
    yield drv
    drv.close()


def test_cohort_select_filters_by_taxonomy_and_state_and_is_sorted(driver: Driver) -> None:
    npis = cohort_select(driver, "332", ["FL", "TX", "CA"])
    assert npis == sorted(npis)
    assert len(npis) > 0
    with driver.session() as session:
        record = session.run(
            "MATCH (p:Provider {npi: $npi})-[:HAS_TAXONOMY]->(t:Taxonomy) "
            "RETURN t.code AS code, p.state AS state",
            npi=npis[0],
        ).single()
    assert record is not None
    assert record["code"].startswith("332")
    assert record["state"] in {"FL", "TX", "CA"}


def test_cohort_select_limit_slices_the_sorted_list(driver: Driver) -> None:
    full = cohort_select(driver, "332", ["FL", "TX", "CA"])
    limited = cohort_select(driver, "332", ["FL", "TX", "CA"], limit=3)
    assert limited == full[:3]


def test_cohort_select_excludes_synthetic_providers_explicitly(driver: Driver) -> None:
    """D-17: a production screening cohort must never depend on the
    accidental absence of a `HAS_TAXONOMY` edge on synthetic providers to
    stay real-data-only — `cohort_select` filters `data_origin='public'`
    explicitly now. Every synthetic scenario provider carries a
    `taxonomy_code` starting with "332" in its raw data (`ingest/
    synthetic.py`), so this only proves something if the graph actually has
    synthetic providers with a real taxonomy prefix loaded.
    """
    npis = cohort_select(driver, "332", ["FL", "TX", "CA"])
    with driver.session() as session:
        synthetic_in_cohort = session.run(
            """
            UNWIND $npis AS npi
            MATCH (p:Provider {npi: npi})
            WHERE p.data_origin = 'synthetic'
            RETURN count(p) AS n
            """,
            npis=npis,
        ).single()["n"]
    assert synthetic_in_cohort == 0


def test_build_candidate_pairs_finds_s03_address_cluster_peers(driver: Driver) -> None:
    pairs = build_candidate_pairs(driver, ["9030000000"])
    assert pairs
    assert all(pair[0] == "9030000000" for pair in pairs)
    peer_npis = {peer for _, peer in pairs}
    assert "9030000000" not in peer_npis  # self-matches excluded


def test_build_candidate_pairs_dedupes_a_peer_seen_via_multiple_attributes(driver: Driver) -> None:
    pairs = build_candidate_pairs(driver, ["9030000000"])
    peer_npis = [peer for _, peer in pairs]
    assert len(peer_npis) == len(set(peer_npis))


def _signal(signal_type: str, value: float = 8.0, threshold: float = 5.0) -> dict:
    return {
        "signal_type": signal_type,
        "value": value,
        "threshold": threshold,
        "detected_at": datetime.now(UTC).isoformat(),
    }


def _service() -> ScoringService:
    return ScoringService(
        signal_families=_FAMILIES, min_independent_signal_families=3, evidence_freshness_days=180
    )


def test_no_signals_is_low_priority_with_perfect_dimensions() -> None:
    score = _service().score("1", [], {"matches": []}, [], confidence_adjustment=0.0)
    assert score.priority_tier == PriorityTier.LOW
    assert score.identity_integrity == 1.0
    assert score.evidence_quality == 1.0
    assert score.fired_signal_families == []
    assert score.escalation_gate_reasons


def test_three_families_plus_gov_source_and_no_conflict_is_high_priority() -> None:
    signals = [
        _signal("address_degree"),
        _signal("phone_degree"),
        _signal("exclusion_proximity"),
    ]
    legal_status_per_match = [{"case_id": "case-1", "legal_status": "charged"}]
    enforcement = {"matches": ["case-1"], "legal_status_per_match": legal_status_per_match}
    score = _service().score("1", signals, enforcement, [], confidence_adjustment=0.0)
    assert score.priority_tier == PriorityTier.HIGH_PRIORITY
    assert score.independent_signal_family_count == 3
    assert score.escalation_gate_reasons == ["meets all four escalation-gate conditions (plan §10)"]


def test_family_dedup_two_signals_same_family_count_as_one() -> None:
    signals = [_signal("address_degree"), _signal("enumeration_burst")]
    score = _service().score("1", signals, {"matches": []}, [], confidence_adjustment=0.0)
    assert score.fired_signal_families == ["address_anomaly"]
    assert score.independent_signal_family_count == 1


def test_entity_conflict_lowers_identity_integrity_and_blocks_high_priority() -> None:
    signals = [_signal("address_degree"), _signal("phone_degree"), _signal("exclusion_proximity")]
    adjudications = [{"decision": "human_review"}]
    score = _service().score(
        "1", signals, {"matches": []}, adjudications, confidence_adjustment=0.0
    )
    assert score.identity_integrity == 0.5
    assert score.priority_tier != PriorityTier.HIGH_PRIORITY
    assert any("conflict" in reason for reason in score.escalation_gate_reasons)


def test_confidence_adjustment_is_the_only_input_to_evidence_quality() -> None:
    score = _service().score("1", [], {"matches": []}, [], confidence_adjustment=-0.4)
    assert score.evidence_quality == pytest.approx(0.6)


def test_stale_evidence_fails_the_freshness_gate_condition() -> None:
    stale = datetime.now(UTC) - timedelta(days=400)
    stale_signal = {
        "signal_type": "address_degree",
        "value": 8.0,
        "threshold": 5.0,
        "detected_at": stale.isoformat(),
    }
    signals = [stale_signal, _signal("phone_degree"), _signal("exclusion_proximity")]
    score = _service().score("1", signals, {"matches": []}, [], confidence_adjustment=0.0)
    assert score.priority_tier != PriorityTier.HIGH_PRIORITY
    assert any("older than" in reason for reason in score.escalation_gate_reasons)
