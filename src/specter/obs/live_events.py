"""In-process fan-out for the dashboard's live screening view (`POST
/screen`) — the "which agent is running, what tool is it calling, is this a
cache hit" map, mirroring ADK's own dev-UI trace panel.

A `ContextVar` rather than a new parameter threaded through five agent
modules and `_llm_call._invoke`: `screen_one_provider` is deliberately the
*exact* function `scripts/40_screen.py` also calls (CLAUDE.md Amendment
4(a)) — every one of its callers still works unchanged, because `emit()` is
a no-op until something calls `listen()` around it. `asyncio.Task` copies
the current context at creation time, so a listener set before
`asyncio.create_task(screen_one_provider(...))` is still visible inside it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_listener: ContextVar[Callable[[dict[str, Any]], None] | None] = ContextVar(
    "specter_live_event_listener", default=None
)


def emit(event: dict[str, Any]) -> None:
    listener = _listener.get()
    if listener is not None:
        listener(event)


@contextmanager
def listen(callback: Callable[[dict[str, Any]], None]) -> Iterator[None]:
    token = _listener.set(callback)
    try:
        yield
    finally:
        _listener.reset(token)
