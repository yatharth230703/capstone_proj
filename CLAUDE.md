# CLAUDE.md — Operating rules for this repository

Place this at the repo root. Claude Code reads it automatically on every session.
The authoritative spec is `PHASE1_BUILD_PLAN.md`. This file is the short list of things you must not get wrong.

---

## Project

Project Specter, Phase 1: a multi-agent screening architecture over Google ADK 2.x that surfaces ranked, evidence-grounded investigative leads on U.S. healthcare providers, then scores them with an independent judge subsystem.

**Phase 1 is architecture only.** No ML models, no web frontend, no billing anomaly detection. If a task feels like Phase 2, stop and ask.

**Pillars: minimal, robust, efficient.** Every file justifies its existence. No abstraction with one implementation. No class where a function will do.

---

## Before you write agent code

ADK Python 2.x has breaking API changes from 1.x. Do not write ADK code from memory.

```bash
mkdir -p .context
curl -sL https://raw.githubusercontent.com/google/adk-docs/main/llms-full.txt -o .context/adk-llms-full.txt
pip show google-adk
```

Read it. If the real API differs from the plan, keep the contract, adapt the call, and log the deviation in `NOTES_API_DEVIATIONS.md`.

---

## Hard rules

1. **No LLM produces a number.** Counts, degrees, distances, percentiles, dates — all from deterministic tools. LLMs plan, interpret, narrate. A number in agent output that isn't in a tool result is a bug that fails the case.
2. **No fabricated identifiers.** NPIs, case IDs, entity IDs must exist in the graph. Validated in `after_model_callback`.
3. **Every claim carries `source_ids`.** A signal without evidence references is a bug, not a warning.
4. **Facts, inferences, and hypotheses are separate schema fields.** Never merged into prose.
5. **`data_origin` (`public` | `synthetic`) on every node, edge, and signal.** Mixing them unlabelled in a case packet is a hard failure.
6. **`legal_status` enum is never collapsed.** Alleged ≠ charged ≠ convicted ≠ settled.
7. **Fail loudly.** No bare `except:`. No fallback that masks a broken source. Bad data halts the run.
8. **Scoring is deterministic code, never an agent.** The Skeptic influences the score only through a bounded `confidence_adjustment ∈ [-0.4, 0.0]`.
9. **Banned output vocabulary**, enforced by regex post-check, not just prompt instruction: `fraudulent`, `criminal`, `guilty`, `proven`, `confirmed fraud`.

---

## The cache boundary — the single most fragile thing here

Prompt blocks are ordered stable → variable, with a cache boundary after B3:

```
B0 tool schemas | B1 evidence policy + output contract | B2 community summaries | B3 exemplars
──────────────── CACHE BOUNDARY ────────────────
B4 provider evidence bundle | B5 task instruction
```

**Forbidden above the boundary:** `datetime.now()`, `uuid4()`, run IDs, trace IDs, `id()`, `repr()` of objects with memory addresses, unsorted dict/set iteration, random sampling, machine-specific absolute paths.

**Required:** `json.dumps(..., sort_keys=True)` everywhere in B0–B3. Sorted tool lists. Sorted community summaries. Stable prefix ≥ ~1200 tokens for every agent, including T0 — Azure needs ~1024+ before caching engages at all.

The four invariant tests in `tests/test_prompt_compiler.py` are not optional. If they fail, stop and fix before continuing. A silently zeroed cache hit rate deletes an entire graded pillar.

---

## Model routing

Every LLM call declares a `task_class`. The router maps it to a tier via `config/models.yaml`. Unknown `task_class` raises — never default silently.

| Tier | Model | Use |
|---|---|---|
| T0_bulk | `gpt-5.4-nano` | normalization, classification, dedup, schema coercion |
| T1_workhorse | `gpt-5.4-mini` | entity adjudication, extraction, narration, triage |
| T2_reasoning | `gpt-5.4` | planning, skeptic, synthesis |
| T3_judge | `Kimi-K2.6` | judge only — different lab, avoids self-preference bias |
| T_ground | `gemini-2.5-flash` (Vertex) | grounded search only |

Kimi uses the **Foundry Models** endpoint, not the Azure OpenAI one — separate base URL and key. It has no reliable prompt caching; that's acceptable, the judge is a single pass.

Do not use Azure's managed Model Router. Routing transparency is a graded requirement.

Leave `price_*` fields `null` in `config/models.yaml` until the operator fills in real Foundry pricing. Report tokens with `cost_usd = null` rather than guessing. A wrong cost chart is worse than none.

---

## The grounding agent will break if you do this wrong

`GroundedResearchAgent` runs on Vertex Gemini and has **exactly one tool**: `google_search`. It is exposed to other agents wrapped in `AgentTool`. It is never a `sub_agent` of a tool-bearing agent, and it never receives a second tool.

Otherwise: `400 INVALID_ARGUMENT: Multiple tools are supported only when they are all search tools`.

Fallback only if the isolation pattern fails on your ADK version: `bypass_multi_tools_limit=True` on `GoogleSearchTool`.

Extract `grounding_metadata` URIs into `EvidenceArtifact`s with `extraction_method="vertex_grounding"`. That is the citation trail.

---

## Neo4j MCP guardrails

Generated Cypher is an injection surface. All four are mandatory:

- Connect as the read-only role (`NEO4J_READONLY_USER`, no write privileges).
- 10s query timeout.
- Reject queries matching `CREATE|MERGE|DELETE|SET|REMOVE|DROP|CALL apoc` before execution.
- Force-append `LIMIT 100` when absent.

Log every generated Cypher string to the trace span as `specter.cypher`.

---

## Address normalization

This is the load-bearing signal in the system. `normalized_key = street_number | street_name_normalized | street_type_abbrev | zip5`. Suite/unit is **excluded** from the key and stored separately — two providers in different suites of one building correctly share an `Address` node, and the Skeptic Agent is what separates "medical office building" from "shell cluster."

Twenty real-world collision test cases must pass before the graph loader is considered done.

---

## Code style

- Python 3.11, full type hints, `ruff` + `mypy` clean before every commit.
- Pydantic v2 for every cross-boundary contract. All contracts live in `core/contracts.py`.
- Polars, not Pandas.
- `structlog`; no `print` outside `cli.py`.
- Modules ≤ 400 lines. Past that, it's doing two jobs — split it.
- Concurrency capped at 4 parallel providers. Exponential backoff on 429.

---

## Build discipline

Work milestone by milestone (`PHASE1_BUILD_PLAN.md` §13). **Do not start a milestone until the previous checkpoint verifiably passes.** Run the checkpoint, show the output, then proceed.

When something in this file conflicts with an instruction in the session, this file wins unless the operator explicitly overrides it by name.


## AMENDMENT 1 to PHASE1_BUILD_PLAN.md — SAM.gov removed

### Remove
- `src/specter/ingest/sam.py` and all references
- `SAM_API_KEY` from `.env.example` and `settings.py`
- SAM.gov row from §5.2 source table
- SAM.gov from Enforcement Intelligence Agent tool/source list (§9.5)

### Add: `src/specter/ingest/state_medicaid.py`

One connector, three configured instances (FL, TX, CA), each a separate
`SourceManifest` with its own `source_id`, checksum, and freshness status.

- FL: AHCA Medicaid provider exclusion/termination list
- TX: Texas HHS-OIG Exclusions list
- CA: DHCS Medi-Cal Suspended & Ineligible Provider List

Resolve current download URLs at implementation time (they move); record the
resolved URL, retrieval date, and file format in each manifest. Do NOT hardcode
a URL without also recording it in `config/sources.yaml`.

Format warning: these are inconsistent — expect a mix of XLSX, CSV, and at
least one PDF. If a source is PDF-only, extract with `pdfplumber` and set
`known_limitations: ["pdf_table_extraction", "no_npi_field"]`. If extraction
confidence is low, the connector must emit WARN, not silently produce rows.

### Schema mapping
Map into the existing `Exclusion` node type with a discriminator:
- `exclusion_authority: Literal["federal_oig", "state_medicaid"]`
- `jurisdiction: str`   # "US" | "FL" | "TX" | "CA"
- `npi: str | None`     # frequently None — this is expected, not an error

### Matching rule (important)
State exclusion records without an NPI must NEVER auto-link to a Provider.
They route through `propose_entity_matches` -> Entity Resolution Agent, and
the resulting link carries `resolution_status` of at most `agent_review`.
Auto-link is prohibited for any match lacking an exact identifier.

### Signal impact
`exclusion_proximity` and `community_exclusion_density` now traverse both
federal and state Exclusion nodes. Weight them separately in
`config/screening.yaml`: a federal OIG exclusion is stronger evidence than a
state Medicaid termination, which may be administrative (e.g. failure to
revalidate) rather than fraud-related. Do not treat them as equivalent.

### Ground truth impact (§12.1)
Federal LEIE + DOJ remain the primary positive labels. State exclusions are a
SECONDARY label set, reported separately in JudgeReport.md, because state
termination reasons are heterogeneous and many are non-fraud administrative
actions. Do not pool them into one precision number.

### M1 checkpoint (revised)
Four connectors pass: NPPES, LEIE, DOJ, state_medicaid (x3 instances = 3
manifests). Deliberate schema corruption on any one yields FAIL.

## AMENDMENT 2 — Judge tier moves to GPT-5.4

### Config change
Delete tier `T3_judge` (Kimi). Route `judge_case_rubric` to `T2_reasoning`.

```yaml
routing:
  judge_case_rubric: T2_reasoning   # was T3_judge (Kimi) — removed
```

Delete from `.env`, `.env.example`, and `settings.py`:
`FOUNDRY_KIMI_ENDPOINT`, `FOUNDRY_KIMI_API_KEY`, `FOUNDRY_KIMI_DEPLOYMENT`.
Remove the `foundry_models` provider branch from `llm/router.py` entirely —
do not leave dead code behind a flag.

### The problem this creates, and the five required mitigations

The judge now shares a model family with the agents it grades. This is
self-preference bias: models rate their own generations higher. The judge is
NOT independent, and the code and the report must both say so. Implement all
five mitigations in `judge/rubric_judge.py`.

**1. Deterministic checks are primary, LLM judge is secondary.**
Three of the five rubric criteria are fully checkable in code. Implement them
as pure functions in `judge/deterministic_checks.py` and treat their output as
authoritative:

- `check_citation_validity(case)` — every `source_ids` entry resolves to a
  stored `EvidenceArtifact` or an existing graph node. Boolean per claim.
- `check_numeric_grounding(case)` — extract every numeric literal from the
  narrative via regex, assert each appears in a recorded tool result for that
  case. Boolean per number.
- `check_entity_existence(case)` — every NPI, case ID, and entity ID mentioned
  exists in the graph. Boolean per identifier.

`JudgeReport.md` leads with these. The LLM rubric scores are reported
underneath, explicitly labelled as secondary.

**2. Blind the judge.**
Strip from the case packet before it reaches the judge: agent names, model
identifiers, tier labels, `prompt_version`, `run_id`, and any generation
metadata. Implement `blind_case(case) -> BlindedCase` and unit-test that no
field containing "gpt", "agent", "tier", or "model" survives it. The judge
grades an anonymous document.

**3. Force negative evidence.**
The judge must not return a score without a citation supporting it. Rubric
output schema requires, per criterion:

```python
class CriterionScore(BaseModel):
    criterion: str
    score: int                    # 0-5
    supporting_quote: str         # verbatim span from the case packet
    weakness_found: str           # REQUIRED, may not be empty
```

`weakness_found` must be non-empty for every criterion. If the judge cannot
name a weakness, it must state why the criterion is fully satisfied in
specific terms — the string "none" is rejected by a validator and triggers one
retry with the rejection quoted back.

**4. Calibration set with known-bad cases.**
Generate 10 deliberately defective case packets in
`judge/calibration_fixtures.py` and score them alongside the real ones:

| ID | Injected defect | Criterion that must catch it |
|---|---|---|
| C01 | Citation pointing to a non-existent artifact ID | citation validity |
| C02 | A number absent from every tool result | numeric grounding |
| C03 | "convicted" used where source says "charged" | legal discipline |
| C04 | Counter-evidence section empty | counter-evidence |
| C05 | A fabricated NPI in linked entities | hallucination |
| C06 | Banned word "fraudulent" in the narrative | legal discipline |
| C07 | Two signals from one underlying fact, weighted twice | numeric grounding |
| C08 | Synthetic provider presented without `data_origin` | citation validity |
| C09 | Real case, no defects (control) | all — should score high |
| C10 | Real case, no defects (control) | all — should score high |

**The judge's score on C01–C08 is the judge's own accuracy metric.** Report it
prominently. A judge that passes defective cases is a broken judge, and saying
so is worth more than a clean-looking score distribution.

**5. Temperature 0 and multi-sample agreement.**
Run the rubric three times per case at `temperature=0.0` with the sample index
excluded from the cache key. Report per-criterion variance. Any criterion with
a spread greater than 1 point across samples is flagged `low_reliability` in
the report and its score is not used in aggregates.

### Reporting requirement — do not omit this

`judge/report.py` must open with this limitation block, generated verbatim:

```
JUDGE INDEPENDENCE: LIMITED.
The rubric judge (gpt-5.4) shares a model family with the agents it grades,
introducing self-preference bias. LLM rubric scores are therefore reported as
SECONDARY. Primary evaluation is deterministic (citation validity, numeric
grounding, entity existence) and does not involve an LLM.
Judge accuracy on injected-defect calibration cases: {n_caught}/8.
Cross-family validation (Kimi K2.6 or Claude) deferred to Phase 2.
```

### Cost note
The judge now runs at T2 pricing across three samples per case. On a 250-case
run this is a real line item. Budget it, cap it via
`SPECTER_JUDGE_SAMPLE_COUNT` (default 3, allow 1 for dev runs), and let the L1
response cache absorb repeat runs.

## AMENDMENT 3 — Geocoding is offline in Phase 1. No Maps API.

### Do not add
- No Google Maps Platform key. No Geocoding API, Places API, or Distance Matrix.
- Maps uses API keys, NOT the Vertex service account. The Vertex SA needs only
  the `Vertex AI User` role. Do not add Maps roles to it — they don't exist there.

### Use instead: ZIP centroid distance (offline, deterministic, free)

Commit a ZCTA centroid table to `data/reference/zcta_centroids.csv`
(source: US Census Bureau ZCTA Gazetteer file — public domain, no key).
Columns: `zip5, lat, lon, state`. ~33k rows, ~1.5 MB. Commit it; do not
download at runtime.

`tools/entity_tools.py`:

```python
def zip_centroid(zip5: str) -> tuple[float, float] | None:
    """ZCTA centroid lookup. Returns None for unmatched ZIPs (PO-box-only
    and military ZIPs have no ZCTA). None is a valid result, not an error."""

def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance. Pure function, no I/O."""
```

`geographic_spread` computes max pairwise `haversine_km` over an officer's
org ZIP centroids. Threshold in `config/screening.yaml`, default 1500 km.

### Accuracy disclosure — required in the case packet
Every signal using this carries:
`"geocoding_method": "zcta_centroid"` and
`known_limitations: ["centroid_precision_only", "not_street_level"]`.
Rural ZIPs can span 50+ km. At a 1500 km threshold this is immaterial, and
saying so is better than implying precision we don't have.

### Unmatched ZIPs
If `zip_centroid` returns None for any org in the set, emit the signal with
`confidence` reduced and `known_limitations: ["incomplete_geocoding"]`.
Never drop the provider silently, and never substitute a guessed coordinate.

### What is explicitly deferred to Phase 2
The Physical Existence agent — address-type classification (residential vs.
commercial vs. mailbox-store), land-use lookup, facility-density comparison.
THAT is where Maps Platform earns its cost, because `location_type` and
Places category data are the actual signal. Phase 1 has no such agent, per the
non-goals in §1.