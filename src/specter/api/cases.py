"""Cohort overview + per-case detail endpoints (M13). Reads the real,
already-screened `data/cases/*.json` `CasePacket`s — no new screening
happens here (CLAUDE.md Amendment 4(a)).

**Debt D-23 — `CaseScore`/`priority_tier` is never persisted**
(`workflow/screening.py:175` writes only the `CasePacket`; `case_score` is
computed, printed, and discarded). Per M13's Action Plan point 4, option
(b): recomputed here via the same `workflow.state.ScoringService` the
screening run itself used, with `entity_adjudications=[]` — the one input
`ScoringService.score` needs that was never persisted anywhere for a
completed case. Every *other* input is fully persisted and this recompute
uses it exactly: `signals`, `enforcement_matches`/`legal_status_per_match`,
and the Skeptic's `confidence_adjustment` (`CasePacket.counter_evidence`).
So the recomputed `identity_integrity` dimension — and only that one — is an
approximation (it assumes zero unresolved entity-match conflicts). Every
response says so explicitly via `priority_tier_approximate: true`. Do not
present this as the exact score `scripts/40_screen.py` computed live.
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

_PRIORITY_TIER_APPROXIMATION_NOTE = (
    "priority_tier recomputed from the persisted CasePacket without "
    "entity_adjudications (BUILD_MILESTONES.md debt D-23 — not persisted by "
    "the screening run); identity_integrity assumes zero unresolved "
    "entity-match conflicts and may differ from the score the live "
    "screening run actually computed"
)


def _require_cases() -> list[Path]:
    if not CASES_DIR.exists():
        raise SpecterError(
            f"{CASES_DIR} is missing — it's a gitignored run artifact. Run "
            "`python scripts/40_screen.py` to populate it (real Azure calls)."
        )
    paths = sorted(CASES_DIR.glob("*.json"))
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
    for path in paths:
        case = _load_case(path)
        if case.signals:
            cases_with_fired_signals += 1
        for signal in case.signals:
            signal_type_counts[signal.signal_type] = (
                signal_type_counts.get(signal.signal_type, 0) + 1
            )
        score = _approximate_score(case, scoring)
        tier_counts[score.priority_tier.value] += 1
        cases.append(
            {
                "npi": case.provider_npi,
                "priority_tier": score.priority_tier.value,
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
        "priority_tier_approximate": True,
        "priority_tier_approximation_note": _PRIORITY_TIER_APPROXIMATION_NOTE,
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
    score = _approximate_score(case, scoring)
    anomaly = score_or_error(npi, request.app.state.driver)
    return {
        "case": case.model_dump(mode="json"),
        "case_score": score.model_dump(mode="json"),
        "priority_tier_approximate": True,
        "priority_tier_approximation_note": _PRIORITY_TIER_APPROXIMATION_NOTE,
        "anomaly_score": anomaly.model_dump(mode="json"),
    }
