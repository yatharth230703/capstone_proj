"""The one place agent wiring lives (plan §9). Every agent is built here so
that routing, the cache boundary, the L1 response cache, the ledger, and the
tracing attributes exist in exactly one implementation.

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

**Where the L1 cache lives.** Deliberately *outside* ADK, in `run_agent`.
Short-circuiting inside `before_model_callback` would still pay for session
setup, request assembly, and event plumbing, and would bypass the response
post-processing that parses `output_schema`. A whole-call cache belongs
around the whole call.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from opentelemetry import trace
from pydantic import BaseModel, ValidationError

from specter.core.contracts import AgentRunResult, EvidenceBundle, LlmCallRecord, LlmResult
from specter.core.enums import CacheLayer
from specter.core.errors import SpecterError
from specter.llm.ledger import CostLedger, compute_cost
from specter.llm.prompt_compiler import PromptCompiler
from specter.llm.response_cache import ResponseCache, make_cache_key
from specter.llm.router import ModelRouter

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

_APP_NAME = "specter"
_USER_ID = "specter"

# Session-state keys the callbacks use to hand telemetry to `run_agent`.
# Deliberately not the `temp:` prefix — ADK trims `temp:` deltas before they
# are persisted (`base_session_service.py:187`), so they would not survive the
# `get_session` read-back below.
_STATE_PREFIX_FINGERPRINT = "specter_prefix_fingerprint"
_STATE_PROMPT_TOKENS = "specter_prompt_tokens"
_STATE_CACHED_TOKENS = "specter_cached_tokens"
_STATE_COMPLETION_TOKENS = "specter_completion_tokens"


class AgentOutputError(SpecterError):
    """The model returned something that is not valid against the agent's
    `output_schema`. Raised rather than repaired — a case built on a
    half-parsed agent response is worse than no case (CLAUDE.md hard rule 7).
    """


class PrefixInstabilityError(SpecterError):
    """The system prefix reaching the model differs from the one the compiler
    produced. This means something is leaking above the cache boundary and the
    caching pillar has silently stopped working — halt rather than continue
    paying full price while reporting success.
    """


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
) -> LlmAgent:
    """Construct one agent with all cross-cutting concerns already attached.

    `name` must be a valid Python identifier — ADK rejects anything else
    (`_base_node.py:46`), which rules out hyphens and dots.
    """
    if not name.isidentifier():
        raise ValueError(f"agent name {name!r} must be a valid Python identifier")

    tier = runtime.router.resolve(task_class)
    model = runtime.router.model_for(task_class)
    prefix = runtime.compiler.system_prefix
    expected_fingerprint = runtime.compiler.compile(
        name, task_class, EvidenceBundle(provider_npi="", evidence={}, task_instruction="")
    ).prefix_fingerprint

    instruction_path = runtime.prompts_dir / instruction_file
    instruction = instruction_path.read_text().strip()

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


def _final_text(event: Any) -> str | None:
    if not (event.is_final_response() and event.content and event.content.parts):
        return None
    text = "".join(
        part.text for part in event.content.parts if part.text and not part.thought
    )
    return text or None


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
    """
    tier = runtime.router.resolve(task_class)
    compiled = runtime.compiler.compile(agent.name, task_class, evidence)
    cache_key = make_cache_key(
        agent.name,
        compiled.prompt_version,
        tier.model,
        {"user": compiled.user, "prefix": compiled.prefix_fingerprint},
    )

    cached = runtime.cache.get(cache_key)
    if cached is not None:
        runtime.ledger.record(
            LlmCallRecord(
                ts=datetime.now(UTC),
                run_id=runtime.run_id,
                agent=agent.name,
                task_class=task_class,
                tier=tier.name,
                model=tier.model,
                # An L1 hit avoids these tokens entirely; recording zero keeps
                # the prefix-cache hit rate honest, and the avoided cost is
                # reconstructible from the cached LlmResult.
                prompt_tokens=0,
                cached_tokens=0,
                completion_tokens=0,
                latency_ms=0.0,
                cost_usd=None,
                cache_layer=CacheLayer.L1,
                escalated=False,
            )
        )
        return AgentRunResult(
            agent=agent.name,
            task_class=task_class,
            tier=tier.name,
            model=tier.model,
            output=_parse_output(agent.name, cached.content, output_schema),
            prompt_tokens=0,
            cached_tokens=0,
            completion_tokens=0,
            latency_ms=0.0,
            cache_layer=CacheLayer.L1,
            escalated=False,
            prefix_fingerprint=compiled.prefix_fingerprint,
        )

    session_service = InMemorySessionService()  # type: ignore[no-untyped-call]
    started = time.perf_counter()
    final_text: str | None = None

    runner = Runner(app_name=_APP_NAME, agent=agent, session_service=session_service)
    try:
        session = await session_service.create_session(app_name=_APP_NAME, user_id=_USER_ID)
        async for event in runner.run_async(
            user_id=_USER_ID,
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=compiled.user)]),
        ):
            # `is_final_response()` is true once per participating agent, not
            # once per invocation — keep the last rather than breaking early.
            text = _final_text(event)
            if text is not None:
                final_text = text
        refreshed = await session_service.get_session(
            app_name=_APP_NAME, user_id=_USER_ID, session_id=session.id
        )
    finally:
        # `close()` tears down toolsets and MCP sessions (M7 depends on this).
        await runner.close()  # type: ignore[no-untyped-call]

    latency_ms = (time.perf_counter() - started) * 1000.0
    if final_text is None:
        raise AgentOutputError(f"{agent.name}: produced no final response")

    state: dict[str, Any] = dict(refreshed.state) if refreshed else {}
    prompt_tokens = int(state.get(_STATE_PROMPT_TOKENS, 0))
    cached_tokens = int(state.get(_STATE_CACHED_TOKENS, 0))
    completion_tokens = int(state.get(_STATE_COMPLETION_TOKENS, 0))

    runtime.cache.set(
        cache_key,
        LlmResult(
            content=final_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            model=tier.model,
            latency_ms=latency_ms,
        ),
    )
    runtime.ledger.record(
        LlmCallRecord(
            ts=datetime.now(UTC),
            run_id=runtime.run_id,
            agent=agent.name,
            task_class=task_class,
            tier=tier.name,
            model=tier.model,
            prompt_tokens=prompt_tokens,
            cached_tokens=cached_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            cost_usd=compute_cost(tier, prompt_tokens, cached_tokens, completion_tokens),
            cache_layer=CacheLayer.NONE,
            escalated=False,
        )
    )
    logger.info(
        "agent.completed",
        agent=agent.name,
        task_class=task_class,
        tier=tier.name,
        prompt_tokens=prompt_tokens,
        cached_tokens=cached_tokens,
        latency_ms=round(latency_ms, 1),
    )

    return AgentRunResult(
        agent=agent.name,
        task_class=task_class,
        tier=tier.name,
        model=tier.model,
        output=_parse_output(agent.name, final_text, output_schema),
        prompt_tokens=prompt_tokens,
        cached_tokens=cached_tokens,
        completion_tokens=completion_tokens,
        latency_ms=latency_ms,
        cache_layer=CacheLayer.NONE,
        escalated=False,
        prefix_fingerprint=compiled.prefix_fingerprint,
    )


def _parse_output(
    agent_name: str, text: str, output_schema: type[BaseModel]
) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgentOutputError(f"{agent_name}: response was not valid JSON: {exc}") from exc
    try:
        return output_schema.model_validate(payload).model_dump(mode="json")
    except ValidationError as exc:
        raise AgentOutputError(
            f"{agent_name}: response did not validate against {output_schema.__name__}: {exc}"
        ) from exc
