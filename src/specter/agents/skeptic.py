"""Skeptic Agent (plan §9.7) — T2 `challenge_hypothesis`.

Argues against every signal `graph_investigation`/`enforcement_intel` found.
No tools — it reasons over the findings bundle it's handed, nothing else.
CLAUDE.md hard rule 8: the Skeptic influences the final score only through
`CounterEvidence.confidence_adjustment`, a bounded `[-0.4, 0.0]` discount the
(M6) deterministic `ScoringService` subtracts — it never writes a fact-number
itself.
"""

from __future__ import annotations

from typing import Any

import structlog

from specter.agents._base import AgentRuntime, build_agent, run_agent
from specter.core.contracts import AgentRunResult, CounterEvidence, EvidenceBundle
from specter.core.errors import SpecterError

logger = structlog.get_logger(__name__)

AGENT_NAME = "skeptic"
TASK_CLASS = "challenge_hypothesis"
INSTRUCTION_FILE = "skeptic.md"

_TASK_INSTRUCTION = (
    "Argue against every signal in fired_signals below. Produce exactly one "
    "Rebuttal per signal_type present — either a concrete benign explanation, "
    "or no_plausible_benign_explanation=true with reasoning why none applies. "
    "Do not skip a signal or invent one that isn't present. "
    "confidence_adjustment is your overall judgment of how much the benign "
    "explanations you found weaken the case as a whole; it must be between "
    "-0.4 and 0.0."
)


class MissingRebuttalError(SpecterError):
    """`per_signal` didn't cover every `signal_type` present in the input
    findings — a silently dropped signal is exactly the failure mode this
    agent exists to prevent (plan §9.7: "must produce at least one benign
    explanation per signal").
    """


def build_evidence(
    npi: str, graph_findings: dict[str, Any], enforcement_findings: dict[str, Any]
) -> EvidenceBundle:
    evidence = {
        "fired_signals": graph_findings.get("signals", []),
        "narration": graph_findings.get("narration"),
        "community_context": graph_findings.get("community_context"),
        "enforcement_matches": enforcement_findings.get("matches", []),
        "enforcement_typologies": enforcement_findings.get("typologies", []),
    }
    return EvidenceBundle(provider_npi=npi, evidence=evidence, task_instruction=_TASK_INSTRUCTION)


async def challenge(
    npi: str,
    graph_findings: dict[str, Any],
    enforcement_findings: dict[str, Any],
    runtime: AgentRuntime,
) -> AgentRunResult:
    agent = build_agent(
        name=AGENT_NAME,
        task_class=TASK_CLASS,
        instruction_file=INSTRUCTION_FILE,
        tools=[],
        output_schema=CounterEvidence,
        runtime=runtime,
    )
    evidence = build_evidence(npi, graph_findings, enforcement_findings)
    logger.info("skeptic.challenging", npi=npi)
    result = await run_agent(agent, TASK_CLASS, evidence, runtime, CounterEvidence)

    expected = {signal["signal_type"] for signal in evidence.evidence["fired_signals"]}
    rebutted = {rebuttal["signal_type"] for rebuttal in result.output["per_signal"]}
    missing = expected - rebutted
    if missing:
        raise MissingRebuttalError(f"{npi}: no rebuttal for signal_type(s) {sorted(missing)}")
    return result
