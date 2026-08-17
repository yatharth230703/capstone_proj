"""Offline tests for `judge/report.py` — no Neo4j/LLM needed. Added after a
real M9 live run surfaced a genuine column-misalignment bug in
`_rubric_distribution` (a criterion excluded from one verdict's
`aggregate_scores` for low reliability shifted every later column left
instead of rendering as "—" in its own column).
"""

from __future__ import annotations

from specter.core.contracts import CriterionScore, JudgeVerdict, RubricJudgment
from specter.judge.report import _rubric_distribution, calibration_accuracy


def _verdict(npi: str, aggregate: dict[str, float], low_reliability: list[str]) -> JudgeVerdict:
    return JudgeVerdict(
        provider_npi=npi,
        samples=[
            RubricJudgment(
                criteria=[
                    CriterionScore(
                        criterion=c, score=int(v), supporting_quote="x", weakness_found="y"
                    )
                    for c, v in aggregate.items()
                ]
            )
        ],
        per_criterion_variance={},
        low_reliability_criteria=low_reliability,
        aggregate_scores=aggregate,
    )


def test_rubric_distribution_row_column_count_matches_header_even_with_exclusion() -> None:
    verdicts = {
        "1111111111": _verdict(
            "1111111111",
            {"citation_validity": 1.0, "counter_evidence": 5.0, "hallucination": 3.0},
            [],
        ),
        "2222222222": _verdict(
            "2222222222",
            {"citation_validity": 1.0, "counter_evidence": 5.0},  # hallucination excluded
            ["hallucination"],
        ),
    }
    table = _rubric_distribution(verdicts)
    lines = table.splitlines()
    header_cell_count = lines[0].count("|") - 1
    for row in lines[2:]:
        assert row.count("|") - 1 == header_cell_count, f"misaligned row: {row}"
    # the excluded criterion renders as a placeholder in its own column,
    # not a shift of later columns into its slot
    row_2222_cells = [c.strip() for c in lines[3].split("|")[1:-1]]
    assert "—" in row_2222_cells


def test_rubric_distribution_empty_verdicts() -> None:
    assert _rubric_distribution({}) == "No case corpus had a rubric judgment run."


def test_calibration_accuracy_excludes_controls_from_denominator() -> None:
    from specter.core.contracts import CalibrationCase, CasePacket, CitationReport, CounterEvidence

    def _case(npi: str) -> CasePacket:
        from datetime import UTC, datetime

        return CasePacket(
            provider_npi=npi, narrative="", signals=[], enforcement_matches=[],
            legal_status_per_match=[],
            counter_evidence=CounterEvidence(
                per_signal=[], unresolved_conflicts=[], confidence_adjustment=0.0
            ),
            citation_report=CitationReport(
                total_citations=0, resolved_citations=0, unresolved_source_ids=[], all_resolved=True
            ),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

    caught = CalibrationCase(
        fixture_id="C01", description="d", injected_defect="x",
        expected_criterion="citation_validity", case=_case("1"),
    )
    control = CalibrationCase(
        fixture_id="C09", description="d", injected_defect=None,
        expected_criterion=None, case=_case("2"),
    )
    calibration = [
        (caught, _verdict("1", {"citation_validity": 0.0}, [])),
        (control, _verdict("2", {"citation_validity": 5.0}, [])),
    ]
    n_caught, notes = calibration_accuracy(calibration)
    assert n_caught == 1
    assert len(notes) == 1  # control not counted or noted
