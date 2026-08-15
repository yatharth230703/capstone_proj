"""Enforcement Intelligence Agent (plan §9.5) — T1 `extract_enforcement_case`.

Matches a provider to candidate enforcement cases found by
`tools/graph_tools.search_enforcement_cases` (deterministic keyword search)
and adjudicates `legal_status` per match — replacing the regex-heuristic
`legal_status` `graph/enforcement_loader.infer_legal_status` stamped onto
`EnforcementCase` nodes at load time (debt D-10). Runs against a 1-row DOJ
corpus today (debt D-2, refilled in M7 via Playwright MCP) — that is a real
data gap, not a bug in this agent.

Out of scope here (plan §9.5 mentions both, neither exists yet): SAM.gov
(removed by CLAUDE.md Amendment 1) and live web search via Playwright MCP
(M7). This agent only searches the stored corpus.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from neo4j import Driver

from specter.agents._base import AgentRuntime, build_agent, run_agent
from specter.core.contracts import (
    AgentRunResult,
    EnforcementFindings,
    EvidenceBundle,
    ScreeningThresholds,
)
from specter.tools import graph_tools
from specter.tools.bindings import build_tool_bindings

logger = structlog.get_logger(__name__)

AGENT_NAME = "enforcement_intel"
TASK_CLASS = "extract_enforcement_case"
INSTRUCTION_FILE = "enforcement_intel.md"

_TOOL_NAMES = {"search_enforcement_cases"}

_TASK_INSTRUCTION = (
    "Decide whether any of the candidate enforcement cases below actually "
    "involve this provider. A case_id only belongs in matches if the "
    "evidence supports a real link (shared exact identifier, or the case "
    "text itself names this provider unambiguously) and its legal_status is "
    "adjudicated from what the case text actually says. Anything resting on "
    "a name match alone goes in disambiguation_flags, never matches."
)


def build_evidence(driver: Driver, npi: str) -> EvidenceBundle:
    profile = graph_tools.get_provider_profile(driver, npi)
    query_parts = []
    if profile is not None:
        if profile.organization_name:
            query_parts.append(profile.organization_name)
        if profile.state:
            query_parts.append(profile.state)
    query = " ".join(query_parts) or npi

    hits = graph_tools.search_enforcement_cases(driver, query, k=10)
    evidence = {
        "search_query": query,
        "profile": profile.model_dump(mode="json") if profile else None,
        "case_hits": [hit.model_dump(mode="json") for hit in hits],
    }
    return EvidenceBundle(provider_npi=npi, evidence=evidence, task_instruction=_TASK_INSTRUCTION)


async def extract(
    driver: Driver,
    npi: str,
    thresholds: ScreeningThresholds,
    evidence_dir: Path,
    runtime: AgentRuntime,
) -> AgentRunResult:
    all_tools = build_tool_bindings(driver, thresholds, evidence_dir)
    tools = [tool for tool in all_tools if tool.__name__ in _TOOL_NAMES]

    agent = build_agent(
        name=AGENT_NAME,
        task_class=TASK_CLASS,
        instruction_file=INSTRUCTION_FILE,
        tools=tools,
        output_schema=EnforcementFindings,
        runtime=runtime,
    )
    evidence = build_evidence(driver, npi)
    logger.info("enforcement_intel.extracting", npi=npi, query=evidence.evidence["search_query"])
    return await run_agent(agent, TASK_CLASS, evidence, runtime, EnforcementFindings)
