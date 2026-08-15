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

import litellm
import structlog

from specter.settings import Settings

logger = structlog.get_logger(__name__)

EMBEDDING_DIMENSIONS = 3072
_BATCH_SIZE = 64


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
        response = litellm.embedding(
            model=f"openai/{settings.azure_embedding_deployment}",
            api_base=settings.azure_api_base,
            api_key=settings.azure_api_key.get_secret_value(),
            input=batch,
        )
        for record in sorted(response.data, key=lambda r: r["index"]):
            vector = record["embedding"]
            if len(vector) != EMBEDDING_DIMENSIONS:
                raise ValueError(
                    f"embedding returned {len(vector)} dims, expected {EMBEDDING_DIMENSIONS}"
                )
            vectors.append(vector)
    logger.info("embeddings.embedded", text_count=len(texts))
    return vectors
