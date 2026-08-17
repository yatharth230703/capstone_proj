"""Batch text embedding (plan §6.4/§6.5) — `text-embedding-3-large` via the
same Azure v1-surface call form as chat completions (`openai/<deployment>` +
explicit `api_base`, see NOTES_API_DEVIATIONS.md D1). Used by
`graph/summaries.py` (community characterizations) and `graph/loader.py`
(EnforcementCase text).

Verified live against this deployment: `response.data` items are plain
dicts keyed `embedding`/`index`/`object`, not attribute-access objects — sort
by `item["index"]`, don't trust arrival order.
"""

from __future__ import annotations

import time

import litellm
import structlog
from litellm.exceptions import BadRequestError

from specter.settings import Settings

logger = structlog.get_logger(__name__)

EMBEDDING_DIMENSIONS = 3072
_BATCH_SIZE = 64
# Found live in M10: this deployment intermittently raises `BadRequestError:
# Unknown model: text-embedding-3-large` for a model that demonstrably
# exists and works (confirmed via `GET {api_base}/models?api-version=v1`
# and by immediate retries succeeding) — Azure/Foundry gateway flakiness
# under the 4-way concurrent fan-out `workflow/screening.py` runs, not a
# real config error. LiteLLM's own `num_retries` does NOT cover this: its
# `_should_retry` only retries HTTP 408/409/429/5xx, and a 400 is none of
# those (litellm/utils.py `_should_retry`) — so this needs its own bounded
# retry, same pattern as `agents._base._invoke_with_retry`. A live 250-
# provider run showed 3 *consecutive* failures (2s/4s backoff, ~7s total)
# on one call after 63 clean calls — a longer bad streak than a single
# blip, so this budgets 5 attempts with backoff up to 16s to give a
# genuinely overloaded gateway room to recover rather than just re-hitting
# it immediately three times.
_MAX_EMBED_ATTEMPTS = 5
_RETRY_BACKOFF_SECONDS = 2.0


def embed_texts(texts: list[str], settings: Settings) -> list[list[float]]:
    """Embeds `texts` in input order, batched. Raises if a returned vector
    isn't `EMBEDDING_DIMENSIONS` wide — a silently wrong-width vector fails
    at the Neo4j vector-index write with a confusing error otherwise
    (CLAUDE.md hard rule 7).
    """
    if not texts:
        return []
    if settings.azure_api_key is None or settings.azure_embedding_deployment is None:
        raise ValueError(
            "AZURE_API_KEY / AZURE_EMBEDDING_DEPLOYMENT must be configured to embed text"
        )

    vectors: list[list[float]] = []
    for start in range(0, len(texts), _BATCH_SIZE):
        batch = texts[start : start + _BATCH_SIZE]
        response = None
        last_error: BadRequestError | None = None
        for attempt in range(_MAX_EMBED_ATTEMPTS):
            try:
                response = litellm.embedding(
                    model=f"openai/{settings.azure_embedding_deployment}",
                    api_base=settings.azure_api_base,
                    api_key=settings.azure_api_key.get_secret_value(),
                    input=batch,
                )
                break
            except BadRequestError as exc:
                last_error = exc
                logger.warning(
                    "embeddings.transient_error", attempt=attempt + 1, error=str(exc)
                )
                if attempt < _MAX_EMBED_ATTEMPTS - 1:
                    time.sleep(_RETRY_BACKOFF_SECONDS * (2**attempt))
        if response is None:
            assert last_error is not None
            raise last_error
        for record in sorted(response.data, key=lambda r: r["index"]):
            vector = record["embedding"]
            if len(vector) != EMBEDDING_DIMENSIONS:
                raise ValueError(
                    f"embedding returned {len(vector)} dims, expected {EMBEDDING_DIMENSIONS}"
                )
            vectors.append(vector)
    logger.info("embeddings.embedded", text_count=len(texts))
    return vectors
