"""Offline tests for `obs/dashboard.py` — no live LLM call, no live Phoenix.
Builds a temp `CostLedger`, inserts known `LlmCallRecord`s, asserts the
rendered `rich.Table` reflects them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from rich.table import Table

from specter.core.contracts import LlmCallRecord
from specter.core.enums import CacheLayer
from specter.llm.ledger import CostLedger
from specter.obs.dashboard import render_dashboard


def _record(agent: str, tier: str, prompt_tokens: int, cached_tokens: int) -> LlmCallRecord:
    return LlmCallRecord(
        ts=datetime.now(UTC),
        run_id="test-run",
        agent=agent,
        task_class="test_task",
        tier=tier,
        model="gpt-5.4-mini",
        prompt_tokens=prompt_tokens,
        cached_tokens=cached_tokens,
        completion_tokens=10,
        latency_ms=100.0,
        cost_usd=None,
        cache_layer=CacheLayer.NONE,
        escalated=False,
    )


def _cell(table: Table, column_header: str, row_index: int) -> str:
    for column in table.columns:
        if column.header == column_header:
            return str(list(column.cells)[row_index])
    raise AssertionError(f"no column {column_header!r}")


def test_hit_rate_matches_hand_computed_value(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite"
    ledger = CostLedger(db_path)
    ledger.record(_record("graph_investigation", "T1_workhorse", 1000, 400))
    ledger.record(_record("graph_investigation", "T1_workhorse", 1000, 600))

    table = render_dashboard(db_path)

    assert _cell(table, "Agent", 0) == "graph_investigation"
    assert _cell(table, "Cache hit%", 0) == "50%"  # (400+600)/(1000+1000)


def test_null_cost_renders_as_dash_never_zero(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite"
    ledger = CostLedger(db_path)
    ledger.record(_record("skeptic", "T2_reasoning", 500, 0))

    table = render_dashboard(db_path)

    cost_cell = _cell(table, "Cost (USD)", 0)
    assert cost_cell == "-"
    assert cost_cell != "$0.00"


def test_empty_ledger_renders_a_table_without_raising(tmp_path: Path) -> None:
    db_path = tmp_path / "ledger.sqlite"

    table = render_dashboard(db_path)

    assert isinstance(table, Table)
    assert len(list(table.columns[0].cells)) == 0
