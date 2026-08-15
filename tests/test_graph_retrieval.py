"""Integration tests against the live Neo4j from docker-compose (M0). Skipped
automatically if Neo4j isn't reachable, so the rest of the suite stays fast
and offline.

`global_()`/`semantic()` need Azure embeddings, not configured yet — covered
here only for their documented degrade-gracefully behavior, not real vector
search (that's follow-up work once AZURE_API_KEY/AZURE_EMBEDDING_DEPLOYMENT
are set).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from neo4j import Driver, GraphDatabase

from specter.graph.retrieval import MAX_HOPS, MAX_LIMIT, GraphRetriever
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
    yield drv
    drv.close()


@pytest.fixture(scope="module")
def sample_npi(driver: Driver) -> str:
    with driver.session() as session:
        record = session.run("MATCH (p:Provider) RETURN p.npi AS npi LIMIT 1").single()
    if record is None:
        pytest.skip("no Provider nodes loaded — run scripts/20_build_graph.py first")
    return str(record["npi"])


def test_local_returns_neighbors(driver: Driver, sample_npi: str) -> None:
    retriever = GraphRetriever(driver)
    result = retriever.local(sample_npi, hops=2, limit=50)
    assert result.mode == "local"
    assert result.query_npi == sample_npi
    for item in result.items:
        assert item.hop_distance is not None
        assert item.hop_distance <= MAX_HOPS


def test_local_hops_and_limit_are_capped(driver: Driver, sample_npi: str) -> None:
    retriever = GraphRetriever(driver)
    result = retriever.local(sample_npi, hops=999, limit=999999)
    assert len(result.items) <= MAX_LIMIT
    for item in result.items:
        assert item.hop_distance is not None
        assert item.hop_distance <= MAX_HOPS


def test_local_unknown_npi_returns_empty(driver: Driver) -> None:
    retriever = GraphRetriever(driver)
    result = retriever.local("0000000000", hops=2, limit=50)
    assert result.items == []


def test_global_and_semantic_degrade_gracefully(driver: Driver) -> None:
    retriever = GraphRetriever(driver)
    global_result = retriever.global_("shell providers at residential addresses")
    semantic_result = retriever.semantic("durable medical equipment fraud")
    assert global_result.items == []
    assert semantic_result.items == []


def test_hybrid_falls_back_to_local_only_without_azure_key(driver: Driver, sample_npi: str) -> None:
    retriever = GraphRetriever(driver)
    result = retriever.hybrid(sample_npi, "shell provider pattern")
    assert result.mode == "hybrid"
    local_only = retriever.local(sample_npi)
    assert len(result.items) <= len(local_only.items)
