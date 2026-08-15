"""Offline-safe-but-Neo4j-backed tests (mirrors test_signal_tools.py's
style): evidence building and error handling, no LLM call. The live agent
call itself is exercised by hand via the M3 checkpoint script — it costs
real money, so it isn't run on every `pytest`.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from neo4j import Driver, GraphDatabase

from specter.agents.entity_resolution import NoMatchProposalError, build_evidence
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
            "MATCH (p:Provider) WHERE p.scenario_id = 'S04' RETURN count(p) AS c"
        ).single()
    if record is None or record["c"] == 0:
        pytest.skip("Synthetic scenarios not loaded — run scripts/20_build_graph.py first")
    yield drv
    drv.close()


def test_build_evidence_carries_the_deterministic_proposal(driver: Driver) -> None:
    bundle = build_evidence(driver, "9040000000", "9040000001")
    assert bundle.provider_npi == "9040000000"
    proposal = bundle.evidence["proposal"]
    assert proposal["npi"] == "9040000000"
    assert proposal["candidate_npi"] == "9040000001"
    assert proposal["shares_officer"] is True
    assert "shares_officer" in bundle.evidence["features_present"]


def test_build_evidence_raises_when_no_proposal_computable(driver: Driver) -> None:
    with pytest.raises(NoMatchProposalError):
        build_evidence(driver, "0000000000", "9040000001")
