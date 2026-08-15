"""Model routing (plan §7.3, pillar #3). Every LLM call declares a
`task_class`; the router maps it to a tier via `config/models.yaml`. Unknown
`task_class` raises — never default silently.

Escalation `when:` conditions are structured YAML (field/op/value), evaluated
by `_conditions_match` below — never `eval()`'d expression strings (plan
§7.3's explicit instruction).
"""

from __future__ import annotations

import operator
from pathlib import Path
from typing import Any

import structlog
import yaml
from google.adk.models.lite_llm import LiteLlm
from opentelemetry import trace
from pydantic import BaseModel

from specter.core.contracts import (
    EscalationCondition,
    EscalationRule,
    ProfileOverrides,
    RouterPolicy,
    TierConfig,
)
from specter.settings import Settings

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

_OPS = {
    "lt": operator.lt,
    "lte": operator.le,
    "gt": operator.gt,
    "gte": operator.ge,
    "eq": operator.eq,
    "ne": operator.ne,
}

_MODEL_ENV_ATTR = {
    "AZURE_DEPLOYMENT_NANO": "azure_deployment_nano",
    "AZURE_DEPLOYMENT_MINI": "azure_deployment_mini",
    "AZURE_DEPLOYMENT_MAIN": "azure_deployment_main",
}


def _resolve_model(tier_data: dict[str, Any], settings: Settings) -> str:
    env_name = tier_data.get("model_env")
    if env_name is None:
        model: str = tier_data["model"]
        return model
    attr = _MODEL_ENV_ATTR.get(env_name)
    if attr is None:
        raise ValueError(f"unknown model_env {env_name!r} in config/models.yaml")
    deployment = getattr(settings, attr)
    if deployment is None:
        raise ValueError(f"config/models.yaml references {env_name}, but it is unset in .env")
    # NOT `azure/` — this resource exposes the Azure OpenAI **v1** API surface
    # (AZURE_API_BASE already ends in `/openai/v1`). LiteLLM's `azure/` provider
    # appends `/openai/deployments/<dep>/chat/completions`, producing a doubled
    # path and a 404. The v1 surface is OpenAI-compatible, so `openai/<dep>`
    # plus an explicit `api_base` is the correct form. See
    # NOTES_API_DEVIATIONS.md.
    return f"openai/{deployment}"


def load_policy(path: Path, settings: Settings) -> RouterPolicy:
    raw = yaml.safe_load(path.read_text())

    tiers = {
        name: TierConfig(
            name=name,
            provider=tier_data["provider"],
            model=_resolve_model(tier_data, settings),
            max_output_tokens=tier_data["max_output_tokens"],
            temperature=tier_data["temperature"],
            supports_prefix_cache=tier_data["supports_prefix_cache"],
            price_input_per_1m=tier_data.get("price_input_per_1m"),
            price_cached_input_per_1m=tier_data.get("price_cached_input_per_1m"),
            price_output_per_1m=tier_data.get("price_output_per_1m"),
        )
        for name, tier_data in raw["tiers"].items()
    }

    escalation = [
        EscalationRule(
            task_class=rule.get("task_class"),
            conditions=[EscalationCondition(**c) for c in rule["conditions"]],
            to=rule["to"],
            max_retries=rule["max_retries"],
        )
        for rule in raw.get("escalation", [])
    ]

    profiles = {
        name: ProfileOverrides(overrides=data["overrides"])
        for name, data in raw.get("profiles", {}).items()
    }

    return RouterPolicy(
        version=raw["version"],
        tiers=tiers,
        routing=raw["routing"],
        escalation=escalation,
        profiles=profiles,
    )


def _conditions_match(conditions: list[EscalationCondition], result: BaseModel) -> bool:
    for condition in conditions:
        if not hasattr(result, condition.field):
            return False
        value = getattr(result, condition.field)
        if not _OPS[condition.op](value, condition.value):
            return False
    return True


class ModelRouter:
    def __init__(
        self,
        policy: RouterPolicy,
        profile: str = "default",
        settings: Settings | None = None,
    ) -> None:
        self._policy = policy
        self._profile = profile
        self._settings = settings
        self._model_cache: dict[str, LiteLlm] = {}

    def _tier_name_for(self, task_class: str) -> str:
        if task_class not in self._policy.routing:
            raise ValueError(f"unknown task_class: {task_class!r}")
        if self._profile != "default":
            override = self._policy.profiles.get(self._profile)
            if override is not None and task_class in override.overrides:
                return override.overrides[task_class]
        return self._policy.routing[task_class]

    def resolve(self, task_class: str) -> TierConfig:
        tier_name = self._tier_name_for(task_class)
        span = trace.get_current_span()
        span.set_attribute("specter.task_class", task_class)
        span.set_attribute("specter.tier", tier_name)
        span.set_attribute("specter.escalated", False)
        return self._policy.tiers[tier_name]

    def model_for(self, task_class: str) -> LiteLlm:
        """Returns a cached `LiteLlm` per tier — constructing one per call is
        wasteful (plan §7.3).

        Transport only goes in the constructor: `api_base`/`api_key` here,
        `temperature`/`max_output_tokens` in the agent's
        `generate_content_config`. LiteLlm applies `generate_content_config`
        *after* constructor kwargs, so setting the same knob in both means
        litellm receives duplicate parameters (`max_output_tokens` maps to
        `max_completion_tokens`, not `max_tokens`). Pick one place — see
        NOTES_API_DEVIATIONS.md.
        """
        return self.model_for_tier(self._tier_name_for(task_class))

    def model_for_tier(self, tier_name: str) -> LiteLlm:
        """Same cache as `model_for`, keyed directly on a tier name rather
        than a `task_class`. Used for escalation (M3): the escalated call
        runs at a tier the router didn't derive from `task_class` routing.
        """
        if tier_name not in self._model_cache:
            tier = self._policy.tiers[tier_name]
            self._model_cache[tier_name] = LiteLlm(model=tier.model, **self._transport(tier))
            logger.info("router.model_instantiated", tier=tier_name, model=tier.model)
        return self._model_cache[tier_name]

    def _transport(self, tier: TierConfig) -> dict[str, Any]:
        if tier.provider != "azure":
            return {}
        if self._settings is None:
            raise ValueError(
                f"tier {tier.name!r} is an Azure tier, but ModelRouter was built without "
                "settings — pass settings= so api_base/api_key can be resolved"
            )
        if self._settings.azure_api_key is None or self._settings.azure_api_base is None:
            raise ValueError(
                f"tier {tier.name!r} needs AZURE_API_KEY and AZURE_API_BASE, but one is unset"
            )
        return {
            "api_base": self._settings.azure_api_base,
            "api_key": self._settings.azure_api_key.get_secret_value(),
        }

    def should_escalate(self, task_class: str, result: BaseModel) -> TierConfig | None:
        for rule in self._policy.escalation:
            if rule.task_class is not None and rule.task_class != task_class:
                continue
            if _conditions_match(rule.conditions, result):
                span = trace.get_current_span()
                span.set_attribute("specter.task_class", task_class)
                span.set_attribute("specter.tier", rule.to)
                span.set_attribute("specter.escalated", True)
                logger.info("router.escalated", task_class=task_class, to=rule.to)
                return self._policy.tiers[rule.to]
        return None
