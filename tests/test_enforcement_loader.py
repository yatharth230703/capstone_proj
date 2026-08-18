"""Tests for `graph/enforcement_loader.update_legal_status_from_adjudications`
(BUILD_MILESTONES.md debt D-10) — same skip-if-unreachable pattern as
`test_graph_tools.py`. Neo4j is a shared, persistent instance across test
runs (not a throwaway fixture), so the round-trip test restores whatever
value it found before it, rather than leaving the graph mutated.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from neo4j import Driver, GraphDatabase

from specter.core.contracts import CaseLegalStatus
from specter.core.enums import LegalStatus
from specter.core.errors import SpecterError
from specter.graph.enforcement_loader import update_legal_status_from_adjudications
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


@pytest.fixture()
def real_case_id(driver: Driver) -> Iterator[str]:
    with driver.session() as session:
        record = session.run(
            "MATCH (c:EnforcementCase) RETURN c.case_id AS id, c.legal_status AS ls LIMIT 1"
        ).single()
    if record is None:
        pytest.skip("No EnforcementCase nodes loaded — run scripts/20_build_graph.py first")
    case_id, original = record["id"], record["ls"]
    yield case_id
    with driver.session() as session:
        session.run(
            "MATCH (c:EnforcementCase {case_id: $case_id}) SET c.legal_status = $ls",
            case_id=case_id,
            ls=original,
        )


def test_writes_the_real_adjudication_onto_the_graph_node(
    driver: Driver, real_case_id: str
) -> None:
    with driver.session() as session:
        before = session.run(
            "MATCH (c:EnforcementCase {case_id: $case_id}) RETURN c.legal_status AS ls",
            case_id=real_case_id,
        ).single()["ls"]
    new_status = LegalStatus.DISMISSED if before != "dismissed" else LegalStatus.ALLEGED

    updated = update_legal_status_from_adjudications(
        driver, [CaseLegalStatus(case_id=real_case_id, legal_status=new_status)]
    )

    assert updated == 1
    with driver.session() as session:
        after = session.run(
            "MATCH (c:EnforcementCase {case_id: $case_id}) RETURN c.legal_status AS ls",
            case_id=real_case_id,
        ).single()["ls"]
    assert after == new_status.value


def test_empty_adjudications_is_a_real_no_op(driver: Driver) -> None:
    assert update_legal_status_from_adjudications(driver, []) == 0


def test_unresolvable_case_id_fails_loudly(driver: Driver) -> None:
    with pytest.raises(SpecterError, match="matched 0/1"):
        update_legal_status_from_adjudications(
            driver,
            [CaseLegalStatus(case_id="does-not-exist", legal_status=LegalStatus.CHARGED)],
        )
