from pathlib import Path

import pytest
from pydantic import BaseModel

from specter.llm.router import ModelRouter, load_policy
from specter.settings import get_settings

MODELS_YAML = Path("config/models.yaml")


class _TriageResult(BaseModel):
    confidence: float


class _MatchResult(BaseModel):
    match_probability: float


class _SchemaResult(BaseModel):
    schema_validation_failed: bool


@pytest.fixture(scope="module")
def router() -> ModelRouter:
    settings = get_settings()
    policy = load_policy(MODELS_YAML, settings)
    # `settings=` is required for Azure tiers: `model_for` needs api_base and
    # api_key to build the LiteLlm instance, because this deployment uses the
    # Azure OpenAI v1 surface (see NOTES_API_DEVIATIONS.md).
    return ModelRouter(policy, settings=settings)


def test_resolve_known_task_class(router: ModelRouter) -> None:
    tier = router.resolve("triage_provider")
    assert tier.name == "T1_workhorse"
    assert tier.provider == "azure"


def test_resolve_unknown_task_class_raises(router: ModelRouter) -> None:
    with pytest.raises(ValueError, match="unknown task_class"):
        router.resolve("not_a_real_task_class")


def test_grounded_research_routes_to_vertex(router: ModelRouter) -> None:
    tier = router.resolve("grounded_research")
    assert tier.provider == "vertex"
    assert tier.model == "gemini-3.7-flash"


def test_judge_case_rubric_routes_to_t2_not_kimi(router: ModelRouter) -> None:
    """CLAUDE.md Amendment 2: T3_judge (Kimi) is deleted."""
    tier = router.resolve("judge_case_rubric")
    assert tier.name == "T2_reasoning"
    assert "T3" not in tier.name


def test_no_t3_judge_tier_exists(router: ModelRouter) -> None:
    assert "T3_judge" not in router._policy.tiers  # noqa: SLF001


def test_model_for_returns_cached_instance(router: ModelRouter) -> None:
    first = router.model_for("triage_provider")
    second = router.model_for("triage_provider")
    assert first is second


def test_cost_profile_overrides_tier() -> None:
    settings = get_settings()
    policy = load_policy(MODELS_YAML, settings)
    default_router = ModelRouter(policy, profile="default")
    cost_router = ModelRouter(policy, profile="cost")
    assert default_router.resolve("plan_investigation").name == "T2_reasoning"
    assert cost_router.resolve("plan_investigation").name == "T1_workhorse"


def test_should_escalate_triage_provider_low_confidence(router: ModelRouter) -> None:
    escalated = router.should_escalate("triage_provider", _TriageResult(confidence=0.30))
    assert escalated is not None
    assert escalated.name == "T2_reasoning"


def test_should_not_escalate_triage_provider_high_confidence(router: ModelRouter) -> None:
    escalated = router.should_escalate("triage_provider", _TriageResult(confidence=0.90))
    assert escalated is None


def test_should_escalate_entity_match_ambiguous_range(router: ModelRouter) -> None:
    escalated = router.should_escalate(
        "adjudicate_entity_match", _MatchResult(match_probability=0.55)
    )
    assert escalated is not None


def test_should_not_escalate_entity_match_confident(router: ModelRouter) -> None:
    escalated = router.should_escalate(
        "adjudicate_entity_match", _MatchResult(match_probability=0.95)
    )
    assert escalated is None


def test_schema_validation_failed_escalates_regardless_of_task_class(router: ModelRouter) -> None:
    escalated = router.should_escalate(
        "narrate_graph_signal", _SchemaResult(schema_validation_failed=True)
    )
    assert escalated is not None
    assert escalated.name == "T2_reasoning"
