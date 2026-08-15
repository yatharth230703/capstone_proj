#!/usr/bin/env python
"""Ingestion CLI (plan §5.3).

    python scripts/10_ingest.py --live      # fetch all sources -> data/raw/
    python scripts/10_ingest.py --freeze     # promote data/raw/ -> data/snapshot/

The screening pipeline reads data/snapshot/ only, never data/raw/directly
(plan §5.3, the frozen-snapshot rule).
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import structlog
import yaml

from specter.core.contracts import SourceConfig, SourceManifest
from specter.core.errors import ConnectorValidationError
from specter.ingest.base import Connector
from specter.ingest.doj import DojConnector
from specter.ingest.leie import LeieConnector
from specter.ingest.nppes import NppesConnector
from specter.ingest.state_medicaid import StateMedicaidConnector
from specter.ingest.synthetic import SyntheticExclusionsConnector, SyntheticProvidersConnector
from specter.settings import get_settings

logger = structlog.get_logger(__name__)

RAW_DIR = Path("data/raw")
SNAPSHOT_DIR = Path("data/snapshot")


def _build_connectors() -> list[tuple[Connector, SourceConfig]]:
    settings = get_settings()
    pairs: list[tuple[Connector, SourceConfig]] = [
        (
            NppesConnector(),
            SourceConfig(
                source_id="nppes",
                raw_dir=RAW_DIR / "nppes",
                params={
                    "states": settings.cohort_states,
                    "taxonomy_prefix": settings.cohort_taxonomy_prefix,
                },
            ),
        ),
        (LeieConnector(), SourceConfig(source_id="leie", raw_dir=RAW_DIR / "leie", params={})),
        (DojConnector(), SourceConfig(source_id="doj", raw_dir=RAW_DIR / "doj", params={})),
    ]
    for jurisdiction in ("FL", "TX", "CA"):
        source_id = f"state_medicaid_{jurisdiction.lower()}"
        pairs.append(
            (
                StateMedicaidConnector(jurisdiction),
                SourceConfig(source_id=source_id, raw_dir=RAW_DIR / source_id, params={}),
            )
        )
    pairs.append(
        (
            SyntheticProvidersConnector(),
            SourceConfig(
                source_id="synthetic_providers", raw_dir=RAW_DIR / "synthetic_providers", params={}
            ),
        )
    )
    pairs.append(
        (
            SyntheticExclusionsConnector(),
            SourceConfig(
                source_id="synthetic_exclusions",
                raw_dir=RAW_DIR / "synthetic_exclusions",
                params={},
            ),
        )
    )
    return pairs


def run_live() -> list[SourceManifest]:
    manifests: list[SourceManifest] = []
    failures: list[str] = []
    for connector, cfg in _build_connectors():
        logger.info("ingest.start", source_id=connector.source_id)
        try:
            df, manifest = connector.run(cfg)
        except ConnectorValidationError as exc:
            logger.error(
                "ingest.failed",
                source_id=connector.source_id,
                missing_columns=exc.report.missing_columns,
                schema_drift=exc.report.schema_drift,
            )
            failures.append(connector.source_id)
            continue

        out_dir = RAW_DIR / connector.source_id
        out_dir.mkdir(parents=True, exist_ok=True)
        df.write_parquet(out_dir / "data.parquet")
        (out_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2))
        logger.info(
            "ingest.complete",
            source_id=connector.source_id,
            row_count=manifest.row_count,
            checksum=manifest.checksum_sha256[:12],
        )
        manifests.append(manifest)

    if failures:
        logger.error("ingest.run_failed", failed_sources=failures)
        sys.exit(1)
    return manifests


def run_freeze() -> None:
    if not RAW_DIR.exists():
        logger.error("freeze.no_raw_data", raw_dir=str(RAW_DIR))
        sys.exit(1)

    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_entries: dict[str, object] = {}
    for source_dir in sorted(p for p in RAW_DIR.iterdir() if p.is_dir()):
        manifest_path = source_dir / "manifest.json"
        data_path = source_dir / "data.parquet"
        if not (manifest_path.exists() and data_path.exists()):
            continue

        manifest = SourceManifest.model_validate_json(manifest_path.read_text())
        dest_dir = SNAPSHOT_DIR / source_dir.name
        dest_dir.mkdir(parents=True, exist_ok=True)
        pl.read_parquet(data_path).write_parquet(dest_dir / "data.parquet", compression="zstd")
        (dest_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2))
        manifest_entries[source_dir.name] = manifest.model_dump(mode="json")
        logger.info("freeze.promoted", source_id=source_dir.name, row_count=manifest.row_count)

    snapshot_manifest = {
        "frozen_at": datetime.now(UTC).isoformat(),
        "sources": manifest_entries,
    }
    (SNAPSHOT_DIR / "MANIFEST.yaml").write_text(yaml.safe_dump(snapshot_manifest, sort_keys=True))
    logger.info(
        "freeze.complete", snapshot_dir=str(SNAPSHOT_DIR), source_count=len(manifest_entries)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--live", action="store_true", help="fetch all sources into data/raw/")
    group.add_argument(
        "--freeze", action="store_true", help="promote data/raw/ into data/snapshot/"
    )
    args = parser.parse_args()

    if args.live:
        run_live()
    elif args.freeze:
        run_freeze()


if __name__ == "__main__":
    main()
