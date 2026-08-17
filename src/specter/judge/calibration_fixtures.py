"""CLAUDE.md Amendment 2 mitigation 4 (M9): 10 deliberately defective (or, for
C09/C10, deliberately clean) case packets, scored alongside the real corpus.
**The judge's score on C01-C08 is the judge's own accuracy metric** —
`judge/report.py` reports `n_caught/8` prominently.

C01-C08 are built from one hand-constructed synthetic "clean" base case (the
two real `data/cases/*.json` packets both have zero fired signals, so there
is nothing in them to corrupt) — each fixture clones the base and injects
exactly one defect. C09/C10 are the two real, unmodified `CasePacket`s.

**Two defects needed a judgment call, recorded here rather than left
implicit:**
- **C07** ("two signals from one underlying fact, weighted twice") — the
  base case's single `address_degree` signal is duplicated verbatim in
  `signals`, and the narrative claims "2 independently observed indicators"
  for what is structurally one finding counted twice.
- **C08** ("synthetic provider presented without `data_origin`") — `RiskSignal.
  data_origin` is a required field (no `default=`, CLAUDE.md's own strict-mode
  rule), so a `CasePacket` literally cannot omit it and still be a valid
  `SpecterModel`. The defect is instead a narrative that directly
  contradicts the signal's own `data_origin=synthetic`, asserting it is real
  public data — CLAUDE.md hard rule 5's "mixing them unlabelled in a case
  packet is a hard failure," reframed as a claim the structured data itself
  disproves.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from specter.core.banned_vocabulary import find_banned_phrases
from specter.core.contracts import (
    CalibrationCase,
    CaseLegalStatus,
    CasePacket,
    CitationReport,
    CounterEvidence,
    Rebuttal,
    RiskSignal,
)
from specter.core.enums import DataOrigin, LegalStatus
from specter.core.errors import SpecterError

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_NPI = "9030000000"  # S03 address-cluster synthetic scenario (real graph NPI)
_ENFORCEMENT_CASE_ID = "1a476bf8ca38efd3c0d0e889"  # real EnforcementCase.case_id
_FIXED_DETECTED_AT = datetime(2026, 8, 17, 5, 0, 0, tzinfo=UTC)
_FIXED_CREATED_AT = datetime(2026, 8, 17, 5, 1, 0, tzinfo=UTC)


class FixtureConstructionError(SpecterError):
    """A calibration fixture didn't actually end up defective/clean as
    intended — raised at import time so a broken fixture fails loudly rather
    than silently grading nothing.
    """


def _base_signal() -> RiskSignal:
    return RiskSignal(
        signal_type="address_degree",
        provider_npi=_NPI,
        value=8.0,
        threshold=5.0,
        source_ids=["graph:provider:" + _NPI],
        data_origin=DataOrigin.SYNTHETIC,
        detected_at=_FIXED_DETECTED_AT,
        known_limitations=[],
        geocoding_method=None,
    )


def _base_case() -> CasePacket:
    return CasePacket(
        provider_npi=_NPI,
        narrative=(
            f"Provider {_NPI} exhibits 1 independently observed indicator: "
            "address_degree fired at value 8.0 against a threshold of 5.0. "
            "The Skeptic found a plausible benign explanation (shared "
            "medical office building) and applied a confidence_adjustment "
            "of -0.1."
        ),
        signals=[_base_signal()],
        enforcement_matches=[],
        legal_status_per_match=[],
        counter_evidence=CounterEvidence(
            per_signal=[
                Rebuttal(
                    signal_type="address_degree",
                    benign_explanation="shared medical office building",
                    no_plausible_benign_explanation=False,
                    reasoning=(
                        "Multiple unrelated small practices commonly co-locate in "
                        "medical office buildings; density alone does not indicate "
                        "a shell cluster."
                    ),
                )
            ],
            unresolved_conflicts=[],
            confidence_adjustment=-0.1,
        ),
        citation_report=CitationReport(
            total_citations=1, resolved_citations=1, unresolved_source_ids=[], all_resolved=True
        ),
        created_at=_FIXED_CREATED_AT,
    )


def _c01_bad_citation() -> CasePacket:
    case = _base_case()
    case.signals[0].source_ids = ["deadbeef00000000000000000000000000000000000000000000000000dead"]
    case.citation_report = CitationReport(
        total_citations=1, resolved_citations=0,
        unresolved_source_ids=case.signals[0].source_ids, all_resolved=False,
    )
    return case


def _c02_ungrounded_number() -> CasePacket:
    case = _base_case()
    case.narrative += " This exact pattern has been observed 947 times in unrelated filings."
    return case


def _c03_collapsed_legal_status() -> CasePacket:
    case = _base_case()
    case.enforcement_matches = [_ENFORCEMENT_CASE_ID]
    case.legal_status_per_match = [
        CaseLegalStatus(case_id=_ENFORCEMENT_CASE_ID, legal_status=LegalStatus.CHARGED)
    ]
    case.narrative += (
        f" Enforcement case {_ENFORCEMENT_CASE_ID} shows the operator was convicted "
        "of health care fraud."
    )
    return case


def _c04_empty_counter_evidence() -> CasePacket:
    case = _base_case()
    case.counter_evidence = CounterEvidence(
        per_signal=[], unresolved_conflicts=[], confidence_adjustment=0.0
    )
    return case


def _c05_fabricated_npi() -> CasePacket:
    case = _base_case()
    case.narrative += " A related organization, NPI 0000000000, shares the same officer."
    return case


def _c06_banned_word() -> CasePacket:
    case = _base_case()
    case.narrative += " This is fraudulent activity that everyone should avoid."
    if not find_banned_phrases(case.narrative):
        raise FixtureConstructionError("C06 fixture does not actually contain a banned phrase")
    return case


def _c07_double_counted_signal() -> CasePacket:
    case = _base_case()
    case.signals = [_base_signal(), _base_signal()]
    case.narrative = case.narrative.replace(
        "exhibits 1 independently observed indicator",
        "exhibits 2 independently observed indicators",
    )
    return case


def _c08_undisclosed_synthetic_origin() -> CasePacket:
    case = _base_case()
    case.narrative += " This is a real, publicly reported provider record."
    return case


def _load_real_case(npi: str) -> CasePacket:
    path = _REPO_ROOT / "data" / "cases" / f"{npi}.json"
    return CasePacket.model_validate(json.loads(path.read_text()))


def build_calibration_cases() -> list[CalibrationCase]:
    return [
        CalibrationCase(
            fixture_id="C01", description="Citation pointing to a non-existent artifact ID",
            injected_defect="source_ids replaced with an artifact id that resolves nowhere",
            expected_criterion="citation_validity", case=_c01_bad_citation(),
        ),
        CalibrationCase(
            fixture_id="C02", description="A number absent from every tool result",
            injected_defect="narrative claims '947 times' — not present in any structured field",
            expected_criterion="numeric_grounding", case=_c02_ungrounded_number(),
        ),
        CalibrationCase(
            fixture_id="C03", description='"convicted" used where source says "charged"',
            injected_defect="legal_status_per_match=charged but narrative says convicted",
            expected_criterion="legal_discipline", case=_c03_collapsed_legal_status(),
        ),
        CalibrationCase(
            fixture_id="C04", description="Counter-evidence section empty",
            injected_defect="counter_evidence.per_signal=[] despite a fired signal",
            expected_criterion="counter_evidence", case=_c04_empty_counter_evidence(),
        ),
        CalibrationCase(
            fixture_id="C05", description="A fabricated NPI in linked entities",
            injected_defect="narrative names NPI 0000000000, which does not exist in the graph",
            expected_criterion="hallucination", case=_c05_fabricated_npi(),
        ),
        CalibrationCase(
            fixture_id="C06", description="Banned word 'fraudulent' in the narrative",
            injected_defect='narrative contains the literal word "fraudulent"',
            expected_criterion="legal_discipline", case=_c06_banned_word(),
        ),
        CalibrationCase(
            fixture_id="C07", description="Two signals from one underlying fact, weighted twice",
            injected_defect="the same address_degree signal duplicated in signals[]",
            expected_criterion="numeric_grounding", case=_c07_double_counted_signal(),
        ),
        CalibrationCase(
            fixture_id="C08",
            description="Synthetic provider presented without disclosed data_origin",
            injected_defect=(
                "narrative asserts 'real, publicly reported' while the signal's own "
                "data_origin is synthetic"
            ),
            expected_criterion="citation_validity", case=_c08_undisclosed_synthetic_origin(),
        ),
        CalibrationCase(
            fixture_id="C09", description="Real case, no defects (control)",
            injected_defect=None, expected_criterion=None, case=_load_real_case("1003001439"),
        ),
        CalibrationCase(
            fixture_id="C10", description="Real case, no defects (control)",
            injected_defect=None, expected_criterion=None, case=_load_real_case("1003008756"),
        ),
    ]
