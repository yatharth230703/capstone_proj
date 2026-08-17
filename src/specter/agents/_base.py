"""Agent *construction* (plan §9): routing, the cache boundary, and the
tracing/telemetry callbacks. Agent *invocation* — the L1 response cache, the
ADK runner, output validation — lives in `_llm_call.py`; both stay under
CLAUDE.md's 400-line module ceiling this way (M3 split them out of one file).

**How the cache boundary maps onto ADK.** ADK 2.6.2 has a built-in primitive
for this and we use it rather than hand-assembling messages:

    static_instruction  ->  B0..B3, verbatim, as the leading system message
    instruction         ->  the per-agent role brief, as a `user` turn
    new_message         ->  B4 evidence bundle + B5 task, as a `user` turn

`flows/llm_flows/instructions.py:99-119` is what guarantees this split: when
`static_instruction` is set, `instruction` is demoted from the system prompt
into `contents`. `lite_llm.py:2367` then inserts `system_instruction` verbatim
as message 0, which is exactly what Azure prompt caching keys on. Measured on
this deployment: 0 cached tokens on the first call, 2,816/3,152 on the second.

`static_instruction` is identical across all agents on purpose — a shared
prefix means one warm cache entry serves every agent, instead of each agent
paying its own cold call.

**Where the L1 cache lives.** Deliberately *outside* ADK, in
`_llm_call._invoke`. Short-circuiting inside `before_model_callback` would
still pay for session setup, request assembly, and event plumbing, and would
bypass the response post-processing that parses `output_schema`. A
whole-call cache belongs around the whole call.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types
from opentelemetry import trace
from pydantic import BaseModel

from specter.agents._errors import AgentOutputError, PrefixInstabilityError
from specter.agents._llm_call import (
    _STATE_CACHED_TOKENS,
    _STATE_COMPLETION_TOKENS,
    _STATE_INPUT_PROMPT_VERSION,
    _STATE_INPUT_PROVIDER_NPI,
    _STATE_PREFIX_FINGERPRINT,
    _STATE_PROMPT_TOKENS,
    _invoke,
)
from specter.core.contracts import AgentRunResult, EvidenceBundle, TierConfig
from specter.core.enums import CacheLayer
from specter.llm.ledger import CostLedger
from specter.llm.prompt_compiler import PromptCompiler
from specter.llm.response_cache import ResponseCache
from specter.llm.router import ModelRouter

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)


@dataclass(frozen=True)
class AgentRuntime:
    """Shared, reusable wiring. Build one per run and hand it to every agent."""

    router: ModelRouter
    compiler: PromptCompiler
    cache: ResponseCache
    ledger: CostLedger
    run_id: str
    prompts_dir: Path


def build_runtime(
    run_id: str,
    *,
    repo_root: Path,
    graph_version: str,
    settings: Any,
) -> AgentRuntime:
    """Assemble the shared wiring from config and env.

    `graph_version` is caller-supplied rather than sniffed from Neo4j: it is
    part of the cached prefix (B2), so it must change deliberately when the
    graph is rebuilt and not drift on its own.
    """
    import redis

    from specter.llm.router import load_policy

    policy_path = repo_root / "config" / "models.yaml"
    policy = load_policy(policy_path, settings)
    return AgentRuntime(
        router=ModelRouter(policy, settings.specter_run_profile, settings=settings),
        compiler=PromptCompiler(
            blocks_dir=repo_root / "prompts" / "blocks",
            graph_version=graph_version,
            policy_version=policy.version,
        ),
        cache=ResponseCache(
            redis.Redis.from_url(settings.redis_url),
            enabled=settings.specter_cache_enabled,
        ),
        ledger=CostLedger(repo_root / "data" / "ledger.sqlite"),
        run_id=run_id,
        prompts_dir=repo_root / "prompts" / "agents",
    )


def build_agent(
    name: str,
    task_class: str,
    instruction_file: str,
    tools: list[Any],
    output_schema: type[BaseModel],
    runtime: AgentRuntime,
    tier_override: TierConfig | None = None,
) -> LlmAgent:
    """Construct one agent with all cross-cutting concerns already attached.

    `name` must be a valid Python identifier — ADK rejects anything else
    (`_base_node.py:46`), which rules out hyphens and dots.

    `tier_override` (M9) lets a caller pin the tier config used to build this
    agent — e.g. `judge/rubric_judge.py` needs `temperature=0.0` without
    changing every other `T2_reasoning` task_class's shared temperature.
    `None` (every existing caller) preserves normal `task_class`-based
    routing, unchanged.
    """
    if not name.isidentifier():
        raise ValueError(f"agent name {name!r} must be a valid Python identifier")

    instruction_path = runtime.prompts_dir / instruction_file
    instruction = instruction_path.read_text().strip()
    return _build_agent_with_instruction(
        name, task_class, instruction, tools, output_schema, runtime,
        tier_override=tier_override,
    )


def _build_agent_with_instruction(
    name: str,
    task_class: str,
    instruction: str,
    tools: list[Any],
    output_schema: type[BaseModel],
    runtime: AgentRuntime,
    tier_override: TierConfig | None = None,
) -> LlmAgent:
    """The actual builder. `tier_override` is escalation's hook (M3): re-run
    the same instruction/tools/schema at a different tier without re-reading
    the instruction file. `build_agent` is the normal entry point; this is
    also called directly by `run_agent` for the one escalated retry.
    """
    tier = tier_override if tier_override is not None else runtime.router.resolve(task_class)
    model = runtime.router.model_for_tier(tier.name)
    prefix = runtime.compiler.system_prefix
    expected_fingerprint = runtime.compiler.compile(
        name, task_class, EvidenceBundle(provider_npi="", evidence={}, task_instruction="")
    ).prefix_fingerprint

    # Params are positional-or-keyword on purpose: ADK invokes these
    # BY KEYWORD (`base_llm_flow.py:243`), so the names `callback_context` /
    # `llm_request` / `llm_response` are load-bearing — but ADK's own type
    # alias declares them positionally, so making them keyword-only would not
    # type-check. Do not rename, do not add `*`.
    def before_model(callback_context: Context, llm_request: LlmRequest) -> LlmResponse | None:
        system_instruction = llm_request.config.system_instruction
        if not isinstance(system_instruction, str):
            raise PrefixInstabilityError(
                f"{name}: system_instruction is {type(system_instruction).__name__}, "
                "expected str — ADK would drop a non-str prefix silently"
            )
        if not system_instruction.startswith(prefix):
            raise PrefixInstabilityError(
                f"{name}: the compiled B0-B3 prefix is not the leading system "
                "instruction; something is being prepended above the cache boundary"
            )
        callback_context.state[_STATE_PREFIX_FINGERPRINT] = expected_fingerprint
        span = trace.get_current_span()
        span.set_attribute("specter.run_id", runtime.run_id)
        span.set_attribute("specter.agent", name)
        span.set_attribute("specter.task_class", task_class)
        span.set_attribute("specter.tier", tier.name)
        span.set_attribute("specter.model", tier.model)
        span.set_attribute("specter.prefix_fingerprint", expected_fingerprint)
        prompt_version = callback_context.state.get(_STATE_INPUT_PROMPT_VERSION)
        if prompt_version:
            span.set_attribute("specter.prompt_version", prompt_version)
        provider_npi = callback_context.state.get(_STATE_INPUT_PROVIDER_NPI)
        if provider_npi:
            span.set_attribute("specter.provider_npi", provider_npi)
        return None

    def after_model(callback_context: Context, llm_response: LlmResponse) -> LlmResponse | None:
        usage = llm_response.usage_metadata
        # `cached_content_token_count` is 0 (never None) when the provider
        # reports nothing, so zero is ambiguous between "no hit" and "not
        # reported" — see NOTES_API_DEVIATIONS.md.
        prompt_tokens = (usage.prompt_token_count or 0) if usage else 0
        cached_tokens = (usage.cached_content_token_count or 0) if usage else 0
        completion_tokens = (usage.candidates_token_count or 0) if usage else 0

        state = callback_context.state
        state[_STATE_PROMPT_TOKENS] = state.get(_STATE_PROMPT_TOKENS, 0) + prompt_tokens
        state[_STATE_CACHED_TOKENS] = state.get(_STATE_CACHED_TOKENS, 0) + cached_tokens
        state[_STATE_COMPLETION_TOKENS] = (
            state.get(_STATE_COMPLETION_TOKENS, 0) + completion_tokens
        )

        span = trace.get_current_span()
        span.set_attribute("specter.cached_tokens", cached_tokens)
        span.set_attribute("specter.cache_layer", CacheLayer.NONE.value)
        return None

    return LlmAgent(
        name=name,
        description=f"Specter {name} ({task_class}, tier {tier.name})",
        model=model,
        static_instruction=prefix,
        instruction=instruction,
        tools=tools,
        output_schema=output_schema,
        generate_content_config=types.GenerateContentConfig(
            temperature=tier.temperature,
            max_output_tokens=tier.max_output_tokens,
        ),
        before_model_callback=before_model,
        after_model_callback=after_model,
    )


_MAX_OUTPUT_ERROR_ATTEMPTS = 3


async def _invoke_with_retry(
    agent: LlmAgent,
    task_class: str,
    tier: TierConfig,
    evidence: EvidenceBundle,
    runtime: AgentRuntime,
    output_schema: type[BaseModel],
) -> tuple[AgentRunResult, BaseModel]:
    """`_invoke`, retried up to `_MAX_OUTPUT_ERROR_ATTEMPTS` times on
    `AgentOutputError` — see `run_agent`'s docstring for why this exists."""
    last_error: AgentOutputError | None = None
    for _attempt in range(_MAX_OUTPUT_ERROR_ATTEMPTS):
        try:
            return await _invoke(agent, task_class, tier, evidence, runtime, output_schema)
        except AgentOutputError as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


async def run_agent(
    agent: LlmAgent,
    task_class: str,
    evidence: EvidenceBundle,
    runtime: AgentRuntime,
    output_schema: type[BaseModel],
) -> AgentRunResult:
    """Run one agent to completion and return its validated output plus
    telemetry.

    L1 cache hit short-circuits the entire ADK invocation. On a miss the call
    runs, is recorded to the ledger, and the result is stored for next time.

    A malformed/truncated response (`AgentOutputError`) is retried up to 2
    extra times before propagating — found live in M10: `workflow/screening.
    py`'s `max_parallel_workers=4` fan-out produces occasional truncated
    responses that a sequential single-worker run never hits (16 sequential
    calls: 0 failures; the same 16 at 4-way concurrency: 2 failures), and a
    plain retry of the identical call succeeds (same empirical pattern as
    BUILD_MILESTONES.md D-18's original finding). litellm's own `num_retries`
    (`llm/router.py`) does not cover this — that retries on a raised
    transport exception (429/5xx), but a truncated-but-200 response isn't
    one. This is a fresh independent call each attempt, not a replay of
    cached content, so it does not mask a broken source (CLAUDE.md hard rule
    7): if all 3 attempts truncate, the last error still propagates.

    After a successful parse, `router.should_escalate` checks the result
    against `config/models.yaml`'s escalation rules. A match re-runs the same
    evidence through the same agent rebuilt at the escalated tier — capped at
    exactly one retry (every rule in the policy today sets `max_retries: 1`;
    `should_escalate` doesn't surface a higher count, so this doesn't loop).
    If the escalated call also fails schema validation, that raises rather
    than retrying again (CLAUDE.md hard rule 7).
    """
    tier = runtime.router.resolve(task_class)
    result, parsed = await _invoke_with_retry(
        agent, task_class, tier, evidence, runtime, output_schema
    )

    escalated_tier = runtime.router.should_escalate(task_class, parsed)
    if escalated_tier is None:
        return result

    # `agent.instruction` is typed `str | Callable[...]` by ADK (it allows a
    # dynamic instruction), but every Specter agent is built by `build_agent`
    # from a static file — always a plain string in practice.
    instruction = agent.instruction
    if not isinstance(instruction, str):
        raise AgentOutputError(f"{agent.name}: instruction is not a static string")
    escalated_agent = _build_agent_with_instruction(
        agent.name, task_class, instruction, agent.tools, output_schema, runtime,
        tier_override=escalated_tier,
    )
    escalated_result, _ = await _invoke(
        escalated_agent, task_class, escalated_tier, evidence, runtime, output_schema,
        escalated=True,
    )
    return escalated_result

