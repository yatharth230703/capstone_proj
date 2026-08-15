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

**Last updated: end of M2.**

### Verified green

```
pytest tests/ -q          141 passed
ruff check src/ tests/ scripts/   All checks passed
mypy src/                 Success: no issues in 40 source files
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
dimensions already declared in `graph/schema.cypher`. Embeddings use the
same `openai/<deployment>` + `api_base` call form as chat completions — see
`NOTES_API_DEVIATIONS.md` D11 for the one surprise (`response.data` items are
plain dicts keyed `embedding`/`index`, not attribute-access objects).

**Vertex is NOT configured** — `GOOGLE_CLOUD_PROJECT` is empty. M4 is blocked
on the operator supplying it.

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

Built and tested: `core/`, `ingest/` (4 connectors + synthetic), `graph/`
(schema, loader, enforcement_loader, communities, summaries, embeddings,
retrieval), `llm/` (router, prompt compiler, response cache, ledger),
`tools/` (graph, signal, entity, evidence, bindings), `agents/` (`_base.py`,
`data_quality.py`).

Still empty: `workflow/`, `judge/`, `obs/`. Missing entirely: `cli.py`,
`tools/mcp_tools.py`, `README.md`, `scripts/00_bootstrap.sh`,
`scripts/40_screen.py`, `scripts/50_judge.py`,
`agents/entity_resolution.py`, `agents/graph_investigation.py`,
`agents/enforcement_intel.py`, `data/reference/zcta_centroids.csv`.

### Known gap in `tools/graph_tools.get_community_context` — read before M3

It **recomputes structural facts fresh from Cypher every call and never
reads the `characterization`/`notable_members`/`risk_themes` M2 just wrote
onto every Community node** — the `CommunitySummary` it returns always has
`characterization=None`. This isn't a bug M2 introduced (the function
predates M2 and was correctly returning `None` because nothing existed to
read yet); it's now stale, because something to read exists. Not fixed here
— `graph_tools.py` isn't in M2's file manifest, and `tools/bindings.py`'s
`get_community_context` binding (the one `narrate_graph_signal` will
actually call) inherits the same gap. Tracked as debt D-9, due M3, because
M3's Graph Investigation agent is the first consumer that will notice.

---

## 4. CARRIED DEBT

| ID | Item | Why deferred | Due |
|---|---|---|---|
| D-1 | `state_medicaid_fl` and `state_medicaid_tx` ingest **0 rows** — both sources are bot-blocked | Needs the Playwright MCP fetch path, which doesn't exist yet | **M7** |
| D-2 | `doj` ingests **1 row**, loaded as 1 `EnforcementCase` node (M2) — the *loader* half is done, the *corpus size* half is still a gap | Semantic retrieval works against a 1-row corpus (`retrieval.semantic()` verified live), but 1 row is not a real corpus for the Enforcement agent to search | **M7** (refill via Playwright MCP) |
| D-3 | `synthetic_providers` has 186 rows; plan §5.5 specifies 50 scenario + 150 controls = 200 | Not blocking; verify the S01–S10 scenario coverage is intact | **M6** |
| D-4 | Amendment 3 geocoding is **not implemented** — no `data/reference/zcta_centroids.csv`, no `zip_centroid()`/`haversine_km()` in `entity_tools.py`. Only 2 of 8,603 providers have `latitude`, so `geographic_spread` never fires on real data | Out of M1's scope; `signal_tools` has a private `_haversine_km` but no centroid source | **M3** |
| D-5 | The Data Quality verdict is **not deterministic** — the same snapshot returned `warn` on one run and `fail` on the next, because tier T1 runs at `temperature=0.1` | A pipeline gate should not flip. Options: per-agent temperature override, or make the gate honour the deterministic `ValidationReport` verdict and treat the agent as advisory | **M6** |
| D-6 | No agent-level **escalation** yet. `router.should_escalate()` exists and is tested, but `run_agent` never calls it (`AgentRunResult.escalated` is always `False`) | Needs a second agent with a confidence field to escalate on | **M3** |
| D-7 | Phoenix container runs but nothing exports to it. `_base.py` sets OTel span attributes with no tracer provider registered, so they go nowhere | Tracing setup is its own milestone | **M8** |
| D-8 | `price_*` fields in `config/models.yaml` are all `null`, so `cost_usd` is always `NULL` | Deliberate — plan §7.4: "a wrong cost chart is worse than no cost chart". Operator must fill in real pricing | **M10** |
| D-9 | `tools/graph_tools.get_community_context` (and the `tools/bindings.py` binding over it) never reads the `characterization`/`notable_members`/`risk_themes` M2 wrote onto every Community node — it recomputes structural facts fresh and always returns `characterization=None` | Not in M2's file manifest; the fix is a one-query edit (read the persisted fields alongside the structural aggregate) but touches a file M2 didn't own | **M3** |
| D-10 | `EnforcementCase.legal_status` loaded by M2's `graph/enforcement_loader.py` comes from a **regex keyword heuristic** (`infer_legal_status`), not real adjudication — a loader has no business calling an LLM | Placeholder good enough to satisfy the schema without overclaiming (defaults to `alleged`, the weakest status, on no match); M3's `extract_enforcement_case` agent re-adjudicates from the full text and should overwrite it | **M3** |

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

**Goal.** Three working investigation agents that turn deterministic
graph/signal output into structured findings — the first agents in the
system that actually reason over evidence rather than just gate on it
(`data_quality`, M1) or summarize it (`community_summarizer`, M2). Also
lands ZIP-centroid geocoding (Amendment 3) so `geographic_spread` fires on
real data for the first time, and wires the escalation path `router.py`
already supports but `run_agent` has never called. Plan §9.3–9.5.

**Inherited context — read this before touching anything.**

- **Every tool these agents need already exists and is already bound.**
  `tools/bindings.build_tool_bindings(driver, thresholds, evidence_dir)`
  returns all 19 model-facing tools — `graph_tools.*`, `signal_tools.*`
  (via `signal_bindings.build_signal_bindings`), `entity_tools.*`
  (including `propose_entity_matches`), and `evidence_tools.validate_citations`.
  None of the three M3 agents should need a new binding *except* the two new
  geocoding functions (Step 1) and, if you take that route,
  `GraphRetriever.hybrid()` (see next bullet). Pass each agent the exact
  subset of `build_tool_bindings()`'s return list it needs — plan §9.4 gives
  Graph Investigation "all of `graph_tools`, all of `signal_tools`"; Entity
  Resolution needs `propose_entity_matches` + `name_similarity`; Enforcement
  Intelligence needs `search_enforcement_cases`. Filter by function identity
  or `__name__`, and regenerate B0
  (`python scripts/05_generate_prompt_blocks.py`) only if you add a genuinely
  new tool — filtering an existing agent's tool *list* doesn't change B0
  itself (B0 is generated from the full binding set, not per-agent).
- **`GraphRetriever` (M2) is not in `tools/bindings.py`.** Plan §9.4 wants
  Graph Investigation to call `retriever.hybrid()`. Nothing wraps
  `GraphRetriever` as a model-facing tool yet. Decide once, in this
  milestone: either add a `hybrid_search(npi, query, k)` binding (mirrors
  the existing bindings' style — closes over `driver`/`settings`, returns a
  plain dict) or give Graph Investigation a Python-side pre-fetch step that
  calls `hybrid()` before the agent runs and puts the result straight into
  the evidence bundle (same pattern as `data_quality.build_evidence`, no new
  tool at all). The second is less code and keeps hard rule 1 structurally
  true the same way `data_quality` does — it has a query, but not a *choice*
  of when to call it. Recommended.
- **`tools/graph_tools.get_community_context` doesn't read M2's persisted
  characterization** (debt D-9). If Graph Investigation calls this tool (or
  the `get_community_context` binding) expecting real narrative context, it
  gets `characterization: null` back — always, on every community, even
  though all 255 have one on the node. Fix `graph_tools.py:142-168` to also
  `RETURN cm.characterization, cm.notable_members, cm.risk_themes,
  cm.generated_at, cm.prompt_version` and populate `CommunitySummary`'s
  optional fields from them, falling back to the current always-fresh
  `structural_facts` computation either way (that part is still correct and
  still needed — characterization can be stale or absent, structural facts
  never are). This is now in scope for M3 since M3 is the first real
  consumer; do it as its own small step, don't let it hide inside a bigger
  diff.
- **`EnforcementCase.legal_status` in the graph today is a regex guess**
  (debt D-10, `graph/enforcement_loader.infer_legal_status`), not a real
  adjudication. `extract_enforcement_case`'s whole job is to replace that
  guess with the real thing for any case it actually matches to a provider —
  don't be surprised the seed value looks low-effort, that's intentional.
- **Escalation (`router.should_escalate`) takes a `pydantic.BaseModel`, not a
  dict**, and reads fields off it via `getattr` (`llm/router.py:187-198`,
  `_conditions_match`). `agents/_base.run_agent` currently only ever
  produces a `dict` (`_parse_output` calls `.model_dump(mode="json")`
  immediately) — there is no point in the current flow where a validated
  model instance survives long enough to call `should_escalate` against it.
  You will need to keep the parsed model instance around (not just its dump)
  through the point where you decide whether to escalate, then dump it after.
  This is the single most likely place to lose time in this milestone — see
  Steps 2 and Traps.
- Escalation rules already exist and don't need editing:
  `config/models.yaml`'s `escalation:` block routes
  `adjudicate_entity_match` with `match_probability` in `[0.45, 0.65]` to
  `T2_reasoning`, and any `schema_validation_failed: true` result
  (`task_class: null`, i.e. applies to all three new agents) to
  `T2_reasoning` as well, both with `max_retries: 1`.
- ZCTA centroid data does **not** exist in this repo yet and is not
  fetchable through any tool already wired up — you need outbound internet
  access (`WebFetch`/`curl`) to pull the Census Bureau's 2020 ZCTA Gazetteer
  file. It's a public-domain, no-key TSV
  (`https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2020_Gazetteer/2020_Gazetteer_zcta_national.zip`
  as of plan-writing time — Census URLs move, so verify before hardcoding
  anything into a script, and record whatever URL actually worked). Columns
  you need out of it: `GEOID` (→ `zip5`), `INTPTLAT`, `INTPTLONG` (→
  `lat`/`lon`); `state` is not in that file — Phase 1 doesn't strictly need
  it (CLAUDE.md's column list includes it, `entity_tools.py`'s callers don't
  currently use it) but keep it if a source column is cheaply available, and
  say plainly in this milestone's write-up if you drop it.

**File manifest.**

| Path | Action | Notes |
|---|---|---|
| `data/reference/zcta_centroids.csv` | CREATE | ~33k rows, `zip5,lat,lon,state`. Committed, not fetched at runtime. |
| `src/specter/tools/entity_tools.py` | EDIT | Add `zip_centroid()`, `haversine_km()`. Leave existing functions alone. |
| `src/specter/tools/signal_tools.py` | EDIT | Rewrite `geographic_spread` to use ZIP centroids instead of `p.latitude`/`p.longitude`. |
| `src/specter/tools/graph_tools.py` | EDIT | `get_community_context` reads persisted characterization (debt D-9). |
| `src/specter/agents/_base.py` | EDIT | `run_agent` calls `router.should_escalate` and retries once at the escalated tier. |
| `src/specter/agents/entity_resolution.py` | CREATE | T1 `adjudicate_entity_match`. |
| `src/specter/agents/graph_investigation.py` | CREATE | T1 `narrate_graph_signal`. |
| `src/specter/agents/enforcement_intel.py` | CREATE | T1 `extract_enforcement_case`. |
| `src/specter/core/contracts.py` | EDIT | `EntityMatchAdjudication`, `GraphFindings`, `EnforcementFindings` (all `AgentOutput`, no defaults). |
| `src/specter/tools/bindings.py` | EDIT | Only if you add `hybrid_search`; otherwise untouched. |
| `prompts/agents/entity_resolution.md` | CREATE | |
| `prompts/agents/graph_investigation.md` | CREATE | |
| `prompts/agents/enforcement_intel.md` | CREATE | |
| `tests/test_entity_tools.py` | EDIT or CREATE | `zip_centroid`/`haversine_km` unit tests — pure functions, no Neo4j needed. |
| `tests/test_signal_tools.py` | EDIT | `geographic_spread` test against real ZIP data instead of the near-empty `latitude`/`longitude` path. |
| `tests/test_agent_base.py` | EDIT | Escalation test: an agent output that trips a rule actually re-runs at the escalated tier with `escalated=True`. |
| `tests/test_entity_resolution.py`, `test_graph_investigation.py`, `test_enforcement_intel.py` | CREATE | Mirror `test_agent_base.py`'s offline style — you likely cannot afford a live-LLM test per agent per session; at minimum test evidence-building and output-schema validation offline. |

**Read before writing.**

- `src/specter/agents/data_quality.py` — the only existing agent; every new
  agent should look structurally like it (evidence builder function +
  `build_agent`/`run_agent` call), not reinvent the shape.
- `src/specter/agents/_base.py:236-395` (`run_agent`, `_parse_output`) — where
  escalation has to slot in.
- `src/specter/llm/router.py:143-198` — `resolve`, `should_escalate`,
  `_conditions_match`. Note `_conditions_match` returns `False` (not an
  error) if the result model lacks the condition's field — an escalation
  rule silently never fires if your output schema's field name doesn't match
  `config/models.yaml` exactly (`match_probability`).
- `src/specter/tools/entity_tools.py` — full file, 221 lines; `propose_entity_matches`
  and `MatchProposal` are what Entity Resolution adjudicates.
- `src/specter/tools/signal_tools.py:201-235` — current (unused-on-real-data)
  `_haversine_km`/`geographic_spread`, to replace.
- `src/specter/tools/bindings.py` — full file, to see the binding style and
  decide the `hybrid_search` question.
- `src/specter/core/contracts.py:212-225` (`RiskSignal`), `:317-332`
  (`MatchProposal`) — the deterministic inputs these agents narrate over.
- `phase_1_build_plan.md` §9.3, §9.4, §9.5 — the three agents' exact
  contracts and tool lists as originally specified (§9.5 mentions SAM.gov and
  Playwright MCP; both are out of scope here — SAM.gov per Amendment 1,
  Playwright per M7 — so Enforcement Intelligence in this milestone only gets
  `search_enforcement_cases`, no live web search yet).

**Steps.**

1. **ZCTA geocoding first — it's self-contained and has no LLM dependency,**
   so get it working and tested before touching agents. Fetch the Census
   Gazetteer file, extract `zip5,lat,lon,state` into
   `data/reference/zcta_centroids.csv`, commit it. In `entity_tools.py`:

   ```python
   def zip_centroid(zip5: str) -> tuple[float, float] | None:
       """ZCTA centroid lookup. None for unmatched ZIPs (PO-box-only and
       military ZIPs have no ZCTA) — that's a valid result, not an error."""

   def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
       """Great-circle distance. Pure function, no I/O."""
   ```
   Load the CSV once at module import or lazily-cached — not per call.
   Rewrite `signal_tools.geographic_spread` to pull `zip5` off each
   officer-linked provider's `Address` node (already in the graph, unlike
   `latitude`/`longitude`) via `zip_centroid`, and compute max pairwise
   `haversine_km` the same way the old code did with lat/lon. Every org
   whose ZIP doesn't resolve (`zip_centroid` returns `None`) drops out of the
   pairwise comparison, not out of the provider — if *any* org's ZIP is
   unmatched, still emit the signal (computed from the orgs that did
   resolve) with `confidence` reduced and
   `known_limitations: ["incomplete_geocoding"]`; never substitute a guessed
   coordinate (CLAUDE.md Amendment 3, verbatim). Every signal from this
   detector also carries `known_limitations: ["centroid_precision_only",
   "not_street_level"]` and a `geocoding_method: "zcta_centroid"` — check
   `RiskSignal`'s current fields in `contracts.py:212-225`; it may need a
   `known_limitations: list[str]` field added if it isn't there already
   (verify, don't assume — the M1/M2 sessions didn't need this field on
   `RiskSignal`, but Amendment 3 requires it here).

2. **Wire escalation in `agents/_base.py` before writing the three agents**,
   so each new agent gets it for free rather than three sessions each
   reinventing a retry loop. In `run_agent`, after `_parse_output` succeeds:
   parse into the model instance (don't immediately dump), call
   `runtime.router.should_escalate(task_class, parsed_model)`; if it returns
   a `TierConfig`, re-run the same evidence through a *second* `LlmAgent`
   built at that tier (reuse `build_agent` with the escalated `task_class`'s
   tier — check whether `build_agent` needs a tier override parameter, since
   today it derives the tier from `task_class` via `router.resolve`, not a
   direct tier argument), cap at one retry
   (`EscalationRule.max_retries`, already 1 everywhere in
   `config/models.yaml`), and return `AgentRunResult(escalated=True, ...)`
   with the escalated call's tokens/model. If the escalated call also fails
   schema validation, do not loop again — raise `AgentOutputError`, per hard
   rule 7.

3. **`agents/entity_resolution.py`.** Evidence: `propose_entity_matches`
   output for a given NPI + candidate list (candidates come from
   `find_shared_attribute_peers` — an entity can only be a match candidate if
   it already shares *something* with the target). Output schema
   (`AgentOutput`, no defaults):

   ```python
   class EntityMatchAdjudication(AgentOutput):
       npi: str
       candidate_npi: str
       matching_features: list[str]
       conflicting_features: list[str]
       match_probability: float          # 0.0-1.0
       decision: MatchDecision           # auto_link | agent_review | human_review | reject
   ```
   `MatchDecision` already exists in `core/enums.py`. Bias conservative per
   plan §9.3 — false merges are worse than missed matches; say so in the
   instruction brief, not just in code comments.

4. **`agents/graph_investigation.py`.** Evidence: whatever Step 1's
   `hybrid_search` decision produced, plus every `RiskSignal` the detectors
   fire for the NPI, plus (once Step 0's D-9 fix lands) real community
   context.

   ```python
   class GraphFindings(AgentOutput):
       signals: list[RiskSignal]         # echoed back, not re-derived
       community_context: str            # narration, not a number
       narration: str
       linked_entities: list[str]        # NPIs/officer_ids/etc. mentioned
   ```
   `after_model_callback` (plan §9.4, hard rule 1): extract every numeric
   literal from `narration`/`community_context` via regex, assert each
   appears in a tool result already gathered for this call. On violation,
   quote it back and retry once; a second violation raises (mirrors the
   judge's own numeric-grounding check design in `CLAUDE.md` Amendment 2 —
   consistent, not coincidental).

5. **`agents/enforcement_intel.py`.** Evidence: `search_enforcement_cases`
   hits for a query built from the provider's name/state/taxonomy.

   ```python
   class EnforcementFindings(AgentOutput):
       matches: list[str]                # case_ids, must exist in the graph
       typologies: list[str]
       legal_status_per_match: dict[str, LegalStatus]
       disambiguation_flags: list[str]   # case_ids needing human review
   ```
   Any match built on a common-name hit (no NPI, no exact identifier overlap
   — same "no auto-link without an exact identifier" rule as CLAUDE.md
   Amendment 1's state-exclusion matching) goes in
   `disambiguation_flags`, never silently into `matches` as settled.

6. Regenerate B0 only if you added `hybrid_search`:
   `python scripts/05_generate_prompt_blocks.py`.

**Checkpoint.**

```bash
docker compose up -d
python -m pytest tests/ -q
ruff check src/ tests/ scripts/ && mypy src/
python3 -c "from specter.tools.entity_tools import zip_centroid; print(zip_centroid('33132'))"
```
Expected: pytest green including the new offline agent tests; the ZIP lookup
prints a real `(lat, lon)` tuple. Then, against a real NPI known to have
shared-officer peers with non-null ZIPs, run each agent once live and paste
its output — `match_probability`/`decision` for entity_resolution,
`narration` with zero numbers absent from its tool calls for
graph_investigation, `legal_status_per_match` using the real enum for
enforcement_intel. Confirm `AgentRunResult.escalated` is `True` at least once
by deliberately constructing a case that trips the `match_probability` rule
(handed a pair with 0.45–0.65 features).

**Traps.**

- **`should_escalate` needs a `BaseModel`, current `run_agent` only ever
  keeps a `dict`.** This is not a small edit — trace the type all the way
  from `_parse_output` through to the return statement before writing code.
- **`_conditions_match` fails silently (returns `False`) on a field-name
  typo**, not an error. If your escalation test never escalates, check the
  field name in `config/models.yaml` against your output schema field name
  character-for-character before suspecting the router logic.
- **Census ZCTA files are large and the exact current URL is not verified
  yet** — budget time for it to have moved. Verify what you actually
  downloaded before committing 33k rows of possibly-wrong data; spot-check a
  few known ZIPs (e.g. Miami 33132, LA 90001) against known coordinates.
- **`get_community_context`'s fix is easy to scope-creep.** It's one query
  edit (read four more properties, map them onto already-optional
  `CommunitySummary` fields) — resist rewriting the function's structural
  facts logic while you're in there; that part isn't broken.
- **Playwright MCP and grounded research don't exist yet** (M7, M4). Don't
  reach for them even though plan §9.5/§9.6 mention them — Enforcement
  Intelligence in this milestone is `search_enforcement_cases` only, against
  a 1-row corpus (debt D-2). Say so plainly in the checkpoint, same as M2
  did for `semantic()`.

**Definition of done.**

- [ ] `zip_centroid()`/`haversine_km()` exist, tested, and `geographic_spread`
      uses them instead of the near-always-null lat/lon fields
- [ ] `run_agent` calls `router.should_escalate` and a real escalation
      (agent output → re-run at higher tier → `escalated=True`) is
      demonstrated live, not just asserted in a mock
- [ ] Three new agents exist, each with a strict-mode-safe `AgentOutput`
      schema, each following `data_quality.py`'s evidence-builder pattern
- [ ] `get_community_context` returns real characterization when one exists
      (debt D-9 cleared)
- [ ] `graph_investigation`'s `after_model_callback` rejects a fabricated
      number at least once in a test
- [ ] `pytest` / `ruff` / `mypy` all clean
- [ ] §3 Current State and §4 Carried Debt updated; M4 Action Plan written
      (note M4 is blocked on `GOOGLE_CLOUD_PROJECT` regardless)
- [ ] Committed as `M3: investigation agents`

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
