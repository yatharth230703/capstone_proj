"""Structural checks on the 10 calibration fixtures (M9, CLAUDE.md Amendment
2 mitigation 4) — schema-valid, C09/C10 are genuinely defect-free controls,
C01-C08 each carry the one named defect. No Neo4j/LLM needed.
"""

from __future__ import annotations

from specter.core.banned_vocabulary import find_banned_phrases
from specter.judge.calibration_fixtures import build_calibration_cases


def test_all_ten_fixtures_present_with_unique_ids() -> None:
    cases = build_calibration_cases()
    ids = [c.fixture_id for c in cases]
    assert ids == [f"C{i:02d}" for i in range(1, 11)]


def test_c09_and_c10_are_controls_with_no_expected_criterion() -> None:
    cases = {c.fixture_id: c for c in build_calibration_cases()}
    for fixture_id in ("C09", "C10"):
        assert cases[fixture_id].injected_defect is None
        assert cases[fixture_id].expected_criterion is None


def test_c01_through_c08_each_name_a_defect_and_expected_criterion() -> None:
    cases = {c.fixture_id: c for c in build_calibration_cases()}
    for fixture_id in (f"C{i:02d}" for i in range(1, 9)):
        assert cases[fixture_id].injected_defect
        assert cases[fixture_id].expected_criterion


def test_c01_citation_actually_unresolvable() -> None:
    cases = {c.fixture_id: c for c in build_calibration_cases()}
    case = cases["C01"].case
    assert case.citation_report.all_resolved is False


def test_c02_narrative_contains_ungrounded_number() -> None:
    cases = {c.fixture_id: c for c in build_calibration_cases()}
    assert "947" in cases["C02"].case.narrative


def test_c03_legal_status_collapsed() -> None:
    cases = {c.fixture_id: c for c in build_calibration_cases()}
    case = cases["C03"].case
    assert case.legal_status_per_match[0].legal_status.value == "charged"
    assert "convicted" in case.narrative.lower()


def test_c04_counter_evidence_actually_empty() -> None:
    cases = {c.fixture_id: c for c in build_calibration_cases()}
    case = cases["C04"].case
    assert case.counter_evidence.per_signal == []
    assert case.signals  # a signal fired, so this is a real omission


def test_c06_narrative_actually_banned() -> None:
    cases = {c.fixture_id: c for c in build_calibration_cases()}
    assert find_banned_phrases(cases["C06"].case.narrative) == ["fraudulent"]


def test_c07_signal_genuinely_duplicated() -> None:
    cases = {c.fixture_id: c for c in build_calibration_cases()}
    case = cases["C07"].case
    assert len(case.signals) == 2
    assert case.signals[0].signal_type == case.signals[1].signal_type


def test_c09_and_c10_load_real_case_files() -> None:
    cases = {c.fixture_id: c for c in build_calibration_cases()}
    assert cases["C09"].case.provider_npi == "1003001439"
    assert cases["C10"].case.provider_npi == "1003008756"
    assert find_banned_phrases(cases["C09"].case.narrative) == []
    assert find_banned_phrases(cases["C10"].case.narrative) == []
