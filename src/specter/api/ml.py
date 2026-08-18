"""Wraps `tools/ml_tools.score_provider` for the API (M13, CLAUDE.md
Amendment 4(b)). D-28 — the anomaly score is weak (`auc=0.556` on held-out
synthetic evaluation, barely above the 0.5 random baseline): every response
carries `AnomalyScore.known_limitations`/`training_set_description` verbatim,
never summarized or dropped, and the score itself is never rescaled into
anything that reads as a probability (Amendment 4(b)(5), plan §16).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from neo4j import Driver

from specter.core.contracts import AnomalyScore
from specter.tools.ml_tools import score_provider

router = APIRouter()


def score_or_error(npi: str, driver: Driver) -> AnomalyScore:
    """A missing `data/models/anomaly_isoforest-v1.joblib` or an unlabelled
    provider raises `SpecterError` from `score_provider` itself — left
    uncaught here (CLAUDE.md hard rule 7: fail loudly, never a placeholder
    0.0 score). `app.py`'s exception handler turns it into a clean 500.
    """
    return score_provider(npi, driver=driver)


@router.get("/ml/{npi}")
def get_anomaly_score(npi: str, request: Request) -> dict[str, Any]:
    score = score_or_error(npi, request.app.state.driver)
    return score.model_dump(mode="json")
