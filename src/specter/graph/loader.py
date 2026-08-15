"""Loads `data/snapshot/` (plan §5.3's frozen snapshot — never `data/raw/`)
into Neo4j per `graph/schema.cypher`.

Scope for M2: Provider, Address, Phone, Officer, Taxonomy, Exclusion,
DataSource nodes and LOCATED_AT/HAS_PHONE/HAS_OFFICER/HAS_TAXONOMY/
EXCLUDED_BY edges. `EnforcementCase` loading is deliberately not here — DOJ
press releases don't carry an NPI, matching a release to a provider is an
entity-resolution judgment call (plan §9.5, the Enforcement Intelligence
Agent), not something a deterministic loader should guess at.

`--hide-labels` (plan §12.1): `hidden_npis` skips creating `EXCLUDED_BY`
edges for the given NPIs (the Exclusion node itself is still loaded) so those
providers' ground-truth labels are invisible to the screening pipeline but
still available to `judge/detection_eval.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import structlog
from neo4j import Driver

from specter.core.contracts import SourceManifest
from specter.core.enums import DataOrigin, EntityType, ExclusionAuthority
from specter.core.hashing import sha256_text
from specter.tools.entity_tools import normalize_address, normalize_phone

logger = structlog.get_logger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.cypher"
_BATCH_SIZE = 1000


def apply_schema(driver: Driver) -> None:
    raw = _SCHEMA_PATH.read_text()
    no_comments = "\n".join(
        line for line in raw.splitlines() if not line.strip().startswith("//")
    )
    statements = [s.strip() for s in no_comments.split(";") if s.strip()]
    with driver.session() as session:
        for statement in statements:
            session.run(statement)
    logger.info("graph.schema_applied", statement_count=len(statements))


def load_data_sources(driver: Driver, snapshot_dir: Path) -> None:
    rows = []
    for manifest_path in sorted(snapshot_dir.glob("*/manifest.json")):
        manifest = SourceManifest.model_validate_json(manifest_path.read_text())
        rows.append(
            {
                "source_id": manifest.source_id,
                "dataset_name": manifest.dataset_name,
                "original_publisher": manifest.original_publisher,
                "source_url": manifest.source_url,
                "snapshot_date": manifest.snapshot_date.isoformat(),
                "checksum_sha256": manifest.checksum_sha256,
                "row_count": manifest.row_count,
            }
        )
    with driver.session() as session:
        session.run(
            """
            UNWIND $rows AS row
            MERGE (ds:DataSource {source_id: row.source_id})
            SET ds += row
            """,
            rows=rows,
        )
    logger.info("graph.data_sources_loaded", count=len(rows))


def _batched(rows: list[dict[str, Any]], size: int = _BATCH_SIZE) -> list[list[dict[str, Any]]]:
    return [rows[i : i + size] for i in range(0, len(rows), size)]


def load_providers(driver: Driver, snapshot_dir: Path) -> int:
    data_path = snapshot_dir / "nppes" / "data.parquet"
    if not data_path.exists():
        logger.warning("graph.nppes_snapshot_missing", path=str(data_path))
        return 0

    df = pl.read_parquet(data_path)
    ingested_at = datetime.now(UTC).isoformat()

    provider_rows: list[dict[str, Any]] = []
    address_rows: list[dict[str, Any]] = []
    phone_rows: list[dict[str, Any]] = []
    officer_rows: list[dict[str, Any]] = []
    taxonomy_rows: list[dict[str, Any]] = []

    for record in df.to_dicts():
        npi = record.get("npi")
        if not npi:
            continue
        observed_at = record.get("last_updated") or record.get("enumeration_date") or ""
        base = {
            "data_origin": DataOrigin.PUBLIC.value,
            "source_id": "nppes",
            "observed_at": observed_at,
            "ingested_at": ingested_at,
            "confidence": 1.0,
        }

        provider_rows.append(
            {
                "npi": npi,
                "organization_name": record.get("organization_name"),
                "entity_type": EntityType.ORGANIZATION.value,
                "state": record.get("state"),
                "enumeration_date": record.get("enumeration_date"),
                "last_updated": record.get("last_updated"),
                "status": record.get("status"),
                **base,
            }
        )

        address_1 = record.get("address_1")
        if address_1:
            addr = normalize_address(
                f"{address_1}, {record.get('city') or ''}, {record.get('state') or ''} "
                f"{record.get('postal_code') or ''}"
            )
            address_rows.append(
                {
                    "npi": npi,
                    "normalized_key": addr.normalized_key,
                    "street_number": addr.street_number,
                    "street_name": addr.street_name,
                    "street_type": addr.street_type,
                    "city": addr.city,
                    "state": addr.state,
                    "zip5": addr.zip5,
                    "unit": addr.unit,
                    **base,
                }
            )

        phone_raw = record.get("telephone_number")
        if phone_raw:
            try:
                e164 = normalize_phone(phone_raw)
            except ValueError:
                e164 = None
            if e164:
                phone_rows.append({"npi": npi, "e164": e164, **base})

        official_last = record.get("authorized_official_last_name")
        if official_last:
            official_first = record.get("authorized_official_first_name") or ""
            officer_id = sha256_text(f"{official_first.upper()}|{official_last.upper()}")[:24]
            officer_rows.append(
                {
                    "npi": npi,
                    "officer_id": officer_id,
                    "first_name": official_first or None,
                    "last_name": official_last,
                    **base,
                }
            )

        taxonomy_code = record.get("taxonomy_code")
        if taxonomy_code:
            taxonomy_rows.append(
                {
                    "npi": npi,
                    "code": taxonomy_code,
                    "description": record.get("taxonomy_desc"),
                    **base,
                }
            )

    with driver.session() as session:
        for batch in _batched(provider_rows):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (p:Provider {npi: row.npi})
                SET p += row
                """,
                rows=batch,
            )
        for batch in _batched(address_rows):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (p:Provider {npi: row.npi})
                MERGE (a:Address {normalized_key: row.normalized_key})
                ON CREATE SET a.street_number = row.street_number, a.street_name = row.street_name,
                              a.street_type = row.street_type, a.city = row.city,
                              a.state = row.state, a.zip5 = row.zip5,
                              a.data_origin = row.data_origin, a.source_id = row.source_id,
                              a.observed_at = row.observed_at, a.ingested_at = row.ingested_at,
                              a.confidence = row.confidence
                MERGE (p)-[r:LOCATED_AT]->(a)
                SET r.unit = row.unit, r.valid_from = row.observed_at, r.valid_to = null,
                    r.data_origin = row.data_origin, r.source_id = row.source_id,
                    r.observed_at = row.observed_at, r.ingested_at = row.ingested_at,
                    r.confidence = row.confidence
                """,
                rows=batch,
            )
        for batch in _batched(phone_rows):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (p:Provider {npi: row.npi})
                MERGE (ph:Phone {e164: row.e164})
                ON CREATE SET ph.data_origin = row.data_origin, ph.source_id = row.source_id,
                              ph.observed_at = row.observed_at, ph.ingested_at = row.ingested_at,
                              ph.confidence = row.confidence
                MERGE (p)-[r:HAS_PHONE]->(ph)
                SET r.valid_from = row.observed_at, r.valid_to = null,
                    r.data_origin = row.data_origin, r.source_id = row.source_id,
                    r.observed_at = row.observed_at, r.ingested_at = row.ingested_at,
                    r.confidence = row.confidence
                """,
                rows=batch,
            )
        for batch in _batched(officer_rows):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (p:Provider {npi: row.npi})
                MERGE (o:Officer {officer_id: row.officer_id})
                ON CREATE SET o.first_name = row.first_name, o.last_name = row.last_name,
                              o.data_origin = row.data_origin, o.source_id = row.source_id,
                              o.observed_at = row.observed_at, o.ingested_at = row.ingested_at,
                              o.confidence = row.confidence
                MERGE (p)-[r:HAS_OFFICER]->(o)
                SET r.valid_from = row.observed_at, r.valid_to = null,
                    r.data_origin = row.data_origin, r.source_id = row.source_id,
                    r.observed_at = row.observed_at, r.ingested_at = row.ingested_at,
                    r.confidence = row.confidence
                """,
                rows=batch,
            )
        for batch in _batched(taxonomy_rows):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (p:Provider {npi: row.npi})
                MERGE (t:Taxonomy {code: row.code})
                ON CREATE SET t.description = row.description
                MERGE (p)-[r:HAS_TAXONOMY]->(t)
                SET r.data_origin = row.data_origin, r.source_id = row.source_id,
                    r.observed_at = row.observed_at, r.ingested_at = row.ingested_at,
                    r.confidence = row.confidence
                """,
                rows=batch,
            )

    logger.info(
        "graph.providers_loaded",
        providers=len(provider_rows),
        addresses=len(address_rows),
        phones=len(phone_rows),
        officers=len(officer_rows),
        taxonomies=len(taxonomy_rows),
    )
    return len(provider_rows)


def _load_exclusion_batch(
    driver: Driver,
    rows: list[dict[str, Any]],
    hidden_npis: set[str],
) -> None:
    for batch in _batched(rows):
        for row in batch:
            row["link"] = bool(row["npi"]) and row["npi"] not in hidden_npis
        with driver.session() as session:
            session.run(
                """
                UNWIND $rows AS row
                MERGE (e:Exclusion {exclusion_id: row.exclusion_id})
                SET e.npi = row.npi, e.name = row.name,
                    e.exclusion_authority = row.exclusion_authority,
                    e.jurisdiction = row.jurisdiction, e.excl_type = row.excl_type,
                    e.excl_date = row.excl_date, e.data_origin = row.data_origin,
                    e.source_id = row.source_id, e.observed_at = row.observed_at,
                    e.ingested_at = row.ingested_at, e.confidence = row.confidence
                WITH e, row
                WHERE row.link
                MATCH (p:Provider {npi: row.npi})
                MERGE (p)-[r:EXCLUDED_BY]->(e)
                SET r.data_origin = row.data_origin, r.source_id = row.source_id,
                    r.observed_at = row.observed_at, r.ingested_at = row.ingested_at,
                    r.confidence = row.confidence
                """,
                rows=batch,
            )


def load_leie_exclusions(
    driver: Driver, snapshot_dir: Path, hidden_npis: set[str] | None = None
) -> int:
    data_path = snapshot_dir / "leie" / "data.parquet"
    if not data_path.exists():
        logger.warning("graph.leie_snapshot_missing", path=str(data_path))
        return 0

    df = pl.read_parquet(data_path)
    ingested_at = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []
    for record in df.to_dicts():
        excl_date = record.get("excl_date")
        row_key = "|".join(
            str(record.get(k, "")) for k in ("bus_name", "last_name", "first_name", "excl_date")
        )
        rows.append(
            {
                "exclusion_id": sha256_text(f"leie|{row_key}")[:24],
                "npi": record.get("npi"),
                "name": record.get("bus_name")
                or f"{record.get('first_name', '')} {record.get('last_name', '')}".strip(),
                "exclusion_authority": ExclusionAuthority.FEDERAL_OIG.value,
                "jurisdiction": "US",
                "excl_type": record.get("excl_type"),
                "excl_date": excl_date.isoformat() if excl_date else None,
                "data_origin": DataOrigin.PUBLIC.value,
                "source_id": "leie",
                "observed_at": excl_date.isoformat() if excl_date else "",
                "ingested_at": ingested_at,
                "confidence": 1.0,
            }
        )
    _load_exclusion_batch(driver, rows, hidden_npis or set())
    logger.info("graph.leie_exclusions_loaded", count=len(rows))
    return len(rows)


def load_state_medicaid_exclusions(
    driver: Driver,
    snapshot_dir: Path,
    jurisdiction: str,
    hidden_npis: set[str] | None = None,
) -> int:
    source_id = f"state_medicaid_{jurisdiction.lower()}"
    data_path = snapshot_dir / source_id / "data.parquet"
    if not data_path.exists():
        logger.warning("graph.state_medicaid_snapshot_missing", path=str(data_path))
        return 0

    df = pl.read_parquet(data_path)
    ingested_at = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []
    for record in df.to_dicts():
        action_date = record.get("action_date")
        row_key = "|".join(
            str(record.get(k, "")) for k in ("provider_name", "address", "action_date")
        )
        rows.append(
            {
                "exclusion_id": sha256_text(f"{source_id}|{row_key}")[:24],
                "npi": record.get("npi"),
                "name": record.get("provider_name"),
                "exclusion_authority": ExclusionAuthority.STATE_MEDICAID.value,
                "jurisdiction": jurisdiction,
                "excl_type": record.get("provider_type"),
                "excl_date": action_date.isoformat() if action_date else None,
                "data_origin": DataOrigin.PUBLIC.value,
                "source_id": source_id,
                "observed_at": action_date.isoformat() if action_date else "",
                "ingested_at": ingested_at,
                "confidence": 1.0,
            }
        )
    _load_exclusion_batch(driver, rows, hidden_npis or set())
    logger.info(
        "graph.state_medicaid_exclusions_loaded", jurisdiction=jurisdiction, count=len(rows)
    )
    return len(rows)


def load_snapshot(
    driver: Driver, snapshot_dir: Path, hidden_npis: set[str] | None = None
) -> dict[str, int]:
    hidden = hidden_npis or set()
    apply_schema(driver)
    load_data_sources(driver, snapshot_dir)
    counts = {
        "providers": load_providers(driver, snapshot_dir),
        "leie_exclusions": load_leie_exclusions(driver, snapshot_dir, hidden),
    }
    for jurisdiction in ("FL", "TX", "CA"):
        counts[f"state_medicaid_{jurisdiction.lower()}_exclusions"] = (
            load_state_medicaid_exclusions(driver, snapshot_dir, jurisdiction, hidden)
        )
    return counts
