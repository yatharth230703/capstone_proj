"""Offline tests for `agents/data_quality.deterministic_verdict` (M6,
BUILD_MILESTONES.md D-5) — the gate `workflow/screening.py` branches on
instead of the LLM's `DataQualityReport.verdict`, precisely because it must
not flip run to run on identical input. Pure function, no Neo4j/LLM needed.
"""

from __future__ import annotations

from specter.agents.data_quality import deterministic_verdict
from specter.core.enums import Verdict

_FRESHNESS_DAYS = 180


def _source(
    *, row_count_matches: bool = True, snapshot_age_days: int = 5, freshness_status: str = "current"
) -> dict:
    return {
        "freshness_status": freshness_status,
        "observed": {
            "row_count_matches_manifest": row_count_matches,
            "snapshot_age_days": snapshot_age_days,
        },
    }


def test_all_current_and_matching_is_pass() -> None:
    sources = [_source(), _source()]
    assert deterministic_verdict(sources, _FRESHNESS_DAYS) == Verdict.PASS_


def test_row_count_mismatch_is_fail_even_if_fresh() -> None:
    sources = [_source(), _source(row_count_matches=False)]
    assert deterministic_verdict(sources, _FRESHNESS_DAYS) == Verdict.FAIL


def test_non_current_freshness_status_is_warn_not_fail() -> None:
    # The real state_medicaid_tx case (BUILD_MILESTONES.md D-1; FL was cleared
    # 2026-08-17 and is now `current`, TX is still blocked): row count
    # honestly matches its manifest (0 == 0), but freshness_status is
    # "unknown" because the source is bot-blocked, not because of a real
    # data-integrity problem — that's a warning, not a halt.
    sources = [_source(), _source(freshness_status="unknown")]
    assert deterministic_verdict(sources, _FRESHNESS_DAYS) == Verdict.WARN


def test_stale_snapshot_is_warn() -> None:
    sources = [_source(snapshot_age_days=200)]
    assert deterministic_verdict(sources, _FRESHNESS_DAYS) == Verdict.WARN


def test_fail_takes_priority_over_warn() -> None:
    sources = [_source(freshness_status="unknown"), _source(row_count_matches=False)]
    assert deterministic_verdict(sources, _FRESHNESS_DAYS) == Verdict.FAIL
