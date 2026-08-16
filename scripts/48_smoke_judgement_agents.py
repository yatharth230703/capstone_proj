#!/usr/bin/env python
"""Live smoke test for the M5 judgement agents (BUILD_MILESTONES.md M5).

    python scripts/48_smoke_judgement_agents.py

Runs `graph_investigation` + `enforcement_intel` on the S03 synthetic
scenario (same NPI M3's own smoke script uses), feeds the result into
`skeptic`, then `case_reporter`, and prints the assembled `CasePacket`.
Real Azure calls — costs money, run by hand, same pattern as
scripts/35_smoke_investigation_agents.py.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from neo4j import GraphDatabase

from specter.agents._base import build_runtime
from specter.agents.case_reporter import synthesize
from specter.agents.enforcement_intel import extract
from specter.agents.graph_investigation import investigate
from specter.agents.skeptic import challenge
from specter.core.banned_vocabulary import find_banned_phrases
from specter.settings import get_settings
from specter.tools.signal_tools import load_thresholds

_REPO_ROOT = Path(__file__).resolve().parent.parent
_NPI = "9030000000"  # S03 address-cluster synthetic scenario


async def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value())
    )
    thresholds = load_thresholds(_REPO_ROOT / "config" / "screening.yaml")
    evidence_dir = _REPO_ROOT / "data" / "evidence"
    runtime = build_runtime(
        run_id="smoke-m5", repo_root=_REPO_ROOT, graph_version="m5-smoke", settings=settings
    )

    graph_result = await investigate(driver, _NPI, thresholds, evidence_dir, runtime)
    print("\n=== graph_investigation ===")
    print(json.dumps(graph_result.output, indent=2, sort_keys=True))

    enforcement_result = await extract(driver, _NPI, thresholds, evidence_dir, runtime)
    print("\n=== enforcement_intel ===")
    print(json.dumps(enforcement_result.output, indent=2, sort_keys=True))

    counter_result = await challenge(
        _NPI, graph_result.output, enforcement_result.output, runtime
    )
    print("\n=== skeptic ===")
    print(json.dumps(counter_result.output, indent=2, sort_keys=True))
    assert len(counter_result.output["per_signal"]) == len(graph_result.output["signals"]), (
        "skeptic must rebut every fired signal"
    )

    case_packet = await synthesize(
        _NPI,
        graph_result.output,
        enforcement_result.output,
        counter_result.output,
        driver,
        evidence_dir,
        runtime,
    )
    print("\n=== case_reporter: CasePacket ===")
    print(case_packet.model_dump_json(indent=2))
    assert case_packet.citation_report.all_resolved, "unresolved citations in the case packet"
    assert find_banned_phrases(case_packet.narrative) == [], "banned phrase leaked into narrative"

    driver.close()


if __name__ == "__main__":
    asyncio.run(main())
