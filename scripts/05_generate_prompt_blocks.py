#!/usr/bin/env python
"""Regenerate `prompts/blocks/b0_tool_schemas.md` from the model-facing tool
bindings (plan §7.1, block B0).

    python scripts/05_generate_prompt_blocks.py

B0 is generated, never hand-edited. It sits above the prompt cache boundary,
so any change to it invalidates every agent's cached prefix — run this only
when a tool signature or docstring actually changed, and commit the result in
the same commit as the tool change. `tests/test_prompt_compiler.py` asserts
the committed file matches what this script produces, so a forgotten
regeneration fails the suite instead of silently drifting.

No Neo4j connection is needed: `build_tool_bindings` only touches the driver
inside each tool body, and this script merely introspects signatures.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import structlog
from neo4j import Driver

from specter.llm.prompt_compiler import generate_b0_tool_schemas
from specter.tools.bindings import build_tool_bindings
from specter.tools.signal_tools import load_thresholds

logger = structlog.get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_B0_PATH = _REPO_ROOT / "prompts" / "blocks" / "b0_tool_schemas.md"


def render_b0() -> str:
    """The single source of truth for B0's content, shared with the test that
    asserts the committed file is current.
    """
    thresholds = load_thresholds(_REPO_ROOT / "config" / "screening.yaml")
    tools = build_tool_bindings(
        cast(Driver, None), thresholds, _REPO_ROOT / "data" / "evidence"
    )
    return generate_b0_tool_schemas(tools) + "\n"


def main() -> None:
    content = render_b0()
    previous = _B0_PATH.read_text() if _B0_PATH.exists() else ""
    _B0_PATH.write_text(content)
    logger.info(
        "b0.generated",
        path=str(_B0_PATH.relative_to(_REPO_ROOT)),
        chars=len(content),
        changed=content != previous,
    )


if __name__ == "__main__":
    main()
