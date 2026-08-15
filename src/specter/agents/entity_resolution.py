"""Entity Resolution Agent (plan §9.3) — T1 `adjudicate_entity_match`.

Adjudicates one candidate pair at a time: `tools/entity_tools.propose_entity_matches`
computes deterministic FEATURES (name similarity, shared address/phone/officer);
this agent turns those features into a match decision. Bias conservative — a
false merge (`auto_link` on a non-match) is far more damaging than a missed
match, and the instruction brief says so explicitly, not just this docstring.
"""

from __future__ import annotations

from pathlib import Path

import structlog
from neo4j import Driver

from specter.agents._base import AgentRuntime, build_agent, run_agent
from specter.core.contracts import (
    AgentRunResult,
    EntityMatchAdjudication,
    EvidenceBundle,
    ScreeningThresholds,
)
from specter.core.errors import SpecterError
from specter.tools import entity_tools
from specter.tools.bindings import build_tool_bindings

logger = structlog.get_logger(__name__)

AGENT_NAME = "entity_resolution"
TASK_CLASS = "adjudicate_entity_match"
INSTRUCTION_FILE = "entity_resolution.md"

_TOOL_NAMES = {"propose_entity_matches", "name_similarity"}

_TASK_INSTRUCTION = (
    "Adjudicate whether npi and candidate_npi in the evidence below are the same "
    "underlying entity. Use only the matching_features/conflicting_features you "
    "can support from the proposal; match_probability and decision are your "
    "judgment, but every other field must be grounded in the evidence."
)


class NoMatchProposalError(SpecterError):
    """`propose_entity_matches` returned nothing for this pair — usually
    because one of the two NPIs doesn't exist in the graph. Adjudicating a
    pair the deterministic tool couldn't even compute features for would be
    exactly the kind of ungrounded claim hard rule 1 exists to prevent.
    """


def build_evidence(driver: Driver, npi: str, candidate_npi: str) -> EvidenceBundle:
    proposals = entity_tools.propose_entity_matches(driver, npi, [candidate_npi])
    if not proposals:
        raise NoMatchProposalError(f"no match proposal for {npi} vs {candidate_npi}")
    proposal = proposals[0]

    shared = ("shares_address", "shares_phone", "shares_officer")
    matching = [f for f in shared if getattr(proposal, f)]
    return EvidenceBundle(
        provider_npi=npi,
        evidence={"proposal": proposal.model_dump(mode="json"), "features_present": matching},
        task_instruction=_TASK_INSTRUCTION,
    )


async def adjudicate(
    driver: Driver,
    npi: str,
    candidate_npi: str,
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
        output_schema=EntityMatchAdjudication,
        runtime=runtime,
    )
    evidence = build_evidence(driver, npi, candidate_npi)
    logger.info("entity_resolution.adjudicating", npi=npi, candidate_npi=candidate_npi)
    return await run_agent(agent, TASK_CLASS, evidence, runtime, EntityMatchAdjudication)
