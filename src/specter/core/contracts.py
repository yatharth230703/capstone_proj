"""All cross-boundary Pydantic v2 contracts for Specter live in this module
(CLAUDE.md: "All contracts live in core/contracts.py"). Contracts are added
here milestone by milestone, as each milestone's plan section pins down their
exact fields — not written speculatively ahead of the milestone that defines
them.

Currently defined:
- SourceManifest, ValidationReport (M0, plan §5.4)
- SourceConfig (M1, plan §5.4 — the `cfg` argument to `Connector.fetch`/`run`)
- NormalizedAddress (M2, plan §6.2 / §8 `tools/entity_tools.py`)
- RetrievedItem, RetrievalResult (M2, plan §6.5 `graph/retrieval.py`)
- TierConfig, EscalationCondition, EscalationRule, ProfileOverrides,
  RouterPolicy (M3, plan §7.3 `llm/router.py`)
- EvidenceBundle, CompiledPrompt (M3, plan §7.1 `llm/prompt_compiler.py`)
- LlmResult (M3, plan §7.2 `llm/response_cache.py`)
- LlmCallRecord (M3, plan §7.4 `llm/ledger.py`)
- RiskSignal (M4, plan §8 `tools/signal_tools.py`)
- ScreeningThresholds (M4, `config/screening.yaml`)
- ProviderProfile, Subgraph, PeerLink, PathResult, CommunitySummary,
  EnforcementCaseHit (M4, plan §8 `tools/graph_tools.py`)
- MatchProposal (M4, plan §8 `tools/entity_tools.propose_entity_matches`)
- EvidenceArtifact, Citation, CitationReport (M4, plan §8 `tools/evidence_tools.py`)
- AgentOutput, SourceVerdict, DataQualityReport, AgentRunResult (M1 of
  BUILD_MILESTONES.md, plan §9 `agents/_base.py` + `agents/data_quality.py`)
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from specter.core.enums import CacheLayer, DataOrigin, FreshnessStatus, Verdict


class SpecterModel(BaseModel):
    """Shared base: unexpected fields are a bug, not a soft warning (CLAUDE.md
    hard rule 3 in spirit — a contract that silently accepts unknown shape is
    exactly the kind of thing that should fail loudly instead).
    """

    model_config = ConfigDict(extra="forbid")


class SourceManifest(SpecterModel):
    """One per ingested source (or per jurisdiction instance, e.g. the three
    state_medicaid manifests from CLAUDE.md Amendment 1). Produced by
    `Connector.run()` in `ingest/base.py` (M1).
    """

    source_id: str
    dataset_name: str
    original_publisher: str
    access_provider: str
    source_url: str
    license_or_terms: str
    snapshot_date: date
    retrieved_at: datetime
    checksum_sha256: str
    schema_version: str
    coverage: dict[str, Any] = Field(description="states, taxonomies, years")
    freshness_status: FreshnessStatus
    known_limitations: list[str]
    row_count: int = Field(ge=0)


class SourceConfig(SpecterModel):
    """Per-invocation configuration for a `Connector`. `params` carries
    connector-specific detail (e.g. which state a `state_medicaid` instance
    targets) so one `Connector` class can back multiple `SourceManifest`
    instances without the ABC needing to know each connector's shape.
    """

    source_id: str
    raw_dir: Path
    params: dict[str, Any] = Field(default_factory=dict)


class NormalizedAddress(SpecterModel):
    """Output of `tools/entity_tools.normalize_address` (plan §6.2). Unit/
    suite is deliberately excluded from `normalized_key` — two providers in
    different suites of one building correctly share an `Address` node.
    """

    normalized_key: str
    street_number: str | None
    street_name: str | None
    street_type: str | None
    unit: str | None
    city: str | None
    state: str | None
    zip5: str | None
    raw: str
    parse_confidence: Literal["high", "low"]


class RetrievedItem(SpecterModel):
    """One item from `GraphRetriever` (plan §6.5), with per-item provenance —
    every retrieval result must be traceable to the `DataSource` it came from.
    """

    item_type: str
    data: dict[str, Any]
    source_ids: list[str] = Field(default_factory=list)
    hop_distance: int | None = None


class RetrievalResult(SpecterModel):
    mode: Literal["local", "global", "semantic", "hybrid"]
    items: list[RetrievedItem]
    query_npi: str | None = None
    query_text: str | None = None


class TierConfig(SpecterModel):
    """One entry under `config/models.yaml`'s `tiers:`. `model` is the
    resolved LiteLLM model string — for Azure tiers this comes from
    `model_env` (an env var name, e.g. AZURE_DEPLOYMENT_NANO) resolved by
    `ModelRouter` at load time, never hardcoded in the YAML.
    """

    name: str
    provider: Literal["azure", "vertex"]
    model: str
    max_output_tokens: int = Field(gt=0)
    temperature: float = Field(ge=0.0, le=2.0)
    supports_prefix_cache: bool
    price_input_per_1m: float | None = None
    price_cached_input_per_1m: float | None = None
    price_output_per_1m: float | None = None


class EscalationCondition(SpecterModel):
    field: str
    op: Literal["lt", "lte", "gt", "gte", "eq", "ne"]
    value: float | bool | str


class EscalationRule(SpecterModel):
    task_class: str | None = Field(
        default=None, description="None means the rule applies to any task_class"
    )
    conditions: list[EscalationCondition]
    to: str
    max_retries: int = Field(ge=1)


class ProfileOverrides(SpecterModel):
    overrides: dict[str, str]


class RouterPolicy(SpecterModel):
    version: str
    tiers: dict[str, TierConfig]
    routing: dict[str, str]
    escalation: list[EscalationRule]
    profiles: dict[str, ProfileOverrides]


class EvidenceBundle(SpecterModel):
    """Provider-specific evidence for one agent call — becomes B4 (plan
    §7.1). Never touches the cached prefix (B0-B3); `PromptCompiler` keeps
    this strictly on the `user` side of the cache boundary.
    """

    provider_npi: str
    evidence: dict[str, Any]
    task_instruction: str


class CompiledPrompt(SpecterModel):
    system: str
    user: str
    prefix_token_estimate: int
    prefix_fingerprint: str
    prompt_version: str


class LlmResult(SpecterModel):
    """The value cached by `llm/response_cache.py`'s L1 whole-call cache."""

    content: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    model: str
    latency_ms: float = Field(ge=0.0)


class LlmCallRecord(SpecterModel):
    """One row of the `llm_calls` SQLite table (plan §7.4)."""

    ts: datetime
    run_id: str
    agent: str
    task_class: str
    tier: str
    model: str
    prompt_tokens: int = Field(ge=0)
    cached_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    cost_usd: float | None = None
    cache_layer: CacheLayer
    escalated: bool


class RiskSignal(SpecterModel):
    """Output of a `tools/signal_tools.py` detector (plan §8) — zero LLM
    involvement. `threshold` is recorded alongside `value` so a case packet
    stays reproducible even if `config/screening.yaml` changes later.
    """

    signal_type: str
    provider_npi: str
    value: float
    threshold: float
    source_ids: list[str]
    data_origin: DataOrigin
    detected_at: datetime


class ScreeningThresholds(SpecterModel):
    """`config/screening.yaml`'s `thresholds:` block. Every signal tool
    records the threshold it used, so a case packet stays reproducible even
    if this file changes later.
    """

    address_degree: float
    phone_degree: float
    officer_degree: float
    enumeration_burst_count: float
    enumeration_burst_window_days: int
    address_churn_count: float
    address_churn_window_days: int
    exclusion_proximity_max_hops: int
    community_exclusion_density_min_fraction: float
    geographic_spread_min_km: float
    phoenix_pattern_max_months_since_exclusion: int


class ProviderProfile(SpecterModel):
    """Output of `tools/graph_tools.get_provider_profile` (plan §8) — the
    single-provider read the rest of a case builds on.
    """

    npi: str
    organization_name: str | None
    entity_type: str | None
    state: str | None
    status: str | None
    enumeration_date: str | None
    addresses: list[dict[str, Any]]
    phones: list[str]
    officers: list[dict[str, Any]]
    taxonomies: list[dict[str, Any]]
    exclusions: list[dict[str, Any]]
    source_ids: list[str]


class Subgraph(SpecterModel):
    """Output of `tools/graph_tools.expand_neighborhood`."""

    center_npi: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class PeerLink(SpecterModel):
    """One entry of `tools/graph_tools.find_shared_attribute_peers`."""

    peer_npi: str
    attribute: Literal["address", "phone", "officer"]
    shared_value: str
    source_ids: list[str]


class PathResult(SpecterModel):
    """Output of `tools/graph_tools.shortest_path_to_exclusion`."""

    target_type: Literal["exclusion"]
    target_id: str
    hops: int
    path_node_ids: list[str]


class CommunitySummary(SpecterModel):
    """Plan §6.4. `characterization`/`risk_themes` are LLM-authored by
    `graph/summaries.py` (needs AZURE_API_KEY, not populated yet) —
    `structural_facts` alone is always available since it's deterministic.
    """

    community_id: str
    member_count: int
    structural_facts: list[str]
    characterization: str | None = None
    notable_members: list[str] = Field(default_factory=list)
    risk_themes: list[str] = Field(default_factory=list)
    generated_at: datetime | None = None
    prompt_version: str | None = None


class EnforcementCaseHit(SpecterModel):
    """Output of `tools/graph_tools.search_enforcement_cases`."""

    case_id: str
    title: str
    snippet: str
    source_ids: list[str]


class MatchProposal(SpecterModel):
    """Output of `tools/entity_tools.propose_entity_matches` (plan §8) —
    deterministic FEATURES only, never a match decision. Adjudication
    (`match_probability`, `auto_link`/`agent_review`/`human_review`/`reject`)
    is the Entity Resolution Agent's job (plan §9.3, M5) — computing a
    probability from these features is exactly the kind of judgment call
    that belongs to the LLM, not to this deterministic tool.
    """

    npi: str
    candidate_npi: str
    name_similarity: float = Field(ge=0.0, le=100.0)
    shares_address: bool
    shares_phone: bool
    shares_officer: bool
    source_ids: list[str]


class EvidenceArtifact(SpecterModel):
    """Output of `tools/evidence_tools.store_artifact` (plan §8)."""

    artifact_id: str
    content_type: str
    source_id: str
    stored_path: Path
    created_at: datetime


class Citation(SpecterModel):
    artifact_id: str
    claim: str


class CitationReport(SpecterModel):
    """Output of `tools/evidence_tools.validate_citations` — every
    `source_ids` entry must resolve to a stored `EvidenceArtifact` or an
    existing graph node (CLAUDE.md hard rule 3).
    """

    total_citations: int = Field(ge=0)
    resolved_citations: int = Field(ge=0)
    unresolved_source_ids: list[str]
    all_resolved: bool


class AgentOutput(SpecterModel):
    """Base for every agent's `output_schema` (M5+, plan §9).

    LiteLlm sends these to Azure as a `json_schema` response format with
    `strict: True` (`lite_llm.py:2321`). Strict mode rejects any property
    carrying a `default` and requires every property to appear in `required`,
    so **agent output models must not give their fields defaults** — an
    optional-looking field must be typed `X | None` and filled explicitly.
    `SpecterModel`'s `extra="forbid"` supplies the `additionalProperties:
    false` that strict mode also demands.
    """


class SourceVerdict(AgentOutput):
    """One source's line in a `DataQualityReport` (plan §9.2)."""

    source_id: str
    verdict: Verdict
    freshness_status: FreshnessStatus
    findings: list[str]
    recommended_action: str


class DataQualityReport(AgentOutput):
    """Output of the Data Quality Agent (plan §9.2). A FAIL verdict halts the
    workflow with case state `data_quality_hold` — it is the one agent whose
    output can stop the run (CLAUDE.md hard rule 7).
    """

    verdict: Verdict
    per_source: list[SourceVerdict]
    blocking_reasons: list[str]
    recommended_action: str


class AgentRunResult(SpecterModel):
    """What `agents/_base.run_agent` returns: the validated agent output plus
    the telemetry needed by the ledger and the M8 dashboard. `output` is the
    agent's `output_schema` already parsed and validated — a schema violation
    raises rather than being returned.
    """

    agent: str
    task_class: str
    tier: str
    model: str
    output: dict[str, Any]
    prompt_tokens: int = Field(ge=0)
    cached_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    cache_layer: CacheLayer
    escalated: bool
    prefix_fingerprint: str


class ValidationReport(SpecterModel):
    """Produced by `Connector.validate()` in `ingest/base.py` (M1) and
    consumed by the Data Quality Agent (plan §9.2). A FAIL verdict halts the
    workflow (CLAUDE.md hard rule 7 / plan §9.2).
    """

    source_id: str
    checked_at: datetime
    missing_columns: list[str]
    schema_drift: list[str] = Field(
        description="columns present but unexpected, or type mismatches vs. expected_columns"
    )
    null_rate_per_column: dict[str, float]
    duplicate_key_rate: float = Field(ge=0.0, le=1.0)
    row_count_delta: int | None = Field(
        default=None, description="vs. previous manifest for this source_id; None if no prior run"
    )
    date_range_sanity_ok: bool
    date_range_notes: str | None = None
    verdict: Verdict
