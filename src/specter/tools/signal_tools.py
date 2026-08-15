"""Deterministic risk-signal detectors (plan §8) — zero LLM involvement.
Each function queries Neo4j directly and returns a `RiskSignal` (with the
`source_ids` and `threshold` it used) or `None`. Thresholds come from
`config/screening.yaml`, never hardcoded inline.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import structlog
import yaml
from neo4j import Driver

from specter.core.contracts import RiskSignal, ScreeningThresholds
from specter.core.enums import DataOrigin

logger = structlog.get_logger(__name__)

_EARTH_RADIUS_KM = 6371.0


def load_thresholds(path: Path) -> ScreeningThresholds:
    raw = yaml.safe_load(path.read_text())
    return ScreeningThresholds.model_validate(raw["thresholds"])


def _now() -> datetime:
    return datetime.now(UTC)


def _signal(
    signal_type: str, npi: str, value: float, threshold: float, source_ids: list[str]
) -> RiskSignal:
    return RiskSignal(
        signal_type=signal_type, provider_npi=npi, value=value, threshold=threshold,
        source_ids=source_ids, data_origin=DataOrigin.PUBLIC, detected_at=_now(),
    )


def address_degree(driver: Driver, npi: str, thresholds: ScreeningThresholds) -> RiskSignal | None:
    with driver.session() as session:
        record = session.run(
            """
            MATCH (p:Provider {npi: $npi})-[:LOCATED_AT]->(a:Address)
            MATCH (a)<-[:LOCATED_AT]-(any:Provider)
            RETURN a.normalized_key AS key, count(DISTINCT any) AS degree
            ORDER BY degree DESC LIMIT 1
            """,
            npi=npi,
        ).single()
    if record is None or record["degree"] < thresholds.address_degree:
        return None
    return _signal(
        "address_degree", npi, float(record["degree"]), thresholds.address_degree,
        [f"graph:address:{record['key']}"],
    )


def phone_degree(driver: Driver, npi: str, thresholds: ScreeningThresholds) -> RiskSignal | None:
    with driver.session() as session:
        record = session.run(
            """
            MATCH (p:Provider {npi: $npi})-[:HAS_PHONE]->(ph:Phone)
            MATCH (ph)<-[:HAS_PHONE]-(any:Provider)
            RETURN ph.e164 AS key, count(DISTINCT any) AS degree
            ORDER BY degree DESC LIMIT 1
            """,
            npi=npi,
        ).single()
    if record is None or record["degree"] < thresholds.phone_degree:
        return None
    return _signal(
        "phone_degree", npi, float(record["degree"]), thresholds.phone_degree,
        [f"graph:phone:{record['key']}"],
    )


def officer_degree(driver: Driver, npi: str, thresholds: ScreeningThresholds) -> RiskSignal | None:
    with driver.session() as session:
        record = session.run(
            """
            MATCH (p:Provider {npi: $npi})-[:HAS_OFFICER]->(o:Officer)
            MATCH (o)<-[:HAS_OFFICER]-(any:Provider)
            RETURN o.officer_id AS key, count(DISTINCT any) AS degree
            ORDER BY degree DESC LIMIT 1
            """,
            npi=npi,
        ).single()
    if record is None or record["degree"] < thresholds.officer_degree:
        return None
    return _signal(
        "officer_degree", npi, float(record["degree"]), thresholds.officer_degree,
        [f"graph:officer:{record['key']}"],
    )


def enumeration_burst(
    driver: Driver, npi: str, thresholds: ScreeningThresholds
) -> RiskSignal | None:
    with driver.session() as session:
        record = session.run(
            """
            MATCH (p:Provider {npi: $npi})-[:LOCATED_AT]->(a:Address)
            MATCH (a)<-[:LOCATED_AT]-(peer:Provider)
            WHERE peer.enumeration_date IS NOT NULL
            RETURN a.normalized_key AS key, collect(peer.enumeration_date) AS dates
            """,
            npi=npi,
        ).single()
    if record is None:
        return None
    dates = sorted(date.fromisoformat(d) for d in record["dates"])
    window = thresholds.enumeration_burst_window_days
    best_count = 0
    for start in dates:
        count = sum(1 for d in dates if 0 <= (d - start).days <= window)
        best_count = max(best_count, count)
    if best_count < thresholds.enumeration_burst_count:
        return None
    return _signal(
        "enumeration_burst", npi, float(best_count), thresholds.enumeration_burst_count,
        [f"graph:address:{record['key']}"],
    )


def address_churn(driver: Driver, npi: str, thresholds: ScreeningThresholds) -> RiskSignal | None:
    with driver.session() as session:
        record = session.run(
            """
            MATCH (:Address)-[r:CHANGED_ADDRESS_TO]->(:Address)
            WHERE r.npi = $npi
            RETURN collect(r.changed_at) AS changes
            """,
            npi=npi,
        ).single()
    if record is None or not record["changes"]:
        return None
    cutoff = _now().date() - timedelta(days=thresholds.address_churn_window_days)
    recent = [c for c in record["changes"] if date.fromisoformat(c) >= cutoff]
    if len(recent) < thresholds.address_churn_count:
        return None
    return _signal(
        "address_churn", npi, float(len(recent)), thresholds.address_churn_count,
        [f"graph:provider:{npi}:changed_address_to:{c}" for c in recent],
    )


def exclusion_proximity(
    driver: Driver, npi: str, thresholds: ScreeningThresholds
) -> RiskSignal | None:
    max_hops = thresholds.exclusion_proximity_max_hops
    with driver.session() as session:
        record = session.run(
            f"""
            MATCH (p:Provider {{npi: $npi}})
            MATCH path = shortestPath((p)-[*1..{max_hops}]-(e:Exclusion))
            RETURN e.exclusion_id AS exclusion_id, length(path) AS hops
            ORDER BY hops ASC LIMIT 1
            """,
            npi=npi,
        ).single()
    if record is None:
        return None
    return _signal(
        "exclusion_proximity", npi, float(record["hops"]), float(max_hops),
        [f"graph:exclusion:{record['exclusion_id']}"],
    )


def community_exclusion_density(
    driver: Driver, npi: str, thresholds: ScreeningThresholds
) -> RiskSignal | None:
    with driver.session() as session:
        record = session.run(
            """
            MATCH (p:Provider {npi: $npi})-[:IN_COMMUNITY]->(cm:Community)
            MATCH (cm)<-[:IN_COMMUNITY]-(member:Provider)
            OPTIONAL MATCH (member)-[:EXCLUDED_BY]->(:Exclusion)
            WITH cm, count(DISTINCT member) AS total,
                 count(DISTINCT CASE WHEN (member)-[:EXCLUDED_BY]->(:Exclusion)
                                      THEN member END) AS excluded_count
            RETURN cm.community_id AS community_id, total, excluded_count
            """,
            npi=npi,
        ).single()
    if record is None or record["total"] == 0:
        return None
    density = record["excluded_count"] / record["total"]
    if density < thresholds.community_exclusion_density_min_fraction:
        return None
    return _signal(
        "community_exclusion_density", npi, density,
        thresholds.community_exclusion_density_min_fraction,
        [f"graph:community:{record['community_id']}"],
    )


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return _EARTH_RADIUS_KM * 2 * math.asin(math.sqrt(a))


def geographic_spread(
    driver: Driver, npi: str, thresholds: ScreeningThresholds
) -> RiskSignal | None:
    with driver.session() as session:
        records = session.run(
            """
            MATCH (p:Provider {npi: $npi})-[:HAS_OFFICER]->(o:Officer)
            MATCH (o)<-[:HAS_OFFICER]-(peer:Provider)
            WHERE peer.npi <> p.npi AND peer.latitude IS NOT NULL AND peer.longitude IS NOT NULL
                  AND p.latitude IS NOT NULL AND p.longitude IS NOT NULL
            RETURN o.officer_id AS officer_id, p.latitude AS lat1, p.longitude AS lon1,
                   peer.npi AS peer_npi, peer.latitude AS lat2, peer.longitude AS lon2
            """,
            npi=npi,
        ).data()
    if not records:
        return None
    best = max(
        records, key=lambda r: _haversine_km(r["lat1"], r["lon1"], r["lat2"], r["lon2"])
    )
    distance = _haversine_km(best["lat1"], best["lon1"], best["lat2"], best["lon2"])
    if distance < thresholds.geographic_spread_min_km:
        return None
    return _signal(
        "geographic_spread", npi, distance, thresholds.geographic_spread_min_km,
        [f"graph:officer:{best['officer_id']}", f"graph:provider:{best['peer_npi']}"],
    )


def phoenix_pattern(driver: Driver, npi: str, thresholds: ScreeningThresholds) -> RiskSignal | None:
    with driver.session() as session:
        record = session.run(
            """
            MATCH (new:Provider {npi: $npi})-[:LOCATED_AT]->(a:Address)
                  <-[:LOCATED_AT]-(old:Provider)
            MATCH (new)-[:HAS_OFFICER]->(o:Officer)<-[:HAS_OFFICER]-(old)
            MATCH (old)-[:EXCLUDED_BY]->(e:Exclusion)
            WHERE old.npi <> new.npi AND e.excl_date IS NOT NULL
                  AND new.enumeration_date IS NOT NULL
            RETURN old.npi AS old_npi, e.exclusion_id AS exclusion_id, e.excl_date AS excl_date,
                   new.enumeration_date AS new_enum_date
            """,
            npi=npi,
        ).single()
    if record is None:
        return None
    excl_date = date.fromisoformat(record["excl_date"])
    enum_date = date.fromisoformat(record["new_enum_date"])
    months_between = (enum_date.year - excl_date.year) * 12 + (enum_date.month - excl_date.month)
    max_months = thresholds.phoenix_pattern_max_months_since_exclusion
    if enum_date < excl_date or months_between > max_months:
        return None
    return _signal(
        "phoenix_pattern", npi, float(months_between), float(max_months),
        [f"graph:provider:{record['old_npi']}", f"graph:exclusion:{record['exclusion_id']}"],
    )
