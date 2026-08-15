"""CLAUDE.md: 'The four invariant tests ... are not optional. If they fail,
stop and fix before continuing. A silently zeroed cache hit rate deletes an
entire graded pillar.'
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from specter.core.contracts import EvidenceBundle
from specter.llm.prompt_compiler import PromptCompiler, generate_b0_tool_schemas
from specter.tools.entity_tools import normalize_address, normalize_phone

BLOCKS_DIR = Path("prompts/blocks")


def _compiler() -> PromptCompiler:
    return PromptCompiler(BLOCKS_DIR, graph_version="v1", policy_version="1.0.0")


def _evidence(npi: str = "1770247926") -> EvidenceBundle:
    return EvidenceBundle(
        provider_npi=npi,
        evidence={"address_degree": 9, "threshold": 5},
        task_instruction="Narrate the structural signals for this provider.",
    )


def test_prefix_is_deterministic() -> None:
    """Compile the same agent/task_class twice, assert prefix_fingerprint is
    identical. Catches datetime.now(), uuid4(), and id() leakage.
    """
    compiler = _compiler()
    first = compiler.compile("graph_investigation", "narrate_graph_signal", _evidence())
    second = compiler.compile("graph_investigation", "narrate_graph_signal", _evidence())
    assert first.prefix_fingerprint == second.prefix_fingerprint
    assert first.system == second.system


def test_prefix_stable_across_evidence() -> None:
    """Compile with three different providers, assert all three
    prefix_fingerprint values match. Catches provider data bleeding above
    the cache boundary.
    """
    compiler = _compiler()
    results = [
        compiler.compile("graph_investigation", "narrate_graph_signal", _evidence(npi))
        for npi in ("1770247926", "1093800195", "1952587172")
    ]
    fingerprints = {r.prefix_fingerprint for r in results}
    assert len(fingerprints) == 1
    # and evidence really did vary — user block differs even though system didn't
    users = {r.user for r in results}
    assert len(users) == 3


# Measured against this Azure deployment (gpt-5.4-mini), not taken from docs:
# a 1,276-token prefix cached 0 tokens on repeat calls, while 1,550 tokens
# cached 1,280. The documented 1,024 floor is therefore not sufficient in
# practice. 1,800 estimated tokens (~1,690 real, since the chars/4 estimator
# runs ~6% high) sits safely above the observed cliff.
MIN_PREFIX_TOKEN_ESTIMATE = 1800


def test_prefix_exceeds_threshold() -> None:
    """Assert prefix_token_estimate >= MIN_PREFIX_TOKEN_ESTIMATE for every
    registered agent (here: every task_class in the router policy, since
    that's the real registry).
    """
    import yaml

    from specter.settings import get_settings

    policy = yaml.safe_load(Path("config/models.yaml").read_text())
    task_classes = list(policy["routing"].keys())
    assert task_classes, "config/models.yaml routing table is empty"

    compiler = _compiler()
    settings = get_settings()
    for task_class in task_classes:
        result = compiler.compile("some_agent", task_class, _evidence())
        assert result.prefix_token_estimate >= MIN_PREFIX_TOKEN_ESTIMATE, (
            f"{task_class}: prefix_token_estimate={result.prefix_token_estimate} "
            f"< {MIN_PREFIX_TOKEN_ESTIMATE}"
        )
    assert settings.specter_cache_enabled is not None  # settings loads cleanly alongside this


def test_b0_block_is_up_to_date() -> None:
    """`prompts/blocks/b0_tool_schemas.md` is generated from the tool bindings.
    If a tool signature or docstring changed without regenerating it, the
    committed prefix no longer describes the tools the agents actually have —
    and because B0 is above the cache boundary, regenerating it later silently
    invalidates every warm cache entry. Catch the drift here instead.

    Fix: python scripts/05_generate_prompt_blocks.py
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generate_prompt_blocks", Path("scripts/05_generate_prompt_blocks.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    committed = Path("prompts/blocks/b0_tool_schemas.md").read_text()
    assert committed == module.render_b0(), (
        "b0_tool_schemas.md is stale — run `python scripts/05_generate_prompt_blocks.py`"
    )


def test_serialization_is_sorted() -> None:
    """json.dumps(..., sort_keys=True) everywhere in B0-B3, and iterating a
    dict twice yields the same block bytes.
    """
    tools: list[Callable[..., Any]] = [normalize_address, normalize_phone]
    first = generate_b0_tool_schemas(tools)
    second = generate_b0_tool_schemas(list(reversed(tools)))  # different iteration order
    assert first == second  # output must not depend on input order

    json_start = first.index("```json\n") + len("```json\n")
    json_end = first.rindex("\n```")
    parsed = json.loads(first[json_start:json_end])
    canonical = json.dumps(parsed, sort_keys=True, indent=2)
    assert first[json_start:json_end] == canonical


def test_compile_produces_valid_prompt() -> None:
    compiler = _compiler()
    result = compiler.compile("graph_investigation", "narrate_graph_signal", _evidence())
    assert result.system
    assert result.user
    assert result.prompt_version == "1.0.0"
    assert len(result.prefix_fingerprint) == 64  # sha256 hex digest


def test_evidence_never_appears_in_system_block() -> None:
    compiler = _compiler()
    unique_npi = "9999999999"
    result = compiler.compile(
        "graph_investigation",
        "narrate_graph_signal",
        _evidence(unique_npi),
    )
    assert unique_npi not in result.system
    assert unique_npi in result.user
