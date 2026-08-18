"""FastAPI app factory (M13, CLAUDE.md Amendment 4(a)) — mounts a read-only
JSON API over the real artifacts this system already produces:
`data/cases/*.json`, `data/ledger.sqlite`, `JudgeReport.md`, Neo4j, and M11/
M12's outputs. `fastapi==0.141.1`/`uvicorn==0.52.1` are already installed
transitively via `google-adk[mcp]` — no new dependency (verified 2026-08-18).

Every router but `research.py` only reads. `research.py` is the single,
operator-approved exception (Amendment 4(a), added 2026-08-18): a
user-triggered POST that makes a real Vertex call. Nothing here computes a
`priority_tier`/anomaly score at data-generation time — every number is
either read straight off a persisted artifact or recomputed live from one,
same as `python -m specter.cli dashboard` already does for the cost ledger.

`app.state.driver` is one shared Neo4j driver, opened with the **read-only**
role (`NEO4J_READONLY_USER`/`NEO4J_READONLY_PASSWORD`) per CLAUDE.md's Neo4j
guardrails — this API only ever reads the graph. `app.state.runtime` is one
shared `AgentRuntime` (router + ledger + cache), built once at startup rather
than per-request, for `research.py`'s one live call.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from neo4j import GraphDatabase

from specter.agents._base import build_runtime
from specter.core.errors import SpecterError
from specter.settings import get_settings

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_readonly_user, settings.neo4j_readonly_password.get_secret_value()),
    )
    app.state.driver = driver
    app.state.runtime = build_runtime(
        run_id="specter-api", repo_root=REPO_ROOT, graph_version="m13-api", settings=settings
    )
    try:
        yield
    finally:
        driver.close()


def create_app() -> FastAPI:
    from specter.api import cases, costs, judge, ml, research

    app = FastAPI(title="Specter Dashboard Data API", lifespan=_lifespan)

    @app.exception_handler(SpecterError)
    async def _handle_specter_error(request: Request, exc: SpecterError) -> JSONResponse:
        # CLAUDE.md hard rule 7: fail loudly. Every `SpecterError` raised
        # anywhere below (a missing artifact, a missing model, an unlabelled
        # provider) already names what's wrong and how to fix it — this just
        # keeps that message as clean JSON instead of a raw 500 traceback.
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    app.include_router(cases.router)
    app.include_router(costs.router)
    app.include_router(judge.router)
    app.include_router(ml.router)
    app.include_router(research.router)
    return app


app = create_app()
