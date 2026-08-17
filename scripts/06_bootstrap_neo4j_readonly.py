#!/usr/bin/env python
"""Idempotent Neo4j read-only user bootstrap (CLAUDE.md "Neo4j MCP
guardrails", M7).

    python scripts/06_bootstrap_neo4j_readonly.py

This project's Neo4j (`docker-compose.yml`) is **Community Edition**, which
does not support `CREATE ROLE`/`GRANT` (`Neo.ClientError.Statement.
UnsupportedAdministrationCommand`, verified live). `CREATE USER` is
CE-supported, so this creates a dedicated `specter_ro` user
(`NEO4J_READONLY_USER`/`NEO4J_READONLY_PASSWORD` in `.env`); the actual
read-only *enforcement* comes from every guarded query running in a session
opened with `default_access_mode="READ"` (`tools/mcp_tools.run_guarded_cypher`),
which Neo4j enforces server-side independent of RBAC. See
`NOTES_API_DEVIATIONS.md` for the full deviation writeup.
"""

from __future__ import annotations

import structlog
from neo4j import GraphDatabase

from specter.settings import get_settings

logger = structlog.get_logger(__name__)


def main() -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value())
    )
    try:
        with driver.session() as session:
            session.run(
                "CREATE USER $user IF NOT EXISTS SET PASSWORD $password CHANGE NOT REQUIRED",
                user=settings.neo4j_readonly_user,
                password=settings.neo4j_readonly_password.get_secret_value(),
            ).consume()
        logger.info("neo4j_readonly.bootstrapped", user=settings.neo4j_readonly_user)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
