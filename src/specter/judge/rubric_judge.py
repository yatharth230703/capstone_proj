"""Rubric judge (plan §12.2, T2 `judge_case_rubric`) — CLAUDE.md Amendment 2's
five self-preference mitigations, all implemented here:

1. Deterministic-primary/LLM-secondary: enforced by `judge/report.py`'s
   ordering, not this module — this module only produces the LLM half.
2. Blinding: every sample is run against `blind.blind_case(case)`, never the
   raw `CasePacket`.
3. Forced negative evidence: `CriterionScore.weakness_found` rejects "none"
   (`core/contracts.py`'s validator) — a rejection is caught once and
   retried with the rejection quoted back, same one-retry shape
   `graph_investigation.investigate` uses for numeric-grounding violations.
4. Calibration: `calibration_fixtures.py` is a separate module; this module
   just needs to be callable per-`CasePacket`, which the calibration runner
   reuses directly.
5. Temperature 0 + genuine 3-sample independence: `judge_case_rubric` routes
   to `T2_reasoning` (temperature 0.2, shared with Skeptic/CaseReporter/
   planning), so this module overrides temperature to 0.0 via `build_agent`'s
   `tier_override` (M9 addition to `agents/_base.py`) rather than mutating
   the tier globally. And — the fix for BUILD_MILESTONES.md debt D-22 —
   each of the 3 samples runs through its own `AgentRuntime` whose
   `ResponseCache` is constructed with `enabled=False`. CLAUDE.md's literal
   wording ("sample index excluded from the cache key") would make samples 2
   and 3 L1 cache *hits* on sample 1's response under the real cache-key
   function (keyed on agent/prompt_version/model/evidence, none of which
   differ between samples) — that collapses "per-criterion variance across 3
   samples" to always exactly zero, defeating the mitigation's own purpose.
   A disabled cache sidesteps the ambiguity entirely: every sample is a real,
   independent Azure call.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import structlog
from neo4j import Driver

from specter.agents._base import AgentRuntime, build_agent, run_agent
from specter.agents._errors import AgentOutputError
from specter.core.contracts import CasePacket, EvidenceBundle, JudgeVerdict, RubricJudgment
from specter.judge import deterministic_checks
from specter.judge.blind import blind_case
from specter.llm.response_cache import ResponseCache

logger = structlog.get_logger(__name__)

AGENT_NAME = "rubric_judge"
TASK_CLASS = "judge_case_rubric"
INSTRUCTION_FILE = "rubric_judge.md"

CRITERIA = (
    "citation_validity",
    "numeric_grounding",
    "legal_discipline",
    "counter_evidence",
    "hallucination",
)

_LOW_RELIABILITY_SPREAD = 1

_TASK_INSTRUCTION = (
    "Grade the blinded case packet below on exactly these 5 criteria, one "
    f"CriterionScore each: {', '.join(CRITERIA)}. Score 0-5. supporting_quote "
    "must be a verbatim span from the case packet. weakness_found is "
    "required for every criterion — name a real weakness, or state "
    "specifically why the criterion is fully satisfied; the literal string "
    '"none" is rejected.'
)


def _sample_runtime(base: AgentRuntime) -> AgentRuntime:
    """A fresh `AgentRuntime` sharing everything with `base` except the L1
    cache, which is disabled — see the module docstring's point 5 / D-22.
    """
    return replace(base, cache=ResponseCache(base.cache._redis, enabled=False))


async def _run_one_sample(case: CasePacket, runtime: AgentRuntime) -> RubricJudgment:
    judge_tier = runtime.router.resolve(TASK_CLASS).model_copy(update={"temperature": 0.0})
    agent = build_agent(
        name=AGENT_NAME,
        task_class=TASK_CLASS,
        instruction_file=INSTRUCTION_FILE,
        tools=[],
        output_schema=RubricJudgment,
        runtime=runtime,
        tier_override=judge_tier,
    )
    blinded = blind_case(case)
    evidence = EvidenceBundle(
        provider_npi=case.provider_npi,
        evidence=blinded.model_dump(mode="json"),
        task_instruction=_TASK_INSTRUCTION,
    )
    try:
        result = await run_agent(agent, TASK_CLASS, evidence, runtime, RubricJudgment)
        return RubricJudgment.model_validate(result.output)
    except AgentOutputError as exc:
        logger.warning("rubric_judge.retry", provider_npi=case.provider_npi, reason=str(exc))
        retry_evidence = EvidenceBundle(
            provider_npi=case.provider_npi,
            evidence=blinded.model_dump(mode="json"),
            task_instruction=(
                f"{_TASK_INSTRUCTION}\n\nYour previous answer was rejected: {exc}. "
                'Every weakness_found must name a real weakness or explain '
                'specifically why the criterion is fully satisfied — never "none".'
            ),
        )
        result = await run_agent(agent, TASK_CLASS, retry_evidence, runtime, RubricJudgment)
        return RubricJudgment.model_validate(result.output)


_AggregateResult = tuple[dict[str, float], list[str], dict[str, float]]


def _aggregate(samples: list[RubricJudgment]) -> _AggregateResult:
    by_criterion: dict[str, list[int]] = {c: [] for c in CRITERIA}
    for sample in samples:
        for score in sample.criteria:
            by_criterion.setdefault(score.criterion, []).append(score.score)

    variance = {c: (max(v) - min(v) if v else 0.0) for c, v in by_criterion.items()}
    low_reliability = sorted(
        c for c, spread in variance.items() if spread > _LOW_RELIABILITY_SPREAD
    )
    aggregate = {
        c: sum(v) / len(v)
        for c, v in by_criterion.items()
        if v and c not in low_reliability
    }
    return aggregate, low_reliability, {c: float(v) for c, v in variance.items()}


async def judge_case(case: CasePacket, runtime: AgentRuntime, sample_count: int) -> JudgeVerdict:
    """Run `sample_count` independent rubric-judge samples over `case` and
    fold them into a `JudgeVerdict`. Callers that also want the deterministic
    checks (to report disagreement, plan §12.2: "Run both") call
    `deterministic_vs_llm_disagreement` separately — it takes its own
    `driver`/`evidence_dir`.
    """
    samples = [
        await _run_one_sample(case, _sample_runtime(runtime)) for _ in range(sample_count)
    ]
    aggregate, low_reliability, variance = _aggregate(samples)
    return JudgeVerdict(
        provider_npi=case.provider_npi,
        samples=samples,
        per_criterion_variance=variance,
        low_reliability_criteria=low_reliability,
        aggregate_scores=aggregate,
    )


def deterministic_vs_llm_disagreement(
    case: CasePacket, verdict: JudgeVerdict, driver: Driver, evidence_dir: Path
) -> list[str]:
    """plan §12.2: citation validity and hallucination are both checkable
    deterministically *and* graded by the LLM — report where they disagree.
    A deterministic FAIL (any unresolved citation / unfound entity) counts as
    disagreement against an LLM score of 4 or 5 on the matching criterion.
    """
    citation_report = deterministic_checks.check_citation_validity(case, driver, evidence_dir)
    citation_ok = all(citation_report.values())
    entity_ok = all(deterministic_checks.check_entity_existence(case, driver).values())

    disagreements: list[str] = []
    for sample_idx, sample in enumerate(verdict.samples):
        by_criterion = {c.criterion: c.score for c in sample.criteria}
        citation_score = by_criterion.get("citation_validity")
        if citation_score is not None and not citation_ok and citation_score >= 4:
            disagreements.append(
                f"sample {sample_idx}: LLM scored citation_validity={citation_score} but the "
                "deterministic check found an unresolved citation"
            )
        hallucination_score = by_criterion.get("hallucination")
        if hallucination_score is not None and not entity_ok and hallucination_score >= 4:
            disagreements.append(
                f"sample {sample_idx}: LLM scored hallucination={hallucination_score} but the "
                "deterministic check found a fabricated identifier"
            )
    return disagreements
