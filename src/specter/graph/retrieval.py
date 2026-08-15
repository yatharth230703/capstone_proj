"""Hybrid GraphRAG retrieval (plan §6.5).

`local()` is deterministic Cypher k-hop expansion — no LLM, fully
implemented. `global_()` (vector search over community summaries) and
`semantic()` (vector search over EnforcementCase text) both need to embed the
query string via the Azure `text-embedding-3-large` deployment, and need
`graph/embeddings.py` / `graph/summaries.py` to have populated the vector
indexes in the first place. Neither `AZURE_API_KEY` nor
`AZURE_EMBEDDING_DEPLOYMENT` is configured yet, so both are wired (correct
signature, correct `RetrievalResult` shape) but return empty results with a
logged reason rather than raising — `hybrid()` degrades to local-only rather
than crashing when they're unavailable.

`hops` capped at 3, `limit` capped at 200 — hard-coded ceilings, not config
(plan §6.5: an unbounded expansion on a hub node returns the whole graph).
"""

from __future__ import annotations

import structlog
from neo4j import Driver

from specter.core.contracts import RetrievalResult, RetrievedItem
from specter.settings import get_settings

logger = structlog.get_logger(__name__)

MAX_HOPS = 3
MAX_LIMIT = 200


class GraphRetriever:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def local(self, npi: str, hops: int = 2, limit: int = 50) -> RetrievalResult:
        hops = min(hops, MAX_HOPS)
        limit = min(limit, MAX_LIMIT)
        query = f"""
            MATCH (start:Provider {{npi: $npi}})
            MATCH path = (start)-[*1..{hops}]-(other)
            WITH DISTINCT other, min(length(path)) AS hop_distance
            RETURN other, labels(other) AS node_labels, hop_distance
            ORDER BY hop_distance
            LIMIT $limit
        """
        with self._driver.session() as session:
            records = list(session.run(query, npi=npi, limit=limit))

        items = [
            RetrievedItem(
                item_type=record["node_labels"][0] if record["node_labels"] else "unknown",
                data=dict(record["other"]),
                source_ids=(
                    [record["other"]["source_id"]] if record["other"].get("source_id") else []
                ),
                hop_distance=record["hop_distance"],
            )
            for record in records
        ]
        return RetrievalResult(mode="local", items=items, query_npi=npi)

    def global_(self, query: str, k: int = 5) -> RetrievalResult:
        logger.warning(
            "retrieval.global_unavailable",
            reason="community summaries/embeddings not populated (needs AZURE_API_KEY)",
        )
        return RetrievalResult(mode="global", items=[], query_text=query)

    def semantic(self, query: str, k: int = 10) -> RetrievalResult:
        logger.warning(
            "retrieval.semantic_unavailable",
            reason="EnforcementCase embeddings not populated (needs AZURE_API_KEY)",
        )
        return RetrievalResult(mode="semantic", items=[], query_text=query)

    def hybrid(self, npi: str, query: str) -> RetrievalResult:
        local_result = self.local(npi)
        combined = list(local_result.items)

        settings = get_settings()
        if settings.azure_api_key is not None:
            combined.extend(self.global_(query).items)
            combined.extend(self.semantic(query).items)
        else:
            logger.info("retrieval.hybrid_local_only", reason="AZURE_API_KEY not configured")

        deduped: list[RetrievedItem] = []
        seen: set[str] = set()
        for item in combined:
            identifier = (
                item.data.get("npi")
                or item.data.get("normalized_key")
                or item.data.get("e164")
                or item.data.get("officer_id")
                or item.data.get("community_id")
                or item.data.get("case_id")
                or item.data.get("exclusion_id")
            )
            key = f"{item.item_type}:{identifier}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        return RetrievalResult(mode="hybrid", items=deduped, query_npi=npi, query_text=query)
