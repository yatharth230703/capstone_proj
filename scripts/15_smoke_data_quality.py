#!/usr/bin/env python
"""Live smoke test for the agent foundation (BUILD_MILESTONES.md M1).

    python scripts/15_smoke_data_quality.py          # run twice to see the L1 cache
    SPECTER_CACHE_ENABLED=false python scripts/15_smoke_data_quality.py

Runs the Data Quality Agent against the frozen snapshot and prints its
verdict plus the cache telemetry. The second invocation should report
`cache_layer=L1`; with the cache disabled it should instead report a non-zero
`cached_tokens`, which is the Azure prefix cache rather than our own.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from specter.agents._base import build_runtime
from specter.agents.data_quality import assess
from specter.settings import get_settings

_REPO_ROOT = Path(__file__).resolve().parent.parent


async def main() -> None:
    settings = get_settings()
    runtime = build_runtime(
        run_id="smoke",
        repo_root=_REPO_ROOT,
        graph_version="m1-smoke",
        settings=settings,
    )
    result = await assess(_REPO_ROOT / "data" / "snapshot", runtime)

    print(f"agent            : {result.agent} ({result.task_class} -> {result.tier})")
    print(f"model            : {result.model}")
    print(f"cache_layer      : {result.cache_layer.value}")
    print(f"prompt tokens    : {result.prompt_tokens}")
    print(f"cached tokens    : {result.cached_tokens}")
    print(f"completion tokens: {result.completion_tokens}")
    if result.prompt_tokens:
        pct = 100 * result.cached_tokens / result.prompt_tokens
        print(f"prefix cache hit : {pct:.0f}%")
    print(f"latency_ms       : {result.latency_ms:.0f}")
    print(f"prefix           : {result.prefix_fingerprint[:16]}...")
    print()
    print(f"VERDICT: {result.output['verdict']}")
    for source in result.output["per_source"]:
        print(f"  {source['source_id']:24} {source['verdict']:5} {source['freshness_status']}")
    if result.output["blocking_reasons"]:
        print("blocking_reasons:")
        print(json.dumps(result.output["blocking_reasons"], indent=2))
    print(f"recommended_action: {result.output['recommended_action']}")


if __name__ == "__main__":
    asyncio.run(main())
