"""M4 checkpoint: 'Every signal tool fires correctly on the synthetic
scenarios it was designed for (one test per scenario S01-S10).'

S01 and S08 are deliberately signal-less in Phase 1 (no address-type
classifier, no utilization data — see ingest/synthetic.py's module
docstring) — the correct test for those is that nothing false-positives.

Integration tests against the live Neo4j from docker-compose, loaded via
`scripts/20_build_graph.py` + `scripts/30_build_communities.py`. Skipped if
the graph isn't populated.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from neo4j import Driver, GraphDatabase

from specter.core.contracts import ScreeningThresholds
from specter.settings import get_settings
from specter.tools import signal_tools as st

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
            "MATCH (p:Provider) WHERE p.scenario_id = 'S01' RETURN count(p) AS c"
        ).single()
    count = record["c"] if record is not None else 0
    if count == 0:
        pytest.skip(
            "Synthetic scenarios not loaded — run scripts/20_build_graph.py and "
            "scripts/30_build_communities.py first"
        )
    yield drv
    drv.close()


@pytest.fixture(scope="module")
def thresholds() -> ScreeningThresholds:
    return st.load_thresholds(THRESHOLDS_PATH)


def _npi(scenario_num: int, index: int) -> str:
    return f"9{scenario_num:02d}{index:07d}"


def test_s01_shell_at_residential_fires_only_physical_existence(
    driver: Driver, thresholds: ScreeningThresholds
) -> None:
    """M11 + D-26: S01's five providers now sit at real Miami residential
    streets, so the address-type classifier the scenario was planted for can
    finally see them. Every *structural* detector must still stay silent —
    S01 shares nothing with anything, and a degree/burst/churn signal here
    would mean the fixture had drifted.

    Requires the addresses to have been classified:
        python scripts/60_classify_addresses.py --scenario S01 --include-synthetic
    """
    npi = _npi(1, 0)
    assert st.address_degree(driver, npi, thresholds) is None
    assert st.phone_degree(driver, npi, thresholds) is None
    assert st.officer_degree(driver, npi, thresholds) is None
    assert st.address_churn(driver, npi, thresholds) is None
    assert st.phoenix_pattern(driver, npi, thresholds) is None

    signal = st.physical_existence(driver, npi, thresholds)
    if signal is None:
        pytest.skip("S01 addresses not yet classified — run scripts/60_classify_addresses.py")
    assert signal.value >= thresholds.physical_existence_min_colocated
    assert signal.source_ids
    # Hard rule 5: the provider is synthetic, so the signal must say so. Before
    # M11 `_signal` hardcoded PUBLIC and this assertion would have failed.
    assert signal.data_origin.value == "synthetic"


def test_signal_data_origin_follows_the_provider(
    driver: Driver, thresholds: ScreeningThresholds
) -> None:
    """CLAUDE.md hard rule 5. `_signal` used to hardcode `public`, which
    mislabelled every signal fired against a synthetic scenario provider.
    """
    synthetic = st.phone_degree(driver, _npi(2, 0), thresholds)
    assert synthetic is not None
    assert synthetic.data_origin.value == "synthetic"


def test_physical_existence_is_none_for_an_unclassified_address(
    driver: Driver, thresholds: ScreeningThresholds
) -> None:
    """Every synthetic address, and every real address not yet run through
    `scripts/60_classify_addresses.py`, has a null `location_type`. That is a
    normal state, not an error — the detector returns None rather than raising
    or guessing.
    """
    with driver.session() as session:
        record = session.run(
            """
            MATCH (p:Provider)-[:LOCATED_AT]->(a:Address)
            WHERE a.location_type IS NULL
            RETURN p.npi AS npi LIMIT 1
            """
        ).single()
    if record is None:
        pytest.skip("every address in the graph is already classified")
    assert st.physical_existence(driver, record["npi"], thresholds) is None


def test_s02_shared_phone_fires_phone_degree(
    driver: Driver, thresholds: ScreeningThresholds
) -> None:
    npi = _npi(2, 0)
    signal = st.phone_degree(driver, npi, thresholds)
    assert signal is not None
    assert signal.value >= thresholds.phone_degree
    assert signal.source_ids


def test_s03_address_cluster_fires_address_degree_and_burst(
    driver: Driver, thresholds: ScreeningThresholds
) -> None:
    npi = _npi(3, 0)
    degree_signal = st.address_degree(driver, npi, thresholds)
    burst_signal = st.enumeration_burst(driver, npi, thresholds)
    assert degree_signal is not None
    assert degree_signal.value == 8
    assert burst_signal is not None
    assert burst_signal.value >= thresholds.enumeration_burst_count


def test_s04_officer_reuse_fires_officer_degree(
    driver: Driver, thresholds: ScreeningThresholds
) -> None:
    npi = _npi(4, 0)
    signal = st.officer_degree(driver, npi, thresholds)
    assert signal is not None
    assert signal.value == 4


def test_s05_near_excluded_peer_fires_exclusion_proximity(
    driver: Driver, thresholds: ScreeningThresholds
) -> None:
    npi = _npi(5, 0)
    signal = st.exclusion_proximity(driver, npi, thresholds)
    assert signal is not None
    assert signal.value <= thresholds.exclusion_proximity_max_hops


def test_s06_phoenix_entity_fires_phoenix_pattern(
    driver: Driver, thresholds: ScreeningThresholds
) -> None:
    npi = _npi(6, 1)  # the new/successor org
    signal = st.phoenix_pattern(driver, npi, thresholds)
    assert signal is not None
    assert signal.value <= thresholds.phoenix_pattern_max_months_since_exclusion


def test_s07_rapid_churn_fires_address_churn(
    driver: Driver, thresholds: ScreeningThresholds
) -> None:
    npi = _npi(7, 0)
    signal = st.address_churn(driver, npi, thresholds)
    assert signal is not None
    assert signal.value >= thresholds.address_churn_count
    # source_ids must resolve via evidence_tools' graph:<type>:<key> scheme —
    # a composite multi-part key (e.g. embedding the change date) never
    # resolves and fails citation validation downstream (M9 live finding).
    assert signal.source_ids == [f"graph:provider:{npi}"]


def test_s08_dormant_reactivation_fires_no_signal(
    driver: Driver, thresholds: ScreeningThresholds
) -> None:
    npi = _npi(8, 0)
    assert st.address_degree(driver, npi, thresholds) is None
    assert st.phone_degree(driver, npi, thresholds) is None
    assert st.officer_degree(driver, npi, thresholds) is None
    assert st.address_churn(driver, npi, thresholds) is None


def test_s09_geographic_implausibility_fires_geographic_spread(
    driver: Driver, thresholds: ScreeningThresholds
) -> None:
    npi = _npi(9, 0)
    signal = st.geographic_spread(driver, npi, thresholds)
    assert signal is not None
    assert signal.value >= thresholds.geographic_spread_min_km
    assert signal.value == pytest.approx(3760, abs=50)  # Miami-LA great-circle distance


def test_s10_dense_excluded_community_fires_community_exclusion_density(
    driver: Driver, thresholds: ScreeningThresholds
) -> None:
    npi = _npi(10, 1)  # non-excluded member of the same community
    signal = st.community_exclusion_density(driver, npi, thresholds)
    assert signal is not None
    assert signal.value == pytest.approx(2 / 6)
    assert signal.value >= thresholds.community_exclusion_density_min_fraction


def test_benign_multi_tenant_building_does_not_trip_enumeration_burst(
    driver: Driver, thresholds: ScreeningThresholds
) -> None:
    """Benign control: high address_degree (75 tenants) is real, but they're
    enumerated years apart, not in a burst — enumeration_burst must not fire.
    """
    npi = f"9{90:02d}{0:07d}"
    burst_signal = st.enumeration_burst(driver, npi, thresholds)
    assert burst_signal is None
