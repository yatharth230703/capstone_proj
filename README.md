# Project Specter — Phase 1

A multi-agent screening architecture over Google ADK 2.x that surfaces
ranked, evidence-grounded investigative leads on U.S. healthcare providers,
then scores those leads with an independent judge subsystem.

**Phase 1 claim, verbatim (`phase_1_build_plan.md` §16):**

> Project Specter Phase 1 is a multi-agent, evidence-grounded screening
> architecture that combines graph retrieval, prefix-cache-aware model
> routing across three provider families, provider-attested source
> grounding, and an independent judge subsystem to surface and score ranked
> investigative leads over a defined U.S. healthcare provider cohort.

It does **not** claim to detect fraud, identify ghost clinics, or produce
calibrated risk probabilities — no ML models, no billing anomaly detection,
no web frontend. Phase 1's UI is `adk web` plus this repo's terminal
dashboard (`python -m specter.cli dashboard`).

`google-adk` version this was built and verified against: **2.6.2**
(`uv pip show google-adk`).

---

## Architecture

Seven agents, orchestrated over an ADK `Workflow` graph
(`src/specter/workflow/screening.py`), fan out at most 4 providers in
parallel (`max_parallel_workers=4`) through a fixed pipeline per provider:

```
cohort_select ─▶ graph_investigation ─▶ enforcement_intel ─▶ skeptic ─▶ case_reporter
   (deterministic,        (Graph RAG:            (T1)         (T2,     (T2, synthesizes
    Cypher, not an        local/global/                     counter-      the CasePacket)
    agent — §"Orchestrator"                       semantic)   evidence,
    below)                                                    bounded
                                                                confidence_
                                                                adjustment)
```

Plus three agents outside the per-provider chain: **Data Quality**
(deterministic gate, `verdict ∈ {pass, warn, fail}` computed in code —
`agents/data_quality.deterministic_verdict` — the LLM call is narration
only, never the gate condition), **Entity Resolution** (fires per candidate
address/officer match, not per provider), and **Grounded Research**
(Vertex Gemini, isolated behind `AgentTool` so it is never a `sub_agent` of
a tool-bearing agent — see "Grounding agent isolation" below).

| # | Pillar | Where it lives |
|---|---|---|
| 1 | Graph RAG (hybrid: local / global / semantic) | `graph/retrieval.py` |
| 2 | Prefix-cache-aware architecture | `llm/prompt_compiler.py` + `llm/response_cache.py` |
| 3 | Model routing (explicit policy, no managed router) | `llm/router.py` + `config/models.yaml` |
| 4 | Source grounding with citations | `agents/grounded_research.py` (Vertex Gemini) |
| 5 | MCP integration (Playwright, Neo4j-Cypher) | `tools/mcp_tools.py` |
| 6 | Production observability | `obs/` + Phoenix + `llm/ledger.py` |
| 7 | LLM-as-judge scoring vs. ground truth | `judge/` |

No LLM Orchestrator agent exists (plan §9.1 was scoped out deliberately,
M6): `workflow/state.cohort_select` (Cypher, deterministic, `ORDER BY npi`)
and `ScoringService` (pure code) do the cohort selection and priority-tier
scoring that a "planning" agent would otherwise attempt — `config/
screening.yaml`'s static `cohort`/`escalation_gate` blocks fully determine
cohort and depth for Phase 1, so an LLM had no real decision left to make.

---

## The three methodological choices CLAUDE.md's amendments made

**1. SAM.gov removed, three state Medicaid exclusion connectors added
instead** (Amendment 1). `src/specter/ingest/state_medicaid.py` — FL
(AHCA), TX (Texas HHS-OIG, via an OpenSanctions mirror of the publisher's
own file — the direct host is WAF-blocked even to a real browser, see
`NOTES_API_DEVIATIONS.md` D21), CA (DHCS). State exclusions never
auto-link to a `Provider` without an exact NPI — they route through
`propose_entity_matches` and cap at `resolution_status="agent_review"`.
Federal LEIE/DOJ remain the primary ground-truth positive label; state
exclusions are a secondary label set, reported separately, because state
termination reasons are heterogeneous (administrative non-revalidation is
common, not just fraud).

**2. The judge tier moved from a separate-lab model (Kimi) to GPT-5.4**
(Amendment 2) — the operator's Foundry access to Kimi never materialized
into a stable endpoint for this build. This means the rubric judge
(`judge/rubric_judge.py`, `task_class=judge_case_rubric` → `T2_reasoning`)
shares a model family with the agents it grades: **self-preference bias**,
not eliminated. Five mitigations, all implemented and all exercised in a
real live run (`JudgeReport.md` at the repo root):

- Three of five rubric criteria are deterministic code, not an LLM call
  (`judge/deterministic_checks.py`: citation validity, numeric grounding,
  entity existence), and `JudgeReport.md` reports these as **primary**,
  the LLM rubric scores as **secondary**.
- The judge is blinded (`judge/blind.py`) — agent names, model
  identifiers, tier labels, `prompt_version`, `run_id` all stripped before
  the case packet reaches the judge.
- Every rubric criterion requires a non-empty `weakness_found` — a judge
  that can't name a weakness must say specifically why the criterion is
  fully satisfied; the literal string `"none"` is rejected and retried once.
- A 10-case calibration set with deliberately injected defects
  (`judge/calibration_fixtures.py`, C01-C10) is scored alongside real
  cases; the judge's catch rate on C01-C08 is reported as **the judge's
  own accuracy metric**, not hidden. Real result: **7/8** — the judge
  reliably missed C08 (a synthetic provider presented without
  `data_origin`), a real, reproducible finding, not flakiness.
- Three samples per case at `temperature=0.0`, cache disabled per-sample
  (`judge/rubric_judge._sample_runtime` — deliberately *not* using the
  standard L1 cache, confirmed live: an intermediate run showed genuinely
  differing per-sample scores, e.g. a mean of 4.333 from 3 disagreeing real
  calls, proving these are independent Azure calls). Any criterion with
  >1-point spread across samples is flagged `low_reliability` and excluded
  from aggregates.

Cross-family validation (a genuinely independent-lab judge — Kimi or
Claude) is explicitly deferred to Phase 2.

**3. Geocoding is offline, no Google Maps API** (Amendment 3).
`geographic_spread` uses ZCTA centroid distance
(`data/reference/zcta_centroids.csv`, US Census Bureau Gazetteer, public
domain, committed — not fetched at runtime) and a pure-function haversine
(`tools/entity_tools.zip_centroid` / `haversine_km`). Every signal using
this carries `geocoding_method: "zcta_centroid"` and
`known_limitations: ["centroid_precision_only", "not_street_level"]` —
rural ZIPs can span 50+ km, which is immaterial at the 1500 km default
threshold but is disclosed rather than implied away. Google Maps Platform
uses API keys, not the Vertex service account, and the Vertex SA carries
only the `Vertex AI User` role — no Maps roles were added, because Maps
roles don't exist on that principal type. Address-type classification
(residential vs. commercial vs. mailbox-store) — where Maps Platform would
actually earn its cost — is explicitly deferred to Phase 2 (plan §1
non-goals).

---

## Routing transparency

Every LLM call declares a `task_class`; `llm/router.py` maps it to a tier
via `config/models.yaml` — an unknown `task_class` raises rather than
silently defaulting. Azure's managed Model Router is deliberately not used,
because a managed router's routing decision isn't inspectable or testable
the way a static policy table is — this project is graded partly on routing
being an explicit, auditable choice, not partly opaque.

| Tier | Model | Use |
|---|---|---|
| `T0_bulk` | `gpt-5.4-nano` | normalization, classification, dedup, schema coercion |
| `T1_workhorse` | `gpt-5.4-mini` | entity adjudication, extraction, narration, triage |
| `T2_reasoning` | `gpt-5.4` | planning, skeptic, synthesis, judge rubric |
| `T_ground` | `gemini-3.7-flash` (Vertex) | grounded search only |

`config/models.yaml`'s `price_*` fields are deliberately `null` — the
operator has not supplied real Azure/Vertex pricing, and per plan §7.4 "a
wrong cost chart is worse than no cost chart." `cost_usd` renders `NULL` /
`-` in the ledger and dashboard rather than a guessed number
(BUILD_MILESTONES.md debt D-8, still open).

This build's real Azure resource exposes the **v1 API surface**
(`AZURE_API_BASE` ends in `/openai/v1`), not the classic
`azure/<deployment>` LiteLLM provider path — every Azure model string is
resolved as `openai/<deployment>` with an explicit `api_base`/`api_key`,
not `azure/<deployment>` (`NOTES_API_DEVIATIONS.md` D1). Azure calls also
carry `num_retries=3, retry_strategy="exponential_backoff_retry"`
(LiteLLM's own retry, no custom code) to absorb 429s under the 4-way
concurrent fan-out `workflow/screening.py` runs — found live in M10 that
this genuinely happens at real cohort scale (`NOTES_API_DEVIATIONS.md`
D23).

---

## The Neo4j MCP / generated-Cypher injection surface

`tools/mcp_tools.py`'s `run_guarded_cypher` wraps every generated Cypher
query with four mandatory guardrails: a read-only DB user
(`NEO4J_READONLY_USER`), a **hard** 10s query timeout (via
`neo4j.Query(text, timeout=10.0)` passed as the query object itself — a
bare `session.run(query, timeout=10)` kwarg is silently treated as an
unused Cypher parameter and does **not** time anything out, confirmed live,
`NOTES_API_DEVIATIONS.md` D20), a regex reject on
`CREATE|MERGE|DELETE|SET|REMOVE|DROP|CALL apoc` before execution, and a
force-appended `LIMIT 100` when the generated query doesn't already have
one. Every generated Cypher string is logged to the trace span as
`specter.cypher`.

The local Neo4j is **Community Edition**, which has no RBAC (`CREATE ROLE`/
`GRANT` raise `UnsupportedAdministrationCommand`, confirmed live) — the
read-only *enforcement* comes instead from every guarded session opening
with `default_access_mode="READ"`, which Neo4j's server itself rejects
writes against independent of any role
(`NOTES_API_DEVIATIONS.md` D19). The regex reject stays as an independent
second layer regardless — CLAUDE.md's "all four are mandatory" wording
doesn't carve out an exception for the case where one guardrail happens to
already be strong enough to make another feel redundant.

---

## The prefix-cache boundary

Prompt blocks are stable → variable, with a cache boundary after B3
(tool schemas, evidence policy + output contract, community summaries,
exemplars), then B4/B5 (provider evidence bundle, task instruction) below
it. `llm/prompt_compiler.py` enforces this: `json.dumps(..., sort_keys=True)`
everywhere in B0-B3, no `datetime.now()`/`uuid4()`/unsorted iteration above
the boundary. `tests/test_prompt_compiler.py`'s four invariant tests are
the guardrail — a silently zeroed cache hit rate deletes an entire graded
pillar, so these are not optional to keep green.

---

## Grounding agent isolation

`agents/grounded_research.py`'s `GroundedResearchAgent` runs on Vertex
Gemini with **exactly one tool**: `google_search`. It is exposed to other
agents wrapped in `AgentTool`, and is never a `sub_agent` of a tool-bearing
agent and never receives a second tool — violating this raises `400:
Multiple tools are supported only when they are all search tools`. ADK's
native `Gemini` model class reads Vertex config
(`GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`,
`GOOGLE_CLOUD_LOCATION`, `GOOGLE_APPLICATION_CREDENTIALS`) straight out of
`os.environ`, not from the typed `Settings` object — `.env` alone is not
enough; `_ensure_vertex_env()` forwards those four settings into
`os.environ` with `setdefault` before construction
(`NOTES_API_DEVIATIONS.md` D14). `grounding_metadata` URIs are extracted
into `EvidenceArtifact`s with `extraction_method="vertex_grounding"` — that
is the citation trail.

---

## Setup

```bash
git clone <repo>
cd capstone_proj
bash scripts/00_bootstrap.sh    # uv sync, docker compose up, Neo4j read-only user
# fill in .env: AZURE_API_KEY/AZURE_API_BASE, GOOGLE_CLOUD_PROJECT + a
# Vertex service-account JSON at .secrets/vertex-sa.json
uv run python scripts/10_ingest.py --live
uv run python scripts/10_ingest.py --freeze
uv run python scripts/20_build_graph.py
uv run python scripts/30_build_communities.py
```

## Demo

```bash
make demo
```

reproduces plan §14's demo script against the real CLI surface:

```bash
docker compose up -d && docker compose ps
uv run python scripts/40_screen.py --limit 250     # cold run
uv run python scripts/40_screen.py --limit 250     # warm run — L1 hits visible
uv run python -m specter.cli dashboard
uv run python scripts/50_judge.py                   # JudgeReport.md
```

Note: plan §14 step 3's literal command,
`python scripts/40_screen.py --cohort dme_fl_tx_ca --limit 250`, does not
match this build's real CLI — `--cohort` doesn't exist; the cohort is fixed
config in `config/screening.yaml`'s `cohort:` block (taxonomy prefix
`"332"`, states `["FL", "TX", "CA"]` — already the DME/FL/TX/CA cohort the
plan's flag would have selected). `--limit` is the only flag `scripts/
40_screen.py` takes.

`workflow/state.cohort_select`'s `ORDER BY npi` makes cohort selection
deterministic, so the cold and warm `--limit 250` runs select the exact
same 250 providers — the warm pass's L1 cache-hit demo needs no extra
setup.

`scripts/50_judge.py` grades a **fixed 22-case corpus** (2 real
`CasePacket`s already on disk + one fresh case per synthetic scenario
S01-S10, built live through the full M5 agent chain, plus the 10
calibration fixtures) — it does not scale with the screening cohort size
and does not grade all 250 screened providers. This is a deliberate scope
decision, not a shortcut: the plan doesn't ask for judging all 250, and
doing so would multiply real Azure spend for no required benefit.

**Both `scripts/40_screen.py` and `scripts/50_judge.py` confirm the Azure
key is live with a fresh `httpx` call before doing anything else** — this
key has gone alive → dead → alive once already during this project; never
trust a prior session's "key was alive as of \<date\>" note without
re-checking.

---

## Known limitations

- **DOJ ingests 1 row** after healthcare-fraud filtering
  (`_is_healthcare_fraud`). DOJ's press-release pagination is hard
  Akamai-blocked regardless of navigation method (confirmed three ways,
  including real Playwright rendering) — this is a source-reachability
  ceiling, not a connector bug. A genuinely deeper DOJ archive needs a
  different official source entirely (a structured case dataset, not this
  press UI).
- **`price_*` fields in `config/models.yaml` are `null`** — no cost figures
  are fabricated; the dashboard's cost column reports `NULL` rather than a
  guess.
- **Synthetic scenario providers (S01-S10) are invisible to a
  cohort-based run** — they carry zero `HAS_TAXONOMY` edges, so
  `cohort_select`'s taxonomy-prefix filter can never select them. The real
  250-provider cohort run and the judge's scenario-based evaluation are two
  disjoint populations by design; query synthetic scenarios by
  `scenario_id` directly (as `scripts/50_judge.py` does), not through the
  cohort.
- **Ground-truth positives for detection evaluation are sparse**: only 4
  real (non-synthetic) providers in the graph carry a direct `EXCLUDED_BY`
  edge out of 8,445. `judge/detection_eval.py` reports this denominator
  plainly and treats per-scenario recall as the headline metric, per plan
  §12.1's own instruction, rather than a precision number a 4-of-8,445
  denominator can't support.
- **The rubric judge shares a model family with the agents it grades**
  (self-preference bias) — see "The three methodological choices" above.
  Cross-family validation is deferred to Phase 2.
- State Medicaid exclusion records (`exclusion_authority="state_medicaid"`)
  without an NPI never auto-link to a provider; they route through agent
  review. State exclusion counts (FL, TX, CA) are reported separately from
  federal LEIE/DOJ counts in ground-truth evaluation, not pooled, because
  state termination reasons are heterogeneous (often administrative, not
  fraud-related).

Full list, with due milestones and disposition: `BUILD_MILESTONES.md` §4.

---

## Tests, lint, types

```bash
pytest tests/ -q
ruff check src/ tests/ scripts/
mypy src/
```
