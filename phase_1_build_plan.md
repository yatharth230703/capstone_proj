# Project Specter — Phase 1 Build Plan

**Audience:** Claude Code (Sonnet), executing implementation.
**Scope:** Phase 1 only — the agentic architecture and its runtime. No ML models, no application UI.
**Pillars:** Minimal. Robust. Efficient. Every file must justify its existence.

---

## 0. READ THIS FIRST — Ground rules for the implementing agent

### 0.1 Verify the ADK API before writing agent code

ADK Python 2.x is recent and its API differs from 1.x in breaking ways (agent API, event model, session schema). **Do not write agent code from memory.** Before starting Milestone 4, run:

```bash
curl -sL https://raw.githubusercontent.com/google/adk-docs/main/llms-full.txt -o .context/adk-llms-full.txt
pip show google-adk   # record exact version in README
```

Read the sections on: `Agent` / `LlmAgent`, `Workflow` (graph runtime), `AgentTool`, `McpToolset`, `Runner`, `SessionService`, callbacks (`before_model_callback` / `after_model_callback`), and OpenTelemetry setup.

Where this plan shows code, treat it as **intent and contract**, not verbatim API. If the real API differs, keep the contract and adapt the call. Record any deviation in `NOTES_API_DEVIATIONS.md`.

### 0.2 Pin versions on day one

Pin `google-adk`, `litellm`, `neo4j`, `pydantic`, `openinference-instrumentation`, `arize-phoenix` in `pyproject.toml` with exact `==` versions. ADK ships constraints files; use the one matching the Python version (3.11 recommended). Note: LiteLLM had a supply-chain incident in versions 1.82.7/1.82.8 — do not pin to those; use the latest patched release, and ADK requires `litellm>=1.84`.

### 0.3 Rules that are not negotiable

1. **No LLM produces a number.** Every numeric claim (counts, degrees, percentiles, distances, dates) originates from a deterministic tool. LLMs interpret, plan, and narrate only. If an agent emits a number not present in a tool result, the Case Reporter must reject the case.
2. **No fabricated identifiers.** NPIs, case numbers, and entity IDs must exist in the graph. There is a validation pass for this; it is not optional.
3. **Every claim carries an evidence reference.** A signal without a `source_ids` array is a bug, not a soft warning.
4. **Facts, inferences, and hypotheses are separate fields** in every output schema. Never merge them into prose.
5. **`data_origin` is mandatory** on every node, edge, and signal: `public` or `synthetic`. A case packet mixing both without labelling is a hard failure.
6. **Allegation ≠ conviction.** Enforcement records carry an explicit `legal_status` enum. Never collapse it.
7. **Fail loudly.** No bare `except:`. No silent fallbacks that mask a broken source. If a source is stale, the run halts with a Data-Quality Hold.

### 0.4 Style

- Python 3.11, full type hints, `ruff` + `mypy` clean.
- Pydantic v2 for every cross-boundary contract.
- No class where a function will do. No abstraction with one implementation, except the `Connector` ABC (which will have five).
- Structured logging via `structlog`. No `print` outside `cli.py`.
- Every module ≤ 400 lines. If it grows past that, it's doing two jobs.

---

## 1. What Phase 1 must demonstrate

Seven distinct agents, orchestrated over an ADK 2.x graph workflow, screening a defined provider cohort and emitting ranked, evidence-grounded investigative leads — then a separate judge subsystem scoring those leads against ground truth.

The seven technical pillars being graded:

| # | Pillar | Where it lives |
|---|---|---|
| 1 | Graph RAG (hybrid: local / global / semantic) | `graph/retrieval.py`, consumed by Graph Investigation Agent |
| 2 | Prefix-cache-aware architecture | `llm/prompt_compiler.py` + `llm/response_cache.py` |
| 3 | Model routing (explicit policy, 3 GPT tiers + Kimi judge) | `llm/router.py` |
| 4 | Source grounding with citations | `agents/grounded_research.py` (Vertex Gemini) |
| 5 | MCP integration (Playwright, Neo4j-Cypher) | `tools/mcp_tools.py` |
| 6 | Production observability | `obs/` + Phoenix + `llm/ledger.py` |
| 7 | LLM-as-judge scoring vs. ground truth | `judge/` |

### Explicit non-goals for Phase 1

Do not build, do not stub, do not mention in code: ML anomaly models, billing z-scores, isolation forests, clinical-note NLP, document forgery detection, geospatial land-use classification, a web frontend. Phase 1's UI is `adk web` plus a terminal dashboard. Anything else is scope creep.

---

## 2. Architecture

```
                        ┌──────────────────────────────┐
                        │   FROZEN SNAPSHOT (git-lfs)  │
                        │  NPPES · LEIE · DOJ · SAM    │
                        │      · Synthetic cohort      │
                        └──────────────┬───────────────┘
                                       │  scripts/20_build_graph.py
                                       ▼
                        ┌──────────────────────────────┐
                        │   Neo4j (graph + vector idx) │
                        │   + Leiden communities       │
                        │   + community summaries      │
                        └──────────────┬───────────────┘
                                       │
   ┌───────────────────────────────────┼────────────────────────────────┐
   │                    ADK 2.x Workflow (graph runtime)                │
   │                                                                    │
   │  START → DataQuality → [gate] → cohort fan-out                     │
   │                                    │                               │
   │            ┌───────────────────────┼───────────────────────┐       │
   │            ▼                       ▼                       ▼       │
   │   EntityResolution ───→ GraphInvestigation ───→ EnforcementIntel   │
   │                                                     │              │
   │                                          [AgentTool: GroundedResearch
   │                                           — Vertex Gemini + google_search]
   │            └───────────────────────┬───────────────────────┘       │
   │                                    ▼                               │
   │                                 Skeptic                            │
   │                                    ▼                               │
   │                              CaseReporter                          │
   │                                    │                               │
   │                        Orchestrator (plans, gates, escalates)      │
   └────────────────────────────────────┼───────────────────────────────┘
                                        ▼
                             CasePacket[] (JSON, validated)
                                        │
                        ┌───────────────┴────────────────┐
                        ▼                                ▼
              DetectionEval (deterministic)      RubricJudge (Kimi-K2.6)
                  precision@k, recall              citation validity,
                  scenario recall                  hallucination, discipline
                        └───────────────┬────────────────┘
                                        ▼
                                  JudgeReport.md
```

Cross-cutting: every LLM call passes through `ModelRouter` → `PromptCompiler` → `ResponseCache` → LiteLLM, and every call is traced to Phoenix and costed into the `CostLedger`.

---

## 3. Repository layout

Create exactly this. No extra directories.

```
specter/
├── CLAUDE.md                        # agent operating rules (see companion file)
├── README.md
├── pyproject.toml
├── .env.example
├── docker-compose.yml               # neo4j, phoenix, redis
├── config/
│   ├── models.yaml                  # router policy table
│   ├── sources.yaml                 # source manifests
│   └── screening.yaml               # cohort, thresholds, escalation rules
├── data/
│   ├── raw/                         # immutable downloads (gitignored)
│   ├── snapshot/                    # frozen demo snapshot (committed)
│   └── synthetic/                   # generated scenarios (committed)
├── prompts/
│   ├── blocks/                      # static cacheable prompt blocks (.md)
│   │   ├── b0_tool_schemas.md       # generated, do not hand-edit
│   │   ├── b1_evidence_policy.md
│   │   ├── b1_output_contract.md
│   │   └── b3_exemplars/*.md
│   └── agents/                      # per-agent variable instruction (.md)
├── src/specter/
│   ├── settings.py
│   ├── cli.py
│   ├── core/
│   │   ├── contracts.py             # ALL pydantic models
│   │   ├── enums.py
│   │   ├── hashing.py
│   │   └── errors.py
│   ├── llm/
│   │   ├── router.py
│   │   ├── prompt_compiler.py
│   │   ├── response_cache.py
│   │   └── ledger.py
│   ├── ingest/
│   │   ├── base.py
│   │   ├── nppes.py
│   │   ├── leie.py
│   │   ├── doj.py
│   │   ├── sam.py
│   │   └── synthetic.py
│   ├── graph/
│   │   ├── schema.cypher
│   │   ├── loader.py
│   │   ├── communities.py
│   │   ├── summaries.py
│   │   ├── embeddings.py
│   │   └── retrieval.py
│   ├── tools/
│   │   ├── graph_tools.py
│   │   ├── signal_tools.py
│   │   ├── entity_tools.py
│   │   ├── evidence_tools.py
│   │   └── mcp_tools.py
│   ├── agents/
│   │   ├── _base.py                 # shared agent factory
│   │   ├── orchestrator.py
│   │   ├── data_quality.py
│   │   ├── entity_resolution.py
│   │   ├── graph_investigation.py
│   │   ├── enforcement_intel.py
│   │   ├── grounded_research.py
│   │   ├── skeptic.py
│   │   └── case_reporter.py
│   ├── workflow/
│   │   ├── screening.py
│   │   └── state.py
│   ├── judge/
│   │   ├── detection_eval.py
│   │   ├── rubric_judge.py
│   │   └── report.py
│   └── obs/
│       ├── tracing.py
│       └── dashboard.py
├── scripts/
│   ├── 00_bootstrap.sh
│   ├── 10_ingest.py
│   ├── 20_build_graph.py
│   ├── 30_build_communities.py
│   ├── 40_screen.py
│   └── 50_judge.py
└── tests/
    ├── test_prompt_compiler.py      # cache-stability tests — CRITICAL
    ├── test_router.py
    ├── test_contracts.py
    ├── test_graph_retrieval.py
    └── test_signal_tools.py
```

---

## 4. Configuration and secrets

### `.env.example`

```bash
# --- Azure Foundry (Azure OpenAI, GPT family) ---
AZURE_API_KEY=
AZURE_API_BASE=https://<resource>.openai.azure.com/
AZURE_API_VERSION=2025-04-01-preview

# --- Azure Foundry (Kimi K2.6, serverless / Foundry Models endpoint) ---
# NOTE: Kimi is NOT an Azure OpenAI deployment. It uses the Foundry Models
# endpoint and a separate key. Confirm both in the portal before wiring.
FOUNDRY_KIMI_ENDPOINT=
FOUNDRY_KIMI_API_KEY=
FOUNDRY_KIMI_DEPLOYMENT=Kimi-K2.6

# --- Azure embeddings ---
AZURE_EMBEDDING_DEPLOYMENT=text-embedding-3-large

# --- Google Cloud / Vertex (grounding only) ---
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=./.secrets/vertex-sa.json
VERTEX_GROUNDING_MODEL=gemini-2.5-flash

# --- Infra ---
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=specter-dev-pw
NEO4J_READONLY_USER=specter_ro
NEO4J_READONLY_PASSWORD=
REDIS_URL=redis://localhost:6379/0
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces

# --- Run control ---
SPECTER_RUN_PROFILE=default      # default | cost | quality
SPECTER_CACHE_ENABLED=true
SPECTER_MAX_COHORT=250
```

**Important on Kimi:** Kimi K2.6 in Foundry is a Foundry Models deployment, not an Azure OpenAI one. It does **not** reliably expose prompt caching, which is fine — the judge is a one-off pass. Route it through LiteLLM using the Foundry Models OpenAI-compatible endpoint (`azure_ai/...` provider prefix) with its own base URL and key. Verify the exact model string against your deployment before assuming; if `azure_ai/` fails, fall back to a raw `openai/`-compatible LiteLlm config pointed at the Foundry endpoint. Write whichever works into `config/models.yaml` and note it in the README.

### `config/models.yaml` — the router policy table

```yaml
version: "1.0.0"

tiers:
  T0_bulk:
    provider: azure
    model: "azure/gpt-5.4-nano"
    max_output_tokens: 512
    temperature: 0.0
    supports_prefix_cache: true

  T1_workhorse:
    provider: azure
    model: "azure/gpt-5.4-mini"
    max_output_tokens: 2048
    temperature: 0.1
    supports_prefix_cache: true

  T2_reasoning:
    provider: azure
    model: "azure/gpt-5.4"
    max_output_tokens: 4096
    temperature: 0.2
    supports_prefix_cache: true

  T3_judge:
    provider: foundry_models
    model: "azure_ai/Kimi-K2.6"
    max_output_tokens: 4096
    temperature: 0.0
    supports_prefix_cache: false

  T_ground:
    provider: vertex
    model: "gemini-2.5-flash"
    max_output_tokens: 2048
    temperature: 0.0
    supports_prefix_cache: false   # grounding metadata is the point, not cache

# task_class -> tier. Every LLM call in the system declares a task_class.
routing:
  normalize_address:        T0_bulk
  classify_taxonomy:        T0_bulk
  dedup_evidence:           T0_bulk
  coerce_schema:            T0_bulk
  prefilter_entity_pair:    T0_bulk

  adjudicate_entity_match:  T1_workhorse
  extract_enforcement_case: T1_workhorse
  narrate_graph_signal:     T1_workhorse
  triage_provider:          T1_workhorse
  summarize_community:      T1_workhorse
  assess_source_quality:    T1_workhorse

  plan_investigation:       T2_reasoning
  challenge_hypothesis:     T2_reasoning
  synthesize_case:          T2_reasoning

  grounded_research:        T_ground
  judge_case_rubric:        T3_judge

# Escalation: conditions under which a task_class is re-run one tier up.
escalation:
  - when: "task_class == 'triage_provider' and result.confidence < 0.60"
    to: T2_reasoning
    max_retries: 1
  - when: "task_class == 'adjudicate_entity_match' and 0.45 <= result.match_probability <= 0.65"
    to: T2_reasoning
    max_retries: 1
  - when: "schema_validation_failed"
    to: T2_reasoning
    max_retries: 1

profiles:
  cost:
    overrides: { plan_investigation: T1_workhorse, synthesize_case: T1_workhorse }
  quality:
    overrides: { triage_provider: T2_reasoning, adjudicate_entity_match: T2_reasoning }
```

**Design note for the presentation:** Microsoft Foundry ships a managed Model Router product. We deliberately do not use it — it would hide routing decisions behind a trained black box, and routing transparency is a core requirement here. Document this choice in the README.

---

## 5. Data layer

### 5.1 Cohort

**DME suppliers (NPPES taxonomy prefix `332`), states FL / TX / CA.** Chosen for enforcement density and clean taxonomy boundaries. Configured in `config/screening.yaml`; nothing may hard-code it.

### 5.2 Sources

| Source | Access | Yields | Est. volume |
|---|---|---|---|
| **NPPES** | NPI Registry API (`https://npiregistry.cms.hhs.gov/api/`), paged | Provider, Address, Phone, AuthorizedOfficial, Taxonomy | 25–40k orgs |
| **HHS OIG LEIE** | Single CSV download | Exclusion nodes, positive labels | ~80k rows, filtered |
| **DOJ** | Press-release index pages, healthcare-fraud filtered; fetch via Playwright MCP | EnforcementCase nodes + text corpus | 300–500 releases |
| **SAM.gov** | Entity/exclusions API | Second adverse-action source | small |
| **Synthetic** | Generated locally | 50 planted-scenario providers + 150 benign controls | 200 |

### 5.3 The frozen-snapshot rule

Live ingestion is the biggest failure risk in a demo. Therefore:

- `scripts/10_ingest.py --live` writes to `data/raw/` with full provenance.
- `scripts/10_ingest.py --freeze` promotes `data/raw/` → `data/snapshot/` as compressed Parquet + a `MANIFEST.yaml`.
- **The screening pipeline reads `data/snapshot/` only.** Never `data/raw/`.
- The demo runs off the committed snapshot. Live ingestion is demonstrated on 2–3 entities as a separate, short showcase.

### 5.4 `Connector` ABC — `ingest/base.py`

```python
class SourceManifest(BaseModel):
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
    coverage: dict[str, Any]          # states, taxonomies, years
    freshness_status: Literal["current", "delayed", "historical", "unknown"]
    known_limitations: list[str]
    row_count: int

class Connector(ABC):
    source_id: ClassVar[str]
    expected_columns: ClassVar[frozenset[str]]

    @abstractmethod
    def fetch(self, cfg: SourceConfig) -> Path: ...
    @abstractmethod
    def parse(self, raw: Path) -> pl.DataFrame: ...
    @abstractmethod
    def validate(self, df: pl.DataFrame) -> ValidationReport: ...
    def run(self, cfg) -> tuple[pl.DataFrame, SourceManifest]:
        """fetch -> hash -> parse -> validate -> manifest. Raises on FAIL."""
```

Use Polars, not Pandas.

`ValidationReport` must report: missing columns, schema drift vs. `expected_columns`, null rate per column, duplicate-key rate, row-count delta vs. previous manifest, date-range sanity, and a verdict of `PASS | WARN | FAIL`.

### 5.5 Synthetic scenarios — `ingest/synthetic.py`

Do **not** pull in Synthea for Phase 1. It generates patients and encounters, and Phase 1 has no claims layer to consume them. Generate the graph-visible scenarios directly. Ten scenarios, five providers each:

| ID | Scenario | Planted signal |
|---|---|---|
| S01 | Shell provider at residential address | Address type + zero co-located facilities |
| S02 | Multiple providers sharing one phone | Phone degree ≥ 5 |
| S03 | Address cluster | Address degree ≥ 8, all enumerated within 90 days |
| S04 | Officer reuse across rapid incorporations | AuthorizedOfficial degree ≥ 4 |
| S05 | One hop from an excluded individual | Shortest path to `Exclusion` = 2 |
| S06 | Phoenix entity | New org, same address+officer as a recently excluded org |
| S07 | Rapid address churn | ≥ 3 `CHANGED_ADDRESS_TO` edges in 12 months |
| S08 | Dormant reactivation | Long enumeration-to-first-activity gap |
| S09 | Geographic implausibility | Same officer, orgs > 1500 km apart |
| S10 | Dense community | Provider inside a community with ≥ 2 excluded members |

Plus **150 benign controls** that superficially resemble positives — legitimate multi-tenant medical buildings (high address degree, but co-located with hospitals), legitimate multi-site chains (officer reuse, but stable and old). Without these your precision number is meaningless and the Skeptic Agent has nothing to catch.

Every synthetic record: `data_origin="synthetic"`, `scenario_id`, `generator_version`, `expected_signals: list[str]`.

---

## 6. Graph layer (Neo4j)

### 6.1 Schema — `graph/schema.cypher`

Phase 1 uses a reduced node set. The full doc lists 22 node types; implement 11.

**Nodes:** `Provider` (org or individual, `entity_type` property), `Address`, `Phone`, `Officer`, `Taxonomy`, `Exclusion`, `EnforcementCase`, `Community`, `DataSource`, `EvidenceArtifact`, `RiskSignal`.

**Relationships:** `LOCATED_AT`, `HAS_PHONE`, `HAS_OFFICER`, `HAS_TAXONOMY`, `EXCLUDED_BY`, `MENTIONED_IN`, `CHANGED_ADDRESS_TO`, `IN_COMMUNITY`, `EVIDENCED_BY`, `SIGNAL_ON`, `SUCCEEDS`.

Every node and relationship carries: `data_origin`, `source_id`, `observed_at`, `ingested_at`, `confidence`. Temporal `valid_from` / `valid_to` on `LOCATED_AT`, `HAS_PHONE`, `HAS_OFFICER` only — the ones that actually change. Do not put temporal properties on everything; it costs write throughput and buys nothing in Phase 1.

Constraints and indexes:

```cypher
CREATE CONSTRAINT provider_npi IF NOT EXISTS
  FOR (p:Provider) REQUIRE p.npi IS UNIQUE;
CREATE CONSTRAINT address_key IF NOT EXISTS
  FOR (a:Address) REQUIRE a.normalized_key IS UNIQUE;
CREATE CONSTRAINT phone_e164 IF NOT EXISTS
  FOR (ph:Phone) REQUIRE ph.e164 IS UNIQUE;
CREATE INDEX provider_state IF NOT EXISTS FOR (p:Provider) ON (p.state);
CREATE INDEX provider_enum_date IF NOT EXISTS FOR (p:Provider) ON (p.enumeration_date);

CREATE VECTOR INDEX case_embedding IF NOT EXISTS
  FOR (c:EnforcementCase) ON (c.embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 3072,
                          `vector.similarity_function`: 'cosine'}};
CREATE VECTOR INDEX community_embedding IF NOT EXISTS
  FOR (cm:Community) ON (cm.embedding)
  OPTIONS {indexConfig: {`vector.dimensions`: 3072,
                          `vector.similarity_function`: 'cosine'}};
```

`text-embedding-3-large` is 3072-dim. If you reduce dimensions via the API `dimensions` parameter, update both indexes to match.

### 6.2 Address normalization — do this properly

Address matching is the load-bearing signal in this entire system. A sloppy normalizer produces false address clusters, which produce false leads, which the judge then correctly punishes.

Use `usaddress` to parse, then build `normalized_key` from: `street_number | street_name_normalized | street_type_abbrev | zip5`. Deliberately **exclude** suite/unit from the key, and store it as a separate `unit` property. Two providers in Suite 100 and Suite 400 of the same building share an `Address` node — which is correct, because that's the fact — and the Skeptic Agent is what distinguishes "medical office building" from "shell cluster."

Write unit tests with at least 20 real-world address pairs that must and must not collide.

### 6.3 Communities — `graph/communities.py`

Project a provider-provider co-occurrence graph (edge if two providers share an Address, Phone, or Officer; weight = number of shared attribute types). Run Leiden via `igraph` (`igraph.Graph.community_leiden(objective_function="modularity")`). Write `Community` nodes and `IN_COMMUNITY` edges back.

Do **not** use the `graphrag` pip package. It's opinionated, slow, and you cannot explain it in a demo. This is ~120 lines you fully control.

Filter: discard communities with < 3 or > 200 members. The giant component is noise.

### 6.4 Community summaries — `graph/summaries.py`

For each surviving community, assemble a deterministic fact block (member count, shared addresses, shared officers, enumeration date range, excluded-member count, state spread) and send it to `summarize_community` (T1). Output a strict schema:

```python
class CommunitySummary(BaseModel):
    community_id: str
    member_count: int
    structural_facts: list[str]      # verbatim from the deterministic block
    characterization: str            # <= 3 sentences, LLM
    notable_members: list[str]       # NPIs, must exist in graph
    risk_themes: list[str]
    generated_at: datetime
    prompt_version: str
```

Persist to the `Community` node and embed `characterization + risk_themes`.

**These summaries are static between graph versions — they go into prompt cache block 2.** That is the point where GraphRAG and the caching architecture meet, and it should be called out in the README.

### 6.5 Hybrid retrieval — `graph/retrieval.py`

Three modes behind one entry point. Each returns `RetrievalResult` with a `mode` field and per-item provenance.

```python
class GraphRetriever:
    def local(self, npi: str, hops: int = 2,
              limit: int = 50) -> RetrievalResult:
        """Deterministic Cypher k-hop expansion. No LLM."""

    def global_(self, query: str, k: int = 5) -> RetrievalResult:
        """Vector search over community summaries -> return summaries +
        structural facts. The 'global' GraphRAG layer."""

    def semantic(self, query: str, k: int = 10) -> RetrievalResult:
        """Vector search over EnforcementCase text."""

    def hybrid(self, npi: str, query: str) -> RetrievalResult:
        """local + global_ + semantic, deduplicated, provenance preserved."""
```

`hops` must be capped at 3 and `limit` at 200 — hard-coded ceilings, not config. An unbounded expansion on a hub address node will return the entire graph and blow the context window.

---

## 7. The LLM layer

### 7.1 `llm/prompt_compiler.py` — the cache architecture

This is the most important file in the repo. Get it wrong and pillar #2 silently evaporates.

**Block order (stable → variable):**

| Block | Content | Changes when |
|---|---|---|
| B0 | Tool schemas, JSON-serialized, sorted by name | Tool signature changes |
| B1 | Evidence policy + output contract + prohibited conclusions | Policy version bump |
| B2 | Graph community summaries relevant to the cohort | Graph version bump |
| B3 | Few-shot exemplars | Prompt version bump |
| — | **CACHE BOUNDARY** | — |
| B4 | Provider-specific evidence bundle | Every call |
| B5 | Current task instruction | Every call |

```python
class CompiledPrompt(BaseModel):
    system: str                 # B0..B3 concatenated
    user: str                   # B4..B5
    prefix_token_estimate: int
    prefix_fingerprint: str     # sha256 of `system`
    prompt_version: str

class PromptCompiler:
    def __init__(self, blocks_dir: Path, graph_version: str,
                 policy_version: str) -> None: ...
    def compile(self, agent: str, task_class: str,
                evidence: EvidenceBundle) -> CompiledPrompt: ...
```

**Four invariants. Each gets a test in `tests/test_prompt_compiler.py`. These tests are not optional — they are the only thing standing between you and a 0% cache hit rate.**

1. **`test_prefix_is_deterministic`** — compile the same agent/task_class twice, 10 seconds apart, assert `prefix_fingerprint` is identical. Catches `datetime.now()`, `uuid4()`, and `id()` leakage.
2. **`test_prefix_stable_across_evidence`** — compile with three different providers, assert all three `prefix_fingerprint` values match. Catches provider data bleeding above the boundary.
3. **`test_prefix_exceeds_threshold`** — assert `prefix_token_estimate >= 1200` for every registered agent. Azure needs a stable prefix of ~1024+ tokens before caching engages at all. For T0 agents this means keeping the full policy block even though it feels wasteful: a cached 1200-token prefix at ~10% of input rate beats an uncached 300-token one.
4. **`test_serialization_is_sorted`** — assert `json.dumps(..., sort_keys=True)` everywhere in B0–B3, and that iterating a dict twice yields the same block bytes.

**Forbidden above the cache boundary:** timestamps, UUIDs, run IDs, trace IDs, random sampling, unsorted set/dict iteration, `repr()` of objects with memory addresses, absolute file paths that vary by machine.

Instrument via an ADK `after_model_callback` that reads `usage.prompt_tokens_details.cached_tokens` off the LiteLLM response and records `(agent, task_class, prompt_tokens, cached_tokens, completion_tokens)` to the ledger. Cache hit rate = `cached_tokens / prompt_tokens`, reported per agent.

### 7.2 `llm/response_cache.py` — L1

Whole-call caching. This is where most of the actual savings come from on re-screening, and it's the most visible demo effect.

Key: `sha256(agent_name | prompt_version | model_id | canonical_json(evidence_bundle))`.
Store: Redis, TTL 7 days, value = serialized `LlmResult` plus original token counts.
On hit: record a `cache_hit` event with the *avoided* cost so the ledger can show cumulative savings.

Disable via `SPECTER_CACHE_ENABLED=false` so you can demo cold vs. warm side by side.

### 7.3 `llm/router.py`

```python
class ModelRouter:
    def __init__(self, policy: RouterPolicy, profile: str = "default") -> None: ...
    def resolve(self, task_class: str) -> TierConfig: ...
    def model_for(self, task_class: str) -> LiteLlm: ...   # cached instances
    def should_escalate(self, task_class: str,
                        result: BaseModel) -> TierConfig | None: ...
```

- Unknown `task_class` → raise. Never default silently.
- Return cached `LiteLlm` instances; constructing one per call is wasteful.
- Escalation rules are evaluated by an explicit small evaluator over the parsed result object. **Do not `eval()` the `when:` strings.** Parse them into a tiny predicate structure (`field`, `op`, `value`) at config-load time, or — simpler and more robust — represent them as structured YAML instead of expression strings. Prefer the structured form.
- Every routing decision emits a span attribute: `specter.task_class`, `specter.tier`, `specter.escalated`.

### 7.4 `llm/ledger.py`

SQLite table `llm_calls`: `ts, run_id, agent, task_class, tier, model, prompt_tokens, cached_tokens, completion_tokens, latency_ms, cost_usd, cache_layer (none|L1|L3), escalated`.

Prices live in `config/models.yaml` under each tier as `price_input_per_1m`, `price_cached_input_per_1m`, `price_output_per_1m`. **Fill these in from your own Foundry pricing blade — do not let the implementing agent guess them.** Leave them `null` initially and have the ledger report tokens only, flagging `cost_usd = null`, until you populate real numbers. A wrong cost chart is worse than no cost chart.

---

## 8. Tools

All tools are ADK `FunctionTool`s with full docstrings and typed signatures — the docstring is what the model sees, so write it for the model.

### `tools/graph_tools.py`
- `get_provider_profile(npi) -> ProviderProfile`
- `expand_neighborhood(npi, hops, limit) -> Subgraph`
- `find_shared_attribute_peers(npi, attribute: Literal["address","phone","officer"]) -> list[PeerLink]`
- `shortest_path_to_exclusion(npi, max_hops=4) -> PathResult | None`
- `get_community_context(npi) -> CommunitySummary | None`
- `search_enforcement_cases(query, k) -> list[EnforcementCaseHit]`

### `tools/signal_tools.py` — deterministic detectors, zero LLM
Each returns a `RiskSignal` or `None`. Each carries `source_ids`, a numeric `value`, and a `threshold`.

| Signal | Rule |
|---|---|
| `address_degree` | distinct providers at same `normalized_key` ≥ threshold |
| `phone_degree` | distinct providers sharing `e164` ≥ threshold |
| `officer_degree` | distinct orgs sharing an Officer ≥ threshold |
| `enumeration_burst` | ≥ N providers at one address enumerated within a 90-day window |
| `address_churn` | count of `CHANGED_ADDRESS_TO` in trailing 12 months |
| `exclusion_proximity` | shortest path length to any `Exclusion` node ≤ 3 |
| `community_exclusion_density` | fraction of community members with exclusions |
| `geographic_spread` | max pairwise distance between an officer's orgs |
| `phoenix_pattern` | new org sharing address+officer with an org excluded < 24 months prior |

Thresholds in `config/screening.yaml`. Every signal records the threshold it used so the case packet is reproducible.

### `tools/entity_tools.py`
- `normalize_address(raw) -> NormalizedAddress` (deterministic, `usaddress`)
- `normalize_phone(raw) -> str` (E.164, `phonenumbers`)
- `name_similarity(a, b) -> float` (`rapidfuzz` token_set_ratio)
- `propose_entity_matches(npi, candidates) -> list[MatchProposal]` (deterministic feature computation; the *adjudication* is the LLM's job)

### `tools/evidence_tools.py`
- `store_artifact(content, content_type, source_id) -> EvidenceArtifact` (SHA-256, writes to `data/evidence/`)
- `cite(artifact_id, claim) -> Citation`
- `validate_citations(case: CasePacket) -> CitationReport` — **every** `source_ids` entry must resolve to a stored artifact or a graph node. Run this before a case is emitted.

### `tools/mcp_tools.py`

Two MCP servers via `McpToolset`.

**Playwright MCP** — fetch and render DOJ releases, SAM.gov pages, provider websites. Wrap every fetch so it stores both rendered HTML and a screenshot as `EvidenceArtifact`s. That's what elevates the MCP from convenience to evidentiary chain.

**Neo4j Cypher MCP (`mcp-neo4j-cypher`)** — text2Cypher retrieval for the Graph Investigation Agent, alongside the hand-written tools. Mandatory guardrails:
- Connect as `NEO4J_READONLY_USER` (create this role in bootstrap; it must have no write privileges).
- Query timeout 10s.
- Reject any generated query containing `CREATE|MERGE|DELETE|SET|REMOVE|DROP|CALL apoc` via pre-execution regex.
- Force-append `LIMIT 100` if absent.
- Log every generated Cypher string to the trace.

Generated Cypher is an injection surface. Say so explicitly in the README — acknowledging it is worth more than pretending it isn't there.

---

## 9. Agents

Seven agents plus one grounding sub-agent. Each gets: a file, a Pydantic output contract, a declared `task_class`, and a fixed tool list.

### `agents/_base.py`

One factory so cache/router/tracing wiring exists in exactly one place:

```python
def build_agent(
    name: str,
    task_class: str,
    instruction_file: str,
    tools: list[BaseTool],
    output_schema: type[BaseModel],
    router: ModelRouter,
    compiler: PromptCompiler,
) -> LlmAgent: ...
```

It attaches `before_model_callback` (compile prompt, check L1 cache, short-circuit on hit) and `after_model_callback` (record tokens/cache stats, validate output schema, trigger escalation if needed).

### 9.1 Orchestrator — T2 `plan_investigation`
Selects the cohort slice, decides which providers warrant full investigation vs. monitoring, enforces the escalation rule, assembles the final packet. **Has no data tools.** It may only call sub-agents. This constraint is the point: it cannot fabricate evidence because it cannot touch data.

Output: `InvestigationPlan { provider_npis, depth: Literal["screen","full"], rationale, budget_hint }`.

### 9.2 Data Quality — T1 `assess_source_quality`
Runs before anything else. Reads every `SourceManifest`, compares against the previous run, and emits `PASS | WARN | FAIL`. **A `FAIL` halts the workflow** with case state `data_quality_hold`. Demonstrate this live by corrupting one manifest — a pipeline that refuses to run on bad data is a stronger demo than one that always runs.

Output: `DataQualityReport { verdict, per_source: list[SourceVerdict], blocking_reasons, recommended_action }`.

### 9.3 Entity Resolution — T1 `adjudicate_entity_match`
Consumes deterministic match features from `propose_entity_matches`. Adjudicates only. Outputs `matching_features`, `conflicting_features`, `match_probability`, and one of `auto_link | agent_review | human_review | reject`.

Thresholds: ≥ 0.90 auto-link, 0.65–0.90 agent review, 0.45–0.65 escalate to T2, < 0.45 reject. **False merges are worse than missed matches** — bias the thresholds conservatively and say why.

### 9.4 Graph Investigation — T1 `narrate_graph_signal`
The GraphRAG consumer. Tools: all of `graph_tools`, all of `signal_tools`, plus the Neo4j MCP. Calls `retriever.hybrid()`, receives deterministic signals, and produces structural narration.

Hard rule enforced in `after_model_callback`: every numeric value in the output must appear in a tool result. Reject and retry once with the violation quoted back, then fail the case.

Output: `GraphFindings { signals: list[RiskSignal], community_context, narration, linked_entities }`.

### 9.5 Enforcement Intelligence — T1 `extract_enforcement_case`
Tools: `search_enforcement_cases`, Playwright MCP, and `AgentTool(grounded_research_agent)`. Matches providers to LEIE/DOJ/SAM records, extracts scheme typology, and — critically — assigns `legal_status` from the enum. Common-name matches must be flagged `requires_disambiguation`, never auto-linked.

Output: `EnforcementFindings { matches: list[EnforcementMatch], typologies, legal_status_per_match, disambiguation_flags }`.

### 9.6 Grounded Research — Vertex Gemini, `grounded_research`

**This is the source-grounding pillar.** Not an Azure agent.

```python
grounded_research_agent = LlmAgent(
    name="GroundedResearchAgent",
    model="gemini-2.5-flash",          # Vertex, via GOOGLE_GENAI_USE_VERTEXAI
    instruction=load("prompts/agents/grounded_research.md"),
    tools=[google_search],             # ONLY this tool
)
grounded_research_tool = AgentTool(agent=grounded_research_agent)
```

**Critical implementation note — this is where people get stuck.** Built-in search tools cannot be combined with other tools in the same agent; you will get `400 INVALID_ARGUMENT: Multiple tools are supported only when they are all search tools`. Two mitigations, in order:

1. **Primary (version-stable): the AgentTool isolation pattern above.** The search agent has exactly one tool. Consumers receive it wrapped as an `AgentTool`.
2. **Fallback:** ADK Python ≥ 1.16 exposes `bypass_multi_tools_limit=True` on `GoogleSearchTool` / `VertexAiSearchTool`. Use only if pattern 1 fails on your ADK version.

Do not give this agent any other tool. Do not make it a `sub_agent` of a tool-bearing agent.

Extract `grounding_metadata` from the response — the web URIs and supports — and convert each into an `EvidenceArtifact` with `extraction_method="vertex_grounding"`. That's your citation trail, and it comes from the provider rather than from an LLM asked nicely to attribute.

### 9.7 Skeptic — T2 `challenge_hypothesis`
Argues *against* every signal. Receives the full findings bundle and must produce at least one benign explanation per signal or explicitly record `no_plausible_benign_explanation` with reasoning.

Checklist in its instruction block: multi-tenant medical building? billing/registration artifact? inappropriate peer comparison? common-name collision? stale source? synthetic contamination? group-practice structure not visible in the data?

Output: `CounterEvidence { per_signal: list[Rebuttal], unresolved_conflicts, confidence_adjustment: float }` where `confidence_adjustment ∈ [-0.4, 0.0]` and is **subtracted deterministically** from the final score by the scoring service. The Skeptic influences the number through a bounded, auditable channel — it never writes the number.

### 9.8 Case Reporter — T2 `synthesize_case`
Assembles the final `CasePacket`. Runs `validate_citations` and the no-fabricated-numbers check. Emits controlled language — a fixed vocabulary with `"exhibits N independently observed indicators"` phrasing and an explicit banned-phrase list (`fraudulent`, `criminal`, `guilty`, `proven`, `confirmed fraud`). Enforce the ban with a regex post-check, not just an instruction.

---

## 10. Orchestration — `workflow/screening.py`

Use the ADK 2.x `Workflow` graph runtime, not nested `sub_agents`. The graph is the artifact worth showing.

```
START
  → data_quality
  → [gate: verdict == PASS or WARN]        # FAIL → halt_node
  → cohort_select (deterministic, not an agent)
  → fan_out over providers (bounded concurrency, 4)
      → entity_resolution
      → graph_investigation
      → enforcement_intel
  → fan_in
  → skeptic
  → score (deterministic scoring service — NOT an agent)
  → case_reporter
  → END
```

`orchestrator` sits above as the planning node feeding `cohort_select` and consuming the gate outcome.

**Scoring is deterministic code, not an agent.** `workflow/state.py` holds a `ScoringService` implementing the doc's dimensional model, reduced for Phase 1 to five dimensions: `identity_integrity`, `network_association`, `adverse_history`, `evidence_quality`, `corporate_complexity`. Signal families are declared in `config/screening.yaml` so overlapping signals (address degree / high address centrality / address-sharing community anomaly all derive from one fact) collapse into one family weight. Implement family dedup explicitly — it's called out as a requirement in the design doc and it's an easy thing for a judge to probe.

Escalation gate, verbatim from the doc:

```
high_priority requires:
  >= 3 materially independent signal families
  AND >= 1 authoritative government source OR strong quantitative anomaly
  AND no unresolved critical entity-match conflict
  AND evidence freshness within threshold
```

Concurrency: cap at 4 parallel providers. Higher will hit Azure rate limits, and 429 handling with exponential backoff must be in the LiteLLM config regardless.

---

## 11. Observability — `obs/`

### `obs/tracing.py`
Arize Phoenix via Docker. Register the OpenTelemetry tracer provider and let ADK's built-in instrumentation emit. Custom span attributes on every LLM span:

`specter.run_id`, `specter.agent`, `specter.task_class`, `specter.tier`, `specter.model`, `specter.prompt_version`, `specter.prefix_fingerprint`, `specter.cached_tokens`, `specter.cache_layer`, `specter.escalated`, `specter.provider_npi`.

Tool spans get `specter.tool_name`, `specter.result_row_count`, `specter.cypher` (Neo4j MCP only).

### `obs/dashboard.py`
A `rich`-based terminal dashboard reading the ledger — this is what you show alongside the Phoenix waterfall:

```
RUN a7f3c1  ·  cohort: DME/FL,TX,CA  ·  providers: 250

AGENT                 CALLS   TIER   TOK IN   CACHED   HIT%   TOK OUT   $
DataQuality               1     T1     3,412    2,180   64%       410   -
EntityResolution        250     T1   612,300  498,100   81%    31,200   -
GraphInvestigation      250     T1   890,400  701,900   79%    68,400   -
EnforcementIntel        180     T1   402,100  310,700   77%    22,900   -
GroundedResearch         64  Tgnd    128,000        0    0%    18,300   -
Skeptic                  92     T2   410,200  322,600   79%    44,100   -
CaseReporter             92     T2   388,900  301,400   78%    61,700   -
                                    ─────────────────────────────────
L1 response-cache hits: 0  ·  avoided: $0.00     (cold run)
```

Run it twice. The second run's L1 line is the demo.

---

## 12. Judge subsystem — `judge/`

Two separate evaluations. Do not merge them.

### 12.1 `judge/detection_eval.py` — deterministic, no LLM

Ground truth:
- **Positives:** providers whose NPI matches a LEIE exclusion or a DOJ case, held out and hidden from the pipeline (`GraphLoader` must support `--hide-labels` which strips `Exclusion` and `EnforcementCase` edges for the held-out set).
- **Synthetic positives:** the 50 planted-scenario providers, with `expected_signals`.
- **Negatives:** the 150 benign controls plus a random sample of unlabelled providers.

Metrics: `precision@10`, `precision@25`, `precision@50`, `recall@50`, per-scenario recall (which of the 10 scenarios were detected at all), false-positive rate on benign controls, and mean rank of known positives.

**Per-scenario recall is your headline number.** "9 of 10 planted patterns detected, S08 missed because Phase 1 has no utilization data" is a far more credible claim than a single AUC.

### 12.2 `judge/rubric_judge.py` — Kimi K2.6, `judge_case_rubric`

Grades each `CasePacket` on five criteria, 0–5 each, with a required justification quoting the packet:

| Criterion | Question |
|---|---|
| Citation validity | Does every claim resolve to a stored artifact or graph node? |
| Numeric grounding | Does every number appear in a tool result? |
| Legal discipline | Are allegations distinguished from adjudicated outcomes? |
| Counter-evidence | Is at least one benign explanation present and substantive? |
| Hallucination | Any entity, NPI, or relationship not in the graph? |

Two of these — citation validity and hallucination — are also checkable deterministically. **Run both.** Where the deterministic checker and the LLM judge disagree, report the disagreement. That comparison is itself a finding and shows you understand LLM-judge reliability limits.

**Why Kimi and not GPT:** grading GPT-5.4 output with GPT-5.4 introduces self-preference bias — models systematically rate their own generations higher. A different lab's model gives genuine independence. State this in the README; it is a methodological choice, not a novelty.

The judge may **not** send cases back for re-investigation in Phase 1. Terminal scoring only. A judge→orchestrator loop is a Phase 2 feature and adds a nontrivial failure mode (oscillation, unbounded cost) for no Phase 1 grading benefit.

### 12.3 `judge/report.py`
Emits `JudgeReport.md`: detection metrics table, per-scenario breakdown, rubric score distribution, deterministic-vs-LLM disagreement list, and the three worst-scoring cases with reasons.

---

## 13. Build order

Each milestone ends with a verifiable checkpoint. **Do not start the next milestone until the checkpoint passes.**

| M | Deliverable | Checkpoint |
|---|---|---|
| **M0** | Repo skeleton, `pyproject.toml`, `docker-compose.yml`, `.env.example`, `settings.py`, `core/contracts.py`, `core/enums.py` | `docker compose up` brings Neo4j + Phoenix + Redis healthy; `pytest tests/test_contracts.py` passes; `ruff` + `mypy` clean |
| **M1** | `ingest/` — all five connectors, `SourceManifest`, validation | `python scripts/10_ingest.py --live` produces manifests with checksums; `--freeze` writes `data/snapshot/`; deliberate schema corruption yields `FAIL` |
| **M2** | `graph/` — loader, schema, address normalizer, communities, embeddings | Neo4j Browser shows the graph; `pytest tests/test_graph_retrieval.py` passes; 20 address-collision cases pass; Leiden yields 40–400 communities |
| **M3** | `llm/` — router, prompt compiler, response cache, ledger | **All four `test_prompt_compiler.py` invariants pass.** A scripted 20-call loop shows cache hit rate > 60% on the second pass. Router raises on unknown `task_class`. |
| **M4** | `tools/` — graph, signal, entity, evidence. No MCP yet. | Every signal tool fires correctly on the synthetic scenarios it was designed for (one test per scenario S01–S10) |
| **M5** | `agents/` — all 7 + grounded research, individually runnable via `adk web` | Each agent produces schema-valid output on a fixture provider. Grounded research returns real URIs in `grounding_metadata`. |
| **M6** | `workflow/screening.py` — the ADK Workflow graph + `ScoringService` | End-to-end run on 25 providers produces valid `CasePacket`s. `validate_citations` passes on all. Data-quality FAIL correctly halts. |
| **M7** | `tools/mcp_tools.py` — Playwright + Neo4j MCP wired in | Playwright stores HTML+screenshot artifacts. Neo4j MCP rejects a write query and honours `LIMIT`. |
| **M8** | `obs/` — Phoenix wiring + terminal dashboard | Full trace waterfall visible in Phoenix; dashboard renders; cold-vs-warm run shows L1 savings |
| **M9** | `judge/` — detection eval + rubric judge + report | `JudgeReport.md` generated with real numbers on the full cohort |
| **M10** | Full run on 250 providers, README, demo script | Reproducible `make demo` |

---

## 14. Demo script (what the run must show, in order)

1. `docker compose up` — infra healthy.
2. Neo4j Browser: the graph, a community, an address cluster.
3. `python scripts/40_screen.py --cohort dme_fl_tx_ca --limit 250` — **cold run.** Phoenix waterfall streaming live.
4. Same command again — **warm run.** Dashboard shows L1 hits and prefix-cache hit rate. Cost line drops.
5. Open one high-priority `CasePacket`: signals, citations resolving to artifacts, counter-evidence section, legal-status discipline.
6. Corrupt a manifest, re-run — pipeline halts with `data_quality_hold`.
7. `python scripts/50_judge.py` — `JudgeReport.md`, per-scenario recall, deterministic-vs-LLM disagreements.
8. Live ingestion on 2–3 entities via Playwright MCP, showing stored evidence artifacts.

---

## 15. Known pitfalls — read before debugging

| Symptom | Cause | Fix |
|---|---|---|
| Cache hit rate is 0% | Something non-deterministic above the boundary, or prefix < 1024 tokens | Run the four compiler invariant tests; diff two `prefix_fingerprint`s |
| `400: Multiple tools are supported only when they are all search tools` | Grounding agent has more than one tool, or is a `sub_agent` of a tool-bearing agent | Use the `AgentTool` isolation pattern (§9.6) |
| Every provider scores high | Address normalizer over-collapsing; no benign controls | Check `normalized_key` collisions; confirm the 150 controls loaded |
| Neo4j MCP returns the whole graph | Missing `LIMIT` injection | Enforce in the wrapper, not the prompt |
| Agents invent NPIs | Missing post-validation | `validate_citations` + graph-existence check in `after_model_callback` |
| 429s under fan-out | Concurrency too high | Cap at 4; exponential backoff in LiteLLM config |
| Kimi call fails on `azure_ai/` prefix | Foundry Models endpoint ≠ Azure OpenAI endpoint | Separate base URL + key; try raw OpenAI-compatible config |
| Community summaries change every run | Non-determinism in Leiden | Set `random_state`; persist and version summaries |
| ADK API doesn't match this plan | ADK 2.x is new | Follow §0.1; log deviations in `NOTES_API_DEVIATIONS.md` |

---

## 16. What Phase 1 explicitly claims

> Project Specter Phase 1 is a multi-agent, evidence-grounded screening architecture that combines graph retrieval, prefix-cache-aware model routing across three provider families, provider-attested source grounding, and an independent judge subsystem to surface and score ranked investigative leads over a defined U.S. healthcare provider cohort.

It does **not** claim to detect fraud, to identify ghost clinics, or to produce calibrated risk probabilities. Phase 2 adds the models that would begin to justify the second claim.