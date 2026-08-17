"""Offline-against-live-Neo4j tests for the 3 primary rubric criteria (M9,
CLAUDE.md Amendment 2 mitigation 1). No LLM needed — reuses the calibration
fixtures' hand-built `CasePacket`s directly.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from neo4j import Driver, GraphDatabase

from specter.judge import calibration_fixtures, deterministic_checks
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


def _fixture(fixture_id: str):
    cases = {c.fixture_id: c for c in calibration_fixtures.build_calibration_cases()}
    return cases[fixture_id]


def test_check_citation_validity_passes_the_clean_base_case(driver: Driver, tmp_path) -> None:
    case = calibration_fixtures._base_case()
    results = deterministic_checks.check_citation_validity(case, driver, tmp_path)
    assert all(results.values())


def test_check_citation_validity_catches_c01(driver: Driver, tmp_path) -> None:
    case = _fixture("C01").case
    results = deterministic_checks.check_citation_validity(case, driver, tmp_path)
    assert not all(results.values())


def test_check_numeric_grounding_passes_the_clean_base_case() -> None:
    case = calibration_fixtures._base_case()
    assert deterministic_checks.check_numeric_grounding(case) == []


def test_check_numeric_grounding_catches_c02() -> None:
    case = _fixture("C02").case
    violations = deterministic_checks.check_numeric_grounding(case)
    assert "947" in violations


def test_check_entity_existence_passes_the_clean_base_case(driver: Driver) -> None:
    case = calibration_fixtures._base_case()
    results = deterministic_checks.check_entity_existence(case, driver)
    # base narrative names only the provider's own (real) NPI
    assert results == {"npi:9030000000": True}


def test_check_entity_existence_catches_c05_fabricated_npi(driver: Driver) -> None:
    case = _fixture("C05").case
    results = deterministic_checks.check_entity_existence(case, driver)
    assert results["npi:0000000000"] is False


def test_check_entity_existence_resolves_real_enforcement_case(driver: Driver) -> None:
    case = _fixture("C03").case
    results = deterministic_checks.check_entity_existence(case, driver)
    assert results["id:1a476bf8ca38efd3c0d0e889"] is True
