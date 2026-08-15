from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import redis

from specter.core.contracts import LlmCallRecord, LlmResult, TierConfig
from specter.core.enums import CacheLayer
from specter.llm.ledger import CostLedger, compute_cost
from specter.llm.response_cache import ResponseCache, make_cache_key
from specter.settings import get_settings


def _tier(**overrides: object) -> TierConfig:
    base: dict[str, object] = {
        "name": "T1_workhorse",
        "provider": "azure",
        "model": "azure/gpt-5.4-mini",
        "max_output_tokens": 2048,
        "temperature": 0.1,
        "supports_prefix_cache": True,
        "price_input_per_1m": None,
        "price_cached_input_per_1m": None,
        "price_output_per_1m": None,
    }
    base.update(overrides)
    return TierConfig.model_validate(base)


def test_compute_cost_none_when_prices_null() -> None:
    cost = compute_cost(_tier(), prompt_tokens=1000, cached_tokens=0, completion_tokens=100)
    assert cost is None


def test_compute_cost_computes_when_prices_present() -> None:
    tier = _tier(price_input_per_1m=1.0, price_cached_input_per_1m=0.1, price_output_per_1m=2.0)
    cost = compute_cost(tier, prompt_tokens=1000, cached_tokens=800, completion_tokens=100)
    assert cost is not None
    # 200 uncached * $1/1M + 800 cached * $0.1/1M + 100 out * $2/1M
    expected = (200 * 1.0 + 800 * 0.1 + 100 * 2.0) / 1_000_000
    assert cost == pytest.approx(expected)


def _record(**overrides: object) -> LlmCallRecord:
    base: dict[str, object] = {
        "ts": datetime.now(UTC),
        "run_id": "test-run",
        "agent": "graph_investigation",
        "task_class": "narrate_graph_signal",
        "tier": "T1_workhorse",
        "model": "azure/gpt-5.4-mini",
        "prompt_tokens": 1500,
        "cached_tokens": 0,
        "completion_tokens": 200,
        "latency_ms": 400.0,
        "cost_usd": None,
        "cache_layer": CacheLayer.NONE,
        "escalated": False,
    }
    base.update(overrides)
    return LlmCallRecord.model_validate(base)


def test_ledger_records_and_counts(tmp_path: Path) -> None:
    ledger = CostLedger(tmp_path / "ledger.db")
    ledger.record(_record())
    ledger.record(_record(agent="skeptic", task_class="challenge_hypothesis"))
    assert ledger.total_calls() == 2


def test_cache_hit_rate_computation(tmp_path: Path) -> None:
    ledger = CostLedger(tmp_path / "ledger.db")
    ledger.record(_record(prompt_tokens=1000, cached_tokens=0))
    ledger.record(_record(prompt_tokens=1000, cached_tokens=800))
    # (0 + 800) / (1000 + 1000) = 0.4
    assert ledger.cache_hit_rate() == pytest.approx(0.4)


@pytest.fixture
def redis_client() -> Iterator[redis.Redis]:
    settings = get_settings()
    client = redis.Redis.from_url(settings.redis_url)
    try:
        client.ping()
    except redis.ConnectionError:
        pytest.skip("Redis not reachable — start it with `docker compose up -d`")
    yield client


def test_20_call_cold_then_warm_pass_exceeds_60pct_hit_rate(
    tmp_path: Path, redis_client: redis.Redis
) -> None:
    """M3 checkpoint: 'A scripted 20-call loop shows cache hit rate > 60% on
    the second pass.'
    """
    cache = ResponseCache(redis_client)
    npis = [f"demo-npi-{i}" for i in range(20)]
    keys = [
        make_cache_key("graph_investigation", "1.0.0", "azure/gpt-5.4-mini", {"npi": npi})
        for npi in npis
    ]

    # Cold pass: every call misses, gets "computed" (simulated), then cached.
    cold_ledger = CostLedger(tmp_path / "cold_ledger.db")
    for npi, key in zip(npis, keys, strict=True):
        assert cache.get(key) is None
        result = LlmResult(
            content=f"narration for {npi}",
            prompt_tokens=1500,
            completion_tokens=200,
            cached_tokens=0,
            model="azure/gpt-5.4-mini",
            latency_ms=350.0,
        )
        cache.set(key, result)
        cold_ledger.record(
            _record(run_id="cold", prompt_tokens=1500, cached_tokens=0, cache_layer=CacheLayer.NONE)
        )
    assert cold_ledger.cache_hit_rate() == 0.0

    # Warm pass: every call should hit L1.
    warm_ledger = CostLedger(tmp_path / "warm_ledger.db")
    try:
        for key in keys:
            cached_result = cache.get(key)
            assert cached_result is not None
            warm_ledger.record(
                _record(
                    run_id="warm",
                    prompt_tokens=1500,
                    cached_tokens=1500,  # full L1 hit — whole call avoided
                    completion_tokens=0,
                    cache_layer=CacheLayer.L1,
                )
            )
    finally:
        for key in keys:
            redis_client.delete(key)

    assert warm_ledger.cache_hit_rate() > 0.60
