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
