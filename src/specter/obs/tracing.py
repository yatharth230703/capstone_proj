"""OTel wiring for Phoenix (plan §11, debt D-7).

`agents/_base.py`, `llm/router.py`, and `tools/mcp_tools.py` already set
`specter.*` span attributes on every LLM call and guarded Cypher query — they
have done so since M1/M3/M7. Nothing was ever registered to receive them, so
every attribute was silently discarded. `setup_tracing()` is the only thing
this milestone adds: a real tracer provider pointed at Phoenix, plus the two
instrumentors that turn ADK/LiteLLM calls into spans in the first place.
"""

from __future__ import annotations

import structlog
from openinference.instrumentation._tracer_providers import TracerProvider

logger = structlog.get_logger(__name__)

_tracer_provider: TracerProvider | None = None


def setup_tracing(collector_endpoint: str) -> TracerProvider:
    """Register the Phoenix exporter and instrument ADK + LiteLLM.

    Idempotent: `phoenix.otel.register()` stacks a new exporter on every call,
    which would double-count every span if a smoke script and `cli.py` both
    called this. A module-level guard makes the second call a no-op.
    """
    global _tracer_provider
    if _tracer_provider is not None:
        return _tracer_provider

    from openinference.instrumentation.google_adk import GoogleADKInstrumentor
    from openinference.instrumentation.litellm import LiteLLMInstrumentor
    from phoenix.otel import register

    tracer_provider = register(
        endpoint=collector_endpoint,
        project_name="specter",
        # `collector_endpoint` is the HTTP path (`/v1/traces`); "grpc" fails
        # silently against it — no spans, no error.
        protocol="http/protobuf",
        batch=True,
        set_global_tracer_provider=True,
        auto_instrument=False,
    )
    GoogleADKInstrumentor().instrument(tracer_provider=tracer_provider)
    LiteLLMInstrumentor().instrument(tracer_provider=tracer_provider)

    _tracer_provider = tracer_provider
    logger.info("tracing.configured", endpoint=collector_endpoint)
    return tracer_provider
