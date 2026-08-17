"""Agent-foundation tests. All offline — no LLM call is made here.

The live path is covered by `scripts/15_smoke_data_quality.py`, which is run
by hand because it costs money. What is asserted here is everything that can
break silently: the cache boundary, the tool bindings, and the strict-mode
constraints Azure imposes on output schemas.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from google.adk.models.llm_request import LlmRequest
from google.adk.tools.function_tool import FunctionTool
from google.genai import types as genai_types
from neo4j import Driver

import specter.agents._base as agent_base
from specter.agents._base import (
    AgentOutputError,
    AgentRuntime,
    build_agent,
    run_agent,
)
from specter.agents._llm_call import (
    _STATE_INPUT_PROMPT_VERSION,
    _STATE_INPUT_PROVIDER_NPI,
    _parse_output,
)
from specter.agents.data_quality import build_evidence
from specter.core.contracts import (
    AgentRunResult,
    DataQualityReport,
    EntityMatchAdjudication,
    EvidenceBundle,
    ScreeningThresholds,
    TierConfig,
)
from specter.core.enums import CacheLayer, MatchDecision
from specter.llm.ledger import CostLedger
from specter.llm.prompt_compiler import PromptCompiler
from specter.llm.response_cache import ResponseCache
from specter.llm.router import ModelRouter, load_policy
from specter.settings import get_settings
from specter.tools.bindings import build_tool_bindings
from specter.tools.signal_tools import load_thresholds

_REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def thresholds() -> ScreeningThresholds:
    return load_thresholds(_REPO_ROOT / "config" / "screening.yaml")


@pytest.fixture
def bindings(thresholds: ScreeningThresholds) -> list[Any]:
    # The driver is only touched inside each tool body, so binding without a
    # live Neo4j is safe for every signature/schema assertion below.
    return build_tool_bindings(cast(Driver, None), thresholds, _REPO_ROOT / "data" / "evidence")


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
        cache=ResponseCache(cast(Any, None), enabled=False),
        ledger=CostLedger(tmp_path / "ledger.sqlite"),
        run_id="test",
        prompts_dir=_REPO_ROOT / "prompts" / "agents",
    )


# --- the cache boundary -------------------------------------------------


def test_static_instruction_is_exactly_the_compiled_prefix(runtime: AgentRuntime) -> None:
    """B0-B3 must reach the model verbatim. ADK puts `static_instruction`
    straight into `config.system_instruction`, so any drift here is drift in
    the cached prefix.
    """
    agent = build_agent(
        name="data_quality",
        task_class="assess_source_quality",
        instruction_file="data_quality.md",
        tools=[],
        output_schema=DataQualityReport,
        runtime=runtime,
    )
    assert agent.static_instruction == runtime.compiler.system_prefix


def test_agent_instruction_stays_below_the_boundary(runtime: AgentRuntime) -> None:
    """The per-agent brief must NOT be part of the shared prefix — otherwise
    every agent gets its own cache entry instead of sharing one.
    """
    agent = build_agent(
        name="data_quality",
        task_class="assess_source_quality",
        instruction_file="data_quality.md",
        tools=[],
        output_schema=DataQualityReport,
        runtime=runtime,
    )
    assert "Role: Data Quality Agent" in agent.instruction
    assert "Role: Data Quality Agent" not in cast(str, agent.static_instruction)


def test_before_model_sets_prompt_version_and_provider_npi_spans(
    runtime: AgentRuntime,
) -> None:
    """M8: `_llm_call._invoke` hands these down via initial session state
    (evidence isn't known yet when `build_agent` constructs the closure), so
    this exercises the real `before_model_callback` directly rather than
    monkeypatching `_invoke` like the escalation test does.
    """
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    agent = build_agent(
        name="data_quality",
        task_class="assess_source_quality",
        instruction_file="data_quality.md",
        tools=[],
        output_schema=DataQualityReport,
        runtime=runtime,
    )
    before_model = agent.before_model_callback
    assert before_model is not None

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    request = LlmRequest(
        model="test",
        config=genai_types.GenerateContentConfig(
            system_instruction=agent.static_instruction
        ),
    )
    state = {
        _STATE_INPUT_PROMPT_VERSION: "policy-v1",
        _STATE_INPUT_PROVIDER_NPI: "1003001439",
    }
    context = cast(Any, SimpleNamespace(state=state))

    with tracer.start_as_current_span("test-model-call"):
        before_model(callback_context=context, llm_request=request)

    (span,) = exporter.get_finished_spans()
    assert span.attributes is not None
    assert span.attributes["specter.prompt_version"] == "policy-v1"
    assert span.attributes["specter.provider_npi"] == "1003001439"


def test_before_model_omits_provider_npi_when_evidence_carries_none(
    runtime: AgentRuntime,
) -> None:
    """`specter.provider_npi` is only meaningful for provider-scoped agents —
    it must be omitted, not written as `""`, when the evidence bundle has no
    NPI (e.g. a non-provider-scoped agent call).
    """
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    agent = build_agent(
        name="data_quality",
        task_class="assess_source_quality",
        instruction_file="data_quality.md",
        tools=[],
        output_schema=DataQualityReport,
        runtime=runtime,
    )
    before_model = agent.before_model_callback
    assert before_model is not None

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")

    request = LlmRequest(
        model="test",
        config=genai_types.GenerateContentConfig(
            system_instruction=agent.static_instruction
        ),
    )
    state = {_STATE_INPUT_PROMPT_VERSION: "policy-v1"}
    context = cast(Any, SimpleNamespace(state=state))

    with tracer.start_as_current_span("test-model-call"):
        before_model(callback_context=context, llm_request=request)

    (span,) = exporter.get_finished_spans()
    assert span.attributes is not None
    assert "specter.provider_npi" not in span.attributes
    assert span.attributes["specter.prompt_version"] == "policy-v1"


def test_agent_name_must_be_python_identifier(runtime: AgentRuntime) -> None:
    with pytest.raises(ValueError, match="valid Python identifier"):
        build_agent(
            name="data-quality",
            task_class="assess_source_quality",
            instruction_file="data_quality.md",
            tools=[],
            output_schema=DataQualityReport,
            runtime=runtime,
        )


def test_unknown_task_class_raises(runtime: AgentRuntime) -> None:
    with pytest.raises(ValueError, match="unknown task_class"):
        build_agent(
            name="nonexistent",
            task_class="not_a_real_task_class",
            instruction_file="data_quality.md",
            tools=[],
            output_schema=DataQualityReport,
            runtime=runtime,
        )


# --- output-schema strictness ------------------------------------------


def _walk_properties(schema: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    for name, definition in schema.get("properties", {}).items():
        found.append((name, definition))
    for definition in schema.get("$defs", {}).values():
        found.extend(_walk_properties(definition))
    return found


def test_agent_output_schemas_carry_no_defaults() -> None:
    """Azure strict mode (`lite_llm.py:2321` sets `strict: True`) rejects any
    property with a `default`. A default here is a 400 at run time, not a
    validation error at build time — so it has to be caught in tests.
    """
    schema = DataQualityReport.model_json_schema()
    offenders = [name for name, defn in _walk_properties(schema) if "default" in defn]
    assert offenders == [], f"fields with defaults break Azure strict mode: {offenders}"


def test_agent_output_schemas_forbid_additional_properties() -> None:
    schema = DataQualityReport.model_json_schema()
    assert schema.get("additionalProperties") is False


def test_parse_output_rejects_non_json() -> None:
    with pytest.raises(AgentOutputError, match="not valid JSON"):
        _parse_output("agent", "I'm afraid I can't do that", DataQualityReport)


def test_parse_output_rejects_schema_violation() -> None:
    with pytest.raises(AgentOutputError, match="did not validate"):
        _parse_output("agent", json.dumps({"verdict": "banana"}), DataQualityReport)


def test_parse_output_accepts_valid_payload() -> None:
    payload = {
        "verdict": "warn",
        "per_source": [
            {
                "source_id": "nppes",
                "verdict": "pass",
                "freshness_status": "current",
                "findings": ["row count matches manifest"],
                "recommended_action": "proceed",
            }
        ],
        "blocking_reasons": [],
        "recommended_action": "proceed with limitations recorded",
    }
    parsed = _parse_output("agent", json.dumps(payload), DataQualityReport)
    assert parsed["verdict"] == "warn"
    assert parsed["per_source"][0]["source_id"] == "nppes"


# --- tool bindings ------------------------------------------------------


def test_bindings_hide_infrastructure_from_the_model(bindings: list[Any]) -> None:
    """No model-facing tool may expose a driver, thresholds, or a filesystem
    path — a model that can pass a threshold is a model choosing a number.
    """
    import inspect

    forbidden = {"driver", "thresholds", "evidence_dir"}
    for tool in bindings:
        params = set(inspect.signature(tool).parameters)
        assert not (params & forbidden), f"{tool.__name__} leaks {params & forbidden}"


def test_every_binding_has_a_docstring(bindings: list[Any]) -> None:
    """The docstring *is* the tool description the model sees
    (`function_tool.py:99`). An undocumented tool is an unusable one.
    """
    missing = [tool.__name__ for tool in bindings if not (tool.__doc__ or "").strip()]
    assert missing == []


def test_binding_names_are_unique(bindings: list[Any]) -> None:
    names = [tool.__name__ for tool in bindings]
    assert len(names) == len(set(names))


def test_adk_can_build_declarations_for_every_binding(bindings: list[Any]) -> None:
    for tool in bindings:
        declaration = FunctionTool(func=tool)._get_declaration()
        assert declaration is not None
        assert declaration.name == tool.__name__
        assert declaration.description


# --- data quality evidence ---------------------------------------------


def test_build_evidence_is_sorted_and_stable() -> None:
    """The evidence bundle feeds the L1 cache key, so an unsorted or
    unstable bundle means the cache never hits.
    """
    snapshot = _REPO_ROOT / "data" / "snapshot"
    if not list(snapshot.glob("*/manifest.json")):
        pytest.skip("no frozen snapshot — run scripts/10_ingest.py --freeze")

    first = build_evidence(snapshot)
    second = build_evidence(snapshot)

    source_ids = [s["source_id"] for s in first.evidence["sources"]]
    assert source_ids == sorted(source_ids)
    assert json.dumps(first.evidence, sort_keys=True, default=str) == json.dumps(
        second.evidence, sort_keys=True, default=str
    )


def test_build_evidence_reports_observed_row_counts() -> None:
    snapshot = _REPO_ROOT / "data" / "snapshot"
    if not list(snapshot.glob("*/manifest.json")):
        pytest.skip("no frozen snapshot — run scripts/10_ingest.py --freeze")

    bundle = build_evidence(snapshot)
    for source in bundle.evidence["sources"]:
        observed = source["observed"]
        assert "row_count" in observed
        assert "null_rate_per_column" in observed
        assert isinstance(observed["row_count_matches_manifest"], bool)


# --- escalation (M3) -----------------------------------------------------


def test_run_agent_escalates_on_ambiguous_match_probability(
    monkeypatch: pytest.MonkeyPatch, runtime: AgentRuntime
) -> None:
    """`adjudicate_entity_match` escalates to T2_reasoning when
    `match_probability` lands in [0.45, 0.65] (`config/models.yaml`). Mocks
    `_invoke` so this stays offline — no LLM call, no cache/ledger I/O — and
    just exercises the escalation wiring in `run_agent` itself.
    """

    def _output(match_probability: float) -> dict[str, Any]:
        return {
            "npi": "1000000000",
            "candidate_npi": "1000000001",
            "matching_features": ["shares_address"],
            "conflicting_features": [],
            "match_probability": match_probability,
            "decision": MatchDecision.AGENT_REVIEW.value,
        }

    calls: list[tuple[str, bool]] = []

    async def fake_invoke(
        agent: Any,
        task_class: str,
        tier: TierConfig,
        evidence: EvidenceBundle,
        runtime_: AgentRuntime,
        output_schema: type[Any],
        *,
        escalated: bool = False,
    ) -> tuple[AgentRunResult, Any]:
        calls.append((tier.name, escalated))
        probability = 0.55 if tier.name == "T1_workhorse" else 0.80
        payload = _output(probability)
        parsed = output_schema.model_validate(payload)
        result = AgentRunResult(
            agent=agent.name,
            task_class=task_class,
            tier=tier.name,
            model=tier.model,
            output=parsed.model_dump(mode="json"),
            prompt_tokens=0,
            cached_tokens=0,
            completion_tokens=0,
            latency_ms=0.0,
            cache_layer=CacheLayer.NONE,
            escalated=escalated,
            prefix_fingerprint="test",
        )
        return result, parsed

    monkeypatch.setattr(agent_base, "_invoke", fake_invoke)

    agent = build_agent(
        name="entity_resolution",
        task_class="adjudicate_entity_match",
        instruction_file="entity_resolution.md",
        tools=[],
        output_schema=EntityMatchAdjudication,
        runtime=runtime,
    )
    evidence = EvidenceBundle(provider_npi="1000000000", evidence={}, task_instruction="test")
    result = asyncio.run(
        run_agent(agent, "adjudicate_entity_match", evidence, runtime, EntityMatchAdjudication)
    )

    assert calls == [("T1_workhorse", False), ("T2_reasoning", True)]
    assert result.escalated is True
    assert result.tier == "T2_reasoning"
    assert result.output["match_probability"] == pytest.approx(0.80)


def test_run_agent_retries_transient_output_error(
    monkeypatch: pytest.MonkeyPatch, runtime: AgentRuntime
) -> None:
    """`_invoke_with_retry` (BUILD_MILESTONES.md D23): a truncated/malformed
    response is retried, not fatal on the first failure. Fails twice, then
    a fresh call succeeds — mirrors the live finding (concurrent fan-out
    truncates occasionally; a plain retry succeeds).
    """
    attempts: list[int] = []

    async def flaky_invoke(
        agent: Any,
        task_class: str,
        tier: TierConfig,
        evidence: EvidenceBundle,
        runtime_: AgentRuntime,
        output_schema: type[Any],
        *,
        escalated: bool = False,
    ) -> tuple[AgentRunResult, Any]:
        attempts.append(1)
        if len(attempts) < 3:
            raise AgentOutputError("response was not valid JSON: Unterminated string")
        payload = {
            "verdict": "pass",
            "per_source": [],
            "blocking_reasons": [],
            "recommended_action": "proceed",
        }
        parsed = output_schema.model_validate(payload)
        result = AgentRunResult(
            agent=agent.name,
            task_class=task_class,
            tier=tier.name,
            model=tier.model,
            output=parsed.model_dump(mode="json"),
            prompt_tokens=0,
            cached_tokens=0,
            completion_tokens=0,
            latency_ms=0.0,
            cache_layer=CacheLayer.NONE,
            escalated=escalated,
            prefix_fingerprint="test",
        )
        return result, parsed

    monkeypatch.setattr(agent_base, "_invoke", flaky_invoke)

    agent = build_agent(
        name="data_quality",
        task_class="assess_source_quality",
        instruction_file="data_quality.md",
        tools=[],
        output_schema=DataQualityReport,
        runtime=runtime,
    )
    evidence = EvidenceBundle(provider_npi="1000000000", evidence={}, task_instruction="test")
    result = asyncio.run(
        run_agent(agent, "assess_source_quality", evidence, runtime, DataQualityReport)
    )

    assert len(attempts) == 3
    assert result.output["verdict"] == "pass"


def test_run_agent_raises_after_exhausting_output_error_retries(
    monkeypatch: pytest.MonkeyPatch, runtime: AgentRuntime
) -> None:
    """A source that is genuinely, persistently broken still fails loudly
    (CLAUDE.md hard rule 7) — the retry has a bound, not an infinite loop.
    """
    attempts: list[int] = []

    async def always_broken_invoke(
        agent: Any,
        task_class: str,
        tier: TierConfig,
        evidence: EvidenceBundle,
        runtime_: AgentRuntime,
        output_schema: type[Any],
        *,
        escalated: bool = False,
    ) -> tuple[AgentRunResult, Any]:
        attempts.append(1)
        raise AgentOutputError("response was not valid JSON: Unterminated string")

    monkeypatch.setattr(agent_base, "_invoke", always_broken_invoke)

    agent = build_agent(
        name="data_quality",
        task_class="assess_source_quality",
        instruction_file="data_quality.md",
        tools=[],
        output_schema=DataQualityReport,
        runtime=runtime,
    )
    evidence = EvidenceBundle(provider_npi="1000000000", evidence={}, task_instruction="test")

    with pytest.raises(AgentOutputError, match="not valid JSON"):
        asyncio.run(
            run_agent(agent, "assess_source_quality", evidence, runtime, DataQualityReport)
        )

    assert len(attempts) == agent_base._MAX_OUTPUT_ERROR_ATTEMPTS
