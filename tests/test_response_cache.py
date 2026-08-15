from collections.abc import Iterator

import pytest
import redis

from specter.core.contracts import LlmResult
from specter.llm.response_cache import ResponseCache, make_cache_key
from specter.settings import get_settings


@pytest.fixture
def redis_client() -> Iterator[redis.Redis]:
    settings = get_settings()
    client = redis.Redis.from_url(settings.redis_url)
    try:
        client.ping()
    except redis.ConnectionError:
        pytest.skip("Redis not reachable — start it with `docker compose up -d`")
    yield client
    for key in client.scan_iter("specter:l1:test:*"):
        client.delete(key)


def _result(content: str = "narration text") -> LlmResult:
    return LlmResult(
        content=content, prompt_tokens=1500, completion_tokens=200, cached_tokens=0,
        model="azure/gpt-5.4-mini", latency_ms=420.0,
    )


def test_make_cache_key_deterministic() -> None:
    key1 = make_cache_key("agent", "1.0.0", "model", {"npi": "123", "signal": 5})
    key2 = make_cache_key("agent", "1.0.0", "model", {"signal": 5, "npi": "123"})
    assert key1 == key2  # dict key order must not matter


def test_make_cache_key_differs_by_evidence() -> None:
    key1 = make_cache_key("agent", "1.0.0", "model", {"npi": "123"})
    key2 = make_cache_key("agent", "1.0.0", "model", {"npi": "456"})
    assert key1 != key2


def test_cache_miss_returns_none(redis_client: redis.Redis) -> None:
    cache = ResponseCache(redis_client)
    assert cache.get("specter:l1:test:nonexistent") is None


def test_cache_set_then_get_returns_result(redis_client: redis.Redis) -> None:
    cache = ResponseCache(redis_client)
    key = "specter:l1:test:roundtrip"
    result = _result()
    cache.set(key, result)
    retrieved = cache.get(key)
    assert retrieved is not None
    assert retrieved.content == result.content
    assert retrieved.prompt_tokens == result.prompt_tokens


def test_cache_disabled_never_stores_or_retrieves(redis_client: redis.Redis) -> None:
    cache = ResponseCache(redis_client, enabled=False)
    key = "specter:l1:test:disabled"
    cache.set(key, _result())
    assert redis_client.get(key) is None
    assert cache.get(key) is None
