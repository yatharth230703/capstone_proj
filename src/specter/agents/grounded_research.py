"""Grounded Research Agent (plan §9.6, CLAUDE.md "the grounding agent will
break if you do this wrong"). The system's one non-Azure LLM call.

**Not built via `agents._base.build_agent`.** That helper always resolves
its model through `ModelRouter.model_for_tier()`, which wraps every tier in
`LiteLlm` — appropriate for the Azure agents, wrong here. ADK's built-in
`google_search` tool only works with ADK's native `Gemini` model class,
which `LlmAgent` resolves automatically from a bare `"gemini-*"` model
*string* (see `google.adk.models.registry.LLMRegistry`). This agent also
has no Specter tool bindings and no evidence bundle, so it needs none of
`_base.py`'s cache-boundary/L1-cache machinery either. `router.resolve(
"grounded_research")` is still used — for the model name only — so
`config/models.yaml` stays the single source of routing truth (CLAUDE.md:
"Routing transparency is a graded requirement").

**Trap that cost real debugging time:** `Settings` reads `.env` through
pydantic-settings, which does NOT populate `os.environ`. ADK's `Gemini`
model builds its `google.genai.Client` by reading `GOOGLE_GENAI_USE_VERTEXAI`
/ `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` /
`GOOGLE_APPLICATION_CREDENTIALS` straight from `os.environ` — not from our
`Settings` object, and not from any ADK constructor kwarg by default. Without
`_ensure_vertex_env` below, the client silently falls back to
non-Vertex/AI-Studio mode (or fails auth) even though `.env` looks correct.
See `NOTES_API_DEVIATIONS.md` D14.

**The isolation rule (CLAUDE.md), enforced structurally, not by convention:**
`GroundedResearchAgent` gets exactly one tool (`google_search`) and is never
a `sub_agent` of a tool-bearing agent. Consumers must call
`build_grounded_research_tool()` and add the result to their own `tools=[]`
— never import `build_grounded_research_agent()` and attach it as a
`sub_agent`.
"""

from __future__ import annotations

import os
from pathlib import Path

import structlog
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.google_search_tool import google_search
from google.genai import types

from specter.core.contracts import EvidenceArtifact, GroundedResearchResult
from specter.core.hashing import sha256_text
from specter.llm.router import ModelRouter
from specter.settings import Settings
from specter.tools.evidence_tools import store_artifact

logger = structlog.get_logger(__name__)

_APP_NAME = "specter_grounded_research"
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_PROMPT_PATH = _REPO_ROOT / "prompts" / "agents" / "grounded_research.md"


def _ensure_vertex_env(settings: Settings) -> None:
    """Forwards `.env`'s Vertex settings into `os.environ` for ADK's native
    Gemini client, which reads them directly and ignores `Settings`. Uses
    `setdefault` so an operator's own shell env always wins. Fails loudly
    (hard rule 7) rather than letting the client silently pick a backend
    nobody asked for.
    """
    if settings.google_cloud_project is None:
        raise ValueError(
            "GOOGLE_CLOUD_PROJECT is unset — grounded_research needs it to build a "
            "Vertex client (CLAUDE.md M4)"
        )
    os.environ.setdefault(
        "GOOGLE_GENAI_USE_VERTEXAI", "TRUE" if settings.google_genai_use_vertexai else "FALSE"
    )
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", settings.google_cloud_project)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", settings.google_cloud_location)
    if settings.google_application_credentials is not None:
        os.environ.setdefault(
            "GOOGLE_APPLICATION_CREDENTIALS", str(settings.google_application_credentials)
        )


def build_grounded_research_agent(router: ModelRouter, settings: Settings) -> LlmAgent:
    """The isolated search agent. Exactly one tool — do not add another."""
    _ensure_vertex_env(settings)
    model = router.resolve("grounded_research").model
    instruction = _PROMPT_PATH.read_text().strip()
    return LlmAgent(
        name="GroundedResearchAgent",
        model=model,
        instruction=instruction,
        tools=[google_search],
    )


def build_grounded_research_tool(agent: LlmAgent) -> AgentTool:
    """What other agents actually receive — never `agent` itself as a
    `sub_agent`. `propagate_grounding_metadata=True` is what keeps citations
    from silently vanishing (D10): without it, `AgentTool` discards
    `grounding_metadata` after forwarding only the response text.
    """
    return AgentTool(agent=agent, propagate_grounding_metadata=True)


async def research_topic(
    query: str, agent: LlmAgent, evidence_dir: Path
) -> GroundedResearchResult:
    """Runs one query directly against the isolated agent (not through a
    consumer's `AgentTool` call — this is the standalone entry point M4's
    own checkpoint exercises) and turns every web grounding chunk into an
    `EvidenceArtifact`. Returns zero citations, not a fabricated one, if the
    model didn't ground its answer — that's a real possible outcome, not a
    bug to paper over.
    """
    session_service = InMemorySessionService()  # type: ignore[no-untyped-call]
    session_id = sha256_text(query)[:16]
    runner = Runner(app_name=_APP_NAME, agent=agent, session_service=session_service)
    content = types.Content(role="user", parts=[types.Part(text=query)])

    narrative = ""
    grounding_metadata = None
    try:
        session = await session_service.create_session(
            app_name=_APP_NAME, user_id="specter", session_id=session_id
        )
        async for event in runner.run_async(
            user_id="specter", session_id=session.id, new_message=content
        ):
            if event.grounding_metadata:
                grounding_metadata = event.grounding_metadata
            if event.is_final_response() and event.content and event.content.parts:
                narrative = "\n".join(
                    p.text for p in event.content.parts if not p.thought and p.text
                )
    finally:
        # `close()` tears down toolsets/MCP sessions — same pattern as
        # `_llm_call._invoke` (M7 depends on this).
        await runner.close()  # type: ignore[no-untyped-call]

    citations: list[EvidenceArtifact] = []
    chunks = grounding_metadata.grounding_chunks if grounding_metadata else None
    if not chunks:
        logger.warning("grounded_research.no_citations", query=query)
    else:
        for chunk in chunks:
            if chunk.web is None or chunk.web.uri is None:
                continue
            content_text = f"{chunk.web.title or chunk.web.uri}\n{chunk.web.uri}"
            citations.append(
                store_artifact(
                    content=content_text,
                    content_type="text/plain",
                    source_id="vertex_grounding",
                    evidence_dir=evidence_dir,
                    extraction_method="vertex_grounding",
                )
            )

    return GroundedResearchResult(
        query=query, model=agent.model if isinstance(agent.model, str) else str(agent.model),
        narrative=narrative, citations=citations,
    )
