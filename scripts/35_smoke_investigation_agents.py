#!/usr/bin/env python
"""Live smoke test for the M3 investigation agents (BUILD_MILESTONES.md M3).

    python scripts/35_smoke_investigation_agents.py

Runs each of the three new agents once against the live graph and prints
its output plus escalation telemetry. Real Azure calls — costs money, run by
hand, same pattern as scripts/15_smoke_data_quality.py.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from neo4j import GraphDatabase

from specter.agents._base import build_runtime
from specter.agents.enforcement_intel import extract
from specter.agents.entity_resolution import adjudicate
from specter.agents.graph_investigation import investigate
from specter.settings import get_settings
from specter.tools.signal_tools import load_thresholds

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _print_result(label: str, result: object) -> None:
    print(f"\n=== {label} ===")
    print(f"tier={result.tier} model={result.model} escalated={result.escalated}")  # type: ignore[attr-defined]
    print(json.dumps(result.output, indent=2, sort_keys=True))  # type: ignore[attr-defined]


async def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value())
    )
    thresholds = load_thresholds(_REPO_ROOT / "config" / "screening.yaml")
    evidence_dir = _REPO_ROOT / "data" / "evidence"
    runtime = build_runtime(
        run_id="smoke-m3", repo_root=_REPO_ROOT, graph_version="m3-smoke", settings=settings
    )

    # Real NPPES pair: identical organization name, shared address only (no
    # shared phone/officer) — genuinely ambiguous, a real candidate for the
    # adjudicate_entity_match escalation rule (match_probability in [0.45, 0.65]).
    entity_result = await adjudicate(
        driver, "1295159275", "1962276899", thresholds, evidence_dir, runtime
    )
    _print_result("entity_resolution: ACUTE MEDICAL SUPPLY pair", entity_result)

    # S03 address-cluster synthetic scenario — address_degree/enumeration_burst fire.
    graph_result = await investigate(driver, "9030000000", thresholds, evidence_dir, runtime)
    _print_result("graph_investigation: S03 address cluster", graph_result)

    enforcement_result = await extract(driver, "9020000000", thresholds, evidence_dir, runtime)
    _print_result("enforcement_intel: S02 (1-row DOJ corpus, debt D-2)", enforcement_result)

    driver.close()


if __name__ == "__main__":
    asyncio.run(main())
