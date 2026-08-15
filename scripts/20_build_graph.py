#!/usr/bin/env python
"""Graph build CLI (plan §6).

    python scripts/20_build_graph.py
    python scripts/20_build_graph.py --hide-labels 1234567890,9876543210

Loads data/snapshot/ (never data/raw/) into Neo4j per graph/schema.cypher.
--hide-labels strips EXCLUDED_BY edges for the given NPIs (plan §12.1 —
held-out ground truth for judge/detection_eval.py); the Exclusion node
itself is still loaded, just not linked to the provider.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import structlog
from neo4j import GraphDatabase

from specter.graph.loader import load_snapshot
from specter.graph.loader_synthetic import load_synthetic_snapshot
from specter.settings import get_settings

logger = structlog.get_logger(__name__)

SNAPSHOT_DIR = Path("data/snapshot")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--hide-labels",
        default="",
        help="comma-separated NPIs to hide EXCLUDED_BY edges for",
    )
    args = parser.parse_args()
    hidden_npis = {npi.strip() for npi in args.hide_labels.split(",") if npi.strip()}

    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    try:
        counts = load_snapshot(driver, SNAPSHOT_DIR, settings, hidden_npis)
        counts.update(load_synthetic_snapshot(driver, SNAPSHOT_DIR))
        logger.info("build_graph.complete", counts=counts, hidden_npi_count=len(hidden_npis))
    finally:
        driver.close()


if __name__ == "__main__":
    main()
