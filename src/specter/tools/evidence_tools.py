"""Evidence artifact storage + citation validation (plan §8). CLAUDE.md hard
rule 3: a claim without `source_ids` is a bug, not a soft warning —
`validate_citations` is what actually enforces that, by checking every
`source_ids` entry resolves to something real.

`source_ids` come in two shapes: `graph:<type>:<key>` (resolved against a
live Neo4j node) or a bare artifact_id (resolved against `evidence_dir`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import structlog
from neo4j import Driver

from specter.core.contracts import Citation, CitationReport, EvidenceArtifact
from specter.core.hashing import sha256_text

logger = structlog.get_logger(__name__)

_GRAPH_LABEL_KEY = {
    "provider": ("Provider", "npi"),
    "address": ("Address", "normalized_key"),
    "phone": ("Phone", "e164"),
    "officer": ("Officer", "officer_id"),
    "exclusion": ("Exclusion", "exclusion_id"),
    "community": ("Community", "community_id"),
    "enforcement_case": ("EnforcementCase", "case_id"),
}


def store_artifact(
    content: str,
    content_type: str,
    source_id: str,
    evidence_dir: Path,
    extraction_method: str,
) -> EvidenceArtifact:
    artifact_id = sha256_text(content)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    stored_path = evidence_dir / f"{artifact_id}.txt"
    stored_path.write_text(content, encoding="utf-8")
    logger.info("evidence.stored", artifact_id=artifact_id, source_id=source_id)
    return EvidenceArtifact(
        artifact_id=artifact_id, content_type=content_type, source_id=source_id,
        stored_path=stored_path, created_at=datetime.now(UTC),
        extraction_method=extraction_method,
    )


def cite(artifact_id: str, claim: str) -> Citation:
    return Citation(artifact_id=artifact_id, claim=claim)


def _resolves_to_graph_node(driver: Driver, source_id: str) -> bool:
    parts = source_id.split(":", 2)
    if len(parts) != 3 or parts[0] != "graph":
        return False
    node_type, key = parts[1], parts[2]
    mapping = _GRAPH_LABEL_KEY.get(node_type)
    if mapping is None:
        return False
    label, key_prop = mapping
    query = f"MATCH (n:{label} {{{key_prop}: $key}}) RETURN n LIMIT 1"
    with driver.session() as session:
        return session.run(query, key=key).single() is not None


def _resolves_to_artifact(source_id: str, evidence_dir: Path) -> bool:
    return (evidence_dir / f"{source_id}.txt").exists()


def validate_citations(
    source_ids: list[str], driver: Driver, evidence_dir: Path
) -> CitationReport:
    """Run before a case is emitted (plan §8). Takes a flat `source_ids`
    list rather than a full `CasePacket` — that contract doesn't exist until
    M6+ builds the workflow that assembles one; this validates whatever
    citation set is handed to it, which is the reusable part.
    """
    unresolved = [
        source_id
        for source_id in source_ids
        if not (
            _resolves_to_graph_node(driver, source_id)
            if source_id.startswith("graph:")
            else _resolves_to_artifact(source_id, evidence_dir)
        )
    ]
    total = len(source_ids)
    resolved = total - len(unresolved)
    if unresolved:
        logger.warning("citations.unresolved", unresolved_source_ids=unresolved)
    return CitationReport(
        total_citations=total, resolved_citations=resolved,
        unresolved_source_ids=unresolved, all_resolved=not unresolved,
    )
