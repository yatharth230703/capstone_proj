"""Cohort overview + per-case detail endpoints (M13). Reads the real,
already-screened `data/cases/*.json` `CasePacket`s — no new screening
happens here (CLAUDE.md Amendment 4(a)).

**Debt D-23 — `CaseScore`/`priority_tier` wasn't persisted, closed for real
post-M14.** `workflow/screening.py` now writes `<npi>.score.json` alongside
`<npi>.json` (the `case_score.model_dump_json()` verbatim), so a case
screened after that fix carries its *exact* score, not a recomputation.
Cases screened before the fix (or in a test fixture that only writes the
packet) have no score file — for those, this module falls back to the same
recompute it always used: `workflow.state.ScoringService.score` with
`entity_adjudications=[]`, the one input never persisted anywhere for a
completed case (every other input — `signals`,
`enforcement_matches`/`legal_status_per_match`, the Skeptic's
`confidence_adjustment` — is fully persisted and the recompute uses it
exactly). `_score_for` returns which happened; every response says so
explicitly, per-case, via `priority_tier_approximate` — never presented as
exact when it isn't, and never presented as approximate when a real
persisted score is available.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException, Request
from neo4j import Driver

from specter.api.ml import score_or_error
from specter.core.contracts import CasePacket, CaseScore
from specter.core.errors import SpecterError
from specter.workflow.state import ScoringService

router = APIRouter()

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CASES_DIR = _REPO_ROOT / "data" / "cases"
SCREENING_CONFIG_PATH = _REPO_ROOT / "config" / "screening.yaml"
_GRAPH_COUNT_LABELS = ["Provider", "Address", "Community", "Exclusion"]

_PRIORITY_TIER_APPROXIMATE_NOTE = (
    "priority_tier recomputed from the persisted CasePacket without "
    "entity_adjudications — no <npi>.score.json exists for this case (it was "
    "screened before D-23's persistence fix landed); identity_integrity "
    "assumes zero unresolved entity-match conflicts and may differ from the "
    "score the live screening run actually computed"
)
_PRIORITY_TIER_EXACT_NOTE = (
    "priority_tier read from <npi>.score.json — persisted by the live "
    "screening run itself (workflow/screening.py), not recomputed "
    "(BUILD_MILESTONES.md debt D-23, closed)"
)


def _require_cases() -> list[Path]:
    if not CASES_DIR.exists():
        raise SpecterError(
            f"{CASES_DIR} is missing — it's a gitignored run artifact. Run "
            "`python scripts/40_screen.py` to populate it (real Azure calls)."
        )
    # `*.json` also matches the `<npi>.score.json` files workflow/screening.py
    # now writes alongside each packet (D-23) — excluded explicitly, not by
    # a stricter glob, since `.score.json` is a real, deliberate suffix
    # rather than something a glob pattern alone can express cleanly.
    paths = sorted(p for p in CASES_DIR.glob("*.json") if not p.name.endswith(".score.json"))
    if not paths:
        raise SpecterError(
            f"{CASES_DIR} exists but has no case files — run "
            "`python scripts/40_screen.py` to populate it."
        )
    return paths


def _load_case(path: Path) -> CasePacket:
    return CasePacket.model_validate(json.loads(path.read_text()))


def _scoring_service() -> ScoringService:
    cfg = yaml.safe_load(SCREENING_CONFIG_PATH.read_text())
    gate = cfg["escalation_gate"]
    return ScoringService(
        signal_families=cfg["signal_families"],
        min_independent_signal_families=gate["min_independent_signal_families"],
        evidence_freshness_days=gate["evidence_freshness_days"],
    )


def _approximate_score(case: CasePacket, scoring: ScoringService) -> CaseScore:
    enforcement_findings: dict[str, Any] = {
        "matches": case.enforcement_matches,
        "legal_status_per_match": [
            s.model_dump(mode="json") for s in case.legal_status_per_match
        ],
    }
    return scoring.score(
        case.provider_npi,
        [s.model_dump(mode="json") for s in case.signals],
        enforcement_findings,
        [],  # entity_adjudications — not persisted, see module docstring (D-23)
        case.counter_evidence.confidence_adjustment,
    )


def _load_persisted_score(npi: str) -> CaseScore | None:
    path = CASES_DIR / f"{npi}.score.json"
    if not path.exists():
        return None
    return CaseScore.model_validate(json.loads(path.read_text()))


def _score_for(case: CasePacket, scoring: ScoringService) -> tuple[CaseScore, bool]:
    """Returns `(score, approximate)`. Prefers the exact score
    `workflow/screening.py` persists post-D-23; falls back to
    `_approximate_score` for a case screened before that fix landed.
    """
    persisted = _load_persisted_score(case.provider_npi)
    if persisted is not None:
        return persisted, False
    return _approximate_score(case, scoring), True


def _graph_counts(driver: Driver) -> dict[str, int]:
    counts: dict[str, int] = {}
    with driver.session() as session:
        for label in _GRAPH_COUNT_LABELS:
            record = session.run(f"MATCH (n:{label}) RETURN count(n) AS n").single()
            counts[label.lower()] = int(record["n"]) if record else 0
    return counts


@router.get("/cohort")
def cohort_overview(request: Request) -> dict[str, Any]:
    """`cases` (added building M14 — the Action Plan's own File Manifest
    didn't list `api/cases.py` as an edit, but the UI's cohort page needs a
    linkable per-case list and `/cohort` previously returned only counts;
    see BUILD_MILESTONES.md M14 Result) is sorted most-signals-first so the
    most interesting cases surface without any client-side sort.
    """
    paths = _require_cases()
    scoring = _scoring_service()

    tier_counts = {"high_priority": 0, "standard": 0, "low": 0}
    signal_type_counts: dict[str, int] = {}
    cases_with_fired_signals = 0
    cases: list[dict[str, Any]] = []
    exact_count = 0
    for path in paths:
        case = _load_case(path)
        if case.signals:
            cases_with_fired_signals += 1
        for signal in case.signals:
            signal_type_counts[signal.signal_type] = (
                signal_type_counts.get(signal.signal_type, 0) + 1
            )
        score, approximate = _score_for(case, scoring)
        exact_count += 0 if approximate else 1
        tier_counts[score.priority_tier.value] += 1
        cases.append(
            {
                "npi": case.provider_npi,
                "priority_tier": score.priority_tier.value,
                "priority_tier_exact": not approximate,
                "signal_count": len(case.signals),
                "signal_types": sorted({s.signal_type for s in case.signals}),
            }
        )
    cases.sort(key=lambda c: (-c["signal_count"], c["npi"]))

    return {
        "total_cases": len(paths),
        "cases_with_fired_signals": cases_with_fired_signals,
        "signal_type_counts": signal_type_counts,
        "priority_tier_counts": tier_counts,
        "cases_with_exact_priority_tier": exact_count,
        "priority_tier_approximate": exact_count < len(paths),
        "priority_tier_approximation_note": (
            _PRIORITY_TIER_EXACT_NOTE
            if exact_count == len(paths)
            else _PRIORITY_TIER_APPROXIMATE_NOTE
        ),
        "graph_counts": _graph_counts(request.app.state.driver),
        "cases": cases,
    }


@router.get("/cases/{npi}")
def case_detail(npi: str, request: Request) -> dict[str, Any]:
    path = CASES_DIR / f"{npi}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"no persisted case for provider {npi}")
    case = _load_case(path)
    scoring = _scoring_service()
    score, approximate = _score_for(case, scoring)
    anomaly = score_or_error(npi, request.app.state.driver)
    return {
        "case": case.model_dump(mode="json"),
        "case_score": score.model_dump(mode="json"),
        "priority_tier_approximate": approximate,
        "priority_tier_approximation_note": (
            _PRIORITY_TIER_APPROXIMATE_NOTE if approximate else _PRIORITY_TIER_EXACT_NOTE
        ),
        "anomaly_score": anomaly.model_dump(mode="json"),
    }
