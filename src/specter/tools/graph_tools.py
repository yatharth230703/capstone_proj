"""Graph read tools (plan §8) — these become ADK `FunctionTool`s in M5. Every
function is deterministic Cypher; no LLM involved. `hops`/`limit` follow the
same hard ceilings as `graph/retrieval.py` (plan §6.5) — an unbounded
expansion on a hub node returns the whole graph.
"""

from __future__ import annotations

from typing import Literal

import structlog
from neo4j import Driver

from specter.core.contracts import (
    CommunitySummary,
    EnforcementCaseHit,
    PathResult,
    PeerLink,
    ProviderProfile,
    Subgraph,
)

logger = structlog.get_logger(__name__)

MAX_HOPS = 3
MAX_LIMIT = 200

_ATTRIBUTE_REL = {"address": "LOCATED_AT", "phone": "HAS_PHONE", "officer": "HAS_OFFICER"}
_ATTRIBUTE_KEY_PROP = {
    "address": ("Address", "normalized_key"),
    "phone": ("Phone", "e164"),
    "officer": ("Officer", "officer_id"),
}


def get_provider_profile(driver: Driver, npi: str) -> ProviderProfile | None:
    with driver.session() as session:
        record = session.run(
            """
            MATCH (p:Provider {npi: $npi})
            OPTIONAL MATCH (p)-[:LOCATED_AT]->(a:Address)
            OPTIONAL MATCH (p)-[:HAS_PHONE]->(ph:Phone)
            OPTIONAL MATCH (p)-[:HAS_OFFICER]->(o:Officer)
            OPTIONAL MATCH (p)-[:HAS_TAXONOMY]->(t:Taxonomy)
            OPTIONAL MATCH (p)-[:EXCLUDED_BY]->(e:Exclusion)
            RETURN p,
                   collect(DISTINCT a {.*}) AS addresses,
                   collect(DISTINCT ph.e164) AS phones,
                   collect(DISTINCT o {.*}) AS officers,
                   collect(DISTINCT t {.*}) AS taxonomies,
                   collect(DISTINCT e {.*}) AS exclusions
            """,
            npi=npi,
        ).single()
    if record is None or record["p"] is None:
        return None
    provider = record["p"]
    return ProviderProfile(
        npi=provider["npi"],
        organization_name=provider.get("organization_name"),
        entity_type=provider.get("entity_type"),
        state=provider.get("state"),
        status=provider.get("status"),
        enumeration_date=provider.get("enumeration_date"),
        addresses=[a for a in record["addresses"] if a],
        phones=[p for p in record["phones"] if p],
        officers=[o for o in record["officers"] if o],
        taxonomies=[t for t in record["taxonomies"] if t],
        exclusions=[e for e in record["exclusions"] if e],
        source_ids=[f"graph:provider:{npi}"],
    )


def expand_neighborhood(driver: Driver, npi: str, hops: int = 2, limit: int = 50) -> Subgraph:
    hops = min(hops, MAX_HOPS)
    limit = min(limit, MAX_LIMIT)
    query = f"""
        MATCH (start:Provider {{npi: $npi}})
        MATCH path = (start)-[*1..{hops}]-(other)
        WITH DISTINCT other, min(length(path)) AS hop_distance
        ORDER BY hop_distance
        LIMIT $limit
        RETURN other, labels(other) AS node_labels, hop_distance
    """
    with driver.session() as session:
        records = session.run(query, npi=npi, limit=limit).data()
    nodes = [
        {"item_type": r["node_labels"][0] if r["node_labels"] else "unknown",
         "hop_distance": r["hop_distance"], **dict(r["other"])}
        for r in records
    ]
    return Subgraph(center_npi=npi, nodes=nodes, edges=[])


def find_shared_attribute_peers(
    driver: Driver, npi: str, attribute: Literal["address", "phone", "officer"]
) -> list[PeerLink]:
    rel = _ATTRIBUTE_REL[attribute]
    label, key_prop = _ATTRIBUTE_KEY_PROP[attribute]
    query = f"""
        MATCH (p:Provider {{npi: $npi}})-[:{rel}]->(attr:{label})
        MATCH (attr)<-[:{rel}]-(peer:Provider)
        WHERE peer.npi <> p.npi
        RETURN DISTINCT peer.npi AS peer_npi, attr.{key_prop} AS shared_value
    """
    with driver.session() as session:
        records = session.run(query, npi=npi).data()
    return [
        PeerLink(
            peer_npi=r["peer_npi"], attribute=attribute, shared_value=r["shared_value"],
            source_ids=[f"graph:{attribute}:{r['shared_value']}"],
        )
        for r in records
    ]


def shortest_path_to_exclusion(
    driver: Driver, npi: str, max_hops: int = 4
) -> PathResult | None:
    # exclusion_proximity's own ceiling is MAX_HOPS; allow +1 margin here
    max_hops = min(max_hops, MAX_HOPS + 1)
    with driver.session() as session:
        record = session.run(
            f"""
            MATCH (p:Provider {{npi: $npi}})
            MATCH path = shortestPath((p)-[*1..{max_hops}]-(e:Exclusion))
            RETURN e.exclusion_id AS exclusion_id, length(path) AS hops,
                   [n IN nodes(path) | coalesce(n.npi, n.normalized_key, n.e164,
                                                  n.officer_id, n.exclusion_id,
                                                  n.community_id, 'unknown')] AS path_ids
            """,
            npi=npi,
        ).single()
    if record is None:
        return None
    return PathResult(
        target_type="exclusion", target_id=record["exclusion_id"], hops=record["hops"],
        path_node_ids=record["path_ids"],
    )


def get_community_context(driver: Driver, npi: str) -> CommunitySummary | None:
    """Structural facts are always recomputed fresh from Cypher — they never
    go stale. `characterization`/`notable_members`/`risk_themes` are read
    alongside them from the Community node's persisted properties (written by
    `graph/summaries.summarize_communities`, M2); they are `None`/empty when
    a community hasn't been characterized yet, which is a valid state, not
    a bug (debt D-9).
    """
    with driver.session() as session:
        record = session.run(
            """
            MATCH (p:Provider {npi: $npi})-[:IN_COMMUNITY]->(cm:Community)
            MATCH (cm)<-[:IN_COMMUNITY]-(member:Provider)
            OPTIONAL MATCH (member)-[:EXCLUDED_BY]->(:Exclusion)
            WITH cm, collect(DISTINCT member) AS members,
                 count(DISTINCT CASE WHEN (member)-[:EXCLUDED_BY]->(:Exclusion)
                                      THEN member END) AS excluded_count
            RETURN cm.community_id AS community_id, size(members) AS member_count,
                   excluded_count, [m IN members | m.state] AS states,
                   cm.characterization AS characterization,
                   cm.notable_members AS notable_members,
                   cm.risk_themes AS risk_themes,
                   cm.generated_at AS generated_at,
                   cm.prompt_version AS prompt_version
            """,
            npi=npi,
        ).single()
    if record is None:
        return None
    states = sorted({s for s in record["states"] if s})
    structural_facts = [
        f"member_count={record['member_count']}",
        f"excluded_member_count={record['excluded_count']}",
        f"state_spread={','.join(states)}",
    ]
    return CommunitySummary(
        community_id=record["community_id"], member_count=record["member_count"],
        structural_facts=structural_facts,
        characterization=record["characterization"],
        notable_members=record["notable_members"] or [],
        risk_themes=record["risk_themes"] or [],
        generated_at=record["generated_at"],
        prompt_version=record["prompt_version"],
    )


def search_enforcement_cases(driver: Driver, query: str, k: int = 10) -> list[EnforcementCaseHit]:
    """Deterministic keyword search over `EnforcementCase.title`/`description`
    — real semantic (vector) search is `graph/retrieval.py`'s `semantic()`,
    which needs AZURE_EMBEDDING_DEPLOYMENT (not configured yet). This always
    returns `[]` today since no `EnforcementCase` nodes are loaded — matching
    a DOJ release to a provider is the Enforcement Intelligence Agent's job
    (plan §9.5, M5), not a deterministic loader's.
    """
    with driver.session() as session:
        records = session.run(
            """
            MATCH (c:EnforcementCase)
            WHERE toLower(c.title) CONTAINS toLower($search_text)
               OR toLower(c.description) CONTAINS toLower($search_text)
            RETURN c.case_id AS case_id, c.title AS title, c.description AS description
            LIMIT $k
            """,
            search_text=query, k=min(k, MAX_LIMIT),
        ).data()
    return [
        EnforcementCaseHit(
            case_id=r["case_id"], title=r["title"], snippet=(r["description"] or "")[:280],
            source_ids=[f"graph:enforcement_case:{r['case_id']}"],
        )
        for r in records
    ]
