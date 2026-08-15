"""Typed access to every environment variable in `.env.example`.

CLAUDE.md Amendment 2 removed the Foundry/Kimi judge tier — there are
deliberately no `FOUNDRY_KIMI_*` fields here. CLAUDE.md Amendment 1 removed
the SAM.gov connector — there is deliberately no `SAM_API_KEY` field here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Neo4j ---
    neo4j_uri: str = Field(alias="NEO4J_URI")
    neo4j_user: str = Field(alias="NEO4J_USER")
    neo4j_password: SecretStr = Field(alias="NEO4J_PASSWORD")
    neo4j_readonly_user: str = Field(alias="NEO4J_READONLY_USER")
    neo4j_readonly_password: SecretStr = Field(alias="NEO4J_READONLY_PASSWORD")

    # --- Redis / Phoenix ---
    redis_url: str = Field(alias="REDIS_URL")
    phoenix_collector_endpoint: str = Field(alias="PHOENIX_COLLECTOR_ENDPOINT")

    # --- Azure OpenAI (GPT family) ---
    azure_api_key: SecretStr | None = Field(default=None, alias="AZURE_API_KEY")
    azure_api_base: str | None = Field(default=None, alias="AZURE_API_BASE")
    azure_api_version: str | None = Field(default=None, alias="AZURE_API_VERSION")
    azure_deployment_nano: str | None = Field(default=None, alias="AZURE_DEPLOYMENT_NANO")
    azure_deployment_mini: str | None = Field(default=None, alias="AZURE_DEPLOYMENT_MINI")
    azure_deployment_main: str | None = Field(default=None, alias="AZURE_DEPLOYMENT_MAIN")
    azure_embedding_deployment: str | None = Field(
        default=None, alias="AZURE_EMBEDDING_DEPLOYMENT"
    )

    # --- Vertex (grounding only) ---
    google_genai_use_vertexai: bool = Field(default=True, alias="GOOGLE_GENAI_USE_VERTEXAI")
    google_cloud_project: str | None = Field(default=None, alias="GOOGLE_CLOUD_PROJECT")
    google_cloud_location: str = Field(default="us-central1", alias="GOOGLE_CLOUD_LOCATION")
    google_application_credentials: Path | None = Field(
        default=None, alias="GOOGLE_APPLICATION_CREDENTIALS"
    )
    vertex_grounding_model: str = Field(
        default="gemini-2.5-flash", alias="VERTEX_GROUNDING_MODEL"
    )

    # --- Run control ---
    specter_run_profile: Literal["default", "cost", "quality"] = Field(
        default="default", alias="SPECTER_RUN_PROFILE"
    )
    specter_cache_enabled: bool = Field(default=True, alias="SPECTER_CACHE_ENABLED")
    specter_max_cohort: int = Field(default=250, gt=0, alias="SPECTER_MAX_COHORT")
    specter_judge_sample_count: int = Field(
        default=3, gt=0, alias="SPECTER_JUDGE_SAMPLE_COUNT"
    )

    # --- Cohort defaults (authoritative source is config/screening.yaml, M6) ---
    cohort_taxonomy_prefix: str = Field(default="332", alias="COHORT_TAXONOMY_PREFIX")
    cohort_states: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["FL", "TX", "CA"], alias="COHORT_STATES"
    )

    @field_validator("cohort_states", mode="before")
    @classmethod
    def _split_cohort_states(cls, value: object) -> object:
        if isinstance(value, str):
            return [state.strip() for state in value.split(",") if state.strip()]
        return value

    @field_validator(
        "azure_api_key",
        "azure_api_base",
        "azure_api_version",
        "azure_deployment_nano",
        "azure_deployment_mini",
        "azure_deployment_main",
        "azure_embedding_deployment",
        "google_cloud_project",
        "google_application_credentials",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and value.strip() == "":
            return None
        return value


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
