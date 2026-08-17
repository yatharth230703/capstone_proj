"""Plan §11's per-agent cost/cache table, rendered from the SQLite ledger
(`llm/ledger.py`). No live agent run required — the ledger already has real
rows from every milestone that ran a live agent.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from rich.console import Console
from rich.table import Table

from specter.llm.ledger import CostLedger

_TIER_SHORT_RE = re.compile(r"^(T\d+)_")


def _short_tier(tier: str) -> str:
    match = _TIER_SHORT_RE.match(tier)
    return match.group(1) if match else tier


def _rows_by_agent(
    db_path: Path,
) -> list[tuple[str, str, int, int, int, int, float | None]]:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            """
            SELECT agent, tier, COUNT(*), SUM(prompt_tokens), SUM(cached_tokens),
                   SUM(completion_tokens), SUM(cost_usd)
            FROM llm_calls
            GROUP BY agent, tier
            ORDER BY COUNT(*) DESC
            """
        ).fetchall()


def render_dashboard(db_path: Path) -> Table:
    """Build the plan §11 table. `CostLedger(db_path)` applies the schema
    first, so an empty/fresh ledger still has a queryable `llm_calls` table
    rather than raising `no such table`.
    """
    ledger = CostLedger(db_path)
    rows = _rows_by_agent(db_path)

    table = Table(title="Specter — LLM call ledger")
    table.add_column("Agent")
    table.add_column("Tier")
    table.add_column("Calls", justify="right")
    table.add_column("Prompt tok", justify="right")
    table.add_column("Cached tok", justify="right")
    table.add_column("Cache hit%", justify="right")
    table.add_column("Cost (USD)", justify="right")

    for agent, tier, calls, prompt_tokens, cached_tokens, _completion_tokens, cost_usd in rows:
        hit_rate = ledger.cache_hit_rate(agent)
        table.add_row(
            agent,
            _short_tier(tier),
            str(calls),
            str(prompt_tokens),
            str(cached_tokens),
            f"{hit_rate:.0%}",
            # `cost_usd` is NULL until real Foundry pricing lands (D-8) —
            # rendering "$0.00" would claim a cost that was never computed.
            "-" if cost_usd is None else f"${cost_usd:.4f}",
        )

    return table


def print_dashboard(db_path: Path) -> None:
    console = Console()
    console.print(render_dashboard(db_path))
    overall_hit_rate = CostLedger(db_path).cache_hit_rate()
    console.print(f"Overall cache hit rate: {overall_hit_rate:.0%}")
