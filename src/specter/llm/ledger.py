"""Cost/token ledger (plan §7.4). SQLite `llm_calls` table. `cost_usd` stays
NULL until real Azure/Vertex pricing is filled into `config/models.yaml`'s
`price_*` fields — "a wrong cost chart is worse than no cost chart."
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import structlog

from specter.core.contracts import LlmCallRecord, TierConfig

logger = structlog.get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_calls (
    ts TEXT NOT NULL,
    run_id TEXT NOT NULL,
    agent TEXT NOT NULL,
    task_class TEXT NOT NULL,
    tier TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    cached_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    latency_ms REAL NOT NULL,
    cost_usd REAL,
    cache_layer TEXT NOT NULL,
    escalated INTEGER NOT NULL
)
"""


def compute_cost(
    tier: TierConfig, prompt_tokens: int, cached_tokens: int, completion_tokens: int
) -> float | None:
    if (
        tier.price_input_per_1m is None
        or tier.price_cached_input_per_1m is None
        or tier.price_output_per_1m is None
    ):
        return None
    uncached_prompt_tokens = max(0, prompt_tokens - cached_tokens)
    return (
        uncached_prompt_tokens * tier.price_input_per_1m
        + cached_tokens * tier.price_cached_input_per_1m
        + completion_tokens * tier.price_output_per_1m
    ) / 1_000_000


class CostLedger:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(_SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record(self, entry: LlmCallRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO llm_calls (
                    ts, run_id, agent, task_class, tier, model, prompt_tokens,
                    cached_tokens, completion_tokens, latency_ms, cost_usd,
                    cache_layer, escalated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.ts.isoformat(),
                    entry.run_id,
                    entry.agent,
                    entry.task_class,
                    entry.tier,
                    entry.model,
                    entry.prompt_tokens,
                    entry.cached_tokens,
                    entry.completion_tokens,
                    entry.latency_ms,
                    entry.cost_usd,
                    entry.cache_layer.value,
                    int(entry.escalated),
                ),
            )
        logger.info(
            "ledger.recorded",
            agent=entry.agent,
            task_class=entry.task_class,
            cache_layer=entry.cache_layer.value,
        )

    def cache_hit_rate(self, agent: str | None = None) -> float:
        query = "SELECT prompt_tokens, cached_tokens FROM llm_calls"
        params: tuple[str, ...] = ()
        if agent is not None:
            query += " WHERE agent = ?"
            params = (agent,)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        total_prompt: int = sum(row[0] for row in rows)
        total_cached: int = sum(row[1] for row in rows)
        if total_prompt == 0:
            return 0.0
        return total_cached / total_prompt

    def total_calls(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM llm_calls").fetchone()
        return int(row[0])
