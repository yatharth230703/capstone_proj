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
| **M2** | Graph RAG completion | `graph/embeddings.py`, `graph/summaries.py`, EnforcementCase corpus, `retrieval.global_/semantic` | `TODO` |
| **M3** | Investigation agents | EntityResolution, GraphInvestigation, EnforcementIntel | `TODO` |
| **M4** | Grounded research | Vertex Gemini agent + `AgentTool` isolation, grounding citations | `TODO` |
| **M5** | Judgement agents | Skeptic, CaseReporter, `CasePacket`, banned-vocabulary enforcement | `TODO` |
| **M6** | Orchestration | `workflow/screening.py`, `ScoringService`, `scripts/40_screen.py` | `TODO` |
| **M7** | MCP integration | `tools/mcp_tools.py` — Playwright + Neo4j Cypher guardrails | `TODO` |
| **M8** | Observability | `obs/tracing.py`, `obs/dashboard.py`, `cli.py` | `TODO` |
| **M9** | Judge subsystem | `judge/` — detection eval, deterministic checks, rubric judge, report | `TODO` |
| **M10** | Full run & docs | 250-provider run, `README.md`, demo script | `TODO` |

---

## 3. CURRENT STATE

*Replace this section each milestone. It describes NOW, not history.*

**Last updated: end of M1.**

### Verified green

```
pytest tests/ -q          134 passed
ruff check src/ tests/ scripts/   All checks passed
mypy src/                 Success: no issues in 36 source files
docker compose ps         neo4j, phoenix, redis — all healthy
```

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
dimensions already declared in `graph/schema.cypher`.

**Vertex is NOT configured** — `GOOGLE_CLOUD_PROJECT` is empty. M4 is blocked
on the operator supplying it.

### Prompt caching — measured, working

Verified end to end through ADK: first call 0 cached tokens, second call
**9,472 / 9,983 = 95%**. The current compiled prefix is **5,284 estimated /
5,267 real tokens**.

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
| **EnforcementCase** | **0** | | | |

255 communities is inside the plan's 40–400 target. `EnforcementCase` is zero
because `graph/loader.py` deliberately does not load DOJ releases — see debt
D-2.

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

Built and tested: `core/`, `ingest/` (4 connectors + synthetic), `graph/`
(schema, loader, communities, retrieval), `llm/` (router, prompt compiler,
response cache, ledger), `tools/` (graph, signal, entity, evidence, bindings),
`agents/` (`_base.py`, `data_quality.py`).

Still empty: `workflow/`, `judge/`, `obs/`. Missing entirely: `cli.py`,
`tools/mcp_tools.py`, `graph/summaries.py`, `graph/embeddings.py`,
`README.md`, `scripts/00_bootstrap.sh`, `scripts/40_screen.py`,
`scripts/50_judge.py`.

---

## 4. CARRIED DEBT

| ID | Item | Why deferred | Due |
|---|---|---|---|
| D-1 | `state_medicaid_fl` and `state_medicaid_tx` ingest **0 rows** — both sources are bot-blocked | Needs the Playwright MCP fetch path, which doesn't exist yet | **M7** |
| D-2 | `doj` ingests **1 row**; no `EnforcementCase` nodes are in the graph | Semantic retrieval and the Enforcement agent both need a real corpus | **M2** (load) / **M7** (refill) |
| D-3 | `synthetic_providers` has 186 rows; plan §5.5 specifies 50 scenario + 150 controls = 200 | Not blocking; verify the S01–S10 scenario coverage is intact | **M6** |
| D-4 | Amendment 3 geocoding is **not implemented** — no `data/reference/zcta_centroids.csv`, no `zip_centroid()`/`haversine_km()` in `entity_tools.py`. Only 2 of 8,603 providers have `latitude`, so `geographic_spread` never fires on real data | Out of M1's scope; `signal_tools` has a private `_haversine_km` but no centroid source | **M3** |
| D-5 | The Data Quality verdict is **not deterministic** — the same snapshot returned `warn` on one run and `fail` on the next, because tier T1 runs at `temperature=0.1` | A pipeline gate should not flip. Options: per-agent temperature override, or make the gate honour the deterministic `ValidationReport` verdict and treat the agent as advisory | **M6** |
| D-6 | No agent-level **escalation** yet. `router.should_escalate()` exists and is tested, but `run_agent` never calls it (`AgentRunResult.escalated` is always `False`) | Needs a second agent with a confidence field to escalate on | **M3** |
| D-7 | Phoenix container runs but nothing exports to it. `_base.py` sets OTel span attributes with no tracer provider registered, so they go nowhere | Tracing setup is its own milestone | **M8** |
| D-8 | `price_*` fields in `config/models.yaml` are all `null`, so `cost_usd` is always `NULL` | Deliberate — plan §7.4: "a wrong cost chart is worse than no cost chart". Operator must fill in real pricing | **M10** |

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

### M2 — Graph RAG completion · `TODO`

#### Action Plan

**Goal.** Finish pillar #1 (hybrid Graph RAG) and fill prompt block B2. Right
now `GraphRetriever.global_()` and `.semantic()` are stubs that log a warning
and return nothing, so `hybrid()` silently degrades to local-only — the
"global" half of GraphRAG does not exist. This milestone builds the embedding
layer, generates and persists community summaries, loads an `EnforcementCase`
corpus so semantic search has something to search, and wires all three into
B2 and into `retrieval.py`. Plan §6.4, §6.5, §7.1.

**Inherited context.**

- Embeddings are confirmed working: `text-embedding-3-large` via
  `openai/<deployment>` + `api_base`, returning **3072 dims** — which already
  matches the `case_embedding` and `community_embedding` vector indexes
  declared in `graph/schema.cypher`. Do not change the dimensions.
- 255 `Community` nodes and 3,469 `IN_COMMUNITY` edges already exist from
  `scripts/30_build_communities.py`. Leiden is seeded (`RANDOM_SEED`) and
  `community_id` is a hash of sorted member NPIs, so IDs are stable across
  runs — you can rely on that for idempotent writes.
- `CommunitySummary` already exists in `core/contracts.py` with
  `characterization`, `notable_members`, `risk_themes`, `generated_at`,
  `prompt_version` all optional. `graph_tools.get_community_context` already
  reads it back. **Note:** it is a plain `SpecterModel`, not an `AgentOutput` —
  if you use it directly as an agent `output_schema`, its optional fields
  carry defaults and Azure strict mode will 400. Define a separate
  strict-mode-safe schema for the LLM call and map it onto `CommunitySummary`
  for storage.
- `summarize_community` is already routed to `T1_workhorse` in
  `config/models.yaml`. Do not add a new `task_class`.
- **`EnforcementCase` count is 0 and the DOJ snapshot has exactly 1 row**
  (debt D-2). Build the loader properly anyway; it is correct with 1 row and
  will be correct with 400 after M7 refills the source. Say plainly in your
  checkpoint that semantic retrieval is exercised against a 1-row corpus.

**File manifest.**

| Path | Action | Notes |
|---|---|---|
| `src/specter/graph/embeddings.py` | CREATE | ~90 lines. Batch embed via litellm; write vectors to nodes. |
| `src/specter/graph/summaries.py` | CREATE | ~180 lines. Deterministic fact block → T1 call → `CommunitySummary` → persist + embed. |
| `src/specter/graph/loader.py` | EDIT | Add `load_enforcement_cases()` only. Leave everything else alone. |
| `src/specter/graph/retrieval.py` | EDIT | Implement `global_()` and `semantic()`; `hybrid()` gating. |
| `src/specter/llm/prompt_compiler.py` | EDIT | `_community_summaries_block` reads real summaries. |
| `src/specter/core/contracts.py` | EDIT | Add the strict-mode LLM schema for community summarization. |
| `scripts/30_build_communities.py` | EDIT | Add `--summaries` / `--embeddings` stages. |
| `tests/test_graph_retrieval.py` | EDIT | Add `global_`/`semantic` cases. |
| `tests/test_summaries.py` | CREATE | Determinism of the fact block; B2 stability. |

**Read before writing.**

- `src/specter/graph/retrieval.py` — all 107 lines, it is short.
- `src/specter/graph/communities.py` — all 115 lines; mirror its write style.
- `src/specter/graph/schema.cypher:81-90` — the two vector index definitions.
- `src/specter/llm/prompt_compiler.py:73-92` — `_community_summaries_block`.
- `src/specter/agents/_base.py:230-300` — how `run_agent` calls a model, if you
  reuse it for summarization.
- `src/specter/core/contracts.py:287-310` — `CommunitySummary`.
- `NOTES_API_DEVIATIONS.md` D1, D5 — the call form and the strict-mode ban on
  defaults.

**Steps.**

1. **`graph/embeddings.py`.** One function that batches text → vectors:

   ```python
   def embed_texts(texts: list[str], settings: Settings) -> list[list[float]]:
       """text-embedding-3-large, 3072 dims. Batches of 64."""
       response = litellm.embedding(
           model=f"openai/{settings.azure_embedding_deployment}",
           api_base=settings.azure_api_base,
           api_key=settings.azure_api_key.get_secret_value(),
           input=batch,
       )
   ```
   Preserve input order — `response.data` is indexed by `index`; sort on it
   rather than trusting arrival order. Assert `len(vector) == 3072` and raise
   on mismatch (hard rule 7); a wrong-width vector fails at index-write time
   with a confusing Neo4j error otherwise.

   Write with `db.create.setNodeVectorProperty(node, 'embedding', $vector)`.

2. **Deterministic community fact block** in `summaries.py`. One Cypher read
   per community producing: member count, distinct shared addresses, distinct
   shared officers, enumeration date range (min/max), excluded-member count,
   state spread. Emit as a **sorted** list of plain strings — this is
   `structural_facts`, and it is what the LLM is forbidden to alter. This
   function must be pure-deterministic and independently testable without an
   LLM.

3. **The LLM call.** `summarize_community` at T1, one call per community.
   Strict-mode-safe output schema (no defaults):

   ```python
   class CommunityCharacterization(AgentOutput):
       characterization: str      # <= 3 sentences
       notable_members: list[str] # NPIs — must exist in the graph
       risk_themes: list[str]
   ```
   Validate `notable_members` against the actual member NPI list and **drop
   or raise on** any NPI the model invented (hard rule 2). Do not trust it.

4. **Persist.** Write `characterization`, `risk_themes`, `notable_members`,
   `generated_at`, `prompt_version` onto the `Community` node, then embed
   `characterization + " " + " ".join(risk_themes)` into
   `community_embedding`.

5. **`load_enforcement_cases()` in `loader.py`.** Read
   `data/snapshot/doj/data.parquet` → `EnforcementCase` nodes carrying
   `case_id`, `title`, text, `legal_status`, `data_origin`, `source_id`. Then
   embed the case text into `case_embedding`. **Do not create edges to
   Providers** — matching a release to a provider is an entity-resolution
   judgement and belongs to the Enforcement agent (M3), not a loader. The
   existing module docstring already says this; keep it true.

6. **`retrieval.global_()` and `.semantic()`.** Embed the query, then:

   ```cypher
   CALL db.index.vector.queryNodes('community_embedding', $k, $vector)
   YIELD node, score
   ```
   Return `RetrievalResult(mode="global"|"semantic", ...)` with per-item
   `source_ids`. Keep the existing behaviour of degrading gracefully — but
   now degrade only when the *index is empty*, and log which. Do not keep the
   blanket "AZURE_API_KEY not configured" guard in `hybrid()`; the key is
   configured now, and that check would keep the global layer permanently off.

7. **B2.** `_community_summaries_block` reads persisted summaries and renders
   them **sorted by `community_id`**, via `json.dumps(..., sort_keys=True)`.
   *This is above the cache boundary* — it must contain no timestamp, no
   score, no iteration-order dependence. **Cap the number included** (suggest
   top 40 by member count, then sorted by id, with the cap in
   `config/screening.yaml`): all 255 would add roughly 20k tokens to every
   single call. State the cap in the block text so the model knows the list is
   partial.

8. Regenerate B0 if any tool signature changed:
   `python scripts/05_generate_prompt_blocks.py`.

**Checkpoint.**

```bash
docker compose up -d
python scripts/20_build_graph.py                 # if the graph needs rebuilding
python scripts/30_build_communities.py --summaries --embeddings
python -m pytest tests/ -q
ruff check src/ tests/ scripts/ && mypy src/
```

Expected, concretely:

- Neo4j: `MATCH (c:Community) WHERE c.embedding IS NOT NULL RETURN count(*)`
  → **255**.
- Neo4j: `MATCH (e:EnforcementCase) RETURN count(*)` → **≥ 1** (1 today; say
  so).
- `GraphRetriever.global_("shell provider address cluster", k=5)` returns
  **5** items with `mode="global"`, each with non-empty `source_ids`.
- `hybrid()` on a real NPI returns strictly more items than `local()` alone.
- `PromptCompiler.compile(...).prefix_fingerprint` is **stable across two
  compilations** and B2 now contains real summary text (the four invariant
  tests in `test_prompt_compiler.py` still pass).
- Whole suite green; ruff and mypy clean.

**Traps.**

- **Changing B2 changes the cached prefix, once.** Expect a one-time 0%
  cache hit run afterwards. That is correct and expected — do not "fix" it.
  What is *not* acceptable is a prefix that differs between two compilations
  in the same run; `test_prefix_is_deterministic` catches that.
- **255 T1 calls cost real money.** Add a `--limit` flag and develop against
  10 communities before running the full set. The L1 cache will absorb
  re-runs only if the fact block is byte-identical, which is exactly why
  step 2 must be deterministic.
- **`CommunitySummary` has defaulted optional fields** and will 400 under
  Azure strict mode if used directly as `output_schema`. Use a separate LLM
  schema (step 3). This is the single most likely way to lose an hour here.
- **Neo4j vector index writes need
  `db.create.setNodeVectorProperty`** — assigning `SET n.embedding = $v`
  directly stores a plain list that the index will not pick up.
- **`response.data` ordering.** litellm returns objects carrying an `index`;
  sort by it. Assuming arrival order silently mis-assigns every embedding,
  and nothing will fail loudly — retrieval just returns nonsense.
- The DOJ corpus is 1 row. `semantic()` returning 1 hit is correct, not a
  bug. Do not pad it, and do not weaken the test to hide it.

**Definition of done.**

- [ ] `graph/embeddings.py` and `graph/summaries.py` exist, ≤ 400 lines each
- [ ] 255 `Community` nodes carry a 3072-dim `embedding` and a
      `characterization`
- [ ] `EnforcementCase` nodes loaded and embedded; no Provider edges created
- [ ] `retrieval.global_()` and `.semantic()` return real, cited results
- [ ] `hybrid()` genuinely merges all three modes and deduplicates
- [ ] B2 contains real, sorted, capped summaries; all four prompt-compiler
      invariants still pass
- [ ] `pytest` / `ruff` / `mypy` all clean
- [ ] §3 Current State and §4 Carried Debt updated; M3 Action Plan written
- [ ] Committed as `M2: graph RAG completion`

---

### M3 — Investigation agents · `TODO`

**Scope.** `agents/entity_resolution.py` (T1 `adjudicate_entity_match`, with
the ≥0.90 / 0.65–0.90 / 0.45–0.65 / <0.45 thresholds from plan §9.3),
`agents/graph_investigation.py` (T1 `narrate_graph_signal`, the GraphRAG
consumer, with the no-fabricated-numbers check enforced in
`after_model_callback`), `agents/enforcement_intel.py` (T1
`extract_enforcement_case`, assigning `legal_status` and flagging
`requires_disambiguation` on common-name matches). Also clears debt **D-4**
(Amendment 3 ZCTA geocoding) and **D-6** (escalation).

#### Action Plan

*(not yet written — the M2 session writes this)*

---

### M4 — Grounded research · `TODO`

**Scope.** `agents/grounded_research.py` on Vertex Gemini with exactly one
tool (`google_search`), exposed to other agents in isolation; extract
`grounding_metadata` URIs into `EvidenceArtifact`s with
`extraction_method="vertex_grounding"`. **Blocked** until
`GOOGLE_CLOUD_PROJECT` is set. See `NOTES_API_DEVIATIONS.md` D10 — grounding
metadata is dropped by default and that would empty the citation trail.

#### Action Plan

*(not yet written)*

---

### M5 — Judgement agents · `TODO`

**Scope.** `agents/skeptic.py` (T2 `challenge_hypothesis`, bounded
`confidence_adjustment ∈ [-0.4, 0.0]`), `agents/case_reporter.py` (T2
`synthesize_case`), the `CasePacket` contract, and regex enforcement of the
banned-vocabulary list — enforced in code, not only in the prompt.

#### Action Plan

*(not yet written)*

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
