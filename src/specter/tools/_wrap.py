"""Tool-call span attributes (plan §11, debt D-7): `specter.tool_name` and
`specter.result_row_count`. Same inline `trace.get_current_span()` pattern
`mcp_tools.run_guarded_cypher` already uses for `specter.cypher`, applied
once here at binding-assembly time rather than inside all ~20 tool bodies.

`functools.wraps` matters beyond convention: it sets `__wrapped__`, which
`inspect.signature`'s default `follow_wrapped=True` follows straight through
to the original tool — so B0 generation and ADK's own `FunctionTool`
introspection see the real signature, not `(*args, **kwargs)`.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from opentelemetry import trace

_ROW_COUNT_KEYS = (
    "hit_count",
    "peer_count",
    "proposal_count",
    "node_count",
    "total_citations",
)


def _row_count(result: dict[str, Any]) -> int | None:
    for key in _ROW_COUNT_KEYS:
        value = result.get(key)
        if isinstance(value, int):
            return value
    return None


def traced(func: Callable[..., dict[str, Any]]) -> Callable[..., dict[str, Any]]:
    """Wrap one tool binding so its call span carries name + row count."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = func(*args, **kwargs)
        span = trace.get_current_span()
        span.set_attribute("specter.tool_name", func.__name__)
        row_count = _row_count(result)
        if row_count is not None:
            span.set_attribute("specter.result_row_count", row_count)
        return result

    return wrapper


def traced_tools(tools: list[Callable[..., Any]]) -> list[Callable[..., Any]]:
    return [traced(tool) for tool in tools]
