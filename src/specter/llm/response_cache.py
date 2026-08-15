"""L1 whole-call response cache (plan §7.2). This is where most of the
actual savings show up on re-screening — the cold-vs-warm demo effect.

Key: sha256(agent_name | prompt_version | model_id | canonical_json(evidence)).
Disable via `SPECTER_CACHE_ENABLED=false` to demo cold vs. warm side by side.
"""

from __future__ import annotations

import json
from typing import Any

import redis
import structlog

from specter.core.contracts import LlmResult
from specter.core.hashing import sha256_text

logger = structlog.get_logger(__name__)

_KEY_PREFIX = "specter:l1:"
_DEFAULT_TTL_SECONDS = 7 * 24 * 3600


def make_cache_key(
    agent_name: str, prompt_version: str, model_id: str, evidence_bundle: dict[str, Any]
) -> str:
    canonical_evidence = json.dumps(evidence_bundle, sort_keys=True, default=str)
    raw = f"{agent_name}|{prompt_version}|{model_id}|{canonical_evidence}"
    return _KEY_PREFIX + sha256_text(raw)


class ResponseCache:
    def __init__(
        self,
        redis_client: redis.Redis,
        enabled: bool = True,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        self._redis = redis_client
        self._enabled = enabled
        self._ttl_seconds = ttl_seconds

    def get(self, key: str) -> LlmResult | None:
        if not self._enabled:
            return None
        raw = self._redis.get(key)
        if raw is None:
            return None
        result = LlmResult.model_validate_json(raw)
        logger.info(
            "cache.hit",
            key=key,
            avoided_prompt_tokens=result.prompt_tokens,
            avoided_completion_tokens=result.completion_tokens,
        )
        return result

    def set(self, key: str, result: LlmResult) -> None:
        if not self._enabled:
            return
        self._redis.set(key, result.model_dump_json(), ex=self._ttl_seconds)
        logger.info("cache.stored", key=key)
