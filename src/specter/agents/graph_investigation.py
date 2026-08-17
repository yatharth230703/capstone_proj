"""Graph Investigation Agent (plan §9.4) — T1 `narrate_graph_signal`.

The first agent that reasons over evidence rather than gating (`data_quality`)
or summarizing (`community_summarizer`). It narrates what the deterministic
signal detectors and `GraphRetriever.hybrid()` already found — it does not
recompute any of it (CLAUDE.md hard rule 1).

`GraphRetriever` is not wrapped as a model-facing tool binding (M2 left this
undecided). This agent takes the Python-side pre-fetch path recommended in
BUILD_MILESTONES.md M3: `hybrid()` runs once before the agent call and its
result goes straight into the evidence bundle, the same pattern
`data_quality.build_evidence` already uses. That keeps hard rule 1
structurally true here too — there is a query, but not a *choice* of when to
run it.

**Numeric grounding.** CLAUDE.md hard rule 1 requires this enforced in
`after_model_callback`. `agents/_base.py`'s callback slot is reserved for
shared telemetry (prefix-fingerprint check, token counters) and isn't
pluggable per agent, so the check here is a functionally equivalent
post-hoc pass in `investigate()`: extract every numeric literal from
`narration`/`community_context` via regex, assert each appears in the
evidence bundle already gathered for this call, quote violations back and
retry once, raise on a second violation. The generic extract/compare logic
lives in `agents/_grounding.py` (M5, shared with `case_reporter.py` —
BUILD_MILESTONES.md debt D-14); this module keeps only the
`narration`/`community_context`-specific wrapper and the retry loop.
`judge/deterministic_checks.py` (M9) will do the authoritative version of
this same check.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from neo4j import Driver

from specter.agents._base import AgentRuntime, build_agent, run_agent
from specter.agents._grounding import numeric_violations as _generic_numeric_violations
from specter.core.contracts import (
    AgentRunResult,
    EvidenceBundle,
    GraphFindings,
    ScreeningThresholds,
)
from specter.core.errors import SpecterError
from specter.graph.retrieval import GraphRetriever
from specter.tools import graph_tools, signal_tools
from specter.tools.bindings import build_tool_bindings

logger = structlog.get_logger(__name__)

AGENT_NAME = "graph_investigation"
TASK_CLASS = "narrate_graph_signal"
INSTRUCTION_FILE = "graph_investigation.md"

_GRAPH_TOOL_NAMES = {
    "get_provider_profile",
    "expand_neighborhood",
    "find_shared_attribute_peers",
    "shortest_path_to_exclusion",
    "get_community_context",
    "search_enforcement_cases",
}
_SIGNAL_TOOL_NAMES = {
    "address_degree",
    "phone_degree",
    "officer_degree",
    "enumeration_burst",
    "address_churn",
    "exclusion_proximity",
    "community_exclusion_density",
    "geographic_spread",
    "phoenix_pattern",
    "physical_existence",
}
_TOOL_NAMES = _GRAPH_TOOL_NAMES | _SIGNAL_TOOL_NAMES

_SIGNAL_DETECTORS = (
    signal_tools.address_degree,
    signal_tools.phone_degree,
    signal_tools.officer_degree,
    signal_tools.enumeration_burst,
    signal_tools.address_churn,
    signal_tools.exclusion_proximity,
    signal_tools.community_exclusion_density,
    signal_tools.geographic_spread,
    signal_tools.phoenix_pattern,
    signal_tools.physical_existence,
)

_TASK_INSTRUCTION = (
    "Narrate the investigation evidence below for this provider: what the "
    "fired signals mean together, what the community context adds, and which "
    "linked entities matter. Every number in your narration and "
    "community_context must be quoted exactly from the evidence — do not "
    "compute, round, or convert any number yourself."
)

class NumericGroundingError(SpecterError):
    """A number in `narration`/`community_context` never appeared anywhere in
    the evidence bundle this call was given — CLAUDE.md hard rule 1. Raised
    after one corrective retry already failed to fix it.
    """


def build_evidence(driver: Driver, npi: str, thresholds: ScreeningThresholds) -> EvidenceBundle:
    retriever = GraphRetriever(driver)
    hybrid = retriever.hybrid(npi, "shell provider pattern shared attributes exclusion proximity")

    signals = [d(driver, npi, thresholds) for d in _SIGNAL_DETECTORS]
    fired = [s.model_dump(mode="json") for s in signals if s is not None]

    community = graph_tools.get_community_context(driver, npi)

    evidence = {
        "hybrid_search": hybrid.model_dump(mode="json"),
        "fired_signals": fired,
        "community": community.model_dump(mode="json") if community else None,
    }
    return EvidenceBundle(provider_npi=npi, evidence=evidence, task_instruction=_TASK_INSTRUCTION)


def _numeric_violations(output: dict[str, object], evidence: dict[str, object]) -> list[str]:
    return _generic_numeric_violations(
        [str(output["narration"]), str(output["community_context"])], evidence
    )


async def investigate(
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
        output_schema=GraphFindings,
        runtime=runtime,
    )
    evidence = build_evidence(driver, npi, thresholds)
    logger.info("graph_investigation.investigating", npi=npi)
    result = await run_agent(agent, TASK_CLASS, evidence, runtime, GraphFindings)

    violations = _numeric_violations(result.output, evidence.evidence)
    if not violations:
        return result

    logger.warning("graph_investigation.numeric_violation", npi=npi, violations=violations)
    retry_evidence = EvidenceBundle(
        provider_npi=npi,
        evidence=evidence.evidence,
        task_instruction=(
            f"{_TASK_INSTRUCTION}\n\nYour previous answer used numbers not present in the "
            f"evidence: {violations}. Quote numbers exactly from the evidence provided; do "
            "not compute, round, or convert any number yourself."
        ),
    )
    result = await run_agent(agent, TASK_CLASS, retry_evidence, runtime, GraphFindings)
    violations = _numeric_violations(result.output, evidence.evidence)
    if violations:
        raise NumericGroundingError(
            f"{npi}: narration/community_context still cites ungrounded numbers "
            f"after one retry: {violations}"
        )
    return result
