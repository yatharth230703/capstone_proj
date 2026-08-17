"""Offline tests for `judge/rubric_judge.py`'s pure/wiring functions — no
live LLM needed. `_run_one_sample`/`judge_case` (the real Azure-calling path)
are exercised by `scripts/50_judge.py` by hand (BUILD_MILESTONES.md debt
D-20: the Azure key is currently dead, so that path cannot be verified live
this session).

`test_sample_runtime_disables_cache` is the actual verification for
BUILD_MILESTONES.md debt D-22 (Amendment 2 mitigation 5's self-contradiction,
recommended fix in the M9 Action Plan): each of the 3 judge samples must run
through a cache-disabled `AgentRuntime`, not the shared L1 cache, or
per-criterion variance would always be zero.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from specter.agents._base import AgentRuntime
from specter.core.contracts import CriterionScore, RubricJudgment
from specter.judge.rubric_judge import _aggregate, _sample_runtime
from specter.llm.ledger import CostLedger
from specter.llm.prompt_compiler import PromptCompiler
from specter.llm.response_cache import ResponseCache
from specter.llm.router import ModelRouter, load_policy
from specter.settings import get_settings

_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def runtime(tmp_path: Path) -> AgentRuntime:
    settings = get_settings()
    policy = load_policy(_REPO_ROOT / "config" / "models.yaml", settings)
    return AgentRuntime(
        router=ModelRouter(policy, "default", settings=settings),
        compiler=PromptCompiler(
            blocks_dir=_REPO_ROOT / "prompts" / "blocks",
            graph_version="test",
            policy_version=policy.version,
        ),
        cache=ResponseCache(cast(Any, None), enabled=True),
        ledger=CostLedger(tmp_path / "ledger.sqlite"),
        run_id="test",
        prompts_dir=_REPO_ROOT / "prompts" / "agents",
    )


def test_sample_runtime_disables_cache_and_preserves_everything_else(
    runtime: AgentRuntime,
) -> None:
    sample_rt = _sample_runtime(runtime)
    assert sample_rt.cache._enabled is False
    assert runtime.cache._enabled is True  # the base runtime is untouched
    assert sample_rt.router is runtime.router
    assert sample_rt.compiler is runtime.compiler
    assert sample_rt.ledger is runtime.ledger
    assert sample_rt.run_id == runtime.run_id


def test_two_sample_runtimes_are_independent_cache_instances(runtime: AgentRuntime) -> None:
    a = _sample_runtime(runtime)
    b = _sample_runtime(runtime)
    assert a.cache is not b.cache


def _judgment(scores: dict[str, int]) -> RubricJudgment:
    return RubricJudgment(
        criteria=[
            CriterionScore(criterion=c, score=s, supporting_quote="x", weakness_found="y")
            for c, s in scores.items()
        ]
    )


def test_aggregate_means_agreeing_samples() -> None:
    samples = [
        _judgment({"citation_validity": 4, "numeric_grounding": 5}),
        _judgment({"citation_validity": 4, "numeric_grounding": 5}),
        _judgment({"citation_validity": 4, "numeric_grounding": 5}),
    ]
    aggregate, low_reliability, variance = _aggregate(samples)
    assert aggregate["citation_validity"] == pytest.approx(4.0)
    assert aggregate["numeric_grounding"] == pytest.approx(5.0)
    assert low_reliability == []
    assert variance["citation_validity"] == 0.0


def test_aggregate_flags_low_reliability_and_excludes_from_aggregate() -> None:
    samples = [
        _judgment({"hallucination": 0}),
        _judgment({"hallucination": 5}),
        _judgment({"hallucination": 3}),
    ]
    aggregate, low_reliability, variance = _aggregate(samples)
    assert low_reliability == ["hallucination"]
    assert "hallucination" not in aggregate
    assert variance["hallucination"] == 5.0


def test_aggregate_spread_of_exactly_one_is_not_low_reliability() -> None:
    samples = [_judgment({"legal_discipline": 3}), _judgment({"legal_discipline": 4})]
    aggregate, low_reliability, variance = _aggregate(samples)
    assert low_reliability == []
    assert aggregate["legal_discipline"] == pytest.approx(3.5)
