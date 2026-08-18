"""The second write path in this API — CLAUDE.md Amendment 4(a) extended
2026-08-19, operator-requested: a user-triggered POST that screens one
provider live, through the exact same agent pipeline
`scripts/40_screen.py`/`workflow.screening.screen_one_provider` runs. Real
Azure calls, real cost, never fired automatically (no GET route, no poller).

Uses its own write-capable Neo4j driver — `app.state.driver` is deliberately
read-only (CLAUDE.md's Neo4j guardrails), and this is the one endpoint that
needs a real write (`update_legal_status_from_adjudications`, D-10).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import yaml
from fastapi import APIRouter, HTTPException, Request
from neo4j import GraphDatabase
from pydantic import BaseModel, Field

from specter.settings import Settings, get_settings
from specter.tools.graph_tools import get_provider_profile
from specter.tools.signal_tools import load_thresholds
from specter.workflow.screening import screen_one_provider
from specter.workflow.state import ScoringService

router = APIRouter()

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_EVIDENCE_DIR = _REPO_ROOT / "data" / "evidence"
_CASES_DIR = _REPO_ROOT / "data" / "cases"
_CONFIG_PATH = _REPO_ROOT / "config" / "screening.yaml"


class ScreenRequest(BaseModel):
    npi: str = Field(pattern=r"^\d{10}$")


def _confirm_azure_key_alive(settings: Settings) -> None:
    """Same discipline as `scripts/40_screen.py` — fail loudly before
    spending anything, not partway through the pipeline. The Azure key has
    flipped alive/dead six times across this project (D-20); never trust a
    prior check.
    """
    if settings.azure_api_base is None or settings.azure_api_key is None:
        raise HTTPException(
            status_code=503,
            detail="Azure is not configured (AZURE_API_BASE/AZURE_API_KEY unset)",
        )
    url = settings.azure_api_base.rstrip("/") + "/chat/completions"
    resp = httpx.post(
        url,
        headers={
            "api-key": settings.azure_api_key.get_secret_value(),
            "Content-Type": "application/json",
        },
        json={
            "model": "gpt-5.4-nano",
            "messages": [{"role": "user", "content": "ping"}],
            "max_completion_tokens": 5,
        },
        timeout=20,
    )
    if resp.status_code != 200:
        raise HTTPException(
            status_code=503,
            detail=f"Azure key check failed ({resp.status_code}): {resp.text[:300]} — "
            "not starting a live screening run against a dead key.",
        )


def _scoring_service() -> ScoringService:
    cfg = yaml.safe_load(_CONFIG_PATH.read_text())
    gate = cfg["escalation_gate"]
    return ScoringService(
        signal_families=cfg["signal_families"],
        min_independent_signal_families=gate["min_independent_signal_families"],
        evidence_freshness_days=gate["evidence_freshness_days"],
    )


@router.post("/screen")
async def run_screening(body: ScreenRequest, request: Request) -> dict[str, Any]:
    settings = get_settings()
    _confirm_azure_key_alive(settings)

    write_driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value())
    )
    try:
        # A bad/unknown npi should 404, not crash deep inside the agent
        # chain — cohort_select only ever hands screen_one_provider npis it
        # already knows exist; a user-typed npi has no such guarantee.
        if get_provider_profile(write_driver, body.npi) is None:
            raise HTTPException(
                status_code=404, detail=f"no provider with npi {body.npi} in the graph"
            )

        result = await screen_one_provider(
            body.npi,
            driver=write_driver,
            runtime=request.app.state.runtime,
            thresholds=load_thresholds(_CONFIG_PATH),
            scoring_service=_scoring_service(),
            evidence_dir=_EVIDENCE_DIR,
            cases_dir=_CASES_DIR,
        )
    finally:
        write_driver.close()
    return result
