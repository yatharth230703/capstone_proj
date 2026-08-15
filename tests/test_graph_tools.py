from __future__ import annotations

from collections.abc import Iterator

import pytest
from neo4j import Driver, GraphDatabase

from specter.settings import get_settings
from specter.tools import graph_tools as gt


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


def test_get_provider_profile_returns_expected_shape(driver: Driver) -> None:
    profile = gt.get_provider_profile(driver, "9020000000")
    assert profile is not None
    assert profile.npi == "9020000000"
    assert profile.phones == ["+13055559000"]


def test_get_provider_profile_missing_npi_returns_none(driver: Driver) -> None:
    assert gt.get_provider_profile(driver, "0000000000") is None


def test_expand_neighborhood_caps_hops_and_limit(driver: Driver) -> None:
    sub = gt.expand_neighborhood(driver, "9020000000", hops=999, limit=999999)
    assert sub.center_npi == "9020000000"
    assert len(sub.nodes) <= gt.MAX_LIMIT
    for node in sub.nodes:
        assert node["hop_distance"] <= gt.MAX_HOPS


def test_find_shared_attribute_peers_phone(driver: Driver) -> None:
    peers = gt.find_shared_attribute_peers(driver, "9020000000", "phone")
    assert len(peers) == 4  # 5 S02 providers share one phone, minus self
    assert all(p.attribute == "phone" for p in peers)


def test_shortest_path_to_exclusion_finds_s05(driver: Driver) -> None:
    result = gt.shortest_path_to_exclusion(driver, "9050000000")
    assert result is not None
    assert result.hops <= gt.MAX_HOPS
    assert result.target_type == "exclusion"


def test_shortest_path_to_exclusion_none_for_unconnected(driver: Driver) -> None:
    result = gt.shortest_path_to_exclusion(driver, "9010000000", max_hops=1)
    assert result is None


def test_get_community_context_s10(driver: Driver) -> None:
    summary = gt.get_community_context(driver, "9100000001")
    assert summary is not None
    assert summary.member_count == 6
    assert any("excluded_member_count=2" in fact for fact in summary.structural_facts)
    # M2 characterized all 255 communities; D-9 fix reads it back rather than
    # always returning None.
    assert summary.characterization is not None
    assert summary.generated_at is not None
    assert summary.prompt_version is not None


def test_search_enforcement_cases_matches_loaded_doj_case(driver: Driver) -> None:
    # M2: graph/loader.load_enforcement_cases loads the DOJ snapshot (1 row
    # today, plan §5.3/debt D-2). This is a substring match over
    # title/description, not the vector search in GraphRetriever.semantic().
    hits = gt.search_enforcement_cases(driver, "fraud")
    assert hits
    assert all(hit.source_ids for hit in hits)


def test_search_enforcement_cases_no_match_returns_empty(driver: Driver) -> None:
    hits = gt.search_enforcement_cases(driver, "xyzzy-no-such-term")
    assert hits == []
