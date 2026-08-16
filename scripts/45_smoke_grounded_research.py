#!/usr/bin/env python
"""Live smoke test for the M4 Grounded Research Agent (BUILD_MILESTONES.md M4).

    python scripts/45_smoke_grounded_research.py

Runs one real query against Vertex Gemini + `google_search` and prints the
narrative plus every `EvidenceArtifact` extracted from `grounding_metadata`.
Costs real Vertex tokens — run by hand, same pattern as
`scripts/15_smoke_data_quality.py` and `scripts/35_smoke_investigation_agents.py`.

An empty citation list on a real grounded response means the isolation
pattern or `propagate_grounding_metadata` broke silently (D10/D15) — this
script raises rather than reporting success in that case.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from specter.agents.grounded_research import (
    build_grounded_research_agent,
    build_grounded_research_tool,
    research_topic,
)
from specter.llm.router import ModelRouter, load_policy
from specter.settings import get_settings

_REPO_ROOT = Path(__file__).resolve().parent.parent

_QUERY = (
    "What durable medical equipment fraud enforcement actions has the "
    "HHS Office of Inspector General announced in Florida in the last year?"
)


async def main() -> None:
    settings = get_settings()
    policy = load_policy(_REPO_ROOT / "config" / "models.yaml", settings)
    router = ModelRouter(policy, settings=settings)

    agent = build_grounded_research_agent(router, settings)
    print(f"agent tools: {[type(t).__name__ for t in agent.tools]}")
    assert len(agent.tools) == 1, "isolation broken: more than one tool on GroundedResearchAgent"

    # Constructed to prove the consumer-facing wiring exists (Definition of
    # Done), even though this script calls the agent directly below rather
    # than through a consumer's tool call.
    tool = build_grounded_research_tool(agent)
    print(f"AgentTool propagate_grounding_metadata={tool.propagate_grounding_metadata}")

    result = await research_topic(_QUERY, agent, _REPO_ROOT / "data" / "evidence")

    print(f"\nmodel: {result.model}")
    print(f"query: {result.query}")
    print(f"\nnarrative:\n{result.narrative}\n")
    print(f"citations: {len(result.citations)}")
    for artifact in result.citations:
        print(
            f"  [{artifact.extraction_method}] {artifact.artifact_id[:12]}  {artifact.stored_path}"
        )

    if not result.citations:
        raise RuntimeError(
            "live grounded query produced zero EvidenceArtifacts — grounding_metadata "
            "propagation is broken (see D10/D15 in NOTES_API_DEVIATIONS.md)"
        )


if __name__ == "__main__":
    asyncio.run(main())
