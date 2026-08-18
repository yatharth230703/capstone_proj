"""Graph read tools (plan §8) — these become ADK `FunctionTool`s in M5. Every
function is deterministic Cypher; no LLM involved. `hops`/`limit` follow the
same hard ceilings as `graph/retrieval.py` (plan §6.5) — an unbounded
expansion on a hub node returns the whole graph.
"""

from __future__ import annotations

from typing import Any, Literal

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

# Per-label business key, same `graph:<type>:<key>` scheme
# `evidence_tools.validate_citations` already resolves citations through —
# reused here as the node identifier `expand_neighborhood` hands out, so a
# graph-viz node id is always a real, resolvable citation, never a
# Neo4j-internal id exposed as if it were a business identifier.
_NODE_KEY_PROP = {
    "Provider": "npi",
    "Address": "normalized_key",
    "Phone": "e164",
    "Officer": "officer_id",
    "Exclusion": "exclusion_id",
    "Community": "community_id",
    "Taxonomy": "code",
    "EnforcementCase": "case_id",
}


def _node_ref(label: str, props: dict[str, Any]) -> str:
    key_prop = _NODE_KEY_PROP.get(label)
    key_value = props.get(key_prop) if key_prop else None
    if key_value is None:
        # A label this mapping doesn't know, or a node missing its own key
        # property — still needs *a* stable id to draw an edge to, so fall
        # back to the label alone rather than raising; this is a rendering
        # correlation key, not a claimed citation (CLAUDE.md hard rule 3 is
        # about identifiers presented as real-world facts, not this).
        return f"graph:{label.lower()}:unknown"
    return f"graph:{label.lower()}:{key_value}"


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
    """The provider itself plus every node reachable within `hops`
    relationships, and the real edges between them — `edges` was silently
    always `[]` until this fixed it; `tools/bindings.py`'s own docstring for
    this tool already promised "plus the edges connecting them" to the
    agent that calls it, so this was a real gap, not a deliberate omission.
    Each node/edge endpoint is a `graph:<label>:<key>` ref, the same scheme
    `evidence_tools.validate_citations` resolves — a rendering id that is
    always a real, citable identifier, never a raw internal one.
    """
    hops = min(hops, MAX_HOPS)
    limit = min(limit, MAX_LIMIT)
    node_query = f"""
        MATCH (start:Provider {{npi: $npi}})
        MATCH path = (start)-[*1..{hops}]-(other)
        WITH start, other, min(length(path)) AS hop_distance
        ORDER BY hop_distance
        LIMIT $limit
        RETURN start, elementId(start) AS start_id,
               other, labels(other) AS node_labels, hop_distance, elementId(other) AS element_id
    """
    with driver.session() as session:
        records = session.run(node_query, npi=npi, limit=limit).data()

    nodes: list[dict[str, Any]] = []
    element_id_to_ref: dict[str, str] = {}
    if records:
        element_id_to_ref[records[0]["start_id"]] = f"graph:provider:{npi}"
    for r in records:
        label = r["node_labels"][0] if r["node_labels"] else "Unknown"
        props = dict(r["other"])
        ref = _node_ref(label, props)
        element_id_to_ref[r["element_id"]] = ref
        nodes.append({"ref": ref, "item_type": label, "hop_distance": r["hop_distance"], **props})

    edges: list[dict[str, Any]] = []
    if element_id_to_ref:
        # Scoped by the exact element ids the node query already found —
        # never an unbounded scan of every relationship in the graph, which
        # a naive `MATCH (a)-[r]-(b)` with no node filter would be against a
        # graph carrying 119k+ Exclusion nodes.
        edge_query = """
            MATCH (a)-[r]-(b)
            WHERE elementId(a) IN $ids AND elementId(b) IN $ids AND elementId(a) < elementId(b)
            RETURN DISTINCT elementId(a) AS a_id, elementId(b) AS b_id, type(r) AS rel_type
        """
        with driver.session() as session:
            edge_records = session.run(
                edge_query, ids=list(element_id_to_ref)
            ).data()
        for r in edge_records:
            edges.append(
                {
                    "source": element_id_to_ref[r["a_id"]],
                    "target": element_id_to_ref[r["b_id"]],
                    "rel_type": r["rel_type"],
                }
            )

    return Subgraph(center_npi=npi, nodes=nodes, edges=edges)


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
