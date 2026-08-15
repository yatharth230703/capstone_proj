"""Data Quality Agent (plan §9.2) — T1 `assess_source_quality`.

Runs before anything else. Reads every `SourceManifest` in the frozen snapshot
plus the deterministic checks below, and returns `pass | warn | fail`. A
`fail` halts the workflow with case state `data_quality_hold` (M6).

The agent has **no tools**. Every number it reasons about is computed here,
deterministically, and handed to it in the evidence bundle — which is what
makes CLAUDE.md hard rule 1 structurally true for this agent rather than
merely instructed: there is no path by which it could obtain a number of its
own.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import polars as pl
import structlog

from specter.agents._base import AgentRuntime, build_agent, run_agent
from specter.core.contracts import (
    AgentRunResult,
    DataQualityReport,
    EvidenceBundle,
    SourceManifest,
)
from specter.core.errors import SpecterError

logger = structlog.get_logger(__name__)

AGENT_NAME = "data_quality"
TASK_CLASS = "assess_source_quality"
INSTRUCTION_FILE = "data_quality.md"

_TASK_INSTRUCTION = (
    "Assess every source below and return a DataQualityReport. Give one "
    "SourceVerdict per source, in the order listed. The overall verdict is the "
    "worst per-source verdict. Populate blocking_reasons only for sources you "
    "mark fail."
)


class SnapshotError(SpecterError):
    """The frozen snapshot is missing or unreadable. Not recoverable — the
    screening pipeline reads `data/snapshot/` only (plan §5.3).
    """


def _observed_facts(source_dir: Path, manifest: SourceManifest) -> dict[str, Any]:
    """Deterministic checks over one source's parquet. These are the numbers
    the agent is allowed to reason about; it computes none of them itself.
    """
    data_path = source_dir / "data.parquet"
    if not data_path.exists():
        raise SnapshotError(f"{manifest.source_id}: {data_path} is missing")

    frame = pl.read_parquet(data_path)
    row_count = frame.height
    null_rate = {
        column: round(frame[column].null_count() / row_count, 4) if row_count else 0.0
        for column in sorted(frame.columns)
    }
    duplicate_rows = row_count - frame.unique().height
    snapshot_age_days = (date.today() - manifest.snapshot_date).days

    return {
        "columns": sorted(frame.columns),
        "row_count": row_count,
        "row_count_in_manifest": manifest.row_count,
        "row_count_matches_manifest": row_count == manifest.row_count,
        "null_rate_per_column": null_rate,
        "duplicate_row_count": duplicate_rows,
        "duplicate_row_rate": round(duplicate_rows / row_count, 4) if row_count else 0.0,
        "snapshot_age_days": snapshot_age_days,
    }


def build_evidence(snapshot_dir: Path) -> EvidenceBundle:
    """Assemble the B4 evidence bundle from the frozen snapshot.

    Sources are sorted by `source_id` so the bundle — and therefore the L1
    cache key — is stable across runs.
    """
    manifest_paths = sorted(snapshot_dir.glob("*/manifest.json"))
    if not manifest_paths:
        raise SnapshotError(f"no source manifests found under {snapshot_dir}")

    sources: list[dict[str, Any]] = []
    for manifest_path in manifest_paths:
        manifest = SourceManifest.model_validate_json(manifest_path.read_text())
        sources.append(
            {
                "source_id": manifest.source_id,
                "dataset_name": manifest.dataset_name,
                "original_publisher": manifest.original_publisher,
                "access_provider": manifest.access_provider,
                "snapshot_date": manifest.snapshot_date.isoformat(),
                "freshness_status": manifest.freshness_status.value,
                "known_limitations": manifest.known_limitations,
                "schema_version": manifest.schema_version,
                "checksum_sha256": manifest.checksum_sha256,
                "coverage": manifest.coverage,
                "observed": _observed_facts(manifest_path.parent, manifest),
            }
        )
    sources.sort(key=lambda source: str(source["source_id"]))

    return EvidenceBundle(
        provider_npi="",
        evidence={"assessed_at": datetime.now(UTC).date().isoformat(), "sources": sources},
        task_instruction=_TASK_INSTRUCTION,
    )


async def assess(snapshot_dir: Path, runtime: AgentRuntime) -> AgentRunResult:
    """Build the agent, run it over the snapshot, and return its result.

    The caller decides what a `fail` means; this function does not halt. That
    keeps the gate decision in `workflow/screening.py` (M6) where it is
    visible in the graph, rather than buried in an agent module.
    """
    agent = build_agent(
        name=AGENT_NAME,
        task_class=TASK_CLASS,
        instruction_file=INSTRUCTION_FILE,
        tools=[],
        output_schema=DataQualityReport,
        runtime=runtime,
    )
    evidence = build_evidence(snapshot_dir)
    logger.info(
        "data_quality.assessing",
        source_count=len(evidence.evidence["sources"]),
        evidence_chars=len(json.dumps(evidence.evidence, sort_keys=True, default=str)),
    )
    return await run_agent(agent, TASK_CLASS, evidence, runtime, DataQualityReport)
