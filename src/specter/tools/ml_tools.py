"""Classical anomaly-detection tool over the structural features this system
already computes (M12, CLAUDE.md Amendment 4(b)). `IsolationForest` is
trained offline (`scripts/70_train_anomaly_model.py`), persisted, and loaded
here as a plain deterministic function — the same shape as
`tools/signal_tools.py`'s detectors and `entity_tools.haversine_km`. An LLM
never touches this number (hard rule 1); a documented, versioned, reproducible
function computes it.

Not a fraud probability, anywhere (plan §16; Amendment 4(b)(5)):
`IsolationForest` produces an unbounded structural-anomaly score. This module
negates `score_samples` so a HIGHER value means MORE anomalous — consistent
with every other `value` in this codebase (`RiskSignal.value` too) — and that
sign flip is the only transformation applied; it is never rescaled into
anything that reads as a probability.

`extract_features` runs one batched Cypher query per feature — across the
*whole* npi list via `UNWIND`, not one query per provider — rather than one
monster query unioning eleven differently-shaped `MATCH` patterns. For a
6,970-row cohort that is ~10 round trips total, not 69,700, and each query
stays readable and independently testable.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import polars as pl
import structlog
import yaml
from neo4j import Driver, GraphDatabase
from sklearn.ensemble import IsolationForest

from specter.core.contracts import AnomalyScore, MlConfig, ProviderFeatures, ScreeningThresholds
from specter.core.enums import DataOrigin
from specter.core.errors import SpecterError
from specter.settings import get_settings
from specter.tools.entity_tools import haversine_km, zip_centroid
from specter.tools.evidence_tools import store_artifact
from specter.tools.signal_tools import load_thresholds

logger = structlog.get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "screening.yaml"
_DEFAULT_MODEL_DIR = _REPO_ROOT / "data" / "models"
_DEFAULT_EVIDENCE_DIR = _REPO_ROOT / "data" / "evidence"

# CLAUDE.md Amendment 4(b) + M12 Action Plan: a missing feature value is
# recorded as an explicit 0.0, never silently imputed to a column mean.
_MISSING = 0.0

KNOWN_LIMITATIONS = [
    "synthetic_dominated_training_evaluation",  # only the 36/150 synthetic set is labelled at all
    "not_a_fraud_probability",
    "unsupervised_no_validated_threshold",
]


def _provider_origin(driver: Driver, npi: str) -> DataOrigin:
    """CLAUDE.md hard rule 5: `data_origin` on every signal, `AnomalyScore`
    included. Fails loudly rather than defaulting — same discipline as
    `signal_tools._provider_origin`, kept local here rather than imported so
    this module doesn't reach into another module's private helper.
    """
    with driver.session() as session:
        record = session.run(
            "MATCH (p:Provider {npi: $npi}) RETURN p.data_origin AS origin", npi=npi
        ).single()
    if record is None or record["origin"] is None:
        raise SpecterError(
            f"provider {npi} has no data_origin — refusing to emit an AnomalyScore with an "
            "unlabelled origin (CLAUDE.md hard rule 5)"
        )
    return DataOrigin(record["origin"])


def load_ml_config(path: Path) -> MlConfig:
    raw = yaml.safe_load(path.read_text())
    return MlConfig.model_validate(raw["ml"])


def _model_paths(model_dir: Path, model_version: str) -> tuple[Path, Path]:
    return (
        model_dir / f"anomaly_{model_version}.joblib",
        model_dir / f"anomaly_{model_version}.json",
    )


def _location_type_ordinal(location_type: str | None, order: list[str]) -> float:
    key = location_type or "unclassified"
    if key not in order:
        raise SpecterError(
            f"location_type {key!r} not in config ml.location_type_order {order} — "
            "config and graph have drifted"
        )
    return float(order.index(key))


def _degree_feature(driver: Driver, npis: list[str], rel: str, node_label: str) -> dict[str, float]:
    query = f"""
        UNWIND $npis AS npi
        MATCH (p:Provider {{npi: npi}})-[:{rel}]->(n:{node_label})<-[:{rel}]-(any:Provider)
        WITH npi, n, count(DISTINCT any) AS degree
        RETURN npi, max(degree) AS value
    """
    with driver.session() as session:
        return {r["npi"]: float(r["value"]) for r in session.run(query, npis=npis)}


def _enumeration_burst_feature(
    driver: Driver, npis: list[str], window_days: int
) -> dict[str, float]:
    query = """
        UNWIND $npis AS npi
        MATCH (p:Provider {npi: npi})-[:LOCATED_AT]->(a:Address)<-[:LOCATED_AT]-(peer:Provider)
        WHERE peer.enumeration_date IS NOT NULL
        RETURN npi, collect(peer.enumeration_date) AS dates
    """
    result: dict[str, float] = {}
    with driver.session() as session:
        for record in session.run(query, npis=npis):
            dates = sorted(date.fromisoformat(d) for d in record["dates"])
            best = 0
            for start in dates:
                count = sum(1 for d in dates if 0 <= (d - start).days <= window_days)
                best = max(best, count)
            result[record["npi"]] = float(best)
    return result


def _address_churn_feature(driver: Driver, npis: list[str], window_days: int) -> dict[str, float]:
    query = """
        UNWIND $npis AS npi
        MATCH (:Address)-[r:CHANGED_ADDRESS_TO]->(:Address)
        WHERE r.npi = npi
        RETURN npi, collect(r.changed_at) AS changes
    """
    cutoff = datetime.now(UTC).date() - timedelta(days=window_days)
    result: dict[str, float] = {}
    with driver.session() as session:
        for record in session.run(query, npis=npis):
            recent = [c for c in record["changes"] if date.fromisoformat(c) >= cutoff]
            result[record["npi"]] = float(len(recent))
    return result


# Measured 2026-08-18: this feature's unrestricted-relationship-type
# `shortestPath` is by far the most expensive query here (~0.25s/provider at
# max_hops=3; raising the cap to 6 made even a 10-row batch exceed two
# minutes). Chunking bounds each round trip's blast radius on the full
# ~7,000-row training cohort instead of one multi-minute UNWIND.
_EXCLUSION_PROXIMITY_CHUNK_SIZE = 250


def _exclusion_proximity_feature(
    driver: Driver, npis: list[str], max_hops: int
) -> dict[str, float]:
    """Real hop count when an `Exclusion` is found within `max_hops`; the
    sentinel `max_hops + 1` when none is — NOT `0.0`. `0.0` would mean
    "adjacent to an exclusion", the most suspicious possible reading, which
    is the opposite of what "nothing found nearby" means. This is the one
    feature where the general 0.0-for-missing rule does not apply.
    """
    query = f"""
        UNWIND $npis AS npi
        MATCH (p:Provider {{npi: npi}})
        OPTIONAL MATCH path = shortestPath((p)-[*1..{max_hops}]-(e:Exclusion))
        RETURN npi, min(length(path)) AS hops
    """
    sentinel = float(max_hops + 1)
    result: dict[str, float] = {}
    with driver.session() as session:
        for start in range(0, len(npis), _EXCLUSION_PROXIMITY_CHUNK_SIZE):
            chunk = npis[start : start + _EXCLUSION_PROXIMITY_CHUNK_SIZE]
            for r in session.run(query, npis=chunk):
                result[r["npi"]] = float(r["hops"]) if r["hops"] is not None else sentinel
            logger.info(
                "ml.exclusion_proximity_chunk_done",
                done=min(start + _EXCLUSION_PROXIMITY_CHUNK_SIZE, len(npis)),
                total=len(npis),
            )
    return result


def _community_exclusion_density_feature(driver: Driver, npis: list[str]) -> dict[str, float]:
    query = """
        UNWIND $npis AS npi
        MATCH (p:Provider {npi: npi})-[:IN_COMMUNITY]->(cm:Community)
        MATCH (cm)<-[:IN_COMMUNITY]-(member:Provider)
        OPTIONAL MATCH (member)-[:EXCLUDED_BY]->(:Exclusion)
        WITH npi, cm, count(DISTINCT member) AS total,
             count(DISTINCT CASE WHEN (member)-[:EXCLUDED_BY]->(:Exclusion)
                                  THEN member END) AS excluded_count
        RETURN npi, max(toFloat(excluded_count) / total) AS value
    """
    with driver.session() as session:
        return {r["npi"]: float(r["value"]) for r in session.run(query, npis=npis)}


def _geographic_spread_feature(driver: Driver, npis: list[str]) -> dict[str, float]:
    query = """
        UNWIND $npis AS npi
        MATCH (p:Provider {npi: npi})-[:HAS_OFFICER]->(o:Officer)<-[:HAS_OFFICER]-(peer:Provider)
        MATCH (p)-[:LOCATED_AT]->(pa:Address)
        MATCH (peer)-[:LOCATED_AT]->(peer_a:Address)
        WHERE peer.npi <> p.npi
        RETURN npi, pa.zip5 AS zip1, peer_a.zip5 AS zip2
    """
    result: dict[str, float] = {}
    with driver.session() as session:
        for record in session.run(query, npis=npis):
            npi = record["npi"]
            centroid1 = zip_centroid(record["zip1"]) if record["zip1"] else None
            centroid2 = zip_centroid(record["zip2"]) if record["zip2"] else None
            if centroid1 is None or centroid2 is None:
                result.setdefault(npi, _MISSING)
                continue
            distance = haversine_km(centroid1, centroid2)
            result[npi] = max(result.get(npi, _MISSING), distance)
    return result


def _address_feature(
    driver: Driver, npis: list[str], location_type_order: list[str]
) -> dict[str, tuple[float, float, float]]:
    query = """
        UNWIND $npis AS npi
        MATCH (p:Provider {npi: npi})-[:LOCATED_AT]->(a:Address)
        RETURN npi, a.establishment_count AS establishment_count,
               a.medical_establishment_count AS medical_establishment_count,
               a.location_type AS location_type
        ORDER BY npi, a.normalized_key
    """
    result: dict[str, tuple[float, float, float]] = {}
    with driver.session() as session:
        for record in session.run(query, npis=npis):
            npi = record["npi"]
            if npi in result:
                continue  # first address wins — one row per provider, like the detectors
            result[npi] = (
                float(record["establishment_count"] or _MISSING),
                float(record["medical_establishment_count"] or _MISSING),
                _location_type_ordinal(record["location_type"], location_type_order),
            )
    return result


def _phoenix_pattern_feature(driver: Driver, npis: list[str]) -> dict[str, float]:
    query = """
        UNWIND $npis AS npi
        MATCH (new:Provider {npi: npi})-[:LOCATED_AT]->(a:Address)<-[:LOCATED_AT]-(old:Provider)
        MATCH (new)-[:HAS_OFFICER]->(o:Officer)<-[:HAS_OFFICER]-(old)
        MATCH (old)-[:EXCLUDED_BY]->(e:Exclusion)
        WHERE old.npi <> new.npi AND e.excl_date IS NOT NULL AND new.enumeration_date IS NOT NULL
        RETURN DISTINCT npi
    """
    with driver.session() as session:
        detected = {r["npi"] for r in session.run(query, npis=npis)}
    return {npi: (1.0 if npi in detected else _MISSING) for npi in npis}


def extract_features(
    driver: Driver, npis: list[str], thresholds: ScreeningThresholds, ml_config: MlConfig
) -> pl.DataFrame:
    """One `pl.DataFrame` row per npi, columns in exactly `ml_config.feature_order`.
    Every feature defaults to `0.0` when a provider has no matching graph
    pattern (documented per-feature above) — `exclusion_proximity_hops` is the
    deliberate, documented exception.
    """
    per_feature: dict[str, dict[str, float]] = {
        "address_degree": _degree_feature(driver, npis, "LOCATED_AT", "Address"),
        "phone_degree": _degree_feature(driver, npis, "HAS_PHONE", "Phone"),
        "officer_degree": _degree_feature(driver, npis, "HAS_OFFICER", "Officer"),
        "enumeration_burst_count": _enumeration_burst_feature(
            driver, npis, thresholds.enumeration_burst_window_days
        ),
        "address_churn_count": _address_churn_feature(
            driver, npis, thresholds.address_churn_window_days
        ),
        "exclusion_proximity_hops": _exclusion_proximity_feature(
            driver, npis, ml_config.exclusion_proximity_feature_max_hops
        ),
        "community_exclusion_density": _community_exclusion_density_feature(driver, npis),
        "geographic_spread_km": _geographic_spread_feature(driver, npis),
        "phoenix_pattern_detected": _phoenix_pattern_feature(driver, npis),
    }
    address = _address_feature(driver, npis, ml_config.location_type_order)

    rows: list[dict[str, Any]] = []
    for npi in npis:
        establishment_count, medical_establishment_count, location_type_ordinal = address.get(
            npi, (_MISSING, _MISSING, _location_type_ordinal(None, ml_config.location_type_order))
        )
        values = {
            "address_degree": per_feature["address_degree"].get(npi, _MISSING),
            "phone_degree": per_feature["phone_degree"].get(npi, _MISSING),
            "officer_degree": per_feature["officer_degree"].get(npi, _MISSING),
            "enumeration_burst_count": per_feature["enumeration_burst_count"].get(npi, _MISSING),
            "address_churn_count": per_feature["address_churn_count"].get(npi, _MISSING),
            "exclusion_proximity_hops": per_feature["exclusion_proximity_hops"].get(
                npi, float(ml_config.exclusion_proximity_feature_max_hops + 1)
            ),
            "community_exclusion_density": per_feature["community_exclusion_density"].get(
                npi, _MISSING
            ),
            "geographic_spread_km": per_feature["geographic_spread_km"].get(npi, _MISSING),
            "establishment_count": establishment_count,
            "medical_establishment_count": medical_establishment_count,
            "location_type_ordinal": location_type_ordinal,
            "phoenix_pattern_detected": per_feature["phoenix_pattern_detected"].get(
                npi, _MISSING
            ),
        }
        rows.append({"provider_npi": npi, **{col: values[col] for col in ml_config.feature_order}})

    return pl.DataFrame(rows)


def provider_features(df: pl.DataFrame, feature_order: list[str]) -> list[ProviderFeatures]:
    """Typed, JSON-serializable view of `extract_features`'s output — what a
    dashboard endpoint hands out instead of a raw `pl.DataFrame`."""
    _matrix(df, feature_order)  # raises before handing out a silently-reordered row
    return [
        ProviderFeatures(
            provider_npi=row["provider_npi"],
            values=[float(row[c]) for c in feature_order],
            feature_order=feature_order,
        )
        for row in df.iter_rows(named=True)
    ]


def _matrix(df: pl.DataFrame, feature_order: list[str]) -> np.ndarray:
    if list(df.columns[1:]) != feature_order:
        raise SpecterError(
            f"feature matrix columns {df.columns[1:]} do not match "
            f"ml_config.feature_order {feature_order} — refusing to fit or score against "
            "a silently reordered matrix"
        )
    return df.select(feature_order).to_numpy()


def train(df: pl.DataFrame, ml_config: MlConfig) -> IsolationForest:
    """Pure given `df` — fit is deterministic for a fixed `random_state`
    (same precedent as `graph/communities.py`'s Leiden `RANDOM_SEED`)."""
    matrix = _matrix(df, ml_config.feature_order)
    model = IsolationForest(
        n_estimators=ml_config.n_estimators,
        contamination=ml_config.contamination,
        random_state=ml_config.random_state,
    )
    model.fit(matrix)
    return model


def score_matrix(model: IsolationForest, df: pl.DataFrame, feature_order: list[str]) -> np.ndarray:
    """Higher = more anomalous (negated `score_samples` — see module docstring)."""
    matrix = _matrix(df, feature_order)
    scores: np.ndarray = -model.score_samples(matrix)
    return scores


def _load_model(model_dir: Path, model_version: str) -> tuple[IsolationForest, dict[str, Any]]:
    model_path, sidecar_path = _model_paths(model_dir, model_version)
    if not model_path.exists() or not sidecar_path.exists():
        raise SpecterError(
            f"no persisted model for version {model_version!r} at {model_path} — run "
            "scripts/70_train_anomaly_model.py first. Never substitute a default score."
        )
    model = joblib.load(model_path)
    sidecar = json.loads(sidecar_path.read_text())
    return model, sidecar


def score_provider(
    npi: str,
    *,
    driver: Driver | None = None,
    thresholds: ScreeningThresholds | None = None,
    ml_config: MlConfig | None = None,
    model_dir: Path = _DEFAULT_MODEL_DIR,
    evidence_dir: Path = _DEFAULT_EVIDENCE_DIR,
) -> AnomalyScore:
    """Tool-callable single-provider scorer — `score_provider('1003050550')`
    is a valid smoke test: unset arguments are constructed from live settings
    (mirroring how `scripts/70_train_anomaly_model.py` wires the same
    pieces), and the function is otherwise pure given the persisted model.
    """
    owns_driver = driver is None
    if driver is None:
        settings = get_settings()
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
        )
    if thresholds is None:
        thresholds = load_thresholds(_DEFAULT_CONFIG_PATH)
    if ml_config is None:
        ml_config = load_ml_config(_DEFAULT_CONFIG_PATH)
    try:
        model, sidecar = _load_model(model_dir, ml_config.model_version)
        if sidecar["feature_order"] != ml_config.feature_order:
            raise SpecterError(
                f"model sidecar feature_order {sidecar['feature_order']} does not match "
                f"config/screening.yaml's current ml.feature_order {ml_config.feature_order} — "
                "config has drifted since this model was trained; retrain before scoring"
            )
        df = extract_features(driver, [npi], thresholds, ml_config)
        score = float(score_matrix(model, df, ml_config.feature_order)[0])
        return AnomalyScore(
            provider_npi=npi,
            anomaly_score=score,
            model_version=ml_config.model_version,
            source_ids=[f"graph:provider:{npi}", sidecar["artifact_id"]],
            training_set_description=sidecar["training_set_description"],
            known_limitations=list(KNOWN_LIMITATIONS),
            data_origin=_provider_origin(driver, npi),
            scored_at=datetime.now(UTC),
        )
    finally:
        if owns_driver:
            driver.close()


def persist_model(
    model: IsolationForest,
    ml_config: MlConfig,
    *,
    trained_rows: int,
    training_set_description: str,
    evidence_dir: Path,
    model_dir: Path,
) -> str:
    """Writes the `.joblib` model, a JSON sidecar (feature order, row count,
    training date, evidence artifact id), and a content-addressed
    `EvidenceArtifact` summarising the run — the `source_id` every
    `AnomalyScore` from this `model_version` cites. Returns the artifact_id.
    """
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path, sidecar_path = _model_paths(model_dir, ml_config.model_version)
    joblib.dump(model, model_path)

    trained_at = datetime.now(UTC)
    content = json.dumps(
        {
            "model_version": ml_config.model_version,
            "algorithm": "IsolationForest",
            "feature_order": ml_config.feature_order,
            "random_state": ml_config.random_state,
            "n_estimators": ml_config.n_estimators,
            "contamination": ml_config.contamination,
            "trained_rows": trained_rows,
            "trained_at": trained_at.isoformat(),
            "training_set_description": training_set_description,
        },
        sort_keys=True,
        indent=2,
    )
    artifact = store_artifact(
        content=content,
        content_type="application/json",
        source_id=f"ml_model:{ml_config.model_version}",
        evidence_dir=evidence_dir,
        extraction_method="isolation_forest_training_summary",
    )
    sidecar_path.write_text(
        json.dumps(
            {
                "model_version": ml_config.model_version,
                "feature_order": ml_config.feature_order,
                "trained_rows": trained_rows,
                "trained_at": trained_at.isoformat(),
                "training_set_description": training_set_description,
                "artifact_id": artifact.artifact_id,
            },
            sort_keys=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info(
        "ml.model_persisted",
        model_version=ml_config.model_version,
        trained_rows=trained_rows,
        artifact_id=artifact.artifact_id,
    )
    return artifact.artifact_id
