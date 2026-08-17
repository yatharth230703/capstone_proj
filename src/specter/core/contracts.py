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
- CommunityCharacterization (M2 of BUILD_MILESTONES.md, plan §6.4
  `graph/summaries.py`)
- EntityMatchAdjudication, GraphFindings, EnforcementFindings (M3 of
  BUILD_MILESTONES.md, plan §9.3-9.5 `agents/entity_resolution.py`,
  `agents/graph_investigation.py`, `agents/enforcement_intel.py`)
- GroundedResearchResult (M4 of BUILD_MILESTONES.md, plan §9.6
  `agents/grounded_research.py`); `EvidenceArtifact` gained a required
  `extraction_method` field in the same milestone
- Rebuttal, CounterEvidence, CaseNarrative, CasePacket (M5 of
  BUILD_MILESTONES.md, plan §9.7-9.8 `agents/skeptic.py`,
  `agents/case_reporter.py`)
- CaseScore (M6 of BUILD_MILESTONES.md, plan §10 `workflow/state.ScoringService`)
- CriterionScore, RubricJudgment, BlindedCase, JudgeVerdict, CalibrationCase,
  ScenarioRecallResult, DetectionEvalReport (M9 of BUILD_MILESTONES.md, plan
  §12 `judge/`)
- AddressClassification (M11 of BUILD_MILESTONES.md, CLAUDE.md Amendment 4(c)
  `tools/maps_tools.py`)
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from specter.core.enums import (
    CacheLayer,
    DataOrigin,
    FreshnessStatus,
    LegalStatus,
    MatchDecision,
    PriorityTier,
    Verdict,
)


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

    `known_limitations`/`geocoding_method` are required (not defaulted) so
    this stays safe nested inside an agent `output_schema` (Azure strict mode
    rejects any property carrying a `default`, transitively through `$defs`)
    — every detector fills them explicitly, empty/`None` where they don't
    apply. CLAUDE.md Amendment 3 requires them on `geographic_spread`.
    """

    signal_type: str
    provider_npi: str
    value: float
    threshold: float
    source_ids: list[str]
    data_origin: DataOrigin
    detected_at: datetime
    known_limitations: list[str]
    geocoding_method: str | None


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
    community_summary_cap: int = Field(gt=0)
    # M11 (CLAUDE.md Amendment 4(c)). `physical_existence_implausible_types`
    # lives here rather than in a separate config block so it reaches every
    # detector through the one `load_thresholds` path already plumbed
    # everywhere. Defaulted so an older `config/screening.yaml` still parses.
    physical_existence_min_colocated: float = 1.0
    physical_existence_implausible_types: list[str] = Field(
        default_factory=lambda: ["residential", "mailbox_store", "po_box"]
    )


LocationType = Literal[
    "residential", "mailbox_store", "po_box", "commercial", "unclassified"
]


class AddressClassification(SpecterModel):
    """Output of `tools/maps_tools.classify` (M11, CLAUDE.md Amendment 4(c)) —
    the Physical Existence signal `phase_1_build_plan.md` Amendment 3 deferred
    to Phase 2.

    `location_type` is derived by a documented, pure function over a Google
    Address Validation response — never by a model, and never by an LLM
    guessing what kind of place an address is. `"unclassified"` is a valid,
    expected result (a PO-box-only ZIP, a rural route, a brand-new building
    Google has never seen), following the precedent Amendment 3 set for
    `zip_centroid` returning `None`: never substitute a guess.
    """

    normalized_key: str
    location_type: LocationType
    matched_formatted_address: str | None
    classification_reason: str
    known_limitations: list[str]


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
    """Output of `tools/evidence_tools.store_artifact` (plan §8). CLAUDE.md
    M4: grounded-research citations set `extraction_method="vertex_grounding"`;
    every other caller states its own method explicitly (e.g. `"direct"`) —
    no default, same no-silent-defaults discipline as `RiskSignal` (M3).
    """

    artifact_id: str
    content_type: str
    source_id: str
    stored_path: Path
    created_at: datetime
    extraction_method: str


class GroundedResearchResult(SpecterModel):
    """Output of `agents/grounded_research.research_topic` (plan §9.6). Not
    an ADK `output_schema` — this agent has no structured output, only a
    narrative plus its citation trail — so it carries none of the
    strict-mode no-defaults constraints that apply to `RiskSignal`/M3.
    """

    query: str
    model: str
    narrative: str
    citations: list[EvidenceArtifact]


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


class CommunityCharacterization(AgentOutput):
    """Output of `graph/summaries.py`'s `summarize_community` LLM call (plan
    §6.4). Strict-mode-safe (no defaulted fields) unlike `CommunitySummary`,
    which it gets mapped onto for storage — `notable_members` here is
    unvalidated model output; the caller must drop any NPI not actually in
    the community before trusting it (CLAUDE.md hard rule 2).
    """

    characterization: str
    notable_members: list[str]
    risk_themes: list[str]


class EntityMatchAdjudication(AgentOutput):
    """Output of the Entity Resolution Agent (plan §9.3, M3) —
    `tools/entity_tools.propose_entity_matches` computes the deterministic
    features; adjudicating them into a match decision is this agent's job.
    Bias conservative: a false merge (`auto_link` on a non-match) is worse
    than a missed match.
    """

    npi: str
    candidate_npi: str
    matching_features: list[str]
    conflicting_features: list[str]
    match_probability: float = Field(ge=0.0, le=1.0)
    decision: MatchDecision


class GraphFindings(AgentOutput):
    """Output of the Graph Investigation Agent (plan §9.4, M3) — the first
    GraphRAG consumer. `signals` are echoed back from the deterministic
    detectors, never re-derived; `after_model_callback` enforces that every
    numeric literal in `narration`/`community_context` traces to a tool
    result already gathered for this call (CLAUDE.md hard rule 1).
    """

    signals: list[RiskSignal]
    community_context: str
    narration: str
    linked_entities: list[str]


class CaseLegalStatus(AgentOutput):
    """One `(case_id, legal_status)` pair. A list of these, not a
    `dict[str, LegalStatus]` — Azure strict-mode structured output cannot
    represent an open-ended `dict` (no fixed `properties`/`required`); see
    NOTES_API_DEVIATIONS.md.
    """

    case_id: str
    legal_status: LegalStatus


class EnforcementFindings(AgentOutput):
    """Output of the Enforcement Intelligence Agent (plan §9.5, M3). A match
    built on a common-name hit (no NPI, no exact identifier overlap) goes in
    `disambiguation_flags`, never silently into `matches` as settled — the
    same "no auto-link without an exact identifier" rule as CLAUDE.md
    Amendment 1's state-exclusion matching.
    """

    matches: list[str]
    typologies: list[str]
    legal_status_per_match: list[CaseLegalStatus]
    disambiguation_flags: list[str]


class Rebuttal(SpecterModel):
    """One counter-argument against one fired signal (plan §9.7). Nested
    inside `CounterEvidence` (an `AgentOutput`) — no defaults, same
    transitive strict-mode rule `RiskSignal` established in M3.
    """

    signal_type: str
    benign_explanation: str | None
    no_plausible_benign_explanation: bool
    reasoning: str


class CounterEvidence(AgentOutput):
    """Output of the Skeptic Agent (plan §9.7, M5). CLAUDE.md hard rule 8:
    `confidence_adjustment` is the one LLM-influenced number the (M6)
    deterministic `ScoringService` may read — a bounded, auditable discount,
    never a fact the Skeptic derives itself.
    """

    per_signal: list[Rebuttal]
    unresolved_conflicts: list[str]
    confidence_adjustment: float = Field(ge=-0.4, le=0.0)


class CaseNarrative(AgentOutput):
    """Output of the Case Reporter Agent (plan §9.8, M5) — deliberately
    narrow. CLAUDE.md hard rule 1 means `CasePacket`'s `signals`/citations/
    `legal_status_per_match` must be echoed from already-computed data, not
    regenerated by the model, so the LLM only ever produces prose.
    `exhibited_indicators_summary`'s claimed count is checked the same way
    as any other number in `narrative` — against a `signal_count` entry
    `case_reporter.build_evidence` adds to the evidence bundle.
    """

    narrative: str
    exhibited_indicators_summary: str


class CasePacket(SpecterModel):
    """The final artifact (plan §9.8, M5) — M9's judge subsystem grades
    this. Assembled in plain Python by `case_reporter.synthesize`, NOT an
    agent `output_schema` itself, so none of `AgentOutput`'s strict-mode
    constraints apply here. `confidence_adjustment` on `counter_evidence` is
    the only LLM-influenced number anywhere in this packet (CLAUDE.md hard
    rule 8) — every other number traces to a deterministic tool result.
    """

    provider_npi: str
    narrative: str
    signals: list[RiskSignal]
    enforcement_matches: list[str]
    legal_status_per_match: list[CaseLegalStatus]
    counter_evidence: CounterEvidence
    citation_report: CitationReport
    created_at: datetime


class CaseScore(SpecterModel):
    """Output of `workflow/state.ScoringService` (plan §10, M6) — deterministic
    code, never an agent (CLAUDE.md hard rule 8). `evidence_quality` is the
    only dimension `confidence_adjustment` (the Skeptic's bounded
    `[-0.4, 0.0]` discount) touches; every other dimension traces to
    `RiskSignal`/`EntityMatchAdjudication`/`EnforcementFindings` fields alone.
    `escalation_gate_reasons` is never empty: it names either the four
    conditions met (`HIGH_PRIORITY`) or which ones weren't.
    """

    provider_npi: str
    identity_integrity: float = Field(ge=0.0, le=1.0)
    network_association: float = Field(ge=0.0, le=1.0)
    adverse_history: float = Field(ge=0.0, le=1.0)
    evidence_quality: float = Field(ge=0.0, le=1.0)
    corporate_complexity: float = Field(ge=0.0, le=1.0)
    fired_signal_families: list[str]
    independent_signal_family_count: int = Field(ge=0)
    priority_tier: PriorityTier
    escalation_gate_reasons: list[str]


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


class CriterionScore(SpecterModel):
    """One of `RubricJudgment.criteria` (M9, CLAUDE.md Amendment 2 mitigation
    3 — verbatim schema). `weakness_found` may never be a placeholder: the
    judge must name a real weakness or explain specifically why the criterion
    is fully satisfied. `score` has no `default=`, same strict-mode rule
    `RiskSignal` established (M3) — this is nested inside `RubricJudgment`,
    itself an agent `output_schema`.
    """

    criterion: str
    score: int = Field(ge=0, le=5)
    supporting_quote: str
    weakness_found: str

    @field_validator("weakness_found")
    @classmethod
    def _reject_placeholder(cls, v: str) -> str:
        if not v.strip() or v.strip().lower() == "none":
            raise ValueError(
                "weakness_found must name a real weakness, or explain "
                'specifically why the criterion is fully satisfied — "none" '
                "is rejected"
            )
        return v


class RubricJudgment(AgentOutput):
    """Output of one rubric-judge sample (M9, plan §12.2) — 5 criteria:
    citation_validity, numeric_grounding, legal_discipline, counter_evidence,
    hallucination. One real Azure call produces one of these;
    `rubric_judge.py` runs 3 independent samples and folds them into a
    `JudgeVerdict`.
    """

    criteria: list[CriterionScore]


class BlindedCase(SpecterModel):
    """`CasePacket` with every provenance-bearing field stripped (CLAUDE.md
    Amendment 2 mitigation 2). Mirrors `CasePacket` field for field —
    `judge/blind.py`'s `blind_case` is what actually proves nothing leaks,
    not this shape (a real `CasePacket` already carries no agent/model/tier
    field, verified against `data/cases/*.json`).
    """

    provider_npi: str
    narrative: str
    signals: list[RiskSignal]
    enforcement_matches: list[str]
    legal_status_per_match: list[CaseLegalStatus]
    counter_evidence: CounterEvidence
    citation_report: CitationReport
    created_at: datetime


class JudgeVerdict(SpecterModel):
    """One provider's full judge result (M9): 3 `RubricJudgment` samples plus
    the variance/aggregation Amendment 2 mitigation 5 requires. Assembled in
    plain Python from 3 real LLM calls, never itself an agent `output_schema`
    — `dict[str, float]` is fine here (D13's strict-mode ban only applies to
    a model Azure validates as structured *output*).
    """

    provider_npi: str
    samples: list[RubricJudgment]
    per_criterion_variance: dict[str, float]
    low_reliability_criteria: list[str]
    aggregate_scores: dict[str, float]


class CalibrationCase(SpecterModel):
    """One entry of CLAUDE.md Amendment 2's C01-C10 table (M9,
    `judge/calibration_fixtures.py`). `injected_defect`/`expected_criterion`
    are `None` only for the two controls (C09/C10) — everything else names
    exactly one deliberately-injected defect and the criterion that must
    catch it.
    """

    fixture_id: str
    description: str
    injected_defect: str | None
    expected_criterion: str | None
    case: CasePacket


class ScenarioRecallResult(SpecterModel):
    """One synthetic scenario's detection outcome (M9, plan §12.1's headline
    metric). `detector_exists=False` for S01/S08, which have no Phase 1
    detector by design (plan's own `expected_signals=[]`) — `recall_hit` is
    `True` for those (correctly producing zero signals is correct behavior,
    not a miss), reported separately from the 8 scenarios with a real
    detector so the headline number isn't inflated by scenarios that were
    never detectable in the first place.
    """

    scenario_id: str
    expected_signals: list[str]
    fired_signal_types: list[str]
    detector_exists: bool
    recall_hit: bool


class DetectionEvalReport(SpecterModel):
    """Output of `judge/detection_eval.py` (M9, plan §12.1) — deterministic,
    no LLM. `real_positive_denominator` is reported alongside
    `real_positive_count` explicitly (BUILD_MILESTONES.md debt D-21: only 4
    real non-synthetic positives exist out of 8,445 real providers) so a
    small-sample precision number never appears without its true denominator.
    """

    precision_at_k: dict[str, float]
    scenario_recall: list[ScenarioRecallResult]
    real_positive_count: int
    real_positive_denominator: int
    ranking_method: str
    false_positive_rate: float | None
