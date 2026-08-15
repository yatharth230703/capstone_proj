"""`graph/summaries.py`'s deterministic pieces — the fact block and the B2
renderer. Neither involves an LLM, so both are testable without one.
CLAUDE.md: B2 is above the cache boundary, so it must never vary between two
compilations against the same graph state (see `test_prompt_compiler.py`'s
invariants — this file covers the Neo4j-facing half of that guarantee).
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from neo4j import Driver, GraphDatabase

from specter.graph.summaries import (
    community_facts,
    list_community_ids,
    render_b2_community_summaries,
)
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
def sample_community_id(driver: Driver) -> str:
    ids = list_community_ids(driver, limit=1)
    if not ids:
        pytest.skip("no Community nodes — run scripts/30_build_communities.py first")
    return ids[0]


def test_community_facts_is_deterministic(driver: Driver, sample_community_id: str) -> None:
    first_facts, first_members = community_facts(driver, sample_community_id)
    second_facts, second_members = community_facts(driver, sample_community_id)
    assert first_facts == second_facts
    assert first_members == second_members
    assert first_facts == sorted(first_facts)
    assert first_members == sorted(first_members)


def test_community_facts_covers_expected_dimensions(
    driver: Driver, sample_community_id: str
) -> None:
    facts, members = community_facts(driver, sample_community_id)
    assert members
    keys = {fact.split("=", 1)[0] for fact in facts}
    assert keys == {
        "member_count",
        "distinct_shared_addresses",
        "distinct_shared_officers",
        "excluded_member_count",
        "enumeration_date_range",
        "state_spread",
    }


def test_community_facts_unknown_id_raises(driver: Driver) -> None:
    with pytest.raises(ValueError, match="not found"):
        community_facts(driver, "does-not-exist")


def test_b2_render_is_deterministic(driver: Driver) -> None:
    first = render_b2_community_summaries(driver, cap=5)
    second = render_b2_community_summaries(driver, cap=5)
    assert first == second


def test_b2_render_is_valid_sorted_json(driver: Driver) -> None:
    body = render_b2_community_summaries(driver, cap=5)
    parsed = json.loads(body)
    assert json.dumps(parsed, sort_keys=True) == body
    assert parsed["cap"] == 5
    assert len(parsed["summaries"]) <= 5
    ids = [summary["community_id"] for summary in parsed["summaries"]]
    assert ids == sorted(ids)
