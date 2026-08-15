from __future__ import annotations

from collections.abc import Iterator

import pytest
from neo4j import Driver, GraphDatabase

from specter.settings import get_settings
from specter.tools.entity_tools import name_similarity, propose_entity_matches


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
    yield drv
    drv.close()


def test_name_similarity_identical() -> None:
    assert name_similarity("Acme Medical Supply LLC", "Acme Medical Supply LLC") == 100.0


def test_name_similarity_reordered_tokens_scores_high() -> None:
    score = name_similarity("Acme Medical Supply LLC", "Medical Supply Acme LLC")
    assert score == 100.0  # token_set_ratio is order-insensitive


def test_name_similarity_unrelated_scores_low() -> None:
    score = name_similarity("Acme Medical Supply LLC", "Totally Different Pharmacy Inc")
    assert score < 50.0


def test_propose_entity_matches_shared_address_and_officer(driver: Driver) -> None:
    # S06: 9060000000 (excluded predecessor) and 9060000001 (phoenix successor)
    # share both address and officer.
    proposals = propose_entity_matches(driver, "9060000001", ["9060000000"])
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.shares_address is True
    assert proposal.shares_officer is True
    assert proposal.shares_phone is False
    assert proposal.source_ids


def test_propose_entity_matches_unrelated_pair_shares_nothing(driver: Driver) -> None:
    proposals = propose_entity_matches(driver, "9010000000", ["9020000000"])
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal.shares_address is False
    assert proposal.shares_phone is False
    assert proposal.shares_officer is False


def test_propose_entity_matches_missing_base_npi_returns_empty(driver: Driver) -> None:
    assert propose_entity_matches(driver, "0000000000", ["9010000000"]) == []
