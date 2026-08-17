# API deviations

Required by `CLAUDE.md` §"Before you write agent code": where the real API
differs from `phase_1_build_plan.md` or from a library's own docs, the
contract is kept, the call is adapted, and the deviation is recorded here.

Each entry: what the plan/docs said, what is actually true, what we did.

---

## D1 — Azure resource exposes the **v1 API surface**, so LiteLLM's `azure/` provider does not work

**Found:** M1, 2026-08-16. **Affects:** `llm/router.py`, `config/models.yaml`.

The plan (§4) assumes a classic Azure OpenAI resource and a
`azure/<deployment>` LiteLLM model string. This operator's `AZURE_API_BASE`
ends in `/openai/v1` — the newer Azure OpenAI **v1** surface, which is
OpenAI-compatible and does *not* use the
`/openai/deployments/<dep>/chat/completions?api-version=...` path.

LiteLLM's `azure/` provider appends that legacy path itself, producing a
doubled URL and a `404 Resource not found` that looks exactly like a wrong
deployment name. Symptom to recognise: **404, not 401** — the key is fine.

What works, verified against all three tiers plus embeddings:

```python
litellm.completion(
    model=f"openai/{deployment}",     # NOT azure/
    api_base=settings.azure_api_base, # ".../openai/v1"
    api_key=settings.azure_api_key.get_secret_value(),
    messages=[...],
)
```

`_resolve_model` in `llm/router.py` therefore emits `openai/<deployment>`, and
`ModelRouter._transport` supplies `api_base`/`api_key`. `config/models.yaml`
still declares `provider: azure` — the resource *is* Azure; only the wire
protocol is OpenAI-shaped.

Useful diagnostic: `GET {api_base}/models?api-version=v1` lists the model
catalog. Note `api-version=v1` literally — dated versions all return
`400 API version not supported` on this surface.

---

## D2 — Prompt caching needs a bigger prefix than the plan assumes

**Found:** M1. **Affects:** `tests/test_prompt_compiler.py`.

Plan §7.1 invariant 3 asserts `prefix_token_estimate >= 1200`, on the basis
that "Azure needs ~1024+". Measured on this deployment (`gpt-5.4-mini`,
identical prefix sent repeatedly):

| Real prefix tokens | `cached_tokens` on repeat call |
|---|---|
| 1,276 | **0** |
| 1,550 | 1,280 |
| 2,060 | 1,792 |
| 2,570 | 2,304 |
| 3,076 | 2,816 |

So the documented 1,024 floor is not sufficient in practice; the observed
cliff sits between 1,276 and 1,550 real tokens. The invariant was raised to
`MIN_PREFIX_TOKEN_ESTIMATE = 1800` (estimated), which is ~1,690 real tokens.

Also calibrated: the compiler's chars/4 estimator runs ~6% high versus a real
tokenizer (estimate 2,680 → real 2,512). Good enough for a threshold check;
do not use it for billing.

---

## D3 — ADK 2.6.2 has a built-in cache-boundary primitive: `static_instruction`

**Found:** M1. **Affects:** `agents/_base.py`.

The plan describes hand-assembling B0–B5 into `system` and `user` strings.
ADK 2.6.2 models this directly, and using it is both less code and more
reliable:

- `LlmAgent.static_instruction` → placed verbatim into
  `llm_request.config.system_instruction`, which `lite_llm.py:2367` inserts
  as message 0. **This is the cached prefix.**
- `LlmAgent.instruction` → when `static_instruction` is also set,
  `flows/llm_flows/instructions.py:107-119` demotes it out of the system
  prompt into `contents` as a `user` turn. **This is below the boundary.**
- `Runner.run_async(new_message=...)` → a further `user` turn, after that.

Verified message layout: `system=[B0..B3]`, `contents=[user(agent brief),
user(evidence bundle)]`.

Two traps that follow:

- `config.system_instruction` is a **`str`**, not `types.Content`. Appending
  a non-str logs a warning and silently drops it (`llm_request.py:252`). The
  vendored docs example showing `types.Content` is stale.
- `global_instruction` is deprecated *and* is prepended **above**
  `static_instruction` (`instructions.py:83-97`), which would corrupt the
  cached prefix. Never set it.

---

## D4 — `tools` + `output_schema` together is legal in 2.6.2, but only with a `LiteLlm` **object**

**Found:** M1. **Affects:** `agents/_base.py`.

ADK 1.x forbade combining `tools` with `output_schema`. In 2.6.2 there is no
such validator, and the docstring endorses the combination
(`llm_agent.py:391`).

The catch is in `utils/output_schema_utils.py:31-52`:
`can_use_output_schema_with_tools` returns `True` for any `LiteLlm`
*instance*, but `False` for a bare model *string*. On `False`, ADK silently
falls back to a prompt-based workaround that injects an extra system
instruction and a synthetic tool — which would perturb the cached prefix and
quietly destroy the caching pillar.

**Therefore: always pass `router.model_for(...)` (a `LiteLlm` object) as
`model=`, never a string.** `build_agent` does this and there is no code path
that passes a string.

Related: `LlmAgent.DEFAULT_MODEL` is `'gemini-3.5-flash'` — an unset `model`
fails *open* to Gemini rather than raising. Always set it explicitly.

---

## D5 — Azure structured output runs in **strict** mode: no defaults allowed

**Found:** M1. **Affects:** `core/contracts.py`, every future agent schema.

`lite_llm.py:2321` builds `response_format` with `"strict": True`. OpenAI
strict mode rejects any property carrying a `default` and requires every
property to be listed in `required`.

Consequence: **agent `output_schema` models must not give fields defaults.**
An optional field must be typed `X | None` and filled explicitly. This is a
400 at run time, not a validation error at build time, so it is guarded by
`tests/test_agent_base.py::test_agent_output_schemas_carry_no_defaults` —
extend that test's coverage as each new agent schema is added.

`SpecterModel`'s `extra="forbid"` already supplies the
`additionalProperties: false` strict mode also requires.

---

## D6 — ADK callbacks are invoked **by keyword**, but typed positionally

**Found:** M1. **Affects:** `agents/_base.py`.

`base_llm_flow.py:243` calls
`callback(callback_context=..., llm_request=...)`, so the parameter *names*
are load-bearing and must be exactly `callback_context` / `llm_request` /
`llm_response`. But ADK's own type alias declares them positionally, so
making them keyword-only (`*,`) fails `mypy`.

Resolution: declare them as plain positional-or-keyword parameters with the
exact required names. Do not rename them, and do not add `*`.

Also: every callback field accepts a single callable *or* a list, run in
order until one returns non-`None`. A truthy return from
`before_model_callback` replaces the model call entirely; from
`after_model_callback` it replaces the response.

---

## D7 — `cached_content_token_count` is `0`, never `None`, when unreported

**Found:** M1. **Affects:** `agents/_base.py`, `llm/ledger.py`, M8 dashboard.

`_extract_cached_prompt_tokens` (`lite_llm.py:804-854`) reads
`usage.prompt_tokens_details.cached_tokens` and **returns `0` when absent**.
So a recorded zero is ambiguous between "genuine cache miss" and "provider
reported nothing". Do not present a 0% hit rate as proof caching is broken
without first confirming the provider populates the field at all — on this
deployment it does.

---

## D8 — ADK's `llms-full.txt` moved

**Found:** M1. **Affects:** the bootstrap command in `CLAUDE.md`.

`CLAUDE.md` says to fetch
`https://raw.githubusercontent.com/google/adk-docs/main/llms-full.txt`. That
URL now returns an 11-line stub pointing elsewhere. The live document is:

```bash
curl -sL https://adk.dev/llms-full.txt -o .context/adk-llms-full.txt
```

~73,800 lines / 3.3 MB. Installed version confirmed: `google-adk 2.6.2`.

---

## D9 — `SequentialAgent` / `ParallelAgent` / `LoopAgent` are deprecated in favour of `Workflow`

**Found:** M1 (research only — nothing built on it yet). **Affects:** M6.

Plan §10 calls for "the ADK 2.x `Workflow` graph runtime, not nested
`sub_agents`". That is correct and now actively enforced: all three legacy
orchestration agents carry `@deprecated` decorators naming `Workflow` as the
replacement (`sequential_agent.py:49`, `loop_agent.py:53`,
`parallel_agent.py:171`).

One documented limitation, repeated in each deprecation message: **"Workflow
cannot yet be used as an LlmAgent sub-agent."** M6 must therefore make the
`Workflow` the root, with the Orchestrator as a node inside it — not an
`LlmAgent` root with a `Workflow` underneath.

Two `Workflow` behaviours worth knowing before M6:

- Edges are **schema-validated at construction time** when node schemas are
  inferable — contract mismatches fail at import rather than mid-run.
- An unmatched conditional route ends that branch with only a
  `logging.warning` (`_graph.py:174`). Against CLAUDE.md hard rule 7 that is a
  silent-failure path: make every routing map exhaustive with an explicit
  `DEFAULT_ROUTE`.

---

## D10 — `AgentTool` drops grounding metadata by default

**Found:** M1 (research only). **Affects:** M4.

**M4 update:** the source-level claim is confirmed against the installed
2.6.2 — `tool_context.state['temp:_adk_grounding_metadata']` is set at
`agent_tool.py:325`, gated on `self.propagate_grounding_metadata`, exactly
as described below. **Not yet exercised live**, though: M4's own checkpoint
(`agents/grounded_research.research_topic`) calls the isolated agent
directly via its own `Runner`, reading `event.grounding_metadata` straight
off the event stream — that path works, confirmed live, 7/7 real citations.
Nothing in M4 actually built a *consumer* agent that calls
`build_grounded_research_tool()`'s `AgentTool` and reads
`temp:_adk_grounding_metadata` back out of its own `tool_context.state`;
that only happens once M5/M9 wires a real consumer. Re-verify the
propagation path live at that point rather than assuming the source read
here is enough.

`AgentTool.run_async` discards the child agent's `grounding_metadata` unless
constructed with `propagate_grounding_metadata=True`, which stashes it at
`tool_context.state['temp:_adk_grounding_metadata']`
(`agent_tool.py:296-299`).

Since the grounding URIs *are* the citation trail for pillar #4, M4 must set
that flag and read the metadata back out, or the `EvidenceArtifact`s with
`extraction_method="vertex_grounding"` will be empty.

Note also that `GoogleSearchTool.bypass_multi_tools_limit` does exist in
2.6.2, but it is not an API bypass: ADK implements it by silently swapping in
an auto-generated single-tool search sub-agent with its own canned
instruction, which cannot be audited against our evidence policy. Prefer the
explicit isolation pattern `CLAUDE.md` already mandates.

---

## D11 — `litellm.embedding()`'s `response.data` items are plain dicts, not attribute-access objects

**Found:** M2. **Affects:** `graph/embeddings.py`.

Verified live against `text-embedding-3-large` on this deployment (same
`openai/<deployment>` + `api_base` v1-surface form as D1): each item in
`response.data` is a `dict` keyed `embedding`/`index`/`object` —
`item["index"]`, not `item.index`. `EmbeddingResponse` elsewhere in the
LiteLLM codebase suggests attribute access should work; on this deployment it
does not. Sort by `item["index"]` before trusting order — arrival order is
not guaranteed, and a wrong-order batch silently mis-assigns every vector.

Confirmed 3072 dims, matching `graph/schema.cypher`'s vector index
declarations — no `dimensions` override needed.

---

## D12 — Neo4j 5.26's `db.create.setNodeVectorProperty` works fine inside `UNWIND`

**Found:** M2 (research only, not a deviation — recorded because the plan
doesn't spell out the call form). **Affects:** `graph/summaries.py`,
`graph/enforcement_loader.py`.

This void procedure can be called per-row directly inside an `UNWIND`,
without the `CALL { ... }` subquery syntax some Neo4j versions require for
per-row procedure calls:

```cypher
UNWIND $rows AS row
MATCH (n:SomeLabel {id: row.id})
CALL db.create.setNodeVectorProperty(n, 'embedding', row.vector)
```

Verified live. `SET n.embedding = $vector` also stores the list but the
vector index never picks it up — use the procedure, not a plain `SET`.

---

## D13 — Azure strict-mode structured output cannot represent `dict[str, X]`

**Found:** M3, live. **Affects:** `core/contracts.py`, every future agent
schema.

`EnforcementFindings.legal_status_per_match` was originally typed
`dict[str, LegalStatus]` (plan §9.5's natural reading: "adjudicate
legal_status per match"). Pydantic renders an open-ended `dict[str, X]` as
`{"type": "object", "additionalProperties": {...}}` with no fixed
`properties`/`required` — strict mode rejects this outright:

```
litellm.BadRequestError: Invalid schema for response_format
'EnforcementFindings': In context=(), 'required' is required to be supplied
and to be an array including every key in properties. Extra required key
'legal_status_per_match' supplied.
```

Resolution: any per-key mapping in an agent `output_schema` must be a
`list[SomeModel]` of explicit `(key, value)` pairs instead of a bare `dict`.
`legal_status_per_match: list[CaseLegalStatus]` where `CaseLegalStatus` has
`case_id: str` and `legal_status: LegalStatus` fields. This is D5's
"no defaults" constraint's sibling — both are strict-mode shape limits that
only surface as a 400 at run time, not at schema-build time. Watch for this
whenever a future agent schema's natural shape is "one value per key."

---

## D14 — ADK's native `Gemini` model reads Vertex config from `os.environ`, not from `Settings`

**Found:** M4, live. **Affects:** `agents/grounded_research.py`, any future
agent that uses a bare `Gemini`/`Vertex` model string instead of `LiteLlm`.

`Settings` (pydantic-settings) reads `.env` into a typed Python object; it
never calls `os.environ[...] = ...`. Every Azure agent doesn't care, because
`ModelRouter._transport()` passes `api_base`/`api_key` explicitly into the
`LiteLlm` constructor. But `google_search` only works with ADK's *native*
`Gemini` model class (D10's "single tool per agent" note), which `LlmAgent`
resolves automatically from a bare `"gemini-*"` model string via
`LLMRegistry`. That native class's `api_client` property builds a
`google.genai.Client()` that reads `GOOGLE_GENAI_USE_VERTEXAI`,
`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and
`GOOGLE_APPLICATION_CREDENTIALS` straight out of `os.environ`
(`google_llm.py:337-362`).

Confirmed live: with `.env` populated but `os.environ` untouched,
`env | grep GOOGLE` in the running shell returns nothing — the client would
silently fall back to whatever `google-genai` defaults to (AI Studio /
unauthenticated) rather than raising. `agents.grounded_research
._ensure_vertex_env()` forwards the four settings into `os.environ` with
`setdefault` (never clobbers a value an operator's shell already set) before
constructing the agent, and raises `ValueError` up front if
`GOOGLE_CLOUD_PROJECT` is unset — hard rule 7, fail loudly, don't let a
misconfigured client silently pick the wrong backend.

`Gemini` also exposes a `client_kwargs: dict` field that merges straight
into the `Client(**kwargs)` call — passing `vertexai=True, project=...,
location=...` there would avoid the global `os.environ` mutation entirely,
but `credentials` still needs Application Default Credentials to find the
service-account file, which in practice means `GOOGLE_APPLICATION_
CREDENTIALS` has to be a real env var anyway. Not worth the extra
indirection for a single field; `setdefault`-based forwarding is simpler and
matches the plan's own framing ("Vertex, via GOOGLE_GENAI_USE_VERTEXAI").

---

## D15 — Google Search grounding URIs are Google redirect links, not the source page URL

**Found:** M4, live. **Affects:** `agents/grounded_research.py`, any human
or downstream process reading a `vertex_grounding` `EvidenceArtifact`.

`grounding_chunks[i].web.uri` on this deployment (`gemini-3.7-flash`,
Vertex) is not the cited page's real URL — it's a
`vertexaisearch.cloud.google.com/grounding-api-redirect/...` tracking link
that resolves to the real source only when actually followed (and per
ADK's own docs, these are meant to be displayed as Search suggestion UI in
a production app, not treated as a stable citation target). `web.title` is
often just the bare domain (e.g. `"hhs.gov"`), not a page title.

This doesn't break `check_citation_validity` (M9) — that check only
confirms a `source_ids` entry resolves to a stored `EvidenceArtifact`, and
it does, regardless of what's inside it. It matters for anyone (human
reviewer, `CaseReporter`) who expects the stored artifact content to be a
directly-followable source URL. Recorded rather than "fixed", since there
is no direct-URL field available in `GroundingChunkWeb` to substitute —
`domain` is the closest thing to a stable, human-readable label.

---

## D16 — `google.adk.workflow.Workflow`: real construction/runtime API (extends D9)

**Found:** M6, both by reading `google/adk/workflow/` source in full and by
running a throwaway two-node experiment before writing the real graph.
**Affects:** `workflow/screening.py`.

D9 (M1, research-only) already established that `Workflow` must be the root
and that an unmatched conditional route is a silent `logging.warning`. This
entry is what M6 actually needed on top of that, confirmed against 2.6.2:

- **`Workflow(...)` requires an explicit `name=` kwarg** (Pydantic-required),
  in addition to `edges=`. Nodes are inferred automatically from the edge
  list at construction time (`Graph.model_post_init` calls
  `validate_graph()`) — do not pass `nodes=` explicitly.
- **Chain-tuple DSL**: `edges` is a list of `Edge` objects or tuples —
  `(a, b, c)` becomes `a→b, b→c`; a `dict` element is a routing map
  (`{route_value: node, DEFAULT_ROUTE: node}`); a bare async function is
  auto-wrapped into a `FunctionNode` the first time it's seen, **deduped by
  `id()` across the whole edge list** — reusing the same Python function
  object in multiple tuples correctly refers to one graph node, not a
  duplicate.
- **Node signature**: `async def f(ctx: Context, node_input: T) -> R`.
  `node_input` is special-cased to always receive the upstream node's raw
  return value directly, in-process — every *other* parameter is looked up
  in `ctx.state` (session state) instead. Infra objects (a `neo4j.Driver`,
  `AgentRuntime`, thresholds, `evidence_dir`) should be bound via closure at
  graph-construction time, not threaded through state.
- **Fan-out is native**: `@node(parallel_worker=True, max_parallel_workers=N)`
  wraps a node in `_ParallelWorker`; if it receives a list as `node_input`
  it runs the wrapped function once per item, capped at `N` truly
  in-flight (`asyncio.wait(..., return_when=FIRST_COMPLETED)`, refilling as
  slots free — not batch-of-N-then-wait), returning results in input order.
  **This cap is per-node, not graph-wide** — multiple fan-out nodes off the
  same upstream output run *concurrently* with each other, each independently
  capped at `N`, so N separate 4-way fan-outs can produce up to 4×N
  simultaneous calls system-wide. Fan-out is also **fail-fast**: the first
  raised exception cancels every other in-flight item in that batch.
- **`JoinNode(name=...)` waits for *every* node listed as its predecessor in
  the edge list to reach `COMPLETED`**, even one that's structurally
  unreachable in the branch actually taken (e.g. the untaken side of a
  conditional route). Confirmed by direct experiment: such a `JoinNode`
  never fires — no error, no timeout — the run just ends without its
  output. Never declare a `JoinNode`'s predecessors across mutually
  exclusive conditional branches. On success, its output is
  `{predecessor_node_name: predecessor_output, ...}`, a dict keyed by name.
- **`DEFAULT_ROUTE` confirmed verbatim** (`_graph.py:172-183`): a route
  value that matches nothing, with no `DEFAULT_ROUTE` edge present, hits
  `logger.warning(...)` and the branch simply ends. Every routing dict
  needs a `DEFAULT_ROUTE` key, full stop.
- **Running it**: `Runner(node=workflow, app_name=..., session_service=...)`
  — **not** `Runner(agent=workflow, ...)`. `Workflow` is a `BaseNode`, not a
  `BaseAgent`; `Runner.__init__` has a separate `node=` parameter exactly
  for this (`Runner._resolve_app`, `runners.py:326-331`). `agent=` would
  type-check under `Optional[BaseAgent]`'s duck typing but silently
  misroutes. `run_async(...)` yields the same `AsyncGenerator[Event, None]`
  as any agent run; the terminal node's output lands on the last event with
  a non-`None` `.output`.

---

## D17 — L1 response cache stores a response before validating it

**Found:** M6, live. **Affects:** `agents/_llm_call.py` (`_invoke`),
`llm/response_cache.py`. Not fixed — outside M6's file list; tracked as
BUILD_MILESTONES.md carried debt D-18.

`_invoke` (`_llm_call.py:162-172`) calls `runtime.cache.set(cache_key,
LlmResult(content=final_text, ...))` on every live call, unconditionally —
`_validate_output(...)` (which parses `final_text` as JSON and validates it
against the agent's `output_schema`) doesn't run until *after* the cache
write, at line 201. A transient truncated/malformed response from the
underlying model therefore gets written to Redis as a "successful" L1 entry
before anyone checks it's well-formed. Every subsequent call sharing that
exact cache key (same agent, same prompt content, same prefix fingerprint —
not scoped by `run_id`, by design, so L1 hits work *across* runs) replays
the identical broken text and raises the identical `AgentOutputError`
forever, with no self-healing path.

Hit live: `graph_investigation` on a real NPPES provider raised
`AgentOutputError: response was not valid JSON: Unterminated string
starting at: line 1 column 6102` — then reproduced *byte-for-byte
identically* (same message, same character offset) across 3 separate
`python scripts/40_screen.py` invocations, which is what exposed it as a
caching bug rather than genuine model flakiness (a real retry, e.g. via
`redis-cli -p 6380 -n 0 flushdb` between attempts, succeeded immediately
with no code change).

Recommended fix, for whoever picks up D-18: call `_validate_output` before
`runtime.cache.set`, or wrap the cache write in a check that skips it on a
validation failure. Do not cache on the parsed/validated side only as a
workaround without also handling the retry path in `run_agent`'s escalation
logic, which currently assumes `_invoke`'s two return paths (cache hit / live
call) are otherwise symmetric.

---

## D18 — `google-adk`'s MCP support is an optional extra, not installed by default

**Found:** M7, Step 0. **Affects:** `pyproject.toml`.

`from google.adk.tools.mcp_tool.mcp_toolset import McpToolset` raised
`ModuleNotFoundError: No module named 'mcp'` on a clean checkout, even
though `google-adk==2.6.2` was already installed and every other ADK import
worked. `importlib.metadata.distribution("google-adk").metadata.get_all(
"Provides-Extra")` lists `mcp` among a dozen optional extras (`a2a`, `gcp`,
`slack`, ...); the base install pulls none of them. Fix: `pyproject.toml`
now pins `"google-adk[mcp]==2.6.2"` (was `"google-adk==2.6.2"`), which
resolves `mcp>=1.24,<2` — landed as `mcp==1.29.0` via `uv sync`. `pip`/
`python -m pip` are still not on PATH in this venv (M7's own Action Plan
already flagged this) — `uv add`/`uv sync` is the only working install path.

---

## D19 — Neo4j Community Edition has no RBAC; read-only enforcement moves to session access mode

**Found:** M7, live. **Affects:** `tools/mcp_tools.py`
(`run_guarded_cypher`), `scripts/06_bootstrap_neo4j_readonly.py`. Narrows
CLAUDE.md's "Neo4j MCP guardrails" §1 ("connect as the read-only role").

`docker-compose.yml`'s Neo4j image is `neo4j:5.26.29-community`. Verified
live: `SHOW ROLES` and `GRANT ROLE reader TO specter_ro` both raise
`Neo.ClientError.Statement.UnsupportedAdministrationCommand` — role-based
access control (`CREATE ROLE`, `GRANT`/`DENY` privileges) is an Enterprise
Edition feature, not present in Community at all. `CREATE USER` **is**
CE-supported and was used to create `specter_ro`
(`scripts/06_bootstrap_neo4j_readonly.py`, idempotent via `IF NOT EXISTS`).

The substitute for the missing role, and it's a real one, not merely
app-level discipline: every guarded query opens its session with
`driver.session(default_access_mode="READ")`. This **is** enforced by the
server itself, independent of RBAC — verified live, a `CREATE` sent through
such a session raises `Neo.ClientError.Statement.AccessMode: Writing in
read access mode not allowed`. It is weaker than a true Enterprise
read-only role (a procedure not correctly mode-tagged could in principle
still write through it), which is exactly why the regex reject
(`reject_unsafe_cypher`) stays as an independent second layer rather than
being treated as redundant belt-and-suspenders. If this project ever moves
to Neo4j Enterprise, replace `default_access_mode="READ"` with a real
`GRANT MATCH {*} ON GRAPH * TO specter_ro` role and keep the regex layer
regardless — CLAUDE.md's "all four are mandatory" wording doesn't carve out
an exception for the case where one guardrail happens to be strong enough
to make another redundant.

---

## D20 — `Session.run(**kwargs)` treats unrecognized kwargs as Cypher parameters, not transaction config

**Found:** M7, live. **Affects:** `tools/mcp_tools.py` (`run_guarded_cypher`).

`inspect.signature(Session.run)` is `(self, query, parameters=None,
**kwargs)`; the docstring says outright: "kwargs: additional keyword
parameters... take precedence over parameters passed as `parameters`." A
first attempt at the guardrails' 10s timeout used `session.run(query,
timeout=10)` — this does **not** raise, does **not** warn, and does
**not** time anything out. Confirmed live: a query given `timeout=2` via
this form ran to completion in 1.4s past a synthetic 8000×8000-row
cartesian-product workload with no error, because `timeout` was silently
treated as an unused Cypher parameter (the query didn't reference `$timeout`,
so it was simply ignored).

The real mechanism is `neo4j.Query(text, timeout=<seconds>)` passed as the
query object itself (`session.run(Query(sql, timeout=10.0))`) — confirmed
live to raise `Neo.ClientError.Transaction.
TransactionTimedOutClientConfiguration` on an equivalent slow workload.
`run_guarded_cypher` uses this form. Any future direct `session.run(...,
timeout=...)` call anywhere else in this codebase is very likely the same
silent no-op bug, not a working timeout — grep for it before trusting it.

---

## D21 — FL/TX state Medicaid sources are WAF-blocked even to a real browser (Playwright MCP does not unblock them)

**Found:** M7, live. **Affects:** `ingest/state_medicaid.py`. Narrowed
CLAUDE.md Amendment 1 / BUILD_MILESTONES.md debt D-1.

> **UPDATE 2026-08-17 — FL is cleared; TX is not.** FL now ingests 246 real
> ineligible providers from a different host (`portal.flmmis.com`). See
> **D21a** below, which also **corrects a wrong diagnosis in this entry**: the
> FLMMIS CSV is not malformed. Everything below about the *WAF blocks* stands
> and is still why `ahca.myflorida.com` is unusable.

The M7 build plan's own prescribed fix for a source blocked to a plain HTTP
client is "needs Playwright MCP." Tried live against both FL and TX with a
real headless Chromium (`@playwright/mcp`, `tools/mcp_tools.fetch_rendered`)
and neither got through:

- **FL** (`ahca.myflorida.com`): Cloudflare's block page (title "Attention
  Required! | Cloudflare", body "Sorry, you have been blocked") — an
  explicit security decision, confirmed after a 6s `browser_wait_for` (rules
  out an unsolved JS challenge) and confirmed on a second distinct path
  under the same host, not just the originally-diagnosed landing page —
  i.e. a zone-wide block, not a page-specific one.
- **TX** (`oig.hhs.texas.gov`): Akamai's block page (title "Access Denied",
  body referencing `errors.edgesuite.net`) — same category of explicit WAF
  decision. The older `oig.hhsc.state.tx.us` domain resolves via DNS
  (`168.58.214.7`) but the TCP connection itself times out — not reachable
  at the network layer at all, which no client-side technique (browser or
  otherwise) can fix.

Both are IP-reputation/WAF-policy blocks, not a JS-rendering gap — the
server is making an explicit "no" decision that a more capable client
doesn't change. `state_medicaid.py`'s `_fetch_blocked` now tries the
Playwright path for real, every run (not skipped as "known dead"), and
falls back to the pre-M7 plain-HTTP-then-empty-marker path when it's
blocked, exactly as before. No further client-side workaround was
attempted beyond this — techniques that specifically target defeating a
site's explicit bot-management decision (IP rotation, residential proxies)
are out of scope for a legitimate connector. D-1 stays open, narrowed: the
plan's prescribed fix was implemented correctly and still doesn't clear it.

**A real, unblocked FL alternative was found but not implemented — the
concrete next step for whoever picks up D-1.** `portal.flmmis.com` (the
Florida Medicaid Web Portal — a different host than the blocked
`ahca.myflorida.com`, same pattern as CA's CKAN-vs-landing-page split) is
**not** behind the same WAF: plain `curl` gets a real 200 and real content,
no Playwright needed. Its "Provider Master List" (PML), linked from
`portal.flmmis.com/FLPublic/Provider_ManagedCare/Provider_ManagedCare_
Registration/tabId/77/Default.aspx?linkid=pml`, is a stable-named download
(`.../StaticContent/Public/Managed%20Care/prw19000.zip`, ~17.8MB zipped,
~93.5MB / 458,906-row CSV unzipped) that is genuinely usable as an
exclusion proxy: it carries a **real NPI column** (rare among state
sources — CA has none at all) and a `Current Medicaid Enrollment Status`
column valued `A` (Active) / `I` (Inactive) / `E` (Ineligible). Filtering
to `status == 'E'` gave ~265 rows on a crude live grep — a real, substantial
FL exclusion signal, not the 0-row empty-marker path.

**Why this session didn't wire it in:** the CSV appeared malformed in a way
`pl.read_csv(..., truncate_ragged_lines=True)` didn't fix —
`ComputeError: CSV malformed: expected 175 rows, actual 250 rows` on the
first chunk. **This diagnosis was wrong — see D21a.** Values do come
Excel-CSV-wrapped (`="000000900"` instead of a plain string) and need
unwrapping. There is no explicit termination/action-date column — only
enrollment eligibility dates — so `action_date` should be left `None` rather
than guessing at a semantic that isn't actually recorded (hard rule 2).
**TX has no equivalent alternate host found this session** — a quick check
of `data.texas.gov`'s Socrata API didn't turn up an obvious exclusions
dataset; a real search (the way CA's CKAN resource and FL's FLMMIS portal
were both found) is still owed for TX.

---

## D21a — the FLMMIS CSV was never malformed; it was a truncated download. FL now ingests 246 real rows

**Found:** 2026-08-17, live. **Affects:** `ingest/state_medicaid.py`,
`config/sources.yaml`. **Clears D-1 for FL.** TX remains open.

**The correction.** D21 above concluded the FLMMIS Provider Master List CSV
had "misaligned fields... likely an unescaped quote or delimiter inside a
name/address field somewhere in 458K rows," and scoped a tolerant-`csv`-module
repair pass as the fix. That was wrong, and the scoped work was unnecessary.
On a complete download, the file parses cleanly with no special handling at
all:

```
pl.read_csv(path, infer_schema_length=0, encoding="utf8-lossy")  ->  (458905, 23)
```

Cross-checked against Python's `csv` module over all 458,905 rows: **zero**
rows with a field count differing from the 23-column header, and no embedded
newlines (physical line count matches record count exactly). Both readers
agree the file is well-formed.

The `expected 175 rows, actual 250 rows` error is what Polars reports when its
chunked reader runs off the end of a file that stops mid-record — the
signature of a truncated artifact, not of misaligned fields. The 17.8MB ZIP
takes ~60s to fetch; the earlier attempt evidently parsed a partial copy.
**Generalisable lesson:** a "malformed CSV" error on a large remote download is
worth testing against a byte-count check before it is believed, because the
repair work it implies is expensive and the truncation explanation is cheap to
rule out.

`_fetch_fl` therefore validates the artifact rather than tolerating it: it
opens the ZIP (a short read raises `BadZipFile` immediately) and asserts
exactly one CSV member before writing anything to disk. Parsing stays strict —
adding `truncate_ragged_lines` now would be exactly the "fallback that masks a
broken source" hard rule 7 forbids, and would have hidden this very bug.

**What FL ingests now (live, 2026-08-17):**

| | |
|---|---|
| CSV rows scanned | 458,905 |
| `Current Medicaid Enrollment Status == 'E'` | 265 |
| after collapsing redundant rows | **246** |
| of those, carrying a real NPI | **220** (89%) |
| `action_date` | null on all 246, by design |

Status distribution across the whole file: `A` 290,076 / blank 140,657 /
`I` 27,907 / `E` 265. The 140,657 blank-status rows are additional
service-location rows for a provider whose enrollment fields sit on its
primary row only; filtering to `E` excludes them, as intended.

**The 265 -> 246 collapse.** 14 provider IDs carry more than one `E` row.
Verified live: **none** of them differ in service address, and the duplication
is a null-NPI enrollment segment shadowing a real-NPI one for the same
provider. Those redundant rows are dropped. Rows are *not* deduped on provider
ID alone, though — a provider listed under two genuinely different NPIs keeps
both, since picking one would discard an identifier the source actually states.
No provider in the current file is (verified: 0), but deduping on ID alone
would silently lose it if one ever were, and the correct filter costs nothing.

**Semantics worth stating plainly, because they limit what this source can
support.** The PML is an *enrollment* file, not a published sanctions list.
`E` means ineligible for Medicaid claims; the source gives **no reason**. An
`E` may be administrative — failure to revalidate, a lapsed licence — and not
fraud-related at all. Per Amendment 1 these must be weighted below a federal
OIG exclusion and reported as a secondary label set, never pooled into one
precision number. All six of these constraints are carried on the manifest's
`known_limitations` so they travel with the data instead of living only here.
`provider_type` is the raw FLMMIS Provider Type Code: no code->name table is
published with the file, and inventing one is hard rule 2.

**TX was still owed a search at the time of writing** — since done, and it
succeeded. See D21b.

---

## D21b — TX cleared via a mirror of the publisher's own file, not an alternate host. D-1 fully closed

**Found:** 2026-08-17, live. **Affects:** `ingest/state_medicaid.py`,
`config/sources.yaml`, `pyproject.toml`. **Closes D-1.**

**Three candidates checked, two rejected.** The FL win came from finding the
state's MMIS portal on a different host, so Texas's exact analogue was tried
first:

| Candidate | Result |
|---|---|
| `www.tmhp.com` (Texas MMIS portal, FLMMIS's analogue) | reachable, HTTP 200 — **but hosts no file.** Its "Excluded Providers" page only links back to the dead OIG host |
| `data.texas.gov` (Socrata) | reachable — **no Medicaid exclusions dataset.** Queried the catalog API for exclusion/excluded/sanction/terminated; zero relevant hits |
| `oig.hhs.texas.gov` / `oig.hhsc.state.tx.us` | unchanged: Akamai block / no TCP connection |

So the FL pattern does **not** generalise: Texas's MMIS portal genuinely
doesn't publish the list. What worked instead is a different pattern — an
aggregator that mirrors the publisher's own artifact.

**The source.** OpenSanctions' `us_tx_med_exclusions` dataset carries a
`source.xls` resource that is the Texas OIG's own workbook, mirrored rather
than re-derived, refreshed on the 1st and 15th (last 2026-08-15). Because it
is the publisher's file, `original_publisher` stays the Texas OIG and
OpenSanctions is recorded only as `access_provider` — a distinction
`SourceManifest` already models. The artifact URL embeds the mirror run's
timestamp (`.../20260815045901-jzv/source.xls`), so it is resolved from the
catalog `index.json` each run; hardcoding it would break at the next refresh.
This is the same reasoning CA already uses with CKAN.

**Licence — the one real cost, and it is recorded, not buried.** OpenSanctions
data is **CC-BY-NC 4.0**. Non-commercial, academic and research use is free and
explicitly permitted, which covers this project. Commercial use requires a paid
licence. The underlying records are a public-domain state government work, but
the stricter term is the one that binds, so `license_or_terms` on the TX
manifest records the CC-BY-NC term rather than the friendlier one, and
`known_limitations` says Phase 2 must re-source if the project is ever
commercialised. The operator should know this was a deliberate trade, not an
oversight.

**What TX ingests (live, 2026-08-17):**

| | |
|---|---|
| workbook rows | 13,404 |
| reinstated, filtered out | 1,456 |
| **current exclusions ingested** | **11,948** |
| with an NPI | 555 (4.6%) |
| with an `action_date` | 11,946 (~100%) |
| `action_date` range | 1959-02-03 → 2026-07-28 |

**`ReinstatedDate` is the trap in this source.** The workbook is a full
*history*, not a current-state list. ~11% of its rows are providers who were
excluded and have since been reinstated. Carrying them would manufacture false
positives against providers in good standing — the most damaging error class
this system can make — so they are dropped at parse and the count is logged.

**How TX and FL differ, which matters for how they're used.** They are close to
complementary, and neither is a substitute for the other:

- **FL** — 89% NPI coverage and a real address, but **no action date and no
  reason**. Strong for linking, weak for judging.
- **TX** — a real exclusion date on essentially every row and a `WebComments`
  reason that distinguishes "Conviction" from "Board action" from "License
  revoked" (directly serving hard rule 6, which forbids collapsing
  `legal_status`), but only 4.6% NPI and **no address column at all**. Strong
  for judging, weak for linking.

Two further TX-specific cautions, both on the manifest:
`state_provider_number` holds a professional **LicenseNumber**, not a Medicaid
provider number — this file carries none, so it must not be compared against
FL/CA provider numbers. And **~17% of rows (2,075) are reason-coded "Federal
mandated exclusion"** — these are federal LEIE exclusions mirrored into the
state list, so they *overlap* the `leie` source. Ground-truth work must dedupe
against LEIE rather than count them as independent state evidence, which is
Amendment 1's "do not pool into one precision number" in a concrete form.

**Dependency added:** `fastexcel==0.16.0`, needed because the artifact is a
legacy `.xls` (CDFV2) that no already-installed library reads. Note that
`polars.read_excel` currently emits a `FutureWarning` that its return type
becomes a `Series` in Polars 2.0 — that would break `_parse_tx`. The warning is
deliberately **not** suppressed, since it is a real forward-compatibility
signal. Tracked as debt D-19.

---

## D22 — DOJ press-release pagination is hard-blocked regardless of navigation method; `keys=`/topic filters are server-side no-ops

**Found:** M7, live. **Affects:** `ingest/doj.py`. Narrows BUILD_MILESTONES.md
debt D-2 — attempted, not cleared; real number is unchanged from before M7.

`justice.gov/news/press-releases?keys=<terms>` (page 0) renders correctly
through Playwright MCP where `curl` at the identical URL gets only the
Akamai challenge shell — real progress on the *rendering* problem. But
`&page=1` (and presumably every page beyond it) returns a hard Akamai
"Access Denied", confirmed live three independent ways, to rule out a
request-construction bug on our side rather than a genuine site policy:

1. Direct `browser_navigate` to the `page=1` URL.
2. The exact same URL as the *very first* request of a brand-new isolated
   session (rules out a bot-score building up over a session's request
   history — the block is immediate, not cumulative).
3. A real in-page `browser_click` on the rendered pager's own "Page 2"
   link — correct `Referer` header, a genuine click event, not a
   constructed URL. Blocked identically.

Separately, `keys=` and `field_pr_topic[]=` are confirmed server-side
no-ops: querying `health+care+fraud` vs. `field_pr_topic[]=Health+Care+
Fraud` vs. no filter at all returns the *same* twelve most-recent releases
every time (an unrelated Amazon/FCRA settlement and a forestry-ministerial
statement both "matched" a health-care-fraud search) — this matches what
the pre-M7 RSS feed's own docstring already documented for its query
params, now confirmed true of the search UI too, not just the feed.

Net effect: this connector's real reachable universe is one page of DOJ's
current most-recent-releases list — the same shape the RSS feed already
provided, not the plan's ~300-500 estimate. A live run on 2026-08-17
returned exactly 1 matching row after the `_is_healthcare_fraud` filter,
identical to the pre-M7 baseline the debt entry was written against. The
gain is real (genuine rendering vs. a challenge shell, well-tested
infrastructure for any future MCP fetch), but it did not move the number.
A genuinely deeper DOJ archive would need a different official source
entirely (e.g. a structured case dataset, not this press UI) — out of
scope for this session; see BUILD_MILESTONES.md §4 D-2.

---
