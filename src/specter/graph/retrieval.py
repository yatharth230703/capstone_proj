"""Hybrid GraphRAG retrieval (plan §6.5).

`local()` is deterministic Cypher k-hop expansion — no LLM. `global_()`
(vector search over community summaries) and `semantic()` (vector search
over EnforcementCase text) embed the query string via `graph/embeddings.py`
and query the `community_embedding`/`case_embedding` vector indexes
populated by `graph/summaries.py` / `graph/loader.load_enforcement_cases`.
Both degrade to an empty, logged result rather than raising when their index
is empty (e.g. no communities summarized yet) — but `hybrid()` no longer
gates on `AZURE_API_KEY` being configured, since it now is.

`hops` capped at 3, `limit` capped at 200 — hard-coded ceilings, not config
(plan §6.5: an unbounded expansion on a hub node returns the whole graph).
"""

from __future__ import annotations

import structlog
from neo4j import Driver

from specter.core.contracts import RetrievalResult, RetrievedItem
from specter.graph.embeddings import embed_texts
from specter.settings import Settings, get_settings

logger = structlog.get_logger(__name__)

MAX_HOPS = 3
MAX_LIMIT = 200


class GraphRetriever:
    def __init__(self, driver: Driver, settings: Settings | None = None) -> None:
        self._driver = driver
        self._settings = settings or get_settings()

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

    def _embed_query(self, query: str) -> list[float] | None:
        settings = self._settings
        if settings.azure_api_key is None or settings.azure_embedding_deployment is None:
            logger.info(
                "retrieval.embedding_unavailable",
                reason="AZURE_API_KEY/AZURE_EMBEDDING_DEPLOYMENT not configured",
            )
            return None
        return embed_texts([query], self._settings)[0]

    def _vector_search(
        self, index: str, item_type: str, id_prop: str, query: str, k: int
    ) -> list[RetrievedItem]:
        vector = self._embed_query(query)
        if vector is None:
            return []
        with self._driver.session() as session:
            records = session.run(
                f"""
                CALL db.index.vector.queryNodes('{index}', $k, $vector)
                YIELD node, score
                RETURN node, score
                """,
                k=k,
                vector=vector,
            ).data()
        if not records:
            logger.info("retrieval.vector_index_empty", index=index)
        return [
            RetrievedItem(
                item_type=item_type,
                data={
                    **{key: value for key, value in dict(r["node"]).items() if key != "embedding"},
                    "score": r["score"],
                },
                source_ids=[f"graph:{item_type.lower()}:{r['node'][id_prop]}"],
            )
            for r in records
        ]

    def global_(self, query: str, k: int = 5) -> RetrievalResult:
        items = self._vector_search("community_embedding", "Community", "community_id", query, k)
        return RetrievalResult(mode="global", items=items, query_text=query)

    def semantic(self, query: str, k: int = 10) -> RetrievalResult:
        items = self._vector_search("case_embedding", "EnforcementCase", "case_id", query, k)
        return RetrievalResult(mode="semantic", items=items, query_text=query)

    def hybrid(self, npi: str, query: str) -> RetrievalResult:
        local_result = self.local(npi)
        combined = list(local_result.items)
        combined.extend(self.global_(query).items)
        combined.extend(self.semantic(query).items)

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
