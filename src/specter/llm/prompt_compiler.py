"""The prefix-cache architecture (plan §7.1, pillar #2). This is the most
important file in the repo — get it wrong and the caching pillar silently
evaporates. Read `tests/test_prompt_compiler.py`'s four invariants before
touching this file; they are not optional.

Block order (stable -> variable), cache boundary after B3:

    B0 tool schemas | B1 evidence policy + output contract | B2 community
    summaries | B3 exemplars
    ──────────────── CACHE BOUNDARY ────────────────
    B4 provider evidence bundle | B5 task instruction

B0-B3 make up `CompiledPrompt.system` and must never contain anything that
varies per call: no `datetime.now()`, `uuid4()`, run IDs, trace IDs, `id()`,
unsorted dict/set iteration, or machine-specific paths. B4-B5 make up
`CompiledPrompt.user` and carry everything call-specific.
"""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from specter.core.contracts import CompiledPrompt, EvidenceBundle
from specter.core.hashing import sha256_text

# A conservative, network-free token estimate (~4 chars/token for English
# prose and JSON). Exact tokenization isn't the point here — the invariant
# this feeds is a cache-eligibility threshold, not a billing calculation.
_CHARS_PER_TOKEN_ESTIMATE = 4


def generate_b0_tool_schemas(tools: list[Callable[..., Any]]) -> str:
    """Introspects `tools` into a sorted, deterministic JSON block. Re-run
    this whenever a tool signature changes — the output file
    (`prompts/blocks/b0_tool_schemas.md`) is generated, not hand-edited.
    """
    schemas: dict[str, dict[str, Any]] = {}
    for tool in tools:
        signature = inspect.signature(tool)
        params = {name: str(param.annotation) for name, param in signature.parameters.items()}
        schemas[tool.__name__] = {
            "params": params,
            "returns": str(signature.return_annotation),
            "docstring": (inspect.getdoc(tool) or "").strip(),
        }
    body = json.dumps(schemas, sort_keys=True, indent=2)
    return "## B0: Tool Schemas\n\n```json\n" + body + "\n```"


class PromptCompiler:
    def __init__(self, blocks_dir: Path, graph_version: str, policy_version: str) -> None:
        self._blocks_dir = blocks_dir
        self._graph_version = graph_version
        self._policy_version = policy_version
        self._system_prefix = self._build_system_prefix()

    def _build_system_prefix(self) -> str:
        parts = [
            (self._blocks_dir / "b0_tool_schemas.md").read_text().strip(),
            (self._blocks_dir / "b1_evidence_policy.md").read_text().strip(),
            (self._blocks_dir / "b1_output_contract.md").read_text().strip(),
            self._community_summaries_block(),
        ]
        exemplars_dir = self._blocks_dir / "b3_exemplars"
        for exemplar_path in sorted(exemplars_dir.glob("*.md")):
            parts.append(exemplar_path.read_text().strip())
        return "\n\n".join(parts)

    def _community_summaries_block(self) -> str:
        # B2: graph community summaries relevant to the cohort. Populated by
        # graph/summaries.py, which needs AZURE_API_KEY — not configured yet.
        # Static and empty until then; never varies per call either way, so
        # it can't leak evidence above the boundary.
        return (
            "## B2: Community Context\n\n"
            f"(graph_version={self._graph_version}; no community summaries "
            "available yet — graph/summaries.py requires AZURE_API_KEY)"
        )

    @property
    def system_prefix(self) -> str:
        """B0-B3, the cacheable prefix. Identical for every agent by design —
        one shared prefix means all agents warm the *same* Azure cache entry
        instead of each paying its own cold call. Per-agent wording belongs
        below the boundary, in the agent's `instruction`.
        """
        return self._system_prefix

    def compile(self, agent: str, task_class: str, evidence: EvidenceBundle) -> CompiledPrompt:
        system = self._system_prefix
        user = self._render_user_blocks(agent, task_class, evidence)
        return CompiledPrompt(
            system=system,
            user=user,
            prefix_token_estimate=max(1, len(system) // _CHARS_PER_TOKEN_ESTIMATE),
            prefix_fingerprint=sha256_text(system),
            prompt_version=self._policy_version,
        )

    def _render_user_blocks(
        self, agent: str, task_class: str, evidence: EvidenceBundle
    ) -> str:
        b4 = json.dumps(
            {"provider_npi": evidence.provider_npi, "evidence": evidence.evidence},
            sort_keys=True,
            default=str,
        )
        b5 = (
            f"## B5: Task\n\nagent={agent}\ntask_class={task_class}\n\n"
            f"{evidence.task_instruction}"
        )
        return f"## B4: Evidence Bundle\n\n```json\n{b4}\n```\n\n{b5}"
