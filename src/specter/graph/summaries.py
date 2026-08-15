"""Community summarization (plan §6.4). Two independent stages, run
separately because they have different cost/failure profiles:

    summarize_communities()  T1 LLM call per community — writes
                              characterization/notable_members/risk_themes
                              onto the Community node. No embedding.
    embed_communities()      Embeds the persisted characterization text into
                              `community_embedding`. Cheap; safe to re-run.

`structural_facts` is deterministic Cypher, independently testable without
an LLM — it is what the model is forbidden to alter (CLAUDE.md hard rule 1).
`notable_members` in the LLM's raw output is unvalidated; any NPI not
actually in the community is dropped and logged (hard rule 2).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import structlog
from neo4j import Driver

from specter.agents._base import AgentRuntime, build_agent, run_agent
from specter.core.contracts import CommunityCharacterization, CommunitySummary, EvidenceBundle
from specter.graph.embeddings import embed_texts
from specter.settings import Settings

logger = structlog.get_logger(__name__)

AGENT_NAME = "community_summarizer"
TASK_CLASS = "summarize_community"
INSTRUCTION_FILE = "community_summarizer.md"

_TASK_INSTRUCTION = (
    "Characterize this provider community from the structural_facts and "
    "member_npis below. Return a CommunityCharacterization: a characterization "
    "of at most 3 sentences, notable_members drawn only from member_npis, and "
    "risk_themes grounded in structural_facts."
)

_FACTS_QUERY = """
MATCH (cm:Community {community_id: $community_id})<-[:IN_COMMUNITY]-(p:Provider)
OPTIONAL MATCH (p)-[:LOCATED_AT]->(a:Address)
OPTIONAL MATCH (p)-[:HAS_OFFICER]->(o:Officer)
RETURN collect(DISTINCT p.npi) AS member_npis,
       count(DISTINCT p) AS member_count,
       count(DISTINCT CASE WHEN (p)-[:EXCLUDED_BY]->(:Exclusion) THEN p END) AS excluded_count,
       min(p.enumeration_date) AS min_enum_date,
       max(p.enumeration_date) AS max_enum_date,
       collect(DISTINCT p.state) AS states,
       count(DISTINCT a) AS distinct_addresses,
       count(DISTINCT o) AS distinct_officers
"""


def list_community_ids(driver: Driver, limit: int | None = None) -> list[str]:
    query = "MATCH (cm:Community) RETURN cm.community_id AS community_id ORDER BY cm.community_id"
    if limit is not None:
        query += " LIMIT $limit"
    with driver.session() as session:
        return [r["community_id"] for r in session.run(query, limit=limit)]


def community_facts(driver: Driver, community_id: str) -> tuple[list[str], list[str]]:
    """Deterministic structural facts for one community, plus its member NPI
    list. Pure Cypher read, no LLM — independently testable.
    """
    with driver.session() as session:
        record = session.run(_FACTS_QUERY, community_id=community_id).single()
    # Cypher aggregates (count/collect) always return exactly one row, even
    # when the MATCH found nothing — .single() is never None here, so an
    # empty member_npis list is what "community doesn't exist" looks like.
    if record is None or not record["member_npis"]:
        raise ValueError(f"community {community_id!r} not found")

    member_npis = sorted(record["member_npis"])
    states = sorted(s for s in record["states"] if s)
    facts = sorted(
        [
            f"member_count={record['member_count']}",
            f"distinct_shared_addresses={record['distinct_addresses']}",
            f"distinct_shared_officers={record['distinct_officers']}",
            f"excluded_member_count={record['excluded_count']}",
            f"enumeration_date_range={record['min_enum_date'] or 'unknown'}"
            f"..{record['max_enum_date'] or 'unknown'}",
            f"state_spread={','.join(states)}",
        ]
    )
    return facts, member_npis


async def summarize_communities(
    driver: Driver, runtime: AgentRuntime, *, limit: int | None = None
) -> int:
    """One T1 call per community (plan §6.4). Costs real money at scale —
    callers should pass `limit` while developing.
    """
    community_ids = list_community_ids(driver, limit)
    if not community_ids:
        logger.warning("summaries.no_communities")
        return 0

    agent = build_agent(
        name=AGENT_NAME,
        task_class=TASK_CLASS,
        instruction_file=INSTRUCTION_FILE,
        tools=[],
        output_schema=CommunityCharacterization,
        runtime=runtime,
    )

    rows: list[dict[str, object]] = []
    generated_at = datetime.now(UTC).isoformat()
    for community_id in community_ids:
        facts, member_npis = community_facts(driver, community_id)
        evidence = EvidenceBundle(
            provider_npi="",
            evidence={
                "community_id": community_id,
                "structural_facts": facts,
                "member_npis": member_npis,
            },
            task_instruction=_TASK_INSTRUCTION,
        )
        result = await run_agent(agent, TASK_CLASS, evidence, runtime, CommunityCharacterization)
        output = CommunityCharacterization.model_validate(result.output)

        member_set = set(member_npis)
        notable = sorted(npi for npi in output.notable_members if npi in member_set)
        fabricated = sorted(set(output.notable_members) - member_set)
        if fabricated:
            logger.warning(
                "summaries.dropped_fabricated_members",
                community_id=community_id,
                fabricated=fabricated,
            )

        summary = CommunitySummary(
            community_id=community_id,
            member_count=len(member_npis),
            structural_facts=facts,
            characterization=output.characterization,
            notable_members=notable,
            risk_themes=sorted(output.risk_themes),
            generated_at=datetime.now(UTC),
            prompt_version=runtime.compiler.compile(
                AGENT_NAME, TASK_CLASS, evidence
            ).prompt_version,
        )
        rows.append(
            {
                "community_id": summary.community_id,
                "characterization": summary.characterization,
                "notable_members": summary.notable_members,
                "risk_themes": summary.risk_themes,
                "generated_at": generated_at,
                "prompt_version": summary.prompt_version,
            }
        )

    with driver.session() as session:
        session.run(
            """
            UNWIND $rows AS row
            MATCH (cm:Community {community_id: row.community_id})
            SET cm.characterization = row.characterization,
                cm.notable_members = row.notable_members,
                cm.risk_themes = row.risk_themes,
                cm.generated_at = row.generated_at,
                cm.prompt_version = row.prompt_version
            """,
            rows=rows,
        )
    logger.info("summaries.communities_summarized", count=len(rows))
    return len(rows)


def embed_communities(driver: Driver, settings: Settings) -> int:
    """Embeds `characterization + risk_themes` into `community_embedding` for
    every Community node that has a characterization. Idempotent — safe to
    re-run after `summarize_communities` adds more.
    """
    with driver.session() as session:
        records = session.run(
            """
            MATCH (cm:Community)
            WHERE cm.characterization IS NOT NULL
            RETURN cm.community_id AS community_id, cm.characterization AS characterization,
                   cm.risk_themes AS risk_themes
            ORDER BY cm.community_id
            """
        ).data()
    if not records:
        logger.warning("summaries.no_characterized_communities")
        return 0

    texts = [
        f"{r['characterization']} {' '.join(r['risk_themes'] or [])}".strip() for r in records
    ]
    vectors = embed_texts(texts, settings)
    rows = [
        {"community_id": r["community_id"], "vector": vector}
        for r, vector in zip(records, vectors, strict=True)
    ]
    with driver.session() as session:
        session.run(
            """
            UNWIND $rows AS row
            MATCH (cm:Community {community_id: row.community_id})
            CALL db.create.setNodeVectorProperty(cm, 'embedding', row.vector)
            """,
            rows=rows,
        )
    logger.info("summaries.communities_embedded", count=len(rows))
    return len(rows)


def render_b2_community_summaries(driver: Driver, cap: int) -> str:
    """Generates the B2 prompt block body: the top `cap` communities by
    member_count, sorted by community_id, `json.dumps(..., sort_keys=True)`.
    Written to `prompts/blocks/b2_community_summaries.md` by
    `scripts/30_build_communities.py` — never rendered live by
    `PromptCompiler`, which has no Neo4j driver and must stay offline-testable.
    """
    with driver.session() as session:
        total_record = session.run(
            "MATCH (cm:Community) WHERE cm.characterization IS NOT NULL RETURN count(cm) AS n"
        ).single()
        assert total_record is not None  # count() always returns exactly one row
        total = total_record["n"]
        records = session.run(
            """
            MATCH (cm:Community)
            WHERE cm.characterization IS NOT NULL
            RETURN cm.community_id AS community_id, cm.member_count AS member_count,
                   cm.characterization AS characterization, cm.risk_themes AS risk_themes,
                   cm.notable_members AS notable_members
            ORDER BY cm.member_count DESC, cm.community_id ASC
            LIMIT $cap
            """,
            cap=cap,
        ).data()

    selected = sorted(records, key=lambda r: r["community_id"])
    payload = {
        "cap": cap,
        "shown_count": len(selected),
        "total_summarized_communities": total,
        "summaries": [
            {
                "community_id": r["community_id"],
                "member_count": r["member_count"],
                "characterization": r["characterization"],
                "risk_themes": sorted(r["risk_themes"] or []),
                "notable_members": sorted(r["notable_members"] or []),
            }
            for r in selected
        ],
    }
    return json.dumps(payload, sort_keys=True)
