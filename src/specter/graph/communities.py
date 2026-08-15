"""Provider co-occurrence communities via Leiden (plan §6.3). Deliberately
hand-rolled instead of the `graphrag` pip package — ~150 lines, fully
explainable in a demo, no opinionated framework to defend.

Communities are recomputed from scratch each run — `RANDOM_SEED` is fixed so
re-running against an unchanged graph is deterministic (plan's own pitfall
table: "Community summaries change every run | Non-determinism in Leiden |
Set random_state"). `community_id` is a hash of the sorted member NPI list,
so the same membership always gets the same ID across runs too.
"""

from __future__ import annotations

import random

import igraph
import structlog
from neo4j import Driver

from specter.core.hashing import sha256_text

logger = structlog.get_logger(__name__)

MIN_COMMUNITY_SIZE = 3
MAX_COMMUNITY_SIZE = 200
RANDOM_SEED = 20260101

_COOCCURRENCE_QUERY = """
MATCH (p1:Provider)-[:LOCATED_AT|HAS_PHONE|HAS_OFFICER]->(shared)
      <-[:LOCATED_AT|HAS_PHONE|HAS_OFFICER]-(p2:Provider)
WHERE p1.npi < p2.npi
WITH p1.npi AS npi1, p2.npi AS npi2, count(DISTINCT labels(shared)) AS weight
RETURN npi1, npi2, weight
"""


def _fetch_cooccurrence_graph(driver: Driver) -> igraph.Graph:
    with driver.session() as session:
        provider_npis = [r["npi"] for r in session.run("MATCH (p:Provider) RETURN p.npi AS npi")]
        pairs = list(session.run(_COOCCURRENCE_QUERY))

    npis = sorted(provider_npis)
    index = {npi: i for i, npi in enumerate(npis)}
    edges = [(index[row["npi1"]], index[row["npi2"]]) for row in pairs]
    weights = [row["weight"] for row in pairs]

    graph = igraph.Graph(n=len(npis), edges=edges)
    graph.vs["npi"] = npis
    graph.es["weight"] = weights
    return graph


def compute_communities(driver: Driver) -> list[list[str]]:
    """Returns communities as lists of NPIs, already filtered to
    [MIN_COMMUNITY_SIZE, MAX_COMMUNITY_SIZE] — "the giant component is noise"
    (plan §6.3).
    """
    graph = _fetch_cooccurrence_graph(driver)
    if graph.ecount() == 0:
        logger.warning("communities.no_cooccurrence_edges")
        return []

    random.seed(RANDOM_SEED)
    igraph.set_random_number_generator(random)
    clustering = graph.community_leiden(
        objective_function="modularity", weights="weight", n_iterations=-1
    )

    communities: list[list[str]] = []
    for member_indices in clustering:
        if MIN_COMMUNITY_SIZE <= len(member_indices) <= MAX_COMMUNITY_SIZE:
            communities.append(sorted(graph.vs[i]["npi"] for i in member_indices))

    logger.info(
        "communities.computed",
        total_clusters=len(clustering),
        surviving_communities=len(communities),
        discarded=len(clustering) - len(communities),
    )
    return communities


def write_communities(driver: Driver, communities: list[list[str]]) -> int:
    rows = []
    for members in communities:
        community_id = sha256_text("|".join(members))[:24]
        rows.append(
            {"community_id": community_id, "members": members, "member_count": len(members)}
        )

    with driver.session() as session:
        session.run("MATCH ()-[r:IN_COMMUNITY]->() DELETE r")
        session.run("MATCH (cm:Community) DETACH DELETE cm")
        for row in rows:
            session.run(
                """
                MERGE (cm:Community {community_id: $community_id})
                SET cm.member_count = $member_count
                WITH cm
                UNWIND $members AS npi
                MATCH (p:Provider {npi: npi})
                MERGE (p)-[:IN_COMMUNITY]->(cm)
                """,
                community_id=row["community_id"],
                member_count=row["member_count"],
                members=row["members"],
            )
    logger.info("communities.written", count=len(rows))
    return len(rows)


def build_communities(driver: Driver) -> int:
    communities = compute_communities(driver)
    return write_communities(driver, communities)
