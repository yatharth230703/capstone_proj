"""Offline-safe-but-Neo4j-backed tests for the Graph Investigation Agent's
evidence builder and its numeric-grounding check — no LLM call. The
grounding check is what CLAUDE.md hard rule 1 requires ("a number in agent
output that isn't in a tool result is a bug that fails the case"); it must
catch a fabricated number without needing a live model to produce one.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from neo4j import Driver, GraphDatabase

from specter.agents.graph_investigation import _numeric_violations, build_evidence
from specter.settings import get_settings
from specter.tools.signal_tools import load_thresholds

THRESHOLDS_PATH = Path("config/screening.yaml")


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


def test_build_evidence_carries_fired_signals_and_hybrid_search(driver: Driver) -> None:
    thresholds = load_thresholds(THRESHOLDS_PATH)
    bundle = build_evidence(driver, "9030000000", thresholds)
    assert bundle.provider_npi == "9030000000"
    assert bundle.evidence["fired_signals"]
    assert any(s["signal_type"] == "address_degree" for s in bundle.evidence["fired_signals"])
    assert "hybrid_search" in bundle.evidence


def test_numeric_violations_empty_when_narration_only_quotes_evidence() -> None:
    evidence = {"fired_signals": [{"signal_type": "address_degree", "value": 8.0}]}
    output = {
        "narration": "address_degree fired with a value of 8.0.",
        "community_context": "no community on record.",
    }
    assert _numeric_violations(output, evidence) == []


def test_numeric_violations_catches_a_fabricated_number() -> None:
    evidence = {"fired_signals": [{"signal_type": "address_degree", "value": 8.0}]}
    output = {
        "narration": "this provider shares its address with 47 other providers.",
        "community_context": "no community on record.",
    }
    violations = _numeric_violations(output, evidence)
    assert "47" in violations
