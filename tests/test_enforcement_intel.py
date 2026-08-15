"""Offline-safe-but-Neo4j-backed test for the Enforcement Intelligence
Agent's evidence builder — no LLM call. Runs against the 1-row DOJ corpus
(debt D-2); that is a real data gap, not something this test works around.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from neo4j import Driver, GraphDatabase

from specter.agents.enforcement_intel import build_evidence
from specter.settings import get_settings


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
            "MATCH (p:Provider) WHERE p.scenario_id = 'S02' RETURN count(p) AS c"
        ).single()
    if record is None or record["c"] == 0:
        pytest.skip("Synthetic scenarios not loaded — run scripts/20_build_graph.py first")
    yield drv
    drv.close()


def test_build_evidence_builds_query_from_profile(driver: Driver) -> None:
    bundle = build_evidence(driver, "9020000000")
    assert bundle.provider_npi == "9020000000"
    assert bundle.evidence["profile"] is not None
    assert bundle.evidence["search_query"]
    assert "case_hits" in bundle.evidence


def test_build_evidence_falls_back_to_npi_when_no_profile(driver: Driver) -> None:
    bundle = build_evidence(driver, "0000000000")
    assert bundle.evidence["profile"] is None
    assert bundle.evidence["search_query"] == "0000000000"
