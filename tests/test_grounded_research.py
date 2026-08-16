"""Offline tests: agent construction, tool isolation, `AgentTool` wiring.
No live Vertex call — that's `scripts/45_smoke_grounded_research.py`, run by
hand because it costs real money (same pattern as every other M-series smoke
script).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.google_search_tool import GoogleSearchTool

from specter.agents.grounded_research import (
    _ensure_vertex_env,
    build_grounded_research_agent,
    build_grounded_research_tool,
)
from specter.llm.router import ModelRouter, load_policy
from specter.settings import get_settings

MODELS_YAML = Path("config/models.yaml")


@pytest.fixture(scope="module")
def router() -> ModelRouter:
    settings = get_settings()
    policy = load_policy(MODELS_YAML, settings)
    return ModelRouter(policy, settings=settings)


def test_agent_has_exactly_one_tool_and_it_is_google_search(router: ModelRouter) -> None:
    settings = get_settings()
    agent = build_grounded_research_agent(router, settings)
    assert len(agent.tools) == 1
    assert isinstance(agent.tools[0], GoogleSearchTool)


def test_agent_model_matches_config_models_yaml(router: ModelRouter) -> None:
    settings = get_settings()
    agent = build_grounded_research_agent(router, settings)
    assert agent.model == router.resolve("grounded_research").model


def test_tool_wraps_the_agent_with_grounding_propagation(router: ModelRouter) -> None:
    settings = get_settings()
    agent = build_grounded_research_agent(router, settings)
    tool = build_grounded_research_tool(agent)
    assert isinstance(tool, AgentTool)
    assert tool.agent is agent
    assert tool.propagate_grounding_metadata is True


def test_ensure_vertex_env_raises_loudly_without_a_project() -> None:
    settings = get_settings().model_copy(update={"google_cloud_project": None})
    with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT"):
        _ensure_vertex_env(settings)
