# Project Specter — Milestone Ledger

**This file is the handoff channel between Claude Code sessions.**
One session = one milestone. Read §0 before doing anything else.

| | |
|---|---|
| Authoritative spec | `phase_1_build_plan.md` |
| Operating rules | `CLAUDE.md` (wins over everything, including this file) |
| Vision doc (context only) | `project_specter_23_point_plan_access_adjusted.md` |
| API deviations log | `NOTES_API_DEVIATIONS.md` |

---

## 0. HOW TO USE THIS FILE — read this first, every session

### 0.1 The loop

You have been started fresh, with no memory of previous sessions. Everything
you need is in this file.

1. Find the **first milestone whose status is `TODO`** in §2. That is yours.
   Do not skip ahead. Do not do two.
2. Read that milestone's **Action Plan**. A `TODO` milestone that has an
   Action Plan written is ready to implement — the previous session wrote it
   for you.
3. **If the Action Plan says `(not yet written)`, stop and write it first**,
   following §1, then implement it. This happens only if a previous session
   ran out of context.
4. Implement it. Run the **Checkpoint** commands verbatim and paste real
   output.
5. **Do not mark a milestone `DONE` unless its checkpoint actually passed.**
   A milestone that half-works is `BLOCKED` with a written reason. Lying in
   this file poisons every session after you — it is the single worst thing
   you can do here.
6. Write the **Action Plan for the next milestone** (§1 tells you how).
7. Update the status table in §2 and the **Current State** block in §3.
8. Commit. One commit per milestone, message `M<n>: <deliverable>`.

### 0.2 Rules that override your instincts

- **`CLAUDE.md` wins.** If this file and `CLAUDE.md` disagree, `CLAUDE.md` is
  right and you should note the conflict in the milestone's Notes.
- **Never start a milestone whose predecessor is not `DONE`.** The build
  plan's §13 discipline is deliberate — checkpoints exist because a broken
  foundation is discovered five milestones too late otherwise.
- **Don't refactor outside your milestone's file list.** If you find a bug
  elsewhere, write it into §4 Carried Debt. Do not fix it silently; a diff
  that spans three milestones is unreviewable.
- **Verify, don't assume.** Every claim in an Action Plan was written by a
  previous session that could have been wrong. If reality contradicts the
  Action Plan, trust reality, fix the plan, and say so in Notes.
- **No scope creep.** `phase_1_build_plan.md` §1 lists explicit non-goals: no
  ML models, no billing anomaly scores, no web frontend, no geospatial
  land-use classification. If a task feels like Phase 2, stop and ask.

### 0.3 Session start ritual (~2 minutes, do it every time)

```bash
cd /Users/yatharthbisht/Desktop/capstone_proj
source .venv/bin/activate

docker compose up -d && docker compose ps        # neo4j, phoenix, redis must be healthy
python -m pytest tests/ -q                       # must be green BEFORE you change anything
ruff check src/ tests/ && mypy src/              # must be clean BEFORE you change anything
```

If the suite is red on a clean checkout, that is a `BLOCKED` finding for the
*previous* milestone — record it in §4 and fix it before starting yours.

### 0.4 Cost discipline

Sessions after the first run on **Sonnet**, deliberately. Keep it cheap:

- Read the files your Action Plan's File Manifest names. Don't spelunk the
  whole repo — a previous session already did that and wrote down the result.
- Prefer `grep`/`Read` with line ranges over reading 400-line files whole.
- Don't re-derive facts recorded in §3 Current State. They were verified.
- Run the real LLM calls your checkpoint requires and no more. `gpt-5.4-nano`
  (T0) for smoke tests; don't loop `gpt-5.4` (T2) to "see if it works".

---

## 1. ACTIONS-WRITING GUIDE — how to write the next milestone's Action Plan

You are writing for a competent stranger with **zero context**, on a cheaper
model, who will not read the files you read. The Action Plan is the only
thing standing between them and re-deriving everything you just learned.

Write it **after** your implementation is done and its checkpoint has passed —
you know things at that point you could not have guessed at the start.

### 1.1 Required structure

Copy this skeleton exactly. Every heading is mandatory; write `None.` rather
than deleting one.

```markdown
#### Action Plan

**Goal.** One paragraph. What exists at the end that doesn't exist now, and
why the project needs it. Name the graded pillar or plan section it serves.

**Inherited context.** What the previous milestone built that this one stands
on, including anything surprising. This is where you warn them.

**File manifest.**
| Path | Action | Notes |
|---|---|---|
| `src/specter/x/y.py` | CREATE | ~120 lines. Does Z. |
| `src/specter/a/b.py` | EDIT | Only `foo()`; leave the rest alone. |
| `tests/test_y.py` | CREATE | Cases listed under Step 3. |

**Read before writing.** Exact paths, with line ranges where the file is long
and only part matters. 4-8 entries. This is a budget, not a wish list.

**Steps.** Numbered, ordered, each independently checkable. Include real code
for any non-obvious contract, signature, or Cypher query. If you know the
exact call that works, write the exact call — don't make them rediscover it.

**Checkpoint.** Runnable commands plus the expected output, concretely.
"Tests pass" is not a checkpoint. "`pytest tests/test_y.py -q` → 7 passed,
and `python scripts/30_x.py` prints `communities=255`" is a checkpoint.

**Traps.** Specific things that will bite them, with the fix. Not generic
advice. Every trap should be something you either hit or nearly hit.

**Definition of done.** A checklist. Every box ticked or the milestone is not
done.
```

### 1.2 What makes an Action Plan good

- **Exact over approximate.** `EXCLUDED_BY` not "the exclusion edge".
  `openai/gpt-5.4-nano` not "the nano model". Line numbers where they help.
- **Record the empirical.** Anything you had to *run something* to learn —
  a real row count, a working call signature, an API that behaves differently
  than documented — belongs in the Action Plan. That's the expensive
  knowledge. A fact they can read off a file is cheap; a fact they'd need to
  burn 20 tool calls to rediscover is not.
- **Warn about what nearly broke you.** Traps are the highest-value section.
- **Name the contracts.** If the milestone adds Pydantic models, write them
  out in full in the Steps. `core/contracts.py` is the only place they live
  (CLAUDE.md), so getting the fields right up front avoids a rewrite.
- **Give exact commands.** Including flags and expected stdout.

### 1.3 What makes it bad — avoid these

- Restating `phase_1_build_plan.md`. They can read it. Say what the plan does
  *not* tell them: what's already built, what deviates, what broke.
- Vague verbs: "handle errors properly", "wire it up", "make sure it works".
- Inventing detail you didn't verify. If you didn't run it, say
  `UNVERIFIED:` in front of it. A confident wrong instruction costs more than
  an honest gap.
- Padding. If the milestone is small, the Action Plan is short. Length is not
  a quality signal.

### 1.4 Also update, every session

- **§2 status table** — your row, and the next row if you learned something
  that changes it.
- **§3 Current State** — the shared factual snapshot. Keep it *replaced*, not
  appended; it must describe now, not history.
- **§4 Carried Debt** — anything you deliberately deferred, with a milestone
  where it comes due. A deferral with no owner is just a bug.
- **`NOTES_API_DEVIATIONS.md`** — any place reality differed from the plan or
  from a library's docs. Required by `CLAUDE.md`.

---

## 2. MILESTONE STATUS

Statuses: `DONE` · `TODO` · `BLOCKED` · `DEFERRED`

| # | Milestone | Deliverable | Status |
|---|---|---|---|
| — | *Pre-existing* | M0–M4 of `phase_1_build_plan.md` §13: contracts, ingest, graph load, llm layer, deterministic tools | `DONE` |
| **M1** | Agent foundation | `agents/_base.py` factory, ADK 2.x verification, tool bindings, DataQuality agent | `DONE` |
| **M2** | Graph RAG completion | `graph/embeddings.py`, `graph/summaries.py`, EnforcementCase corpus, `retrieval.global_/semantic` | `DONE` |
| **M3** | Investigation agents | EntityResolution, GraphInvestigation, EnforcementIntel | `DONE` |
| **M4** | Grounded research | Vertex Gemini agent + `AgentTool` isolation, grounding citations | `DONE` |
| **M5** | Judgement agents | Skeptic, CaseReporter, `CasePacket`, banned-vocabulary enforcement | `DONE` |
| **M6** | Orchestration | `workflow/screening.py`, `ScoringService`, `scripts/40_screen.py` | `TODO` |
| **M7** | MCP integration | `tools/mcp_tools.py` — Playwright + Neo4j Cypher guardrails | `TODO` |
| **M8** | Observability | `obs/tracing.py`, `obs/dashboard.py`, `cli.py` | `TODO` |
| **M9** | Judge subsystem | `judge/` — detection eval, deterministic checks, rubric judge, report | `TODO` |
| **M10** | Full run & docs | 250-provider run, `README.md`, demo script | `TODO` |

---

## 3. CURRENT STATE

*Replace this section each milestone. It describes NOW, not history.*

**Last updated: end of M5.**

### Verified green

```
pytest tests/ -q          176 passed
ruff check src/ tests/ scripts/   All checks passed
mypy src/                 Success: no issues found in 50 source files
docker compose ps         neo4j, phoenix, redis — all healthy
```

B0 (`prompts/blocks/b0_tool_schemas.md`) is untouched by M3 — no new tool
binding was added (see "GraphRetriever wiring" below), so no regeneration
was needed and the cached prefix did not go cold.

### Infrastructure

| Service | Where | Note |
|---|---|---|
| Neo4j 5.26 | `bolt://localhost:7687` | 1 GB heap |
| Redis 8.6 | `localhost:**6380**` | **not** 6379 — an unrelated `diligence-redis` owns that port |
| Phoenix | `localhost:6006` | running, **no tracing wired to it yet** (M8) |

Docker Desktop is often not running at session start. `docker compose up -d`
then wait for health; 36 tests skip themselves when Neo4j/Redis are down, so a
"green" suite with 36 skips means you tested almost nothing.

### Azure — working, and the call form is non-obvious

`AZURE_API_BASE` ends in `/openai/v1`: this is the Azure OpenAI **v1**
surface, so LiteLLM's `azure/` provider 404s. The working form is
`openai/<deployment>` plus an explicit `api_base`. `llm/router.py` already
does this — see `NOTES_API_DEVIATIONS.md` D1 before touching model strings.

All verified live: `gpt-5.4-nano` (T0), `gpt-5.4-mini` (T1), `gpt-5.4` (T2),
and `text-embedding-3-large` → **3072 dims**, matching the vector index
dimensions already declared in `graph/schema.cypher`. Embeddings use the
same `openai/<deployment>` + `api_base` call form as chat completions — see
`NOTES_API_DEVIATIONS.md` D11 for the one surprise (`response.data` items are
plain dicts keyed `embedding`/`index`, not attribute-access objects).

**Vertex — configured and working (M4).** Operator supplied
`GOOGLE_CLOUD_PROJECT` and a service-account key at
`.secrets/vertex-sa.json`, and changed `VERTEX_GROUNDING_MODEL` from the
plan's `gemini-2.5-flash` to **`gemini-3.7-flash`** (also updated in
`config/models.yaml`'s `T_ground` tier and `.env.example`) — that model name
is outside this codebase's own knowledge and was taken as given, not
second-guessed. `GOOGLE_CLOUD_LOCATION` is `global`, not the plan's
`us-central1` default (also an operator change, both `.env` and
`.env.example`/`settings.py`'s default updated to match).

**Load-bearing trap, not obvious from the plan:** `Settings` (pydantic-
settings) reads `.env` into a Python object; it never populates
`os.environ`. ADK's native `Gemini` model (required for `google_search` —
see M4 below) builds its `google.genai.Client` by reading
`GOOGLE_GENAI_USE_VERTEXAI`/`GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION`/
`GOOGLE_APPLICATION_CREDENTIALS` straight from `os.environ`, which was
empty of all four (`env | grep GOOGLE` → nothing) even with a fully correct
`.env`. `agents.grounded_research._ensure_vertex_env()` forwards them with
`setdefault` before agent construction. Any *other* future Vertex-native
(non-`LiteLlm`) agent needs the same forwarding — it does not come for free
from `Settings` existing. `NOTES_API_DEVIATIONS.md` D14.

### Prompt caching — measured, working

Verified end to end through ADK: first call 0 cached tokens, second call
**9,472 / 9,983 = 95%**. B2 going from a placeholder to real community
summaries (M2) grew the compiled prefix from 5,284 to **11,152 estimated
tokens** (44,610 chars) — expect one *new* cold call after this milestone,
same as after any B0-B3 edit; that's correct, not a regression. Because the
prefix is identical across every agent by design, the 255 `summarize_community`
calls in this milestone's own checkpoint already warmed Azure's server-side
cache for it before `data_quality` was ever re-run.

The caching cliff is higher than the plan assumed — 1,276 real tokens cached
nothing; 1,550 cached 1,280. The invariant is now
`MIN_PREFIX_TOKEN_ESTIMATE = 1800`. Details in `NOTES_API_DEVIATIONS.md` D2.

### Graph contents (live, `docker compose up -d` to query)

| Node | Count | | Edge | Count |
|---|---|---|---|---|
| Exclusion | 106,755 | | LOCATED_AT | 8,603 |
| Provider | 8,603 | | HAS_OFFICER | 8,603 |
| Address | 7,825 | | HAS_PHONE | 8,588 |
| Phone | 7,681 | | HAS_TAXONOMY | 8,417 |
| Officer | 4,118 | | IN_COMMUNITY | 3,469 |
| Community | 255 | | EXCLUDED_BY | 7 |
| Taxonomy | 13 | | CHANGED_ADDRESS_TO | 3 |
| DataSource | 8 | | | |
| EnforcementCase | 1 | | | |

255 communities is inside the plan's 40–400 target. **All 255 now carry a
3072-dim `embedding` and an LLM `characterization`** (M2, full run — 255 real
`summarize_community` T1 calls, not a `--limit` dev sample; zero fabricated
`notable_members` were caught/dropped across the run). `EnforcementCase` is 1
because the DOJ snapshot itself is 1 row (debt D-2 refill is M7); that one
row is loaded and embedded into `case_embedding`. No `Provider`→
`EnforcementCase` edge exists — never will, from this loader; linking is
M3's Enforcement Intelligence Agent's job.

### Frozen snapshot (`data/snapshot/`)

| Source | Rows | Freshness |
|---|---|---|
| leie | 83,665 | current |
| state_medicaid_ca | 23,229 | current |
| nppes | 8,417 | current |
| synthetic_providers | 186 | current |
| synthetic_exclusions | 4 | current |
| **doj** | **1** | current |
| **state_medicaid_fl** | **0** | unknown |
| **state_medicaid_tx** | **0** | unknown |

The three bold rows are real data gaps, tracked as debt D-1/D-2/D-3. The
Data Quality Agent correctly returns `fail` on this snapshot because of them —
that is the agent working, not a bug.

### What exists in `src/specter/`

Built and tested: `core/` (contracts, enums, errors, hashing,
`banned_vocabulary.py` — M5), `ingest/` (4 connectors + synthetic), `graph/`
(schema, loader, enforcement_loader, communities, summaries, embeddings,
retrieval), `llm/` (router, prompt compiler, response cache, ledger),
`tools/` (graph, signal, entity, evidence, bindings), `agents/` (`_base.py`,
`_llm_call.py`, `_errors.py`, `_grounding.py` — M5, `data_quality.py`,
`entity_resolution.py`, `graph_investigation.py`, `enforcement_intel.py`,
`grounded_research.py`, `skeptic.py` — M5, `case_reporter.py` — M5).

`agents/_base.py` (agent construction) and `agents/_llm_call.py` (agent
invocation — the L1 cache, the ADK runner, output validation) were split in
M3: `_base.py` had grown to 479 lines, over CLAUDE.md's 400-line module
ceiling, once escalation was wired in. `agents/_errors.py` holds
`AgentOutputError`/`PrefixInstabilityError` — split out purely to give both
files a place to import them from without a circular import. `core/contracts.py`
is at 541 lines and was **not** split — CLAUDE.md's "all contracts live in
`core/contracts.py`" is a more specific rule than the generic 400-line cap,
and it was already over 400 before M3 (450, unaddressed by M1/M2). Treat
this as an accepted tension, not debt with a fix pending.

**`agents/grounded_research.py` does not go through `agents/_base.py` at
all** — no `build_agent`/`run_agent`, no cache boundary, no L1 cache, no
router-resolved `LiteLlm`. It's a standalone `LlmAgent` built directly from
a bare `"gemini-*"` model string (required for ADK's `google_search`
built-in tool — see M4 below), constructed by
`build_grounded_research_agent(router, settings)` and invoked by its own
`Runner`/`InMemorySessionService` in `research_topic()`. `router.resolve(
"grounded_research")` is still used, but only to read the model name out of
`config/models.yaml` — not to build a `LiteLlm`.

Still empty: `workflow/`, `judge/`, `obs/`. Missing entirely: `cli.py`,
`tools/mcp_tools.py`, `README.md`, `scripts/00_bootstrap.sh`,
`scripts/40_screen.py`, `scripts/50_judge.py`.

### GraphRetriever wiring — the decision M2 left open, resolved

`agents/graph_investigation.py` takes the Python pre-fetch path, not a new
tool binding: `build_evidence` calls `GraphRetriever(driver).hybrid(...)`
directly and puts the result straight into the evidence bundle, the same
pattern `data_quality.build_evidence` already used. `tools/bindings.py` is
unchanged — no `hybrid_search` binding exists, and none was needed.

### `get_community_context` now reads the persisted characterization (D-9 cleared)

It still recomputes `structural_facts` fresh from Cypher every call (that
part was never broken), but now also returns `characterization`,
`notable_members`, `risk_themes`, `generated_at`, `prompt_version` read
straight off the Community node — `None`/empty when a community hasn't been
characterized, real text when it has. Verified live via
`scripts/35_smoke_investigation_agents.py`: the S03 community's
`community_context` narration quotes the real M2-authored characterization
text, not `None`.

### ZCTA geocoding (Amendment 3) — done, offline

`data/reference/zcta_centroids.csv` — 33,791 rows, `zip5,lat,lon,state`,
source: US Census Bureau 2025 Gazetteer national ZCTA file (the file CLAUDE.md
pointed at had moved — see below). `state` column is committed empty: the
Gazetteer file doesn't carry it, and no caller needs it yet; said plainly
rather than reverse-geocoding it in. `entity_tools.zip_centroid()`/
`haversine_km()` are pure functions, `lru_cache`-loaded once.
`signal_tools.geographic_spread` now pulls `zip5` off each officer-linked
provider's `Address` node and computes max pairwise `haversine_km` over
resolved centroids; unmatched ZIPs drop out of the pairwise comparison (not
the provider), the signal still fires if any pair resolves, and
`known_limitations`/`geocoding_method` are recorded on the `RiskSignal`
(both are now **required** fields on `RiskSignal`, not defaulted — see
"strict-mode nested models" below). Verified live against the S09 synthetic
scenario: ZCTA centroids give **3769.7 km** for the Miami/LA pair, vs. the
test's `pytest.approx(3760, abs=50)` — within tolerance.

**Census URL moved, as warned.** `2020_Gazetteer_zcta_national.zip` 404s now;
the working URL (as of this session) is
`https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2025_Gazetteer/2025_Gaz_zcta_national.zip`
— pipe-delimited, not the tab-delimited format the 2020 file used. Verify
again before hardcoding it anywhere else; Census re-publishes these paths
per-year.

### Strict-mode nested models — a new rule, not just a top-level one

`RiskSignal` (nested inside `GraphFindings.signals`, itself an agent
`output_schema`) needed its own no-defaults treatment: D5's "no `default=`ed
fields" rule turned out to apply **transitively through `$defs`**, not just
to the top-level output model. `known_limitations: list[str]` and
`geocoding_method: str | None` are both required (filled explicitly at every
`_signal()` call site), not defaulted.

A second, sharper version of the same class of bug hit live: `dict[str, X]`
fields cannot appear **anywhere** in an agent output schema — Azure strict
mode has no way to express an open-ended object. `EnforcementFindings.
legal_status_per_match` was `dict[str, LegalStatus]` in the Action Plan's own
draft schema; it 400'd on the first real call and was changed to
`list[CaseLegalStatus]` (`{case_id, legal_status}` pairs). Full writeup:
`NOTES_API_DEVIATIONS.md` D13.

### Escalation — wired, demonstrated offline and it did not fire live (correctly)

`agents/_base.py`'s `run_agent` calls `router.should_escalate` after every
call and re-runs once at the escalated tier via `_build_agent_with_instruction`
with `tier_override=`; `AgentRunResult.escalated` is `True` only for a real
escalated call. `router.model_for_tier(tier_name)` is new — `model_for
(task_class)` now delegates to it — needed because escalation resolves a
tier directly, not through `task_class` routing.

Deliberately capped at exactly one retry with no configurable count: every
`config/models.yaml` escalation rule already sets `max_retries: 1`, and
`should_escalate` returns a bare `TierConfig` (no rule/count), so there was
nothing to thread through. Revisit only if a rule ever needs `max_retries: 2`.

Proven two ways: an offline test (`test_run_agent_escalates_on_ambiguous_match_probability`,
`tests/test_agent_base.py`) monkeypatches `_invoke` to deterministically trip
the `adjudicate_entity_match` rule and asserts the second call runs at
`T2_reasoning` with `escalated=True`. Live, a genuinely ambiguous real NPPES
pair (identical org name "ACUTE MEDICAL SUPPLY", shared address, no shared
phone/officer) scored `match_probability=0.78` — a real, considered judgment
call from the model, just one that landed above the escalation band rather
than inside it. That's expected: escalation is conditioned on the model's
actual output, which this session doesn't control call-to-call. The offline
test is the authoritative proof the wiring works; the live run is evidence
the agent's own judgment is reasonable.

### Numeric grounding — implemented as a post-hoc check, not literally inside `after_model_callback`

CLAUDE.md hard rule 1 / the M3 Action Plan both say "enforce this in
`after_model_callback`." `agents/_base.py`'s callback slot is shared,
fixed-signature telemetry plumbing used by every agent — adding a second,
per-agent-customizable callback slot would touch `_base.py`/`_llm_call.py`
for every future agent, not just this one. `graph_investigation.investigate()`
instead does the check as an explicit Python step after `run_agent` returns:
extract every numeric literal from `narration`/`community_context` via
regex, assert each appears somewhere in the evidence bundle (as rendered
JSON text), quote violations back and retry once, raise
`NumericGroundingError` on a second failure. Functionally equivalent; proven
in `tests/test_graph_investigation.py::test_numeric_violations_catches_a_fabricated_number`
without needing a live model to actually fabricate a number. Not exercised
live this session — the real model's narration didn't invent any numbers,
so the retry path never fired; the offline test is what actually exercises
the reject-and-retry logic.

### Live agent verification (`scripts/35_smoke_investigation_agents.py`)

All three new agents ran successfully end to end against the live graph and
Azure T1 (`gpt-5.4-mini`): `entity_resolution` on a real ambiguous NPPES pair,
`graph_investigation` on the S03 synthetic address-cluster scenario (real
characterization text confirmed, zero numeric-grounding violations),
`enforcement_intel` on a real provider against the 1-row DOJ corpus (debt
D-2 — correctly returned empty `matches`, not a fabricated one). Full output
captured in this session's transcript; re-run the script to reproduce
(costs real Azure tokens, same caveat as `scripts/15_smoke_data_quality.py`).

### Grounded Research Agent (M4) — live, isolated, citation trail confirmed

`agents/grounded_research.py`: `build_grounded_research_agent(router,
settings)` builds an `LlmAgent` with exactly one tool (`google_search`);
`build_grounded_research_tool(agent)` wraps it in `AgentTool(...,
propagate_grounding_metadata=True)` for future consumers, who must receive
it as a bound tool, never attach `agent` itself as a `sub_agent`
(CLAUDE.md's hard isolation rule). `research_topic(query, agent,
evidence_dir)` runs the agent directly against its own `Runner` and turns
every `grounding_metadata.grounding_chunks[i].web` into an
`EvidenceArtifact` with `extraction_method="vertex_grounding"`.

`scripts/45_smoke_grounded_research.py` run live against a real DME-fraud
enforcement query: **7/7 real citations**, each a genuine
`EvidenceArtifact` written to `data/evidence/`, narrative correctly used
`charged`/`sentenced`/`pleaded guilty` language per source rather than
collapsing them. Raises if citations come back empty — that's the D10
regression this script exists to catch.

**Two things the *next* session must not get wrong:**

1. **`build_grounded_research_tool()`'s `AgentTool` propagation path has
   not been exercised live** — only the direct-call path
   (`research_topic`) has. M5's `enforcement_intel`-style consumer (or
   whichever agent first gets `AgentTool(grounded_research_agent)` in its
   `tools=[]`) must re-verify `tool_context.state['temp:_adk_grounding_
   metadata']` actually round-trips before trusting it. `NOTES_API_
   DEVIATIONS.md` D10.
2. **Grounding URIs are Google redirect links, not the source page URL**
   (`vertexaisearch.cloud.google.com/grounding-api-redirect/...`), and
   `web.title` is sometimes just the bare domain. Confirmed live — see
   the stored artifact content in this session's `data/evidence/` output.
   `check_citation_validity` (M9) is unaffected (it only checks an
   artifact exists), but don't assume the stored URI is directly
   followable by a human reviewer. `NOTES_API_DEVIATIONS.md` D15.

`EvidenceArtifact` gained a required `extraction_method: str` field (no
default, same discipline as `RiskSignal`'s M3 fields) — `store_artifact()`
now takes it as a 5th positional/keyword argument. Every existing call site
(4 in `tests/test_evidence_tools.py`) was updated to pass `"direct"`.

### Judgement agents (M5) — Skeptic + CaseReporter, live-verified end to end

`agents/skeptic.py` (`challenge`, T2, no tools) and `agents/case_reporter.py`
(`synthesize`, T2, no tools) both take the *previous step's*
`AgentRunResult.output` dict directly (`graph_findings`,
`enforcement_findings`, `counter_evidence`) — no reshaping needed between
pipeline stages, by design, so M6's fan-in can call them with zero glue code.

`agents/_grounding.py` generalizes the numeric-grounding extract/compare
logic `graph_investigation.py` (M3) implemented first — `numbers_in`/
`numeric_violations`, both pure functions. `graph_investigation._numeric_violations`
is now a 3-line wrapper over it (D-14 cleared); `case_reporter.synthesize` is
the second real consumer. `core/banned_vocabulary.py` implements CLAUDE.md
hard rule 9 as a word-boundary, case-insensitive regex — verified live that
"guiltily" doesn't false-match "guilty" and that a possessive ("guilty's")
still does.

`CasePacket` (in `core/contracts.py`) is assembled in plain Python by
`case_reporter.synthesize`, not by an LLM `output_schema` — the LLM only ever
produces `CaseNarrative` (`narrative` + `exhibited_indicators_summary`, the
latter's claimed count grounded against a `signal_count` entry
`build_evidence` adds to the evidence bundle for exactly that purpose).
Verified live against the S03 scenario: 2/2 signals rebutted by the Skeptic,
`confidence_adjustment=-0.3` (within `[-0.4, 0.0]`), `CasePacket.citation_report
.all_resolved=True`, zero banned phrases — both assertions run in-script
(`scripts/48_smoke_judgement_agents.py`), not eyeballed.

**Not yet live-verified:** the `graph:enforcement_case:<case_id>` branch of
`case_reporter._collect_source_ids` / `validate_citations` — S03's
`enforcement_intel` call correctly returned `matches=[]` against the 1-row
DOJ corpus (debt D-2), so the live checkpoint only exercised a
`graph:address:...` citation. Unit-tested, not live-verified; worth a real
check once M7 refills the DOJ corpus.

D-16 (the plan §9.1 Orchestrator agent, missing from every milestone's
scope) is still open — M5 didn't touch it. M6's own Action Plan (below)
proposes a deterministic substitute for `cohort_select`/fan-out rather than
building the plan's LLM planning agent, flagged there as a decision for the
operator to confirm or override.

---

## 4. CARRIED DEBT

| ID | Item | Why deferred | Due |
|---|---|---|---|
| D-1 | `state_medicaid_fl` and `state_medicaid_tx` ingest **0 rows** — both sources are bot-blocked | Needs the Playwright MCP fetch path, which doesn't exist yet | **M7** |
| D-2 | `doj` ingests **1 row**, loaded as 1 `EnforcementCase` node (M2) — the *loader* half is done, the *corpus size* half is still a gap | Semantic retrieval works against a 1-row corpus (`retrieval.semantic()` verified live), but 1 row is not a real corpus for the Enforcement agent to search | **M7** (refill via Playwright MCP) |
| D-3 | `synthetic_providers` has 186 rows; plan §5.5 specifies 50 scenario + 150 controls = 200 | Not blocking; verify the S01–S10 scenario coverage is intact | **M6** |
| ~~D-4~~ | ~~Amendment 3 geocoding not implemented~~ | **Cleared M3.** `data/reference/zcta_centroids.csv` (33,791 rows), `zip_centroid()`/`haversine_km()`, `geographic_spread` rewritten to use ZIP centroids. Verified live against S09. | — |
| D-5 | The Data Quality verdict is **not deterministic** — the same snapshot returned `warn` on one run and `fail` on the next, because tier T1 runs at `temperature=0.1` | A pipeline gate should not flip. Options: per-agent temperature override, or make the gate honour the deterministic `ValidationReport` verdict and treat the agent as advisory | **M6** |
| ~~D-6~~ | ~~No agent-level escalation~~ | **Cleared M3.** `run_agent` calls `router.should_escalate`; proven offline (deterministic test) and exercised live (didn't fire — real model output landed outside the escalation band, which is expected, not a gap). | — |
| D-7 | Phoenix container runs but nothing exports to it. `_base.py` sets OTel span attributes with no tracer provider registered, so they go nowhere | Tracing setup is its own milestone | **M8** |
| D-8 | `price_*` fields in `config/models.yaml` are all `null`, so `cost_usd` is always `NULL` | Deliberate — plan §7.4: "a wrong cost chart is worse than no cost chart". Operator must fill in real pricing | **M10** |
| ~~D-9~~ | ~~`get_community_context` never reads persisted characterization~~ | **Cleared M3.** Reads `characterization`/`notable_members`/`risk_themes`/`generated_at`/`prompt_version` off the Community node alongside the always-fresh structural facts. Verified live. | — |
| D-10 | `EnforcementCase.legal_status` loaded by M2's `graph/enforcement_loader.py` still comes from the **regex keyword heuristic** (`infer_legal_status`) on the graph node itself — **clarified, not fully cleared, M5.** `case_reporter.synthesize` now embeds the agent's real per-match adjudication (`EnforcementFindings.legal_status_per_match`) directly into `CasePacket.legal_status_per_match` — the *case packet*, not the graph node, is the system of record for an investigation's adjudicated legal status. The graph node's own `legal_status` property is left as the loader's coarse heuristic deliberately (a default/fallback for queries that never ran the agent), not an oversight. | Whether the graph node should *also* be updated (vs. staying loader-only) is a separate, lower-stakes question — nothing currently reads the stale node property for a screened provider, since `CasePacket` is what gets reported | not urgent — revisit only if something starts reading `EnforcementCase.legal_status` directly for a screened provider |
| ~~D-14~~ | ~~Numeric-grounding check duplicated per-agent~~ | **Cleared M5.** `agents/_grounding.py` — `numbers_in`/`numeric_violations`, both pure functions. `graph_investigation._numeric_violations` is now a thin wrapper over it; `case_reporter.synthesize` is the second real consumer. | — |
| D-15 | `build_grounded_research_tool()`'s `AgentTool(..., propagate_grounding_metadata=True)` wiring exists and is unit-tested offline, but **the propagation path has never actually run live** — M4's own checkpoint calls the search agent directly via its own `Runner`, not through a consumer's tool call, so `tool_context.state['temp:_adk_grounding_metadata']` round-tripping is verified against ADK 2.6.2 source only, not by a real call | M5's `skeptic`/`case_reporter` both run with `tools=[]` — neither consumes `grounded_research`, so M5 did not wire a live consumer either | **M9** (no earlier milestone has a natural consumer left) |
| D-16 | Plan §9.1's **Orchestrator agent** (`plan_investigation`, T2, output `InvestigationPlan { provider_npis, depth, rationale, budget_hint }`) is not scoped into any milestone in this file | M5 did not resolve this either. M6's own Action Plan now proposes a concrete deterministic substitute (`cohort_select` + `find_shared_attribute_peers`-based candidate pairing, no LLM planning call) rather than building the plan's LLM agent — a proposal for the operator to confirm or override, not yet an implemented decision | **M6**, proposal written, needs operator confirmation before or during implementation |

---

## 5. MILESTONES

---

### M1 — Agent foundation · `DONE`

**Delivered.** The shared agent factory, verified against a live Azure
deployment, plus the first working agent.

| Path | What |
|---|---|
| `src/specter/agents/_base.py` | `AgentRuntime`, `build_runtime`, `build_agent`, `run_agent`, `_parse_output` |
| `src/specter/agents/data_quality.py` | Data Quality Agent + deterministic snapshot facts |
| `src/specter/tools/bindings.py` | 10 model-facing bindings + the assembler (`build_tool_bindings`) |
| `src/specter/tools/signal_bindings.py` | the 9 signal-detector bindings, split out to stay under the 400-line ceiling |
| `prompts/agents/data_quality.md` | agent role brief (below the cache boundary) |
| `prompts/blocks/b0_tool_schemas.md` | regenerated — was 2 tools, now 19 |
| `scripts/05_generate_prompt_blocks.py` | B0 regeneration |
| `scripts/15_smoke_data_quality.py` | live smoke test |
| `tests/test_agent_base.py` | 14 offline tests |
| `NOTES_API_DEVIATIONS.md` | D1–D10 |
| `src/specter/llm/router.py` | EDIT — v1-surface model string + transport kwargs |
| `src/specter/llm/prompt_compiler.py` | EDIT — `system_prefix` property |
| `src/specter/core/contracts.py` | EDIT — `AgentOutput`, `SourceVerdict`, `DataQualityReport`, `AgentRunResult` |
| `tests/test_prompt_compiler.py` | EDIT — threshold 1200→1800, B0 staleness guard |
| `tests/test_router.py` | EDIT — pass `settings=` |

**Checkpoint — passed.**

```
pytest tests/ -q                      134 passed
ruff check src/ tests/ scripts/       All checks passed
mypy src/                             Success: no issues in 36 source files
python scripts/15_smoke_data_quality.py
  → VERDICT: fail, 8 per-source verdicts, blocking_reasons naming FL/TX
  → run 1: cached 0/9,983    run 2: cached 9,472/9,983 (95%)
  → L1 enabled, second run: cache_layer=L1, latency 0ms
```

**Key decisions, and why.**

1. **The cache boundary is ADK's `static_instruction`, not hand-built
   messages.** B0–B3 → `static_instruction` (verbatim system message);
   per-agent brief → `instruction` (demoted to a `user` turn); evidence + task
   → `new_message`. Less code than assembling strings, and it is the path
   ADK's own request pipeline is built around. See `NOTES_API_DEVIATIONS.md`
   D3.

2. **One prefix shared by every agent.** `static_instruction` is identical
   across agents on purpose — all agents then warm the *same* Azure cache
   entry rather than each paying its own cold call. Anything agent-specific
   must stay in `instruction`, and
   `test_agent_instruction_stays_below_the_boundary` enforces that.

3. **L1 cache sits outside ADK, in `run_agent`.** Short-circuiting inside
   `before_model_callback` would still pay for session setup and request
   assembly, and would bypass `output_schema` post-processing. A whole-call
   cache belongs around the whole call.

4. **Tools are bound, never raw.** Every underlying tool takes a `Driver` and
   `ScreeningThresholds`. Exposing those to a model would let it choose a
   threshold — i.e. choose a number, violating hard rule 1.
   `tools/bindings.py` closes over them and re-exposes clean signatures;
   `test_bindings_hide_infrastructure_from_the_model` enforces it.

5. **`_parse_output` raises instead of repairing.** A half-parsed agent
   response is worse than none (hard rule 7).

**Things the next sessions must not get wrong.**

- **Never pass a model *string* to `LlmAgent`.** With `output_schema` + `tools`
  and a bare string, ADK silently swaps in a prompt-based workaround that
  injects extra system text and destroys the cached prefix. Always
  `router.model_for(task_class)`. (D4)
- **No `default=` on any agent `output_schema` field.** Azure runs structured
  output in strict mode and rejects defaults with a 400 at run time. Use
  `X | None` and fill explicitly. (D5)
- **Regenerate B0 whenever a tool changes:**
  `python scripts/05_generate_prompt_blocks.py`. A test fails if you forget.
  B0 is above the cache boundary, so stale B0 means the agents are described
  the wrong tools *and* regenerating later invalidates every warm entry.
- **Callback parameter names are load-bearing** — `callback_context`,
  `llm_request`, `llm_response`, positional-or-keyword, no `*`. (D6)

---

### M2 — Graph RAG completion · `DONE`

**Delivered.** Pillar #1 finished — `global_()`/`semantic()` are real vector
search, not stubs, and B2 carries real content. Full run, not a dev sample:
all 255 communities got a real `summarize_community` LLM call (operator
explicitly chose the full 255-call run over a `--limit` dev sample, given
the real Azure cost).

| Path | What |
|---|---|
| `src/specter/graph/embeddings.py` | `embed_texts()` — 55 lines |
| `src/specter/graph/summaries.py` | `summarize_communities`, `embed_communities`, `render_b2_community_summaries`, `community_facts` — 261 lines |
| `src/specter/graph/enforcement_loader.py` | `load_enforcement_cases`, `infer_legal_status` — split out of `loader.py`, see Deviations |
| `src/specter/graph/loader.py` | EDIT — `load_snapshot` now takes `settings` and calls `load_enforcement_cases`; 399 lines |
| `src/specter/graph/retrieval.py` | EDIT — real `global_()`/`semantic()`, `hybrid()` no longer gates on `AZURE_API_KEY` |
| `src/specter/llm/prompt_compiler.py` | EDIT — `_community_summaries_block` reads `prompts/blocks/b2_community_summaries.md` |
| `src/specter/core/contracts.py` | EDIT — `CommunityCharacterization`, `ScreeningThresholds.community_summary_cap` |
| `config/screening.yaml` | EDIT — `thresholds.community_summary_cap: 40` |
| `prompts/agents/community_summarizer.md` | agent role brief |
| `prompts/blocks/b2_community_summaries.md` | generated, committed — 255 characterized communities, capped to top 40 shown |
| `scripts/20_build_graph.py` | EDIT — passes `settings` to `load_snapshot` |
| `scripts/30_build_communities.py` | EDIT — `--summaries`/`--embeddings`/`--limit` flags; regenerates B2 |
| `tests/test_summaries.py` | CREATE — 5 offline-safe-but-Neo4j-backed tests |
| `tests/test_graph_retrieval.py` | EDIT — `global_`/`semantic`/`hybrid` now assert real shape, not the old "empty without a key" behavior |
| `tests/test_graph_tools.py` | EDIT — `search_enforcement_cases` test updated for the real loaded case (see Deviations) |
| `NOTES_API_DEVIATIONS.md` | D11 (embedding response shape), D12 (vector-write Cypher form) |

**Checkpoint — passed, against the live graph (not a fixture).**

```
pytest tests/ -q                      141 passed
ruff check src/ tests/ scripts/       All checks passed
mypy src/                             Success: no issues in 40 source files

MATCH (c:Community) WHERE c.embedding IS NOT NULL RETURN count(*)        → 255
MATCH (c:Community) WHERE c.characterization IS NOT NULL RETURN count(*) → 255
MATCH (c:EnforcementCase) RETURN count(*)                                → 1
MATCH (c:EnforcementCase) WHERE c.embedding IS NOT NULL RETURN count(*)  → 1
MATCH (:Provider)-[r]->(:EnforcementCase) RETURN count(r)                → 0

GraphRetriever.global_("shell provider address cluster", k=5)
  → mode=global, 5 items, all item_type=Community, all source_ids non-empty
GraphRetriever.hybrid(sample_npi, "shell provider pattern")
  → local: 50 items, hybrid: 56 items — strictly more, confirmed live
test_prompt_compiler.py — all 7 tests (the 4 invariants + 3 more) pass
0 fabricated `notable_members` dropped across all 255 summarization calls
```

**Key decisions, and why.**

1. **B2 is a generated, committed file, not something `PromptCompiler`
   queries live.** `PromptCompiler` has no Neo4j driver and must stay
   offline-constructible (the four cache invariants are tested without a
   live graph). `scripts/30_build_communities.py` renders
   `prompts/blocks/b2_community_summaries.md` from the graph — same pattern
   as B0 — and `_community_summaries_block` just reads it, stamping its own
   `graph_version` into the header at read time so that field never goes
   stale relative to the file.

2. **`summarize_communities()` and `embed_communities()` are separate
   functions, not one.** Different cost/failure profiles: 255 T1 chat calls
   are the real money and time; embedding calls are cheap. Splitting them
   lets `scripts/30_build_communities.py --embeddings` alone re-embed after a
   characterization edit without re-paying for the LLM call, and lets
   `--summaries --limit N` develop cheaply before committing to the full run.

3. **`EnforcementCase.legal_status` comes from a regex keyword heuristic in
   the loader, not an LLM call.** A loader has no business calling an LLM —
   that's M3's `extract_enforcement_case` agent's job. The heuristic
   defaults to `alleged` (the weakest claim) on no match, so it never
   overclaims even though it's crude. Tracked as debt D-10 for M3 to
   properly adjudicate.

4. **`graph/loader.py` split into `graph/loader.py` +
   `graph/enforcement_loader.py`.** Adding `load_enforcement_cases` in place
   pushed `loader.py` to 503 lines, over CLAUDE.md's 400-line ceiling. Per
   BUILD_MILESTONES.md §0.2 ("CLAUDE.md wins" when it conflicts with an
   Action Plan), split rather than left oversized — a deviation from the
   Action Plan's literal file manifest (which said "EDIT `loader.py`" with no
   new file), noted here rather than silently done.

**Deviations from the Action Plan — say so plainly.**

- **The full 255-community run, not a `--limit` dev sample.** The Action
  Plan's Definition of Done required all 255 to carry both `embedding` and
  `characterization`; its own Traps section warned "255 T1 calls cost real
  money, develop against `--limit`." Both are true at once — developing
  cheap and *shipping* the full run are different steps. Asked the operator
  explicitly before spending; they chose the full run.
- **`scripts/20_build_graph.py` and `load_snapshot()` needed `settings`
  threaded through, not just `graph/loader.py` edited in isolation.** The
  Action Plan's file manifest didn't list either, but `load_enforcement_cases`
  needs `Settings` to embed, and there was no other place for the checkpoint's
  own "`EnforcementCase` count ≥ 1" requirement to be satisfied from — the
  loader has to actually run somewhere. Minimal, unavoidable, one line each.
- **`tests/test_graph_tools.py::test_search_enforcement_cases_empty_until_m5`
  broke** once a real `EnforcementCase` node existed (correctly — it was
  asserting the pre-M2 stub behavior). Not in the file manifest, but the
  failure is a direct, intended consequence of this milestone's own change,
  not an unrelated bug — fixed and renamed rather than left red.

**Things the next session must not get wrong.**

- **`get_community_context` (both the `graph_tools.py` function and the
  `tools/bindings.py` binding over it) does not read the characterization
  M2 just paid for.** It recomputes `structural_facts` fresh every call and
  always returns `characterization=None`. Real gap, not a false alarm — see
  §3's "Known gap" callout and debt D-9.
- **`GraphRetriever` isn't exposed as an agent tool binding.** Plan §9.4 says
  Graph Investigation should call `retriever.hybrid()`; `tools/bindings.py`
  only wraps `graph_tools`/`signal_tools`/`entity_tools`/`evidence_tools`
  functions today. M3 needs to decide whether to add a `hybrid_search`
  binding or route through something else — this wasn't decided in M2.
- **`db.create.setNodeVectorProperty` works fine directly inside `UNWIND`** —
  no `CALL { ... }` subquery wrapper needed on Neo4j 5.26. Verified live;
  see `NOTES_API_DEVIATIONS.md` D12.
- **`litellm.embedding()`'s `response.data` items are dicts** (`item["index"]`,
  `item["embedding"]`), not attribute-access objects, on this deployment.
  See D11.

---

### M3 — Investigation agents · `DONE`

**Delivered.** Three working investigation agents, ZCTA-centroid geocoding
(Amendment 3), escalation wiring, and the D-9 fix — the first agents that
reason over evidence rather than gating (`data_quality`) or summarizing
(`community_summarizer`).

| Path | What |
|---|---|
| `src/specter/agents/entity_resolution.py` | T1 `adjudicate_entity_match`, tools `propose_entity_matches`/`name_similarity` |
| `src/specter/agents/graph_investigation.py` | T1 `narrate_graph_signal`, all of `graph_tools`+`signal_tools`, `GraphRetriever.hybrid()` pre-fetch, numeric-grounding retry |
| `src/specter/agents/enforcement_intel.py` | T1 `extract_enforcement_case`, tool `search_enforcement_cases` |
| `src/specter/agents/_llm_call.py` | CREATE — split out of `_base.py`: `_invoke`, `_validate_output`, `_parse_output`, `_final_text` |
| `src/specter/agents/_errors.py` | CREATE — `AgentOutputError`, `PrefixInstabilityError`, split out to break a circular import between `_base.py` and `_llm_call.py` |
| `src/specter/agents/_base.py` | EDIT — escalation in `run_agent`; `_build_agent_with_instruction` takes `tier_override`; 265 lines (was 395, peaked at 479 mid-edit before the split) |
| `src/specter/llm/router.py` | EDIT — `model_for_tier(tier_name)`; `model_for(task_class)` now delegates to it |
| `src/specter/tools/entity_tools.py` | EDIT — `zip_centroid()`, `haversine_km()` |
| `src/specter/tools/signal_tools.py` | EDIT — `geographic_spread` rewritten on ZIP centroids; `_signal()` takes `known_limitations`/`geocoding_method` |
| `src/specter/tools/graph_tools.py` | EDIT — `get_community_context` reads persisted characterization (D-9) |
| `src/specter/core/contracts.py` | EDIT — `EntityMatchAdjudication`, `GraphFindings`, `EnforcementFindings`, `CaseLegalStatus`; `RiskSignal` gained required `known_limitations`/`geocoding_method` |
| `data/reference/zcta_centroids.csv` | CREATE — 33,791 rows, committed |
| `prompts/agents/entity_resolution.md`, `graph_investigation.md`, `enforcement_intel.md` | CREATE — role briefs |
| `scripts/35_smoke_investigation_agents.py` | CREATE — live checkpoint script |
| `tests/test_entity_tools.py` | EDIT — `zip_centroid`/`haversine_km` cases |
| `tests/test_signal_tools.py` | unchanged — S09 passed as-is against the rewritten `geographic_spread` |
| `tests/test_graph_tools.py` | EDIT — `test_get_community_context_s10` now asserts real characterization, not `None` |
| `tests/test_agent_base.py` | EDIT — offline escalation test; imports `_parse_output` from `_llm_call` now |
| `tests/test_entity_resolution.py`, `test_graph_investigation.py`, `test_enforcement_intel.py` | CREATE — offline evidence-builder + numeric-grounding-helper tests |
| `NOTES_API_DEVIATIONS.md` | D13 |

**Checkpoint — passed.**

```
pytest tests/ -q                      154 passed
ruff check src/ tests/ scripts/       All checks passed
mypy src/                             Success: no issues in 45 source files
docker compose ps                     neo4j, phoenix, redis — all healthy

zip_centroid('33132') -> (25.776585, -80.173242)
S09 geographic_spread (live, ZIP centroids): 3769.7 km (was 3760±50 on lat/lon)

scripts/35_smoke_investigation_agents.py (live, real Azure T1 calls):
  entity_resolution: ACUTE MEDICAL SUPPLY pair -> match_probability=0.78,
    decision=agent_review, escalated=False (real judgment call, outside the
    [0.45,0.65] escalation band — see "Escalation" below)
  graph_investigation: S03 address cluster -> 2 signals narrated correctly,
    community_context quotes the real M2 characterization text, zero
    numeric-grounding violations
  enforcement_intel: S02 vs. 1-row DOJ corpus -> matches=[] (correct — no
    real case to find, debt D-2)

tests/test_agent_base.py::test_run_agent_escalates_on_ambiguous_match_probability
  -> escalated=True, tier=T2_reasoning (offline, monkeypatched — the
     deterministic proof the escalation live run above didn't happen to trigger)
```

**Key decisions, and why.**

1. **`GraphRetriever` gets a Python pre-fetch, not a new tool binding.** M2
   left this open; the recommended-and-taken path keeps hard rule 1
   structurally true the same way `data_quality.build_evidence` does — there
   is a query, but not a *choice* of when to run it. `tools/bindings.py` is
   untouched, so B0 never went cold this milestone.

2. **Numeric grounding is a post-hoc Python check in `graph_investigation.py`,
   not literally inside ADK's `after_model_callback`.** `_base.py`'s callback
   slot is fixed, shared telemetry plumbing; making it pluggable per agent
   would touch it for every future agent for one consumer's need.
   Functionally identical (extract → assert → quote-back retry → raise);
   `judge/deterministic_checks.py` (M9) does the real, authoritative version
   of the same idea. Tracked as debt D-14, not urgent.

3. **Escalation caps at exactly one retry, unconditionally** — no threading
   of `EscalationRule.max_retries` through `should_escalate`'s return value.
   Every rule in `config/models.yaml` already sets `max_retries: 1`, so there
   was nothing to configure; `run_agent` calls `_invoke` a second time and
   does not check `should_escalate` again on that result.

4. **`_base.py` split into `_base.py` (construction) + `_llm_call.py`
   (invocation) + `_errors.py` (shared exception types).** The escalation
   refactor pushed `_base.py` to 479 lines, over CLAUDE.md's 400-line
   ceiling — same situation M2 hit with `graph/loader.py`, same resolution.
   `_errors.py` exists only to break the circular import `_llm_call.py`
   would otherwise have on `_base.py` (both need to raise
   `AgentOutputError`); `_llm_call.py` type-hints `AgentRuntime` under
   `TYPE_CHECKING` rather than importing it, so the dependency stays
   one-directional (`_base.py` → `_llm_call.py`, never the reverse).

5. **`core/contracts.py` (512 lines) was *not* split**, despite also being
   over 400. CLAUDE.md's "all contracts live in `core/contracts.py`" is a
   more specific rule than the generic module-size cap, and it was already
   over 400 (450 lines) before this milestone with no debt entry raised by
   M1/M2 — an established, if unstated, precedent that this rule wins here.

**Deviations from the Action Plan — say so plainly.**

- **`EnforcementFindings.legal_status_per_match` changed from
  `dict[str, LegalStatus]` to `list[CaseLegalStatus]`.** The Action Plan's
  own draft schema used a `dict`; Azure strict-mode structured output cannot
  represent an open-ended `dict` at all (400 at run time, not a schema-build
  error) — see `NOTES_API_DEVIATIONS.md` D13. Found live, on the third of
  three smoke-script agent calls.
- **`RiskSignal` gained two new *required* fields** (`known_limitations`,
  `geocoding_method`), not optional/defaulted ones. `GraphFindings.signals`
  nests `RiskSignal` inside an agent `output_schema`, and D5's "no defaults"
  strict-mode rule turned out to apply transitively through `$defs` — a
  defaulted nested field would have broken the same way `dict` did.
- **D-10 is marked partially addressed, not cleared**, contrary to the
  Action Plan's inherited-context note ("M3's `extract_enforcement_case`
  agent re-adjudicates from the full text and should overwrite it"). The
  agent does adjudicate `legal_status_per_match` correctly, but nothing in
  this milestone's Steps 1-6 or Definition of Done asked for writing that
  back onto the `EnforcementCase` graph node, and doing so wasn't obviously
  this agent's job vs. something CasePacket assembly (M6) should own — left
  as an explicit open question rather than guessed at.
- **Live escalation didn't fire.** The Action Plan's checkpoint asked to
  "confirm `AgentRunResult.escalated` is `True` at least once... by
  deliberately constructing a case." Read literally, "deliberately
  constructing a case" is exactly what the offline monkeypatched test does;
  the live run used a genuinely ambiguous real pair and the model's own
  judgment (0.78) simply didn't land in the escalation band. Reported
  honestly rather than cherry-picking inputs to force a live trigger.

**Things the next session must not get wrong.**

- **`agents/_base.py` no longer defines `_invoke`/`_validate_output`/
  `_parse_output`/`_final_text`** — they live in `agents/_llm_call.py` now.
  `_base.py` still imports `_invoke` into its own namespace (so
  `monkeypatch.setattr(agent_base, "_invoke", ...)` against
  `specter.agents._base` still works — see the escalation test), but
  `_parse_output` must be imported from `specter.agents._llm_call` directly.
- **Census Gazetteer URLs move.** The one CLAUDE.md pointed at 404s; the
  working 2025 file has a different filename pattern
  (`2025_Gaz_zcta_national.zip`, not `2020_Gazetteer_zcta_national.zip`) and
  is pipe-delimited. Verify again before hardcoding a URL anywhere else.
- **A `dict[str, X]` field anywhere in an agent `output_schema` — including
  nested inside a `list[SomeModel]` item — will 400 at call time, not at
  schema-build time.** Use `list[SomeModel]` of explicit key/value pairs
  instead. Same failure class as D5's no-defaults rule; both only surface
  live. `NOTES_API_DEVIATIONS.md` D13.
- **`get_community_context`'s `characterization` is still `None` for any
  community M2 never characterized** (the top-40-by-cap community summary
  run, not necessarily all 255 — verify against current graph state, don't
  assume). `None` there is a valid, expected state, not a bug.
- **D-10 is still open** (narrower now): `search_enforcement_cases` and the
  `EnforcementCase.legal_status` graph property still reflect the loader's
  regex heuristic. `enforcement_intel`'s own adjudication only lives in its
  return value until something decides to persist it.

---

### M4 — Grounded research · `DONE`

**Delivered.** The system's first and only Vertex (non-Azure) LLM call: an
isolated `google_search` agent with a real, live-verified citation trail.
Unblocked mid-session — the operator supplied `GOOGLE_CLOUD_PROJECT`, a
service-account key, and changed the model to `gemini-3.7-flash` (not in
this codebase's training-era knowledge; taken as given, per CLAUDE.md's
"operator supplies pricing/config" pattern elsewhere).

| Path | What |
|---|---|
| `src/specter/agents/grounded_research.py` | `build_grounded_research_agent`, `build_grounded_research_tool`, `research_topic`, `_ensure_vertex_env` |
| `src/specter/core/contracts.py` | EDIT — `GroundedResearchResult`; `EvidenceArtifact` gained required `extraction_method: str` |
| `src/specter/tools/evidence_tools.py` | EDIT — `store_artifact()` takes `extraction_method` as a required 5th argument |
| `prompts/agents/grounded_research.md` | CREATE — role brief: answer the question, characterize source type, legal-language discipline |
| `scripts/45_smoke_grounded_research.py` | CREATE — live checkpoint, raises on zero citations |
| `tests/test_grounded_research.py` | CREATE — 4 offline tests: tool isolation, model routing, `AgentTool` wiring, fail-loudly on missing project |
| `tests/test_evidence_tools.py` | EDIT — 4 call sites updated for the new required argument |
| `tests/test_router.py` | EDIT — `test_grounded_research_routes_to_vertex` updated for `gemini-3.7-flash` (was already failing when this session started, from the operator's pre-session config edit) |
| `NOTES_API_DEVIATIONS.md` | D10 updated (confirmed against source, live gap noted); D14, D15 added |

**Checkpoint — passed, live.**

```
pytest tests/ -q                      158 passed
ruff check src/ tests/ scripts/       All checks passed
mypy src/                             Success: no issues in 46 source files
docker compose ps                     neo4j, phoenix, redis — all healthy

python scripts/45_smoke_grounded_research.py
  agent tools: ['GoogleSearchTool']
  AgentTool propagate_grounding_metadata=True
  citations: 7   (all extraction_method=vertex_grounding, all real EvidenceArtifacts on disk)
  narrative used charged/pleaded guilty/sentenced correctly per source — no
  legal-status collapsing, no banned vocabulary
```

**Key decisions, and why.**

1. **`GroundedResearchAgent` bypasses `agents/_base.py` entirely** — no
   `build_agent`, no cache boundary, no L1 cache, no `router.model_for_tier`.
   `google_search` only works with ADK's native `Gemini` model class, which
   `LlmAgent` auto-resolves from a bare `"gemini-*"` string; `_base.py`'s
   `model_for_tier` always wraps in `LiteLlm`, which is the wrong client for
   this agent. `router.resolve("grounded_research")` is still used, but only
   to read the model name — routing transparency stays intact without
   forcing this agent through machinery it doesn't need (no evidence bundle,
   no Specter tool bindings, nothing to cache).

2. **`_ensure_vertex_env()` forwards `.env` into `os.environ` with
   `setdefault`.** The empirical finding that cost the most time this
   session: `Settings` never touches `os.environ`, but ADK's native `Gemini`
   client reads Vertex config *only* from `os.environ`. Confirmed live —
   `env | grep GOOGLE` returned nothing in the running shell despite a fully
   correct `.env`. `setdefault` (never clobbers an operator's real shell env)
   plus an upfront `ValueError` if `GOOGLE_CLOUD_PROJECT` is unset, per hard
   rule 7. `NOTES_API_DEVIATIONS.md` D14.

3. **`research_topic()` calls the agent directly via its own `Runner`,
   not through a consumer's `AgentTool` call.** M4's own scope is "one
   working grounded-research agent," not "one working consumer" — no
   consumer exists yet. `build_grounded_research_tool()` is still built and
   unit-tested (`propagate_grounding_metadata=True`, wraps the given agent),
   satisfying the Definition of Done's wiring requirement, but the
   `tool_context.state['temp:_adk_grounding_metadata']` round-trip itself
   has only been verified against ADK 2.6.2 source, not a live call. Tracked
   as debt D-15, due whichever milestone wires the first real consumer.

4. **`EvidenceArtifact.extraction_method` is required, not defaulted** —
   same no-silent-defaults discipline `RiskSignal` established in M3, even
   though this isn't a strict-mode agent `output_schema` field (nothing
   forced it). Consistency: every future caller states its evidence's
   provenance explicitly rather than the codebase silently assuming one.

**Deviations from the Action Plan — say so plainly.**

- **`tests/test_router.py::test_grounded_research_routes_to_vertex` was
  already red at session start**, from the operator's own pre-session `.env`
  /`config/models.yaml` edit switching the model to `gemini-3.7-flash`
  without updating the test's hardcoded `"gemini-2.5-flash"` assertion.
  Fixed as the first action of this session, before any M4 code was written
  — a stale assertion, not a new bug introduced by this milestone.
- **The Action Plan's own "Read before writing" pointed at `.context/adk-
  llms-full.txt`, which had gone stale** (the file at that path now just
  redirects to `https://adk.dev/llms-full.txt` — the docs moved off the
  `adk-docs` GitHub repo entirely). Re-fetched from the new location per
  CLAUDE.md's ritual; the old URL in CLAUDE.md's own instructions is now
  itself stale and should be updated if anyone edits that file next.

**Things the next session must not get wrong.**

- **Do not build a second Vertex-native agent by copying `_base.py`'s
  pattern.** Any future bare-`Gemini`-string agent needs its own
  `_ensure_vertex_env`-style env forwarding — it is not automatic just
  because `Settings` has the right values. `NOTES_API_DEVIATIONS.md` D14.
- **`GroundedResearchAgent` must never be attached as a `sub_agent`, and
  never gets a second tool.** `build_grounded_research_tool()` is the only
  sanctioned way another agent gets access to it.
- **The stored citation URIs are Google redirect links, not the source
  page URL** (`vertexaisearch.cloud.google.com/grounding-api-redirect/...`).
  Don't build anything that assumes `EvidenceArtifact.stored_path`'s content
  is a directly-followable URL for a human reviewer. `NOTES_API_DEVIATIONS.md`
  D15.
- **The `AgentTool` propagation path (`propagate_grounding_metadata=True`)
  is unit-tested but not live-verified** (debt D-15). Whoever wires the
  first consumer must re-check it actually works end to end, not just trust
  the offline test.

---

---

### M5 — Judgement agents · `DONE`

**Delivered.** The last two of the plan's seven agents. `Skeptic` argues
against every signal `graph_investigation`/`enforcement_intel` found;
`CaseReporter` assembles their combined output into the final `CasePacket` —
the artifact M9's judge subsystem will grade. D-14 (numeric-grounding check
duplicated per-agent) cleared as a byproduct of Step 1.

| Path | What |
|---|---|
| `src/specter/agents/_grounding.py` | CREATE — `numbers_in`, `numeric_violations`, generalized out of `graph_investigation.py` |
| `src/specter/agents/graph_investigation.py` | EDIT — `_numeric_violations` now a thin wrapper over `_grounding.numeric_violations`; no behavior change |
| `src/specter/agents/skeptic.py` | CREATE — T2 `challenge_hypothesis`, no tools, `MissingRebuttalError` if `per_signal` doesn't cover every fired `signal_type` |
| `src/specter/agents/case_reporter.py` | CREATE — T2 `synthesize_case`; `BannedVocabularyError`/`NumericGroundingError`/`UnresolvedCitationError` |
| `src/specter/core/contracts.py` | EDIT — `Rebuttal`, `CounterEvidence`, `CaseNarrative`, `CasePacket` |
| `src/specter/core/banned_vocabulary.py` | CREATE — `BANNED_PHRASES`, `find_banned_phrases` (word-boundary, case-insensitive) |
| `prompts/agents/skeptic.md`, `case_reporter.md` | CREATE — role briefs |
| `scripts/48_smoke_judgement_agents.py` | CREATE — live checkpoint |
| `tests/test_grounding.py`, `test_banned_vocabulary.py`, `test_skeptic.py`, `test_case_reporter.py` | CREATE — 18 offline tests total |

**Checkpoint — passed, live.**

```
pytest tests/ -q                      176 passed
ruff check src/ tests/ scripts/       All checks passed
mypy src/                             Success: no issues found in 50 source files
docker compose ps                     neo4j, phoenix, redis — all healthy

python scripts/48_smoke_judgement_agents.py   (real Azure T1/T2 calls, S03 scenario)
  graph_investigation: 2 signals (address_degree, enumeration_burst), 0 numeric-grounding violations
  enforcement_intel: matches=[] (1-row DOJ corpus, debt D-2 — correct, not a bug)
  skeptic: 2/2 signals rebutted, confidence_adjustment=-0.3, in [-0.4, 0.0]
  case_reporter: CasePacket assembled — citation_report.all_resolved=True,
    find_banned_phrases(narrative) == [] — both asserted in-script, not eyeballed
```

**Key decisions, and why.**

1. **`CaseReporter`'s `output_schema` is `CaseNarrative` (prose only), never
   `CasePacket` itself.** `CasePacket` is assembled in plain Python from
   already-computed `GraphFindings`/`EnforcementFindings`/`CounterEvidence`
   dicts — CLAUDE.md hard rule 1 means the model must never re-derive
   `signals`/citations/`legal_status_per_match`. `CasePacket(SpecterModel)`
   is deliberately *not* an `AgentOutput`, so none of the strict-mode
   no-defaults/no-`dict` constraints apply to it.
2. **`exhibited_indicators_summary`'s claimed count is checked the same way
   as any other number** — `case_reporter.build_evidence` adds a
   `signal_count` entry to the evidence bundle so the model's count claim has
   something concrete to be grounded against, rather than a bespoke
   count-matches-`len(signals)` check living outside the numeric-grounding
   path.
3. **Skeptic's missing-rebuttal check is a hard raise, not a retry loop.**
   The Action Plan flagged this as undecided ("UNVERIFIED whether this needs
   a retry loop... or a hard raise"). The live run covered both signals on
   the first call, so the retry path was never exercised either way; raising
   immediately is the simpler choice and consistent with CLAUDE.md hard rule
   7 (fail loudly) — revisit only if a live run actually drops a signal.
4. **`CaseReporter`'s enforcement-match citations are synthesized, not
   pulled from stored artifacts.** `_collect_source_ids` builds
   `graph:enforcement_case:<case_id>` strings directly off
   `EnforcementFindings.matches`, mirroring the exact format
   `graph_tools.search_enforcement_cases` already stamps onto
   `EnforcementCaseHit.source_ids` — no new lookup needed, `validate_citations`
   resolves it via `_resolves_to_graph_node` like any other `graph:` id.
5. **Check order in `synthesize()` is banned-vocabulary → numeric-grounding →
   citation-validation**, each a distinct `SpecterError` subtype, documented
   in the module docstring per the Action Plan's own Traps section.

**Deviations from the Action Plan — say so plainly.**

- **Live run never exercised the enforcement-citation branch of
  `_collect_source_ids`.** S03's `enforcement_intel` call correctly returned
  `matches=[]` against the 1-row DOJ corpus (debt D-2), so the smoke
  checkpoint only ever validated a `graph:address:...` citation, not a
  `graph:enforcement_case:...` one. The logic is unit-tested
  (`test_collect_source_ids_dedupes_signals_and_enforcement_matches`) but not
  live-verified end to end through `validate_citations` against a real
  `EnforcementCase` node. Worth a real check once M7 refills the DOJ corpus.
- **No live trigger of `MissingRebuttalError`, `BannedVocabularyError`,
  `NumericGroundingError` (case_reporter's), or `UnresolvedCitationError`.**
  All four are unit-testable-in-principle but none were built with a
  dedicated offline test that forces the failure path (unlike
  `graph_investigation`'s `test_numeric_violations_catches_a_fabricated_number`
  pattern) — the shared logic they call (`_grounding.numeric_violations`,
  `find_banned_phrases`) is tested directly instead. If a future session adds
  one, that's tightening, not a gap this milestone left open carelessly.

**Things the next session must not get wrong.**

- **`skeptic.challenge` and `case_reporter.synthesize` both take
  `AgentRunResult.output` dicts directly** (`graph_findings`,
  `enforcement_findings`, `counter_evidence` are all plain
  `dict[str, Any]`, not parsed Pydantic objects) — mirrors how
  `AgentRunResult.output` is already shaped (`model_dump(mode="json")`).
  Datetime/enum fields inside those dicts are ISO strings / plain string
  values; `RiskSignal(**signal)` and `CaseLegalStatus(**match)` both
  round-trip through pydantic validation fine from that shape (confirmed
  live in `case_reporter.synthesize`).
- **`case_reporter.py` and `skeptic.py` both call `build_agent(..., tools=[])`
  directly** — no `build_tool_bindings`/driver plumbing, since neither agent
  has any tools. Don't add a driver parameter to either module's public
  functions "for consistency" with the M3 agents; they genuinely don't need
  one.
- **D-16 (missing Orchestrator agent, plan §9.1) is still open, still not
  decided.** M5 didn't touch it — flagged again below for M6, which is where
  `cohort_select`/fan-out naturally needs *some* answer to "what decides the
  screening cohort and depth," whether that's the plan's `Orchestrator` LLM
  agent or a deterministic substitute. M6's own Action Plan (below) proposes
  the deterministic substitute rather than resolving it via a new LLM agent —
  flagged there as a decision for the operator to confirm or override, not
  silently assumed.

---

### M6 — Orchestration · `TODO`

**Scope.** `workflow/screening.py` on the ADK `Workflow` graph runtime,
`workflow/state.py` with the deterministic `ScoringService` (five dimensions,
signal-family dedup, the §10 escalation gate), `scripts/40_screen.py`.
Concurrency capped at 4. Clears debt **D-3** and **D-5**.

Read `NOTES_API_DEVIATIONS.md` D9 first: `Workflow` must be the **root** —
it cannot be an `LlmAgent` sub-agent — and unmatched conditional routes end a
branch with only a warning, which needs an explicit exhaustive
`DEFAULT_ROUTE` to satisfy hard rule 7.

#### Action Plan

**Goal.** Wire every agent M1-M5 built into one deterministic graph that
runs the full screening pipeline over a real cohort — data quality gate →
cohort selection → bounded-concurrency fan-out (entity resolution, graph
investigation, enforcement intel) → skeptic → deterministic scoring → case
reporter — and emits a `CasePacket` per screened provider. Plan §10. This is
the milestone where the seven agents built in M1-M5 stop being independently
callable functions and become one pipeline.

**Inherited context — read this before touching anything.**

- **Every agent function M6 needs already exists with a stable, working
  signature — this milestone is wiring, not new agent-building.**
  `data_quality.assess(snapshot_dir, runtime) -> AgentRunResult`,
  `graph_investigation.investigate(driver, npi, thresholds, evidence_dir,
  runtime) -> AgentRunResult`, `enforcement_intel.extract(driver, npi,
  thresholds, evidence_dir, runtime) -> AgentRunResult`,
  `entity_resolution.adjudicate(driver, npi, candidate_npi, thresholds,
  evidence_dir, runtime) -> AgentRunResult`, `skeptic.challenge(npi,
  graph_findings: dict, enforcement_findings: dict, runtime) ->
  AgentRunResult`, `case_reporter.synthesize(npi, graph_findings: dict,
  enforcement_findings: dict, counter_evidence: dict, driver, evidence_dir,
  runtime) -> CasePacket`. `skeptic`/`case_reporter` take the *previous
  step's* `AgentRunResult.output` dict directly — no reshaping needed between
  fan-out and fan-in.
- **`config/screening.yaml` already has `cohort`, `signal_families`, and
  `escalation_gate` blocks — written ahead of this milestone, unused until
  now.** `cohort.taxonomy_prefix: "332"` / `cohort.states: [FL, TX, CA]`;
  `signal_families` groups the 9 signal types into 3 families
  (`address_anomaly`, `network_anomaly`, `adverse_history`);
  `escalation_gate.min_independent_signal_families: 3`,
  `evidence_freshness_days: 180`. No config work needed for cohort/family
  membership — just consume it.
- **The 3 `signal_families` and the plan's 5 scoring `dimensions` are NOT the
  same list, and nothing maps one to the other yet.** Plan §10:
  `identity_integrity, network_association, adverse_history, evidence_quality,
  corporate_complexity`. `screening.yaml`'s families are
  `address_anomaly, network_anomaly, adverse_history` — family dedup (which
  raw signals collapse into one vote) is a different concern from the
  dimensional score (what axis that vote counts toward). This mapping is
  real design work this milestone has to do, not a config lookup. Step 2
  below has a strawman; treat it as a proposal to validate, not a spec to
  transcribe.
- **`ADK`'s `Workflow` graph runtime has never been imported anywhere in this
  codebase.** `NOTES_API_DEVIATIONS.md` D9 is research-only — found during M1,
  nothing built against it since. `grep -rn "adk.agents.Workflow" src/`
  returns nothing today. Do not write `workflow/screening.py` from memory of
  the plan's pseudocode graph; find the actual `Workflow`/node/edge API in
  the installed package first (Step 0).
- **`SourceManifest` does not persist a deterministic verdict.** D-5 says the
  Data Quality gate shouldn't flip run to run because T1 runs at
  `temperature=0.1`. The obvious fix — "gate on the deterministic
  `ValidationReport` instead of the LLM's `DataQualityReport`" — doesn't
  have a `ValidationReport` sitting anywhere to read at screening time:
  `Connector.validate()` produces one at *ingest* time and it isn't stored in
  `manifest.json` (`SourceManifest` has no `verdict` field). What *is*
  available and already deterministic is `data_quality._observed_facts()` —
  currently a private, per-source helper that recomputes
  `row_count_matches_manifest`/`null_rate_per_column`/`snapshot_age_days`
  fresh from the parquet on every call. Step 3 below.
- **A live cohort run will very likely hit a real `FAIL` on day one, and
  that's correct, not a bug to route around.** `state_medicaid_fl`/
  `state_medicaid_tx` ingest 0 rows (D-1) and `doj` has 1 row (D-2) — both
  still open, due M7. Decide up front (Step 6) whether M6's own checkpoint
  demonstrates the `halt_node` path as a legitimate pass condition, or runs
  with an explicit, logged override flag. Either is fine; silently loosening
  the gate until the demo run passes is not.
- **`entity_resolution.adjudicate` takes a *pair* (`npi`, `candidate_npi`),
  not a single provider — it doesn't fan out over the cohort the same way
  `graph_investigation`/`enforcement_intel` do.** There is already a
  deterministic candidate generator for this:
  `graph_tools.find_shared_attribute_peers(driver, npi, "address" |
  "phone" | "officer")` returns peer NPIs sharing an attribute, with
  `source_ids` already populated. Step 4 below uses it as the pairing step
  ahead of the entity-resolution fan-out — this wasn't decided by any
  earlier milestone, flagged in M5 as debt-adjacent, resolved here as a
  concrete proposal.

**File manifest.**

| Path | Action | Notes |
|---|---|---|
| `src/specter/workflow/state.py` | CREATE | `cohort_select`, `build_candidate_pairs`, `ScoringService`, `CaseScore`/`PriorityTier` contracts (or add the two contracts to `core/contracts.py` per CLAUDE.md's "all contracts live there" — decide in Step 2, note the choice). |
| `src/specter/workflow/screening.py` | CREATE | The ADK `Workflow` graph: gate → cohort_select → fan-out → fan-in → skeptic → score → case_reporter → END, with an explicit `DEFAULT_ROUTE` on every conditional edge. |
| `src/specter/agents/data_quality.py` | EDIT | `_observed_facts` → `observed_facts` (public) plus a small `deterministic_verdict(sources: list[dict]) -> Verdict` pure function the workflow gate calls instead of the LLM's `DataQualityReport.verdict`. |
| `src/specter/core/contracts.py` | EDIT | `CaseScore`, `PriorityTier` (or in `workflow/state.py`, see above) — not an `AgentOutput`, never sent to an LLM. |
| `config/screening.yaml` | EDIT (maybe) | Only if Step 2's dimension mapping needs a new config key (e.g. per-dimension weights) — don't add one speculatively if a flat/equal weighting is defensible for Phase 1. |
| `scripts/40_screen.py` | CREATE | Entry point: builds runtime, runs the workflow over the live cohort, writes each `CasePacket` to `data/cases/<npi>.json`, prints a per-provider summary + `PriorityTier`. |
| `tests/test_workflow_state.py` | CREATE | Offline: `cohort_select` (Neo4j-backed like `test_graph_investigation.py`), `ScoringService` dimension math and escalation-gate logic (pure, no Neo4j needed — feed it synthetic `CasePacket`-shaped input). |
| `tests/test_screening_workflow.py` | CREATE | Whatever `Workflow`'s own testability surface turns out to be (UNVERIFIED until Step 0) — at minimum, the `DEFAULT_ROUTE` exhaustiveness and the halt-on-FAIL path. |

**Read before writing.**

- `NOTES_API_DEVIATIONS.md` D9 (already quoted above) and D3-D8 for the
  general "what surprised us about ADK 2.6.2" context.
- `src/specter/agents/skeptic.py` and `case_reporter.py` in full — the exact
  dict shapes the fan-in step needs to produce.
- `src/specter/tools/graph_tools.py:95-113` (`find_shared_attribute_peers`)
  and `entity_tools.py:185-226` (`propose_entity_matches`) — the pairing
  primitives for Step 4.
- `src/specter/agents/data_quality.py:60-78` (`_observed_facts`) — the
  deterministic facts to build `deterministic_verdict` from.
- `config/screening.yaml` in full (already read this session, reproduced
  above) — `cohort`/`signal_families`/`escalation_gate` are ready to consume.
- Whatever `python -c "import google.adk.agents as a; print(a.__file__)"`
  points you to for the actual `Workflow` class — Step 0, do this before
  anything else.

**Steps.**

0. **Find the real `Workflow` API before writing anything.** `pip show
   google-adk` for the installed version, then locate `Workflow` in that
   package (`_graph.py` per D9's own file references) and read its
   constructor/node/edge/conditional-routing surface directly from source —
   the plan's pseudocode graph is a shape to build, not an API to call
   verbatim. If it differs from what CLAUDE.md's ritual assumes, log the
   deviation in `NOTES_API_DEVIATIONS.md` (a new D-number) before writing
   `workflow/screening.py`.

1. **`cohort_select(driver, config) -> list[str]`.** Deterministic Cypher:
   providers whose taxonomy code starts with `cohort.taxonomy_prefix` and
   whose state is in `cohort.states`. No LLM. Verify the returned count
   against D-3 while you're in there — `synthetic_providers` has 186 rows
   against the plan's 200 (50 scenario + 150 controls); confirm all ten
   scenario_ids (S01-S10) are actually represented in the live graph and the
   150-control figure is what's short, not a scenario. Update D-3's status
   with whatever you find — don't just carry the note forward unread.

2. **Dimension mapping — a concrete starting proposal, not gospel.** Given
   `signal_families` already groups the 9 detectors into 3 families:

   ```
   corporate_complexity  <- address_anomaly family (address_degree, enumeration_burst, address_churn)
                             + community structural facts (member_count, shared-officer density)
   network_association   <- network_anomaly family (phone_degree, officer_degree, geographic_spread)
   adverse_history        <- adverse_history family (exclusion_proximity, community_exclusion_density,
                             phoenix_pattern) + EnforcementFindings.matches / legal_status_per_match
   identity_integrity     <- EntityMatchAdjudication.decision across this provider's candidate pairs
                             (any human_review/reject conflict lowers it; auto_link/no pairs raises it)
   evidence_quality        <- CitationReport.all_resolved + CounterEvidence.confidence_adjustment
                             (this is where hard rule 8's bounded discount actually gets applied —
                             deterministically, in ScoringService, never inside the Skeptic's own output)
   ```

   Validate this against the plan doc's fuller dimensional model (referenced
   but not reproduced in §10) before committing to it — §10 only gives the
   five names, not their formulas, so this mapping is this session's own
   synthesis. Sanity-check family dedup with a concrete example:
   `address_degree` and `enumeration_burst` both firing on the *same*
   provider should count as ONE fired family for
   `min_independent_signal_families`, not two.

3. **`deterministic_verdict`.** Pull `_observed_facts` out of
   `data_quality.py` as a public function (or leave it private and add a
   thin public wrapper — either is fine, just don't duplicate the Polars
   logic). New pure function, e.g.:

   ```python
   def deterministic_verdict(observed: list[dict[str, Any]]) -> Verdict:
       if any(not o["row_count_matches_manifest"] for o in observed):
           return Verdict.FAIL
       if any(o["snapshot_age_days"] > <threshold> for o in observed):
           return Verdict.WARN
       return Verdict.PASS_
   ```

   Decide the freshness threshold from `evidence_freshness_days` (180) or a
   separate `screening.yaml` value — either is defensible, just state which.
   The workflow gate reads this, not `DataQualityReport.verdict` — the LLM
   call still runs (for the human-readable narrative/`blocking_reasons`),
   it's just no longer what the gate branches on.

4. **Candidate pairing ahead of the entity-resolution fan-out.** Per cohort
   NPI, call `find_shared_attribute_peers` for `address`/`phone`/`officer`,
   union the peer NPIs, dedupe, drop self-matches (already excluded by the
   Cypher's `WHERE peer.npi <> p.npi`) — that's the candidate list
   `entity_resolution.adjudicate` runs against, one call per pair, inside the
   same bounded-concurrency pool as the rest of the fan-out. If a cohort NPI
   has zero peers on any attribute, it simply gets no entity-resolution call
   — that's a correct, informative state (`identity_integrity` scores as
   "no conflict found," not as "unresolved").

5. **Fan-out concurrency: one shared `asyncio.Semaphore(4)`** across every
   LLM call the workflow makes per run (entity resolution pairs + graph
   investigation + enforcement intel, all sharing the same pool) — simplest
   reading of CLAUDE.md's "concurrency capped at 4 parallel providers," and
   avoids needing separate caps per agent type that would let the real
   in-flight Azure request count exceed 4 anyway.

6. **`halt_node` decision.** Given D-1/D-2 are still open, decide explicitly
   whether `scripts/40_screen.py`'s own checkpoint run (a) is expected to hit
   `data_quality_hold` and that IS the passing checkpoint (prove the halt
   path works), or (b) takes an explicit `--override-data-quality-gate` flag
   that logs a loud warning and proceeds anyway for demo purposes. Do not
   quietly downgrade `deterministic_verdict`'s thresholds until a FAIL stops
   happening — that's the silent-loosening CLAUDE.md's rule 7 exists to
   prevent.

**Checkpoint.** `pytest`/`ruff`/`mypy` clean. `python scripts/40_screen.py`
against the live cohort: prints `cohort_size=N`, then either
`data_quality_hold` (if (a) above) or one `CasePacket` summary line per
provider with its `PriorityTier` (if (b)). At least one `CasePacket` on disk
under `data/cases/` with `citation_report.all_resolved=True` and zero banned
phrases, same assertions `scripts/48_smoke_judgement_agents.py` already
makes, now running through the graph instead of by hand.

**Traps.**

- `Workflow`'s unmatched-route behavior is a silent `logging.warning`, not an
  exception (D9). Every conditional edge — the data-quality gate at minimum
  — needs an explicit `DEFAULT_ROUTE`; a warning buried in logs is a silent
  failure under CLAUDE.md hard rule 7 even though nothing crashes.
- Don't let `entity_resolution.adjudicate` calls silently multiply — a cohort
  where many providers share one address (exactly what `address_anomaly`
  fires on) means `find_shared_attribute_peers` can return a large peer set
  for a single NPI. Log the candidate-pair count before running the
  fan-out; if it's large enough to matter, that's a real finding worth a
  `config/screening.yaml` cap, not something to guess a limit for in advance.
- `CounterEvidence.confidence_adjustment` is the one LLM-influenced number
  `ScoringService` may read (hard rule 8) — don't let any other Skeptic field
  (`per_signal`, `unresolved_conflicts`) leak into a score calculation; those
  are for the narrative only.

**Definition of done.**

- [ ] `Workflow` graph runs gate → cohort_select → fan-out → fan-in →
      skeptic → score → case_reporter → END, root-level (not an `LlmAgent`
      sub-agent), against the live cohort
- [ ] `ScoringService` is deterministic code (no agent call), implements the
      five dimensions with signal-family dedup and the escalation gate from
      `config/screening.yaml`
- [ ] Data-quality gate branches on a deterministic verdict, not the LLM's;
      D-5 cleared
- [ ] D-3 resolved with real numbers (not just re-stated) — actual
      scenario/control counts checked against the live graph
- [ ] Every conditional route has an explicit `DEFAULT_ROUTE`
- [ ] `pytest`/`ruff`/`mypy` clean; `scripts/40_screen.py` checkpoint passes
      per whichever halt-node decision Step 6 made
- [ ] §3 Current State and §4 Carried Debt updated; M7 Action Plan written
- [ ] Committed as `M6: orchestration`

---

**Goal.** The last two of the plan's seven agents. `Skeptic` argues against
every signal `graph_investigation`/`enforcement_intel` found; `CaseReporter`
assembles their combined output into the final `CasePacket` — the artifact
M9's judge subsystem grades. Plan §9.7, §9.8.

**Inherited context — read this before touching anything.**

- **No orchestrator exists yet.** Plan §9.1 (`Orchestrator`, T2
  `plan_investigation`, output `InvestigationPlan`) is not scoped into *any*
  BUILD_MILESTONES.md milestone — not M5, not M6 (`workflow/screening.py`
  scope is the deterministic `Workflow` graph + `ScoringService`, no LLM
  planning agent mentioned). This looks like a real gap between this file
  and plan §9.1, not a deliberate cut — flag it to the operator rather than
  quietly building it into M5 (out of this milestone's stated scope) or
  quietly dropping it. Recorded as debt below.
- **Nothing assembles a "full findings bundle" yet either** — that's also
  implicitly the orchestrator's job in the plan. M5 calls `graph_investigation
  .investigate()` and `enforcement_intel.extract()` directly by hand (same
  pattern M3's own smoke script uses) to get real `GraphFindings`/
  `EnforcementFindings` to feed `Skeptic`/`CaseReporter` — there is no
  end-to-end pipeline to run them through until M6.
- **CLAUDE.md hard rule 1 vs. hard rule 8 — this looks like a contradiction
  and isn't.** Rule 1: "No LLM produces a number... a number in agent output
  that isn't in a tool result is a bug." Rule 8: "Scoring is deterministic
  code, never an agent. The Skeptic influences the score only through a
  bounded `confidence_adjustment ∈ [-0.4, 0.0]`." Rule 8 is a narrow,
  explicit carve-out of rule 1: `confidence_adjustment` is a bounded
  judgment discount, not a fact-number derived from evidence — validate it
  with `Field(ge=-0.4, le=0.0)` (no `default=`, same pattern
  `EntityMatchAdjudication.match_probability` already uses successfully,
  M3) and leave it alone. Don't "fix" this into a deterministic tool call —
  it's supposed to be the one LLM-influenced number in the system, on a
  short leash.
- **D-14** (numeric-grounding check duplicated per-agent, not in a shared
  `after_model_callback`) **comes due here.** `CaseReporter`'s own
  no-fabricated-numbers check (plan §9.8) is exactly the second consumer of
  the same pattern `graph_investigation.py` already implemented
  (`_numbers_in`/`_numeric_violations` at `graph_investigation.py:95-127`).
  Extract a generic version rather than copy-pasting a third time. See Step
  1.
- **The numeric-grounding pattern in `graph_investigation.py` is
  field-specific** (`_numeric_violations` reads `output["narration"]` and
  `output["community_context"]` by hardcoded key) — the generic extraction
  needs a `text_fields: list[str]` parameter or similar so `CaseReporter`
  can pass its own narrative field name(s) instead.

**File manifest.**

| Path | Action | Notes |
|---|---|---|
| `src/specter/agents/_grounding.py` | CREATE | `numbers_in(text) -> set[str]`, `numeric_violations(claimed_texts: list[str], evidence: dict) -> list[str]` — generalized out of `graph_investigation.py`. |
| `src/specter/agents/graph_investigation.py` | EDIT | Replace its local `_numbers_in`/`_numeric_violations` with calls into `_grounding.py`. No behavior change — refactor only, existing tests must still pass unmodified. |
| `src/specter/agents/skeptic.py` | CREATE | T2 `challenge_hypothesis`. No tools (reasoning-only over the findings bundle it's handed) — `tools=[]` to `build_agent`, consistent with the subset-of-`all_tools` pattern M3 established. |
| `src/specter/agents/case_reporter.py` | CREATE | T2 `synthesize_case`. Assembles `CasePacket` (see Step 3 for the split between the LLM's narrow `output_schema` and the deterministic assembly code around it). |
| `src/specter/core/contracts.py` | EDIT | `Rebuttal`, `CounterEvidence` (plan §9.7); `CaseNarrative` (LLM output_schema, narrow); `CasePacket` (the assembled artifact — not an agent `output_schema`, so none of the strict-mode no-defaults/no-dict constraints apply to it). |
| `src/specter/core/banned_vocabulary.py` | CREATE | `BANNED_PHRASES = ("fraudulent", "criminal", "guilty", "proven", "confirmed fraud")`; `find_banned_phrases(text: str) -> list[str]`, case-insensitive regex, word-boundary matched. CLAUDE.md hard rule 9: "enforced by regex post-check, not just prompt instruction." |
| `prompts/agents/skeptic.md` | CREATE | Role brief — the benign-explanation checklist from plan §9.7 verbatim (multi-tenant building, billing artifact, peer-comparison mismatch, common-name collision, stale source, synthetic contamination, group-practice structure). |
| `prompts/agents/case_reporter.md` | CREATE | Role brief — controlled vocabulary, `"exhibits N independently observed indicators"` phrasing, explicit reminder of the banned list (belt-and-suspenders with the regex check). |
| `scripts/48_smoke_judgement_agents.py` | CREATE | Live checkpoint: runs `graph_investigation` + `enforcement_intel` on a synthetic scenario NPI, feeds the result into `skeptic`, then `case_reporter`; prints the assembled `CasePacket`. |
| `tests/test_grounding.py` | CREATE | Offline: `numbers_in`/`numeric_violations` unit tests (move/extend whatever's implicitly covered by `test_graph_investigation.py` today). |
| `tests/test_banned_vocabulary.py` | CREATE | Offline: each banned phrase is caught, case-insensitively; a clean narrative returns `[]`; a substring false-positive check (e.g. "guiltily" shouldn't false-match "guilty" — decide word-boundary behavior explicitly and test it). |
| `tests/test_skeptic.py`, `tests/test_case_reporter.py` | CREATE | Offline evidence-builder tests, same style as `test_entity_resolution.py`/`test_graph_investigation.py` (M3). |

**Read before writing.**

- `phase_1_build_plan.md` §9.7-9.8 (lines ~738-746) — exact scope text,
  already quoted above.
- `src/specter/agents/graph_investigation.py` lines 90-180 — the numeric-
  grounding pattern to generalize, and the `build_evidence`/`investigate`
  shape to mirror for `skeptic.py`/`case_reporter.py`.
- `src/specter/core/contracts.py`'s `RiskSignal`, `GraphFindings`,
  `EnforcementFindings`, `CaseLegalStatus`, `EvidenceArtifact` — everything
  `CasePacket` needs to reference or embed.
- `src/specter/tools/evidence_tools.py`'s `validate_citations` — `CaseReporter`
  must call this before returning; it already takes a flat `source_ids: list[str]`
  (M2 built it exactly for this, unused until now).
- CLAUDE.md hard rules 1, 3, 4, 5, 6, 8, 9 — this milestone touches more of
  them at once than any other so far.

**Steps.**

1. **Extract `agents/_grounding.py` first**, refactor `graph_investigation.py`
   to use it, run `pytest tests/test_graph_investigation.py -q` — must still
   pass unmodified before writing anything new. This clears D-14 as a
   byproduct rather than a separate pass.

2. **`Skeptic`.** Draft schema:

   ```python
   class Rebuttal(SpecterModel):
       signal_type: str                    # echoes RiskSignal.signal_type — never invented
       benign_explanation: str | None
       no_plausible_benign_explanation: bool
       reasoning: str

   class CounterEvidence(AgentOutput):
       per_signal: list[Rebuttal]
       unresolved_conflicts: list[str]
       confidence_adjustment: float = Field(ge=-0.4, le=0.0)
   ```

   Evidence bundle: the `GraphFindings`/`EnforcementFindings` this milestone's
   smoke script already ran by hand, serialized the same way
   `graph_investigation.build_evidence` does. `challenge()` should validate
   that `per_signal` covers every `signal_type` actually present in the
   input `GraphFindings.signals` — an LLM silently dropping a signal from
   its rebuttal list is a real failure mode worth catching, same spirit as
   the numeric-grounding check (UNVERIFIED whether this needs a retry loop
   like `graph_investigation`'s or a hard raise; decide once you see real
   output).

3. **`CaseReporter` — the two-part split.** Don't make the LLM's
   `output_schema` *be* `CasePacket`. Rule 1 means fields like
   `signals`/`citations`/`legal_status_per_match` must be echoed from
   already-computed data, not regenerated by the model, so let the LLM
   produce only what's genuinely generative — the narrative — and assemble
   the rest in Python:

   ```python
   class CaseNarrative(AgentOutput):
       narrative: str                      # the controlled-vocabulary prose
       exhibited_indicators_summary: str   # e.g. "exhibits 3 independently observed indicators" — count must be echoed from len(signals), not computed by the model

   class CasePacket(SpecterModel):         # NOT an AgentOutput — assembled, not model-produced
       provider_npi: str
       narrative: str
       signals: list[RiskSignal]
       enforcement_matches: list[str]
       legal_status_per_match: list[CaseLegalStatus]
       counter_evidence: CounterEvidence
       citation_report: CitationReport
       created_at: datetime
   ```

   `synthesize_case()`: run the `CaseNarrative` agent call, run
   `find_banned_phrases()` on `narrative` (raise if non-empty — CLAUDE.md
   hard rule 9 says regex-enforced, not advisory), run
   `numeric_violations()` against the same evidence bundle passed in, run
   `validate_citations()` against every `source_ids` collected off
   `signals`/enforcement matches/counter-evidence, then construct
   `CasePacket` directly in Python from the already-validated pieces. This
   draft schema is a starting point, not gospel — validate every field
   against strict-mode/ADK reality the way M3/M4 both had to (D5/D13 were
   both discovered live, not predicted); expect at least one field shape to
   change once you actually call it.

4. **Banned vocabulary.** Word-boundary, case-insensitive:
   `re.compile(r"\b(" + "|".join(re.escape(p) for p in BANNED_PHRASES) + r")\b", re.IGNORECASE)`.
   Decide and test the "guiltily"-contains-"guilty" edge case explicitly —
   `\b` after "guilty" won't match inside "guiltily" (no word boundary
   between "y" and "i"), which is probably the right call, but prove it
   with a test rather than assuming.

**Checkpoint.** `pytest tests/ -q` all green (offline suite grows by ~4
files); `ruff`/`mypy` clean; `python scripts/48_smoke_judgement_agents.py`
against a real synthetic scenario NPI (e.g. S03, already used by M3's own
smoke script) prints a `CounterEvidence` with at least one `Rebuttal` per
input signal, then a `CasePacket` whose `citation_report.all_resolved is
True` and whose narrative contains none of the banned phrases (assert this
in the script, don't just eyeball it).

**Traps.**

- Giving `CaseReporter`'s `output_schema` the full `CasePacket` shape
  directly — tempting, and wrong twice over: it would let the model
  restate signal counts/citations itself (rule 1), and `CasePacket` isn't
  an `AgentOutput` in the first place (nothing forces strict-mode shape
  constraints on it, which is exactly why assembling it in plain Python is
  easier, not harder).
- Forgetting `CounterEvidence.confidence_adjustment`'s bound is enforced by
  `Field(ge=-0.4, le=0.0)` at the schema level — that's necessary but not
  sufficient; nothing stops a future `workflow/state.ScoringService` (M6)
  from misusing a correctly-bounded value. Note in `CasePacket`'s docstring
  that this field is *the only* LLM-influenced number the scorer may read.
- `find_banned_phrases` running on the raw LLM output before the citation/
  numeric checks — order matters for a useful error message (a banned-word
  violation is a content problem, worth surfacing before spending a retry
  cycle on a citation problem), but don't let one check's exception path
  swallow the others silently. Decide and document the check order in
  `synthesize_case`'s docstring.

**Definition of done.**

- [ ] `Skeptic` produces a `Rebuttal` per input signal, `confidence_adjustment`
      bounded and validated by the schema
- [ ] `CaseReporter` assembles a `CasePacket` with `validate_citations()`
      passing and zero banned phrases, enforced by a regex check that raises
      (not just an instruction)
- [ ] The numeric-grounding check is shared code (`agents/_grounding.py`),
      used by both `graph_investigation.py` and `case_reporter.py` — D-14
      cleared
- [ ] `pytest`/`ruff`/`mypy` clean; existing `test_graph_investigation.py`
      still passes unmodified after the refactor
- [ ] §3 Current State and §4 Carried Debt updated (including a decision or
      an explicit escalation on the missing-Orchestrator-agent gap); M6
      Action Plan written
- [ ] Committed as `M5: judgement agents`

---

### M6 — Orchestration · `TODO`

**Scope.** `workflow/screening.py` on the ADK `Workflow` graph runtime,
`workflow/state.py` with the deterministic `ScoringService` (five dimensions,
signal-family dedup, the §10 escalation gate), `scripts/40_screen.py`.
Concurrency capped at 4. Clears debt **D-3** and **D-5**.

Read `NOTES_API_DEVIATIONS.md` D9 first: `Workflow` must be the **root** —
it cannot be an `LlmAgent` sub-agent — and unmatched conditional routes end a
branch with only a warning, which needs an explicit exhaustive
`DEFAULT_ROUTE` to satisfy hard rule 7.

#### Action Plan

*(not yet written)*

---

### M7 — MCP integration · `TODO`

**Scope.** `tools/mcp_tools.py` — Playwright MCP (storing rendered HTML *and*
a screenshot as `EvidenceArtifact`s) and Neo4j Cypher MCP with all four
mandatory guardrails from `CLAUDE.md`: read-only role, 10s timeout, write-verb
rejection regex, forced `LIMIT 100`. Clears debt **D-1** and **D-2** by
refilling the bot-blocked FL/TX sources and the DOJ corpus.

#### Action Plan

*(not yet written)*

---

### M8 — Observability · `TODO`

**Scope.** `obs/tracing.py` (register the OTel provider → Phoenix; the span
attributes are already being set in `agents/_base.py` and currently go
nowhere — debt **D-7**), `obs/dashboard.py` (the `rich` terminal table from
plan §11), `cli.py`. Cold-vs-warm run must visibly show L1 savings.

#### Action Plan

*(not yet written)*

---

### M9 — Judge subsystem · `TODO`

**Scope.** `judge/detection_eval.py` (deterministic, no LLM — precision@k,
per-scenario recall), `judge/deterministic_checks.py` (the three primary
checks), `judge/rubric_judge.py` with **all five** self-preference mitigations
from `CLAUDE.md` Amendment 2, `judge/calibration_fixtures.py` (C01–C10),
`judge/report.py` — which must open with the verbatim
`JUDGE INDEPENDENCE: LIMITED.` block.

#### Action Plan

*(not yet written)*

---

### M10 — Full run & docs · `TODO`

**Scope.** 250-provider run, `README.md` (including the routing-transparency
rationale and the generated-Cypher injection-surface acknowledgement),
`scripts/00_bootstrap.sh`, reproducible `make demo` per plan §14. Clears debt
**D-8** if the operator supplies pricing.

#### Action Plan

*(not yet written)*
