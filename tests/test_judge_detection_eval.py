"""Offline tests for `judge/detection_eval.py`'s pure functions (M9, plan
§12.1) — `scenario_recall`, `precision_at_k`, `false_positive_rate` need no
Neo4j/LLM. `real_positive_npis`/`real_provider_count` need live Neo4j only
(no LLM either) and are covered separately, skipped if Neo4j is down.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from neo4j import Driver, GraphDatabase

from specter.core.contracts import CasePacket, CitationReport, CounterEvidence, RiskSignal
from specter.core.enums import DataOrigin
from specter.judge.detection_eval import (
    SCENARIO_EXPECTED_SIGNALS,
    build_report,
    false_positive_rate,
    precision_at_k,
    real_positive_npis,
    real_provider_count,
    scenario_recall,
)
from specter.settings import get_settings


def _empty_case(npi: str, signal_types: list[str]) -> CasePacket:
    signals = [
        RiskSignal(
            signal_type=t, provider_npi=npi, value=9.0, threshold=5.0, source_ids=[],
            data_origin=DataOrigin.SYNTHETIC, detected_at=datetime(2026, 1, 1, tzinfo=UTC),
            known_limitations=[], geocoding_method=None,
        )
        for t in signal_types
    ]
    return CasePacket(
        provider_npi=npi, narrative="", signals=signals, enforcement_matches=[],
        legal_status_per_match=[],
        counter_evidence=CounterEvidence(
            per_signal=[], unresolved_conflicts=[], confidence_adjustment=0.0
        ),
        citation_report=CitationReport(
            total_citations=0, resolved_citations=0, unresolved_source_ids=[], all_resolved=True
        ),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_scenario_recall_hits_when_expected_signal_fired() -> None:
    case = _empty_case("9020000000", ["phone_degree"])
    result = scenario_recall("S02", case)
    assert result.recall_hit is True
    assert result.detector_exists is True


def test_scenario_recall_misses_when_signal_does_not_fire() -> None:
    case = _empty_case("9020000000", [])
    result = scenario_recall("S02", case)
    assert result.recall_hit is False


def test_scenario_recall_none_case_is_a_miss_when_detector_exists() -> None:
    result = scenario_recall("S04", None)
    assert result.recall_hit is False
    assert result.detector_exists is True


def test_scenario_recall_no_detector_scenarios_always_hit() -> None:
    """S08 alone now: Phase 1 has no utilization data, so it is genuinely
    undetectable and must not be counted as a miss.

    **S01 was in this list until M11.** It gained a real detector
    (`physical_existence`, the Maps address-type classifier) and its providers
    were moved onto real residential streets (D-26), so it is now held to the
    same standard as every other scenario — see the test below.
    """
    result = scenario_recall("S08", _empty_case("x", []))
    assert result.detector_exists is False
    assert result.recall_hit is True


def test_s01_now_has_a_detector_and_is_held_to_it() -> None:
    """Guards the D-26 change from being silently reverted: if someone drops
    `physical_existence` from S01's expectations, the headline recall number
    would quietly get easier rather than the regression being visible.
    """
    assert SCENARIO_EXPECTED_SIGNALS["S01"] == ["physical_existence"]
    assert scenario_recall("S01", _empty_case("x", [])).detector_exists is True
    assert scenario_recall("S01", _empty_case("x", [])).recall_hit is False
    assert scenario_recall("S01", _empty_case("x", ["physical_existence"])).recall_hit is True


def test_precision_at_k_ranks_by_signal_count() -> None:
    positives = {"a", "b"}
    cases = [
        _empty_case("a", ["x", "y"]),  # 2 signals, positive
        _empty_case("c", ["x"]),       # 1 signal, negative
        _empty_case("b", []),          # 0 signals, positive
    ]
    result = precision_at_k(positives, cases)
    assert result["10"] == pytest.approx(2 / 3)


def test_precision_at_k_empty_cases_is_zero() -> None:
    result = precision_at_k({"a"}, [])
    assert all(v == 0.0 for v in result.values())


def test_false_positive_rate_none_when_no_controls() -> None:
    assert false_positive_rate([]) is None


def test_false_positive_rate_counts_fired_controls() -> None:
    controls = [_empty_case("c1", ["x"]), _empty_case("c2", [])]
    assert false_positive_rate(controls) == pytest.approx(0.5)


def test_build_report_assembles_all_ten_scenarios() -> None:
    scenario_cases = {"S02": _empty_case("9020000000", ["phone_degree"])}
    report = build_report(
        scenario_cases=scenario_cases, real_positive_npis_set=set(),
        real_provider_total=100, ranked_real_cases=[], control_cases=[],
    )
    assert len(report.scenario_recall) == 10
    assert report.real_positive_denominator == 100


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


def test_real_positive_npis_matches_debt_d21(driver: Driver) -> None:
    # BUILD_MILESTONES.md debt D-21: 4 real (public) providers carry a
    # direct EXCLUDED_BY edge, as of M8's live query.
    npis = real_positive_npis(driver)
    assert isinstance(npis, list)
    assert len(npis) <= 8  # 4 real + up to 4 synthetic scenario providers, upper-bounded


def test_real_provider_count_is_large(driver: Driver) -> None:
    assert real_provider_count(driver) > 1000
