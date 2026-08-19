"""One full agent call — L1 cache lookup or a real ADK run (plan §9).

Split out of `_base.py` (M3) to stay under CLAUDE.md's 400-line module
ceiling: agent *construction* (`build_agent`, the cache-boundary wiring)
lives in `_base.py`; agent *invocation* — the L1 cache, the ADK runner, and
output validation — lives here. `_base.py`'s `run_agent` calls `_invoke`
directly for the initial call and again for the one escalated retry, so this
module has no dependency on `_base.py` (only on `AgentRuntime`'s shape, via a
type-checking-only import — the actual code only ever does attribute access).
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, ValidationError

from specter.agents._errors import AgentOutputError
from specter.core.contracts import (
    AgentRunResult,
    EvidenceBundle,
    LlmCallRecord,
    LlmResult,
    TierConfig,
)
from specter.core.enums import CacheLayer
from specter.llm.ledger import compute_cost
from specter.llm.response_cache import make_cache_key
from specter.obs.live_events import emit

if TYPE_CHECKING:
    from specter.agents._base import AgentRuntime

logger = structlog.get_logger(__name__)

_APP_NAME = "specter"
_USER_ID = "specter"

# Session-state keys the callbacks in `_base.py` use to hand telemetry here.
# Deliberately not the `temp:` prefix — ADK trims `temp:` deltas before they
# are persisted (`base_session_service.py:187`), so they would not survive the
# `get_session` read-back below.
_STATE_PREFIX_FINGERPRINT = "specter_prefix_fingerprint"
_STATE_PROMPT_TOKENS = "specter_prompt_tokens"
_STATE_CACHED_TOKENS = "specter_cached_tokens"
_STATE_COMPLETION_TOKENS = "specter_completion_tokens"

# Inputs, not outputs: `_invoke` knows `compiled.prompt_version` and
# `evidence.provider_npi` before the run starts, but `before_model_callback`
# (in `_base.py`) is where the span with the actual model-call context is
# active — so these are handed down via initial session state instead of a
# closure, the same state-passing mechanism the four keys above use in
# reverse (callback -> `_invoke`).
_STATE_INPUT_PROMPT_VERSION = "specter_input_prompt_version"
_STATE_INPUT_PROVIDER_NPI = "specter_input_provider_npi"


def _final_text(event: Any) -> str | None:
    if not (event.is_final_response() and event.content and event.content.parts):
        return None
    text = "".join(
        part.text for part in event.content.parts if part.text and not part.thought
    )
    return text or None


async def _invoke(
    agent: LlmAgent,
    task_class: str,
    tier: TierConfig,
    evidence: EvidenceBundle,
    runtime: AgentRuntime,
    output_schema: type[BaseModel],
    *,
    escalated: bool = False,
) -> tuple[AgentRunResult, BaseModel]:
    """One full agent call — L1 cache lookup or a real ADK run — at a given,
    already-resolved `tier`. Returns both the telemetry-carrying
    `AgentRunResult` and the validated output model, so `run_agent` can check
    escalation conditions without re-parsing.
    """
    compiled = runtime.compiler.compile(agent.name, task_class, evidence)
    cache_key = make_cache_key(
        agent.name,
        compiled.prompt_version,
        tier.model,
        {"user": compiled.user, "prefix": compiled.prefix_fingerprint},
    )

    cached = runtime.cache.get(cache_key)
    if cached is not None:
        emit(
            {
                "type": "llm_call",
                "agent": agent.name,
                "task_class": task_class,
                "tier": tier.name,
                "model": tier.model,
                "status": "cache_hit",
                "cache_layer": "L1",
            }
        )
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
                escalated=escalated,
            )
        )
        parsed = _validate_output(agent.name, cached.content, output_schema)
        return (
            AgentRunResult(
                agent=agent.name,
                task_class=task_class,
                tier=tier.name,
                model=tier.model,
                output=parsed.model_dump(mode="json"),
                prompt_tokens=0,
                cached_tokens=0,
                completion_tokens=0,
                latency_ms=0.0,
                cache_layer=CacheLayer.L1,
                escalated=escalated,
                prefix_fingerprint=compiled.prefix_fingerprint,
            ),
            parsed,
        )

    emit(
        {
            "type": "llm_call",
            "agent": agent.name,
            "task_class": task_class,
            "tier": tier.name,
            "model": tier.model,
            "status": "started",
        }
    )
    session_service = InMemorySessionService()  # type: ignore[no-untyped-call]
    started = time.perf_counter()
    final_text: str | None = None

    initial_state: dict[str, Any] = {_STATE_INPUT_PROMPT_VERSION: compiled.prompt_version}
    if evidence.provider_npi:
        initial_state[_STATE_INPUT_PROVIDER_NPI] = evidence.provider_npi

    runner = Runner(app_name=_APP_NAME, agent=agent, session_service=session_service)
    try:
        session = await session_service.create_session(
            app_name=_APP_NAME, user_id=_USER_ID, state=initial_state
        )
        async for event in runner.run_async(
            user_id=_USER_ID,
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=compiled.user)]),
        ):
            for part in (event.content.parts if event.content else None) or []:
                if part.function_call is not None:
                    emit(
                        {
                            "type": "tool_call",
                            "agent": agent.name,
                            "tool": part.function_call.name,
                            "args": part.function_call.args or {},
                        }
                    )
                if part.function_response is not None:
                    emit(
                        {
                            "type": "tool_result",
                            "agent": agent.name,
                            "tool": part.function_response.name,
                        }
                    )
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

    # Validate before caching (BUILD_MILESTONES.md D-18): a transient
    # truncated response must not poison this cache key for every future
    # call that shares it. The ledger still records the call (and its real
    # cost) even when validation fails — only the cache write is gated.
    validation_error: AgentOutputError | None = None
    try:
        parsed = _validate_output(agent.name, final_text, output_schema)
    except AgentOutputError as exc:
        validation_error = exc

    if validation_error is None:
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
            escalated=escalated,
        )
    )
    emit(
        {
            "type": "llm_call",
            "agent": agent.name,
            "task_class": task_class,
            "tier": tier.name,
            "model": tier.model,
            "status": "completed",
            "latency_ms": round(latency_ms, 1),
            "prompt_tokens": prompt_tokens,
            "cached_tokens": cached_tokens,
            "completion_tokens": completion_tokens,
            "cache_layer": "prefix" if cached_tokens else "none",
        }
    )
    logger.info(
        "agent.completed",
        agent=agent.name,
        task_class=task_class,
        tier=tier.name,
        prompt_tokens=prompt_tokens,
        cached_tokens=cached_tokens,
        latency_ms=round(latency_ms, 1),
        escalated=escalated,
    )

    if validation_error is not None:
        raise validation_error

    return (
        AgentRunResult(
            agent=agent.name,
            task_class=task_class,
            tier=tier.name,
            model=tier.model,
            output=parsed.model_dump(mode="json"),
            prompt_tokens=prompt_tokens,
            cached_tokens=cached_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            cache_layer=CacheLayer.NONE,
            escalated=escalated,
            prefix_fingerprint=compiled.prefix_fingerprint,
        ),
        parsed,
    )


def _validate_output(
    agent_name: str, text: str, output_schema: type[BaseModel]
) -> BaseModel:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise AgentOutputError(f"{agent_name}: response was not valid JSON: {exc}") from exc
    try:
        return output_schema.model_validate(payload)
    except ValidationError as exc:
        raise AgentOutputError(
            f"{agent_name}: response did not validate against {output_schema.__name__}: {exc}"
        ) from exc


def _parse_output(
    agent_name: str, text: str, output_schema: type[BaseModel]
) -> dict[str, Any]:
    return _validate_output(agent_name, text, output_schema).model_dump(mode="json")
