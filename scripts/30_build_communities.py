#!/usr/bin/env python
"""Community detection + summarization CLI (plan §6.3, §6.4).

    python scripts/30_build_communities.py                              # Leiden only
    python scripts/30_build_communities.py --summaries --limit 10       # + T1 LLM calls (dev)
    python scripts/30_build_communities.py --summaries --embeddings     # + embed + regenerate B2

`--summaries` and `--embeddings` are separate flags because they have
different cost profiles: summarization is one T1 call per community (real
money at 255 communities — develop against `--limit`), embeddings are cheap
and safe to re-run. `prompts/blocks/b2_community_summaries.md` is
regenerated whenever either ran, since either can change what it should say;
running with neither flag leaves it untouched.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import structlog
from neo4j import GraphDatabase

from specter.agents._base import build_runtime
from specter.graph.communities import build_communities
from specter.graph.summaries import (
    embed_communities,
    render_b2_community_summaries,
    summarize_communities,
)
from specter.settings import get_settings
from specter.tools.signal_tools import load_thresholds

logger = structlog.get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_B2_PATH = _REPO_ROOT / "prompts" / "blocks" / "b2_community_summaries.md"


async def _run(args: argparse.Namespace) -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    try:
        count = build_communities(driver)
        logger.info("build_communities.complete", community_count=count)

        if args.summaries:
            runtime = build_runtime(
                run_id="build-communities",
                repo_root=_REPO_ROOT,
                graph_version="m2-build-communities",
                settings=settings,
            )
            summarized = await summarize_communities(driver, runtime, limit=args.limit)
            logger.info("build_communities.summarized", count=summarized)

        if args.embeddings:
            embedded = embed_communities(driver, settings)
            logger.info("build_communities.embedded", count=embedded)

        if args.summaries or args.embeddings:
            thresholds = load_thresholds(_REPO_ROOT / "config" / "screening.yaml")
            body = render_b2_community_summaries(driver, thresholds.community_summary_cap)
            _B2_PATH.write_text(body + "\n")
            logger.info("build_communities.b2_regenerated", path=str(_B2_PATH))
    finally:
        driver.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--summaries", action="store_true", help="also run the T1 characterization LLM call"
    )
    parser.add_argument(
        "--embeddings", action="store_true", help="also embed community summaries"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="cap communities summarized (dev/cost control)"
    )
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
