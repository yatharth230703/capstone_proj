"""Cost/cache endpoint (M13). Reuses `llm.ledger.CostLedger` and
`obs/dashboard.py`'s `GROUP BY agent, tier` query rather than re-deriving the
SQL. `cost_usd` stays `null` in the JSON response whenever the ledger has it
NULL (D-8 — no real Foundry/Vertex pricing filled in yet) — never coerced to
`0`, same discipline as `obs/dashboard.py`'s table.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from specter.core.errors import SpecterError
from specter.llm.ledger import CostLedger
from specter.obs.dashboard import _rows_by_agent, _short_tier

router = APIRouter()

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
LEDGER_PATH = _REPO_ROOT / "data" / "ledger.sqlite"


def _calls_by_day(db_path: Path) -> list[dict[str, Any]]:
    """Real history, not a synthesized trend line — `ts` is recorded on
    every ledger row already (`llm/ledger.py`), just never bucketed before.
    Spans every session that has run a live agent against this ledger, not
    just today's.
    """
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT substr(ts, 1, 10) AS day, COUNT(*), SUM(prompt_tokens), SUM(cached_tokens)
            FROM llm_calls GROUP BY day ORDER BY day
            """
        ).fetchall()
    return [
        {
            "day": day,
            "calls": calls,
            "cache_hit_rate": (cached / prompt) if prompt else 0.0,
        }
        for day, calls, prompt, cached in rows
    ]


@router.get("/costs")
def costs() -> dict[str, Any]:
    if not LEDGER_PATH.exists():
        raise SpecterError(
            f"{LEDGER_PATH} is missing — it's a gitignored run artifact. Run any "
            "live agent script (e.g. `python scripts/40_screen.py`) to populate it."
        )
    ledger = CostLedger(LEDGER_PATH)
    rows = [
        {
            "agent": agent,
            "tier": _short_tier(tier),
            "calls": calls,
            "prompt_tokens": prompt_tokens,
            "cached_tokens": cached_tokens,
            "completion_tokens": completion_tokens,
            "cache_hit_rate": ledger.cache_hit_rate(agent),
            "cost_usd": cost_usd,
        }
        for agent, tier, calls, prompt_tokens, cached_tokens, completion_tokens, cost_usd in (
            _rows_by_agent(LEDGER_PATH)
        )
    ]
    return {
        "rows": rows,
        "overall_cache_hit_rate": ledger.cache_hit_rate(),
        "total_calls": ledger.total_calls(),
        "calls_by_day": _calls_by_day(LEDGER_PATH),
    }
