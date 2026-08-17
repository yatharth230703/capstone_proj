#!/usr/bin/env python
"""Judge subsystem entry point (BUILD_MILESTONES.md M9, plan §12).

    python scripts/50_judge.py

Builds a case corpus (the 2 real `data/cases/*.json` packets, plus one fresh
`CasePacket` per synthetic scenario S01-S10 via the M5 agent chain — see
`scripts/48_smoke_judgement_agents.py`, the proven pattern this adapts),
runs the deterministic checks, the rubric judge (3 samples/case + the 10
calibration fixtures), detection_eval, and writes `JudgeReport.md` at the
repo root. Real Azure calls — costs money, run by hand.

Fails loudly and immediately (CLAUDE.md hard rule 7) if the Azure key is
dead — this is not caught and downgraded to a partial report; a judge
subsystem that silently produces a report without judging is worse than one
that doesn't run.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
from neo4j import Driver, GraphDatabase

from specter.agents._base import AgentRuntime, build_runtime
from specter.agents.case_reporter import synthesize
from specter.agents.enforcement_intel import extract
from specter.agents.graph_investigation import investigate
from specter.agents.skeptic import challenge
from specter.core.contracts import CasePacket
from specter.core.errors import SpecterError
from specter.judge import calibration_fixtures, detection_eval, deterministic_checks, report
from specter.judge.rubric_judge import deterministic_vs_llm_disagreement, judge_case
from specter.settings import get_settings

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCENARIO_NPIS = {
    "S01": "9010000000", "S02": "9020000000", "S03": "9030000000", "S04": "9040000000",
    # S06: "9060000000" is _npi(6, 0), the EXCLUDED PREDECESSOR org
    # (ingest/synthetic.py's _scenario_06, expected_signals=[]) — the
    # provider that should exhibit phoenix_pattern is the successor,
    # _npi(6, 1) = "9060000001" ("S06 Phoenix Successor Org", confirmed
    # live). A prior session's "verified live" claim for this NPI table was
    # wrong for S06 specifically; found live in M9 when the detection_eval
    # headline showed 7/8 instead of the expected 8/8.
    "S05": "9050000000", "S06": "9060000001", "S07": "9070000000", "S08": "9080000000",
    "S09": "9090000000", "S10": "9100000000",
}
_EXISTING_CASE_NPIS = ["1003001439", "1003008756"]


def _confirm_azure_key_alive(settings) -> None:
    url = settings.azure_api_base.rstrip("/") + "/chat/completions"
    resp = httpx.post(
        url,
        headers={
            "api-key": settings.azure_api_key.get_secret_value(),
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-5.4-nano",
            "messages": [{"role": "user", "content": "ping"}],
            "max_completion_tokens": 5,
        },
        timeout=20,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Azure key check failed ({resp.status_code}): {resp.text[:300]} — "
            "M9 is BLOCKED per BUILD_MILESTONES.md §0.1 rule 5 until this is fixed. "
            "Do not proceed with live judge calls against a dead key."
        )


async def _build_scenario_case(
    scenario_id: str, npi: str, driver: Driver, evidence_dir: Path, runtime: AgentRuntime
) -> CasePacket:
    from specter.tools.signal_tools import load_thresholds

    thresholds = load_thresholds(_REPO_ROOT / "config" / "screening.yaml")
    graph_result = await investigate(driver, npi, thresholds, evidence_dir, runtime)
    enforcement_result = await extract(driver, npi, thresholds, evidence_dir, runtime)
    counter_result = await challenge(npi, graph_result.output, enforcement_result.output, runtime)
    case_packet = await synthesize(
        npi, graph_result.output, enforcement_result.output, counter_result.output,
        driver, evidence_dir, runtime,
    )
    print(f"  {scenario_id} ({npi}): {len(case_packet.signals)} signals fired")
    return case_packet


async def main() -> None:
    settings = get_settings()
    print("Confirming Azure key is live...")
    _confirm_azure_key_alive(settings)
    print("Azure key OK.")

    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value())
    )
    evidence_dir = _REPO_ROOT / "data" / "evidence"
    runtime = build_runtime(
        run_id="m9-judge", repo_root=_REPO_ROOT, graph_version="m9-judge", settings=settings
    )

    print("\n=== Building case corpus ===")
    corpus: dict[str, CasePacket] = {}
    for npi in _EXISTING_CASE_NPIS:
        corpus[npi] = CasePacket.model_validate(
            json.loads((_REPO_ROOT / "data" / "cases" / f"{npi}.json").read_text())
        )
    scenario_cases: dict[str, CasePacket] = {}
    skipped_scenarios: dict[str, str] = {}
    for scenario_id, npi in _SCENARIO_NPIS.items():
        try:
            case = await _build_scenario_case(scenario_id, npi, driver, evidence_dir, runtime)
        except SpecterError as exc:
            # A live-only agent-chain failure (e.g. a genuinely ungrounded
            # number the model produced, caught by graph_investigation's own
            # numeric-grounding retry) must not kill the whole judge run —
            # skip this one scenario, loudly, and keep going. Not a silent
            # fallback: logged, printed, and carried into the report/ledger.
            print(f"  {scenario_id} ({npi}): SKIPPED — {exc}")
            skipped_scenarios[scenario_id] = str(exc)
            continue
        scenario_cases[scenario_id] = case
        corpus[npi] = case
    if skipped_scenarios:
        print(f"\nSkipped {len(skipped_scenarios)} scenario(s) due to live agent-chain "
              f"failures: {sorted(skipped_scenarios)} — see BUILD_MILESTONES.md debt.")

    print("\n=== Deterministic checks ===")
    deterministic_summary: dict[str, dict[str, int]] = {}
    for npi, case in corpus.items():
        citations = deterministic_checks.check_citation_validity(case, driver, evidence_dir)
        numeric = deterministic_checks.check_numeric_grounding(case)
        entities = deterministic_checks.check_entity_existence(case, driver)
        deterministic_summary[npi] = {
            "citations_ok": sum(citations.values()),
            "citations_total": len(citations),
            "numeric_violations": len(numeric),
            "entities_ok": sum(entities.values()),
            "entities_total": len(entities),
        }
        print(f"  {npi}: citations {deterministic_summary[npi]['citations_ok']}/"
              f"{deterministic_summary[npi]['citations_total']}, "
              f"numeric_violations={len(numeric)}, "
              f"entities {deterministic_summary[npi]['entities_ok']}/"
              f"{deterministic_summary[npi]['entities_total']}")

    print("\n=== Rubric judge (3 samples/case) ===")
    judge_verdicts = {}
    disagreements = {}
    for npi, case in corpus.items():
        verdict = await judge_case(case, runtime, settings.specter_judge_sample_count)
        judge_verdicts[npi] = verdict
        disagreements[npi] = deterministic_vs_llm_disagreement(case, verdict, driver, evidence_dir)
        print(f"  {npi}: aggregate={verdict.aggregate_scores}")

    print("\n=== Calibration fixtures (C01-C10) ===")
    calibration_cases = calibration_fixtures.build_calibration_cases()
    calibration_results = []
    for cal_case in calibration_cases:
        verdict = await judge_case(cal_case.case, runtime, settings.specter_judge_sample_count)
        calibration_results.append((cal_case, verdict))
        print(f"  {cal_case.fixture_id}: aggregate={verdict.aggregate_scores}")

    print("\n=== Detection evaluation ===")
    positive_npis = set(detection_eval.real_positive_npis(driver))
    real_total = detection_eval.real_provider_count(driver)
    detection = detection_eval.build_report(
        scenario_cases=scenario_cases,
        real_positive_npis_set=positive_npis,
        real_provider_total=real_total,
        ranked_real_cases=[corpus[npi] for npi in _EXISTING_CASE_NPIS],
        control_cases=[],
    )

    text = report.render_report(
        detection=detection,
        deterministic_summary=deterministic_summary,
        judge_verdicts=judge_verdicts,
        calibration=calibration_results,
        disagreements=disagreements,
        skipped_scenarios=skipped_scenarios,
    )
    (_REPO_ROOT / "JudgeReport.md").write_text(text)
    print("\nJudgeReport.md written.")

    driver.close()


if __name__ == "__main__":
    asyncio.run(main())
