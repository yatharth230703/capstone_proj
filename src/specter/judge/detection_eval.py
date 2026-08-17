"""Deterministic detection evaluation (plan §12.1, M9) — no LLM. Two
evaluable ground-truth sets, both plainly small (BUILD_MILESTONES.md debt
D-21): 4 real non-synthetic providers with a direct `EXCLUDED_BY` edge out of
8,445 real providers loaded, and 10 synthetic scenarios with known
`expected_signals`.

Per plan §12.1's own instruction, **per-scenario recall is the headline
number**, not the thin real-positive precision figure — both are reported,
but the real-positive denominator is always stated alongside it.
"""

from __future__ import annotations

from neo4j import Driver

from specter.core.contracts import CasePacket, DetectionEvalReport, ScenarioRecallResult

# ingest/synthetic.py's _scenario_01..._scenario_10 (verified live pre-M9) —
# design-time knowledge, not loaded from the graph (Provider nodes carry
# `scenario_id` but not `expected_signals`).
#
# M11 update: S01 is no longer detector-less. The Maps address-type classifier
# CLAUDE.md Amendment 3 deferred now exists (`physical_existence`), and S01's
# five providers were moved onto real residential streets so it can see them
# (BUILD_MILESTONES.md D-26, operator-approved). Verified live 2026-08-18: all
# five classify `residential` with 0 establishments within 50m and fire
# `physical_existence` and nothing else. **S08 is still genuinely
# detector-less** — Phase 1 has no utilization data — and must stay `[]`.
SCENARIO_EXPECTED_SIGNALS: dict[str, list[str]] = {
    "S01": ["physical_existence"],
    "S02": ["phone_degree"],
    "S03": ["address_degree", "enumeration_burst"],
    "S04": ["officer_degree"],
    "S05": ["exclusion_proximity"],
    "S06": ["phoenix_pattern"],
    "S07": ["address_churn"],
    "S08": [],
    "S09": ["geographic_spread"],
    "S10": ["community_exclusion_density"],
}

_K_VALUES = (10, 25, 50)


def scenario_recall(scenario_id: str, case: CasePacket | None) -> ScenarioRecallResult:
    expected = SCENARIO_EXPECTED_SIGNALS[scenario_id]
    fired = [s.signal_type for s in case.signals] if case is not None else []
    detector_exists = bool(expected)
    hit = True if not detector_exists else bool(set(expected) & set(fired))
    return ScenarioRecallResult(
        scenario_id=scenario_id,
        expected_signals=expected,
        fired_signal_types=fired,
        detector_exists=detector_exists,
        recall_hit=hit,
    )


def real_positive_npis(driver: Driver) -> list[str]:
    """NPIs of real (non-synthetic) `Provider` nodes carrying a direct
    `EXCLUDED_BY` edge — BUILD_MILESTONES.md debt D-21: 4 as of M8, out of
    8,445 real providers loaded.
    """
    query = (
        "MATCH (p:Provider {data_origin: 'public'})-[:EXCLUDED_BY]->() "
        "RETURN DISTINCT p.npi AS npi ORDER BY npi"
    )
    with driver.session() as session:
        return [record["npi"] for record in session.run(query)]


def real_provider_count(driver: Driver) -> int:
    with driver.session() as session:
        record = session.run(
            "MATCH (p:Provider {data_origin: 'public'}) RETURN count(p) AS n"
        ).single()
        return int(record["n"]) if record else 0


def _score(case: CasePacket) -> float:
    """Ranking proxy: `len(signals)` — `workflow.state.ScoringService` isn't
    wired into this evaluation (plan allows either; simpler proxy stated
    plainly per the M9 Action Plan)."""
    return float(len(case.signals))


def precision_at_k(
    positive_npis: set[str], ranked_cases: list[CasePacket]
) -> dict[str, float]:
    ranked = sorted(ranked_cases, key=_score, reverse=True)
    result: dict[str, float] = {}
    for k in _K_VALUES:
        top_k = ranked[:k]
        if not top_k:
            result[str(k)] = 0.0
            continue
        hits = sum(1 for case in top_k if case.provider_npi in positive_npis)
        result[str(k)] = hits / len(top_k)
    return result


def false_positive_rate(control_cases: list[CasePacket], fired_threshold: int = 1) -> float | None:
    """Fraction of benign-control cases (synthetic, no `scenario_id`, no
    expected signal) that fired at least `fired_threshold` signals anyway.
    `None` if no control cases were supplied.
    """
    if not control_cases:
        return None
    flagged = sum(1 for case in control_cases if len(case.signals) >= fired_threshold)
    return flagged / len(control_cases)


def build_report(
    *,
    scenario_cases: dict[str, CasePacket | None],
    real_positive_npis_set: set[str],
    real_provider_total: int,
    ranked_real_cases: list[CasePacket],
    control_cases: list[CasePacket],
) -> DetectionEvalReport:
    scenario_results = [
        scenario_recall(scenario_id, scenario_cases.get(scenario_id))
        for scenario_id in sorted(SCENARIO_EXPECTED_SIGNALS)
    ]
    return DetectionEvalReport(
        precision_at_k=precision_at_k(real_positive_npis_set, ranked_real_cases),
        scenario_recall=scenario_results,
        real_positive_count=len(real_positive_npis_set),
        real_positive_denominator=real_provider_total,
        ranking_method="signal_count_proxy",
        false_positive_rate=false_positive_rate(control_cases),
    )
