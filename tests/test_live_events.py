"""`obs/live_events.emit`/`listen` — the dashboard's live agent-map events
(`api/screen.py`) ride a `ContextVar`, not a threaded parameter, so
`scripts/40_screen.py` and every other caller of `screen_one_provider` must
keep working with zero events emitted. Two things to prove: `emit()` is a
silent no-op with no listener, and a listener set via `listen()` sees every
event emitted inside the block, including from an `asyncio.create_task`
spawned inside it (the real shape `api/screen.py` uses).
"""

from __future__ import annotations

import asyncio

from specter.obs.live_events import emit, listen


def test_emit_without_listener_is_a_noop() -> None:
    emit({"type": "stage", "stage": "graph_investigation", "status": "started"})  # must not raise


def test_listen_captures_events_emitted_inside_the_block() -> None:
    captured: list[dict[str, object]] = []
    with listen(captured.append):
        emit({"type": "stage", "stage": "skeptic", "status": "started"})
        emit({"type": "stage", "stage": "skeptic", "status": "completed"})
    emit({"type": "stage", "stage": "case_reporter", "status": "started"})  # outside the block
    assert captured == [
        {"type": "stage", "stage": "skeptic", "status": "started"},
        {"type": "stage", "stage": "skeptic", "status": "completed"},
    ]


def test_listen_reaches_a_task_created_inside_the_block() -> None:
    """`asyncio.create_task` copies the current context at creation time —
    this is what makes `api/screen.py`'s `asyncio.create_task(_run())`
    (created inside `with listen(...)`) see the listener at all.
    """
    captured: list[dict[str, object]] = []

    async def _child() -> None:
        emit({"type": "tool_call", "agent": "graph_investigation", "tool": "expand_neighborhood"})

    async def _main() -> None:
        with listen(captured.append):
            await asyncio.create_task(_child())

    asyncio.run(_main())
    assert captured == [
        {"type": "tool_call", "agent": "graph_investigation", "tool": "expand_neighborhood"}
    ]
