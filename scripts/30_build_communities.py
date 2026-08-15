#!/usr/bin/env python
"""Community detection CLI (plan §6.3).

    python scripts/30_build_communities.py

Runs Leiden over the provider co-occurrence graph and writes Community
nodes + IN_COMMUNITY edges. Deterministic (fixed RANDOM_SEED in
graph/communities.py) — re-running against an unchanged graph reproduces
the same communities with the same community_ids.
"""

from __future__ import annotations

import structlog
from neo4j import GraphDatabase

from specter.graph.communities import build_communities
from specter.settings import get_settings

logger = structlog.get_logger(__name__)


def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    try:
        count = build_communities(driver)
        logger.info("build_communities.complete", community_count=count)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
