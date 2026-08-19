"""The one write endpoint in this API (M13; CLAUDE.md Amendment 4(a), the
operator's 2026-08-18 exception to the dashboard's read-only rule, closing
debt D-15 — `grounded_research` had no live consumer since M4).

Conditions this endpoint must hold, verbatim from Amendment 4(a):
- **POST, never GET** — never fired on page load or by a background poller.
- **Cost visible in the ledger** — `research_topic` is called with this
  app's shared `AgentRuntime` so the call's real token usage lands in
  `llm_calls` like every other agent (see `agents/grounded_research.py`'s
  `router`/`ledger` params, added this milestone for exactly this).
- **D-15 disclosed, not papered over** — every response carries
  `citation_disclosure`, spelled out in the JSON, not just a code comment:
  grounding URIs are Google redirect links
  (`vertexaisearch.cloud.google.com/grounding-api-redirect/...`), not the
  cited page's real URL (NOTES_API_DEVIATIONS.md D15).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from specter.agents.grounded_research import build_grounded_research_agent, research_topic
from specter.core.contracts import EvidenceArtifact
from specter.settings import get_settings

router = APIRouter()

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_EVIDENCE_DIR = _REPO_ROOT / "data" / "evidence"

_CITATION_DISCLOSURE = (
    "Each citation's stored content is a Google grounding redirect link "
    "(vertexaisearch.cloud.google.com/grounding-api-redirect/...), not the "
    "cited page's real URL, and is not directly followable outside a "
    "session where Google resolves it (NOTES_API_DEVIATIONS.md D15)."
)


class ResearchRequest(BaseModel):
    query: str = Field(min_length=1)


def _citation_view(artifact: EvidenceArtifact) -> dict[str, Any]:
    """Adds the human-facing `title`/`url` the dashboard links to.
    `grounded_research.research_topic` stores each citation's content as
    `"{title}\\n{uri}"` (the chunk's site title plus its grounding-redirect
    URL) — read back here rather than duplicating that write, so the API
    and the stored artifact can never drift apart.
    """
    title, _, url = artifact.stored_path.read_text(encoding="utf-8").partition("\n")
    return {**artifact.model_dump(mode="json"), "title": title.strip(), "url": url.strip()}


@router.post("/research")
async def run_grounded_research(body: ResearchRequest, request: Request) -> dict[str, Any]:
    settings = get_settings()
    runtime = request.app.state.runtime
    agent = build_grounded_research_agent(runtime.router, settings)
    result = await research_topic(
        body.query,
        agent,
        _EVIDENCE_DIR,
        router=runtime.router,
        ledger=runtime.ledger,
        run_id=runtime.run_id,
    )
    return {
        "query": result.query,
        "model": result.model,
        "narrative": result.narrative,
        "citations": [_citation_view(c) for c in result.citations],
        "citation_disclosure": _CITATION_DISCLOSURE,
    }
