"""The screening pipeline (plan §10, M6) as an ADK 2.x `Workflow` graph —
the root, never an `LlmAgent` sub-agent (NOTES_API_DEVIATIONS.md D9).

    START -> data_quality_gate -> {FAIL: halt_node, DEFAULT_ROUTE: cohort_select_node}
    cohort_select_node -> screen_provider (parallel_worker, max_parallel_workers=4)

**Deviation from plan §10's pseudocode, deliberate.** The plan draws
`entity_resolution`, `graph_investigation`, `enforcement_intel` as three
separate fan-out boxes after `cohort_select`, then a `fan_in` before
`skeptic`/`score`/`case_reporter`. `google.adk.workflow`'s `max_parallel_workers`
is a per-node cap, not a graph-wide one (confirmed against ADK 2.6.2 source):
three separate fan-out nodes each capped at 4, running concurrently off the
same `cohort_select_node` output, would allow up to 12 simultaneous Azure
calls — CLAUDE.md's "concurrency capped at 4 parallel providers" is a hard
cap on the whole system, not per stage. `screen_provider` runs
entity_resolution (over this provider's own candidate pairs), graph_
investigation, enforcement_intel, skeptic, score, and case_reporter
*sequentially* inside one node body, one Azure call in flight at a time; the
fan-out over providers is what `max_parallel_workers=4` bounds, so at most 4
providers — and therefore at most 4 Azure calls — run at once, system-wide.
The M8 dashboard reads the cost ledger by `agent` name, not by graph node, so
this collapse costs nothing in per-agent-type observability.

**Fail-fast is deliberate, not a gap.** `_ParallelWorker`'s fan-out cancels
every in-flight provider the moment one raises. CLAUDE.md hard rule 7 ("fail
loudly... bad data halts the run") is exactly this behavior — a provider
whose case would come out fabricated or citation-broken should stop the run
visibly, not get silently dropped from a big batch. `screen_provider` catches
nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from google.adk.agents.context import Context
from google.adk.workflow import DEFAULT_ROUTE, Workflow, node
from neo4j import Driver

from specter.agents._base import AgentRuntime
from specter.agents.case_reporter import synthesize
from specter.agents.data_quality import assess, build_evidence, deterministic_verdict
from specter.agents.enforcement_intel import extract
from specter.agents.entity_resolution import adjudicate
from specter.agents.graph_investigation import investigate
from specter.agents.skeptic import challenge
from specter.core.contracts import ScreeningThresholds
from specter.core.enums import Verdict
from specter.workflow.state import ScoringService, build_candidate_pairs, cohort_select

logger = structlog.get_logger(__name__)

_STATUS_HALTED = "data_quality_hold"


def build_screening_workflow(
    *,
    driver: Driver,
    runtime: AgentRuntime,
    thresholds: ScreeningThresholds,
    evidence_dir: Path,
    cases_dir: Path,
    snapshot_dir: Path,
    taxonomy_prefix: str,
    states: list[str],
    signal_families: dict[str, list[str]],
    min_independent_signal_families: int,
    evidence_freshness_days: int,
    cohort_limit: int | None = None,
    max_parallel_providers: int = 4,
) -> Workflow:
    """Build the graph. Every closure below captures `driver`/`runtime`/
    `thresholds`/`evidence_dir` directly — infra objects don't belong in ADK's
    JSON-shaped session state, so they're bound at construction time instead
    (confirmed against ADK 2.6.2 source: `node_input` is the only param the
    framework passes through in-process; everything else is a state lookup).
    """
    cases_dir.mkdir(parents=True, exist_ok=True)
    scoring_service = ScoringService(
        signal_families=signal_families,
        min_independent_signal_families=min_independent_signal_families,
        evidence_freshness_days=evidence_freshness_days,
    )

    async def data_quality_gate(ctx: Context, node_input: str) -> dict[str, Any]:
        result = await assess(snapshot_dir, runtime)
        evidence = build_evidence(snapshot_dir)
        verdict = deterministic_verdict(evidence.evidence["sources"], evidence_freshness_days)
        logger.info(
            "screening.data_quality_gate",
            deterministic_verdict=verdict.value,
            llm_verdict=result.output["verdict"],
            blocking_reasons=result.output["blocking_reasons"],
        )
        ctx.route = verdict.value
        return {
            "status": _STATUS_HALTED,
            "deterministic_verdict": verdict.value,
            "blocking_reasons": result.output["blocking_reasons"],
        }

    async def halt_node(ctx: Context, node_input: dict[str, Any]) -> dict[str, Any]:
        logger.warning("screening.halted", **node_input)
        return node_input

    async def cohort_select_node(ctx: Context, node_input: dict[str, Any]) -> list[str]:
        npis = cohort_select(driver, taxonomy_prefix, states, cohort_limit)
        logger.info("screening.cohort_selected", cohort_size=len(npis), limit=cohort_limit)
        return npis

    @node(parallel_worker=True, max_parallel_workers=max_parallel_providers)
    async def screen_provider(ctx: Context, node_input: str) -> dict[str, Any]:
        npi = node_input

        pairs = build_candidate_pairs(driver, [npi])
        entity_adjudications: list[dict[str, Any]] = []
        for _, candidate_npi in pairs:
            result = await adjudicate(driver, npi, candidate_npi, thresholds, evidence_dir, runtime)
            entity_adjudications.append(result.output)

        graph_result = await investigate(driver, npi, thresholds, evidence_dir, runtime)
        enforcement_result = await extract(driver, npi, thresholds, evidence_dir, runtime)

        counter_result = await challenge(
            npi, graph_result.output, enforcement_result.output, runtime
        )

        case_score = scoring_service.score(
            npi,
            graph_result.output["signals"],
            enforcement_result.output,
            entity_adjudications,
            counter_result.output["confidence_adjustment"],
        )

        case_packet = await synthesize(
            npi,
            graph_result.output,
            enforcement_result.output,
            counter_result.output,
            driver,
            evidence_dir,
            runtime,
        )
        (cases_dir / f"{npi}.json").write_text(case_packet.model_dump_json(indent=2))

        return {
            "npi": npi,
            "priority_tier": case_score.priority_tier.value,
            "case_score": case_score.model_dump(mode="json"),
            "candidate_pair_count": len(pairs),
            "citation_report_all_resolved": case_packet.citation_report.all_resolved,
        }

    return Workflow(
        name="specter_screening",
        edges=[
            ("START", data_quality_gate),
            (data_quality_gate, {Verdict.FAIL.value: halt_node, DEFAULT_ROUTE: cohort_select_node}),
            (cohort_select_node, screen_provider),
        ],
    )
