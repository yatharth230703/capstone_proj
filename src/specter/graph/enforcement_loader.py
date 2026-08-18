"""Loads `data/snapshot/doj/data.parquet` into `EnforcementCase` nodes (plan
§5.3/§6). Split out of `graph/loader.py` to keep that module under CLAUDE.md's
400-line ceiling — `load_snapshot` calls `load_enforcement_cases` directly.

Never creates a `MENTIONED_IN` edge to a Provider: DOJ press releases don't
carry an NPI, and matching a release to a provider is an entity-resolution
judgment call (plan §9.5, the Enforcement Intelligence Agent, M3), not
something a deterministic loader should guess at.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import structlog
from neo4j import Driver

from specter.core.contracts import CaseLegalStatus
from specter.core.enums import DataOrigin, LegalStatus
from specter.core.errors import SpecterError
from specter.core.hashing import sha256_text
from specter.graph.embeddings import embed_texts
from specter.settings import Settings

logger = structlog.get_logger(__name__)

_LEGAL_STATUS_KEYWORDS: list[tuple[re.Pattern[str], LegalStatus]] = [
    (
        re.compile(r"pleads? guilty|pled guilty|found guilty|sentenced|convicted", re.I),
        LegalStatus.CONVICTED,
    ),
    (re.compile(r"settl|agrees? to pay|reache[sd] .*agreement", re.I), LegalStatus.SETTLED),
    (re.compile(r"indict|charged|charges|arrested", re.I), LegalStatus.CHARGED),
    (re.compile(r"dismiss", re.I), LegalStatus.DISMISSED),
]


def infer_legal_status(text: str) -> LegalStatus:
    """Deterministic keyword heuristic over a DOJ release's title+description.

    This is a loader, not an agent — no LLM call belongs here. Conservative
    default of `ALLEGED` (the weakest claim) when no keyword matches; M3's
    Enforcement Intelligence Agent re-adjudicates `legal_status` from the full
    text with the real `extract_enforcement_case` LLM call. This heuristic
    only has to be good enough to satisfy the schema without ever
    overclaiming (CLAUDE.md hard rule 6).
    """
    for pattern, status in _LEGAL_STATUS_KEYWORDS:
        if pattern.search(text):
            return status
    return LegalStatus.ALLEGED


def load_enforcement_cases(driver: Driver, snapshot_dir: Path, settings: Settings) -> int:
    """Loads `data/snapshot/doj/data.parquet` into `EnforcementCase` nodes and
    embeds each into `case_embedding`.
    """
    data_path = snapshot_dir / "doj" / "data.parquet"
    if not data_path.exists():
        logger.warning("graph.doj_snapshot_missing", path=str(data_path))
        return 0

    df = pl.read_parquet(data_path)
    ingested_at = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []
    for record in df.to_dicts():
        guid = record.get("guid") or record.get("link")
        if not guid:
            continue
        title = record.get("title") or ""
        description = record.get("description") or ""
        pub_date = record.get("pub_date")
        pub_date_str = pub_date.isoformat() if pub_date else None
        rows.append(
            {
                "case_id": sha256_text(f"doj|{guid}")[:24],
                "title": title,
                "description": description,
                "link": record.get("link"),
                "legal_status": infer_legal_status(f"{title} {description}").value,
                "pub_date": pub_date_str,
                "data_origin": DataOrigin.PUBLIC.value,
                "source_id": "doj",
                "observed_at": pub_date_str or "",
                "ingested_at": ingested_at,
                "confidence": 1.0,
            }
        )
    if not rows:
        logger.warning("graph.doj_snapshot_empty", path=str(data_path))
        return 0

    with driver.session() as session:
        session.run(
            """
            UNWIND $rows AS row
            MERGE (c:EnforcementCase {case_id: row.case_id})
            SET c.title = row.title, c.description = row.description, c.link = row.link,
                c.legal_status = row.legal_status, c.pub_date = row.pub_date,
                c.data_origin = row.data_origin, c.source_id = row.source_id,
                c.observed_at = row.observed_at, c.ingested_at = row.ingested_at,
                c.confidence = row.confidence
            """,
            rows=rows,
        )

    texts = [f"{row['title']} {row['description']}".strip() for row in rows]
    vectors = embed_texts(texts, settings)
    embed_rows = [
        {"case_id": row["case_id"], "vector": vector}
        for row, vector in zip(rows, vectors, strict=True)
    ]
    with driver.session() as session:
        session.run(
            """
            UNWIND $rows AS row
            MATCH (c:EnforcementCase {case_id: row.case_id})
            CALL db.create.setNodeVectorProperty(c, 'embedding', row.vector)
            """,
            rows=embed_rows,
        )

    logger.info("graph.enforcement_cases_loaded", count=len(rows))
    return len(rows)


def update_legal_status_from_adjudications(
    driver: Driver, adjudications: list[CaseLegalStatus]
) -> int:
    """Writes the Enforcement Intelligence Agent's real per-match
    adjudication (`CasePacket.legal_status_per_match`, plan §9.5) onto the
    `EnforcementCase` node it corresponds to (BUILD_MILESTONES.md debt D-10).

    `infer_legal_status`'s keyword heuristic is a conservative default for a
    case no agent has ever adjudicated — CLAUDE.md hard rule 6 means it must
    never overclaim, so it defaults to `ALLEGED`. Once a real adjudication
    exists for a case, the node should carry that, not keep serving the
    heuristic's guess to every future reader who queries the graph directly
    instead of going through a `CasePacket`. Every `case_id` here already
    resolved through `evidence_tools.validate_citations` before the packet
    was assembled, so a `MATCH` that doesn't hit is a real bug — fails
    loudly (hard rule 7) rather than silently dropping the write.
    """
    if not adjudications:
        return 0
    rows = [{"case_id": a.case_id, "legal_status": a.legal_status.value} for a in adjudications]
    with driver.session() as session:
        record = session.run(
            """
            UNWIND $rows AS row
            MATCH (c:EnforcementCase {case_id: row.case_id})
            SET c.legal_status = row.legal_status
            RETURN count(c) AS n
            """,
            rows=rows,
        ).single()
    updated = int(record["n"]) if record else 0
    if updated != len(rows):
        raise SpecterError(
            f"legal_status write-back matched {updated}/{len(rows)} EnforcementCase nodes — "
            f"a case_id in {sorted({r['case_id'] for r in rows})} doesn't resolve to a real "
            "graph node (CLAUDE.md hard rule 3: no fabricated identifiers)"
        )
    logger.info("graph.legal_status_updated", count=updated)
    return updated
