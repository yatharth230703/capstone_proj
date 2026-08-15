"""Loads synthetic scenario data (plan §5.5) into the same graph schema
`graph/loader.py` uses for real data — kept in a separate module because
`loader.py` was already at the 400-line cap (CLAUDE.md: "if it grows past
400 lines, it's doing two jobs — split it") and synthetic data genuinely is
a different job: it needs `latitude`/`longitude` (for `geographic_spread`,
which real NPPES data can't support without geocoding — out of Phase 1
scope) and `CHANGED_ADDRESS_TO` history chains (for `address_churn`), neither
of which the real-data loader needs.

Reuses `graph.loader`'s batching helper and exclusion-writing logic rather
than duplicating it.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import structlog
from neo4j import Driver

from specter.core.enums import DataOrigin, EntityType
from specter.core.hashing import sha256_text
from specter.graph.loader import _batched, _load_exclusion_batch
from specter.tools.entity_tools import normalize_address, normalize_phone

logger = structlog.get_logger(__name__)


def load_synthetic_providers(driver: Driver, snapshot_dir: Path) -> int:
    data_path = snapshot_dir / "synthetic_providers" / "data.parquet"
    if not data_path.exists():
        logger.warning("graph.synthetic_providers_snapshot_missing", path=str(data_path))
        return 0

    df = pl.read_parquet(data_path)
    ingested_at = datetime.now(UTC).isoformat()

    provider_rows: list[dict[str, Any]] = []
    address_rows: list[dict[str, Any]] = []
    historical_address_rows: list[dict[str, Any]] = []
    phone_rows: list[dict[str, Any]] = []
    officer_rows: list[dict[str, Any]] = []
    history_rows: list[dict[str, Any]] = []

    for record in df.to_dicts():
        npi = record["npi"]
        base = {
            "data_origin": DataOrigin.SYNTHETIC.value,
            "source_id": "synthetic_providers",
            "observed_at": record.get("enumeration_date") or "",
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
                "latitude": record.get("latitude"),
                "longitude": record.get("longitude"),
                "scenario_id": record.get("scenario_id"),
                **base,
            }
        )

        addr = normalize_address(
            f"{record['address_1']}, {record.get('city') or ''}, "
            f"{record.get('state') or ''} {record.get('postal_code') or ''}"
        )
        address_rows.append(
            {
                "npi": npi, "normalized_key": addr.normalized_key,
                "street_number": addr.street_number, "street_name": addr.street_name,
                "street_type": addr.street_type, "city": addr.city, "state": addr.state,
                "zip5": addr.zip5, "unit": addr.unit, **base,
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

        officer_last = record.get("authorized_official_last_name")
        if officer_last:
            officer_first = record.get("authorized_official_first_name") or ""
            officer_id = sha256_text(f"{officer_first.upper()}|{officer_last.upper()}")[:24]
            officer_rows.append(
                {
                    "npi": npi, "officer_id": officer_id, "first_name": officer_first or None,
                    "last_name": officer_last, **base,
                }
            )

        prior_addresses = json.loads(record.get("prior_addresses") or "[]")
        chain = [
            {
                "address_1": a["address_1"], "city": a["city"], "state": a["state"],
                "postal_code": a["zip5"], "changed_at": a["changed_at"],
            }
            for a in prior_addresses
        ]
        chain.append({"address_1": record["address_1"], "city": record.get("city"),
                       "state": record.get("state"), "postal_code": record.get("postal_code"),
                       "changed_at": record.get("enumeration_date")})
        chain_addrs = [
            normalize_address(f"{e['address_1']}, {e['city']}, {e['state']} {e['postal_code']}")
            for e in chain
        ]
        # Historical (non-current) addresses in the chain have no Provider
        # currently LOCATED_AT them — they still need Address nodes to exist
        # before CHANGED_ADDRESS_TO can link them.
        for historical_addr in chain_addrs[:-1]:
            historical_address_rows.append(
                {
                    "normalized_key": historical_addr.normalized_key,
                    "street_number": historical_addr.street_number,
                    "street_name": historical_addr.street_name,
                    "street_type": historical_addr.street_type, "city": historical_addr.city,
                    "state": historical_addr.state, "zip5": historical_addr.zip5, **base,
                }
            )
        for prev_addr, next_addr, next_event in zip(
            chain_addrs, chain_addrs[1:], chain[1:], strict=False
        ):
            history_rows.append(
                {
                    "npi": npi, "from_key": prev_addr.normalized_key,
                    "to_key": next_addr.normalized_key, "changed_at": next_event["changed_at"],
                    **base,
                }
            )

    with driver.session() as session:
        for batch in _batched(provider_rows):
            session.run(
                "UNWIND $rows AS row MERGE (p:Provider {npi: row.npi}) SET p += row",
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
        for batch in _batched(historical_address_rows):
            session.run(
                """
                UNWIND $rows AS row
                MERGE (a:Address {normalized_key: row.normalized_key})
                ON CREATE SET a.street_number = row.street_number, a.street_name = row.street_name,
                              a.street_type = row.street_type, a.city = row.city,
                              a.state = row.state, a.zip5 = row.zip5,
                              a.data_origin = row.data_origin, a.source_id = row.source_id,
                              a.observed_at = row.observed_at, a.ingested_at = row.ingested_at,
                              a.confidence = row.confidence
                """,
                rows=batch,
            )
        for batch in _batched(history_rows):
            session.run(
                """
                UNWIND $rows AS row
                MATCH (from_addr:Address {normalized_key: row.from_key})
                MATCH (to_addr:Address {normalized_key: row.to_key})
                MERGE (from_addr)-[r:CHANGED_ADDRESS_TO {changed_at: row.changed_at}]->(to_addr)
                SET r.npi = row.npi, r.data_origin = row.data_origin, r.source_id = row.source_id,
                    r.observed_at = row.observed_at, r.ingested_at = row.ingested_at,
                    r.confidence = row.confidence
                """,
                rows=batch,
            )

    logger.info(
        "graph.synthetic_providers_loaded",
        providers=len(provider_rows),
        address_history_edges=len(history_rows),
    )
    return len(provider_rows)


def load_synthetic_exclusions(driver: Driver, snapshot_dir: Path) -> int:
    data_path = snapshot_dir / "synthetic_exclusions" / "data.parquet"
    if not data_path.exists():
        logger.warning("graph.synthetic_exclusions_snapshot_missing", path=str(data_path))
        return 0

    df = pl.read_parquet(data_path)
    ingested_at = datetime.now(UTC).isoformat()
    rows: list[dict[str, Any]] = []
    for record in df.to_dicts():
        rows.append(
            {
                "exclusion_id": sha256_text(f"synthetic|{record['npi']}|{record['excl_date']}")[
                    :24
                ],
                "npi": record.get("npi"),
                "name": record.get("bus_name"),
                # data_origin (below) is what actually marks this synthetic — reusing
                # federal_oig here models "an excluded peer" structurally, not the
                # real federal/state weighting distinction Amendment 1 cares about.
                "exclusion_authority": "federal_oig",
                "jurisdiction": "SYNTHETIC",
                "excl_type": "synthetic",
                "excl_date": record.get("excl_date"),
                "data_origin": DataOrigin.SYNTHETIC.value,
                "source_id": "synthetic_exclusions",
                "observed_at": record.get("excl_date") or "",
                "ingested_at": ingested_at,
                "confidence": 1.0,
            }
        )
    _load_exclusion_batch(driver, rows, hidden_npis=set())
    logger.info("graph.synthetic_exclusions_loaded", count=len(rows))
    return len(rows)


def load_synthetic_snapshot(driver: Driver, snapshot_dir: Path) -> dict[str, int]:
    return {
        "synthetic_providers": load_synthetic_providers(driver, snapshot_dir),
        "synthetic_exclusions": load_synthetic_exclusions(driver, snapshot_dir),
    }
