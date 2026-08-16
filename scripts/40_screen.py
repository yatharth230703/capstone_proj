#!/usr/bin/env python
"""Screening pipeline entry point (BUILD_MILESTONES.md M6, plan §10).

    python scripts/40_screen.py --limit 5

Builds the `Workflow` graph, runs it over the live cohort (`config/
screening.yaml`'s `cohort` block: taxonomy prefix + states), writes one
`CasePacket` per screened provider to `data/cases/<npi>.json`, and prints a
per-provider summary with its `PriorityTier`. `--limit` slices the cohort for
a cheap/demo run — real Azure calls, costs money — the full ~7k-provider
cohort run is deferred to M10 (plan's 250-provider figure). Without
`--limit`, a `data_quality_hold` halt prints and the run stops before any
Azure call for a screened provider.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import yaml
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from neo4j import GraphDatabase

from specter.agents._base import build_runtime
from specter.settings import get_settings
from specter.tools.signal_tools import load_thresholds
from specter.workflow.screening import build_screening_workflow

_REPO_ROOT = Path(__file__).resolve().parent.parent
_APP_NAME = "specter_screening"


async def main(limit: int | None) -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value())
    )
    config_path = _REPO_ROOT / "config" / "screening.yaml"
    thresholds = load_thresholds(config_path)
    screening_config = yaml.safe_load(config_path.read_text())
    runtime = build_runtime(
        run_id="screen", repo_root=_REPO_ROOT, graph_version="m6-screen", settings=settings
    )

    workflow = build_screening_workflow(
        driver=driver,
        runtime=runtime,
        thresholds=thresholds,
        evidence_dir=_REPO_ROOT / "data" / "evidence",
        cases_dir=_REPO_ROOT / "data" / "cases",
        snapshot_dir=_REPO_ROOT / "data" / "snapshot",
        taxonomy_prefix=screening_config["cohort"]["taxonomy_prefix"],
        states=screening_config["cohort"]["states"],
        signal_families=screening_config["signal_families"],
        min_independent_signal_families=screening_config["escalation_gate"][
            "min_independent_signal_families"
        ],
        evidence_freshness_days=screening_config["escalation_gate"]["evidence_freshness_days"],
        cohort_limit=limit,
    )

    session_service = InMemorySessionService()
    await session_service.create_session(app_name=_APP_NAME, user_id="specter", session_id="run")
    runner = Runner(node=workflow, app_name=_APP_NAME, session_service=session_service)

    result: object = None
    try:
        async for event in runner.run_async(
            user_id="specter",
            session_id="run",
            new_message=types.Content(role="user", parts=[types.Part(text="run")]),
        ):
            if event.output is not None:
                result = event.output
    finally:
        await runner.close()

    if isinstance(result, dict) and result.get("status") == "data_quality_hold":
        print(f"HALTED: data_quality_hold — verdict={result['deterministic_verdict']}")
        print(f"blocking_reasons={result['blocking_reasons']}")
        driver.close()
        return

    assert isinstance(result, list), f"expected a list of summaries, got {type(result)}"
    print(f"cohort_size={len(result)}")
    for summary in result:
        score = summary["case_score"]
        print(
            f"  {summary['npi']}: priority_tier={summary['priority_tier']} "
            f"families={score['fired_signal_families']} "
            f"citations_resolved={summary['citation_report_all_resolved']} "
            f"candidate_pairs={summary['candidate_pair_count']}"
        )
    driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="slice the cohort for a cheap run")
    args = parser.parse_args()
    asyncio.run(main(args.limit))
