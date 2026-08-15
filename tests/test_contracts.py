from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from specter.core.contracts import SourceManifest, ValidationReport
from specter.core.enums import FreshnessStatus, Verdict


def _manifest_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "source_id": "nppes",
        "dataset_name": "NPPES NPI Registry",
        "original_publisher": "CMS",
        "access_provider": "CMS",
        "source_url": "https://npiregistry.cms.hhs.gov/api/",
        "license_or_terms": "public domain",
        "snapshot_date": date(2026, 1, 1),
        "retrieved_at": datetime(2026, 1, 1, tzinfo=UTC),
        "checksum_sha256": "a" * 64,
        "schema_version": "1.0.0",
        "coverage": {"states": ["FL", "TX", "CA"], "taxonomies": ["332"]},
        "freshness_status": FreshnessStatus.CURRENT,
        "known_limitations": [],
        "row_count": 1000,
    }
    kwargs.update(overrides)
    return kwargs


def test_source_manifest_constructs_with_valid_data() -> None:
    manifest = SourceManifest.model_validate(_manifest_kwargs())
    assert manifest.source_id == "nppes"
    assert manifest.freshness_status is FreshnessStatus.CURRENT


def test_source_manifest_missing_required_field_raises() -> None:
    kwargs = _manifest_kwargs()
    del kwargs["checksum_sha256"]
    with pytest.raises(ValidationError):
        SourceManifest.model_validate(kwargs)


def test_source_manifest_rejects_unknown_freshness_status() -> None:
    with pytest.raises(ValidationError):
        SourceManifest.model_validate(_manifest_kwargs(freshness_status="stale"))


def test_source_manifest_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SourceManifest.model_validate(_manifest_kwargs(unexpected_field="nope"))


def test_source_manifest_rejects_negative_row_count() -> None:
    with pytest.raises(ValidationError):
        SourceManifest.model_validate(_manifest_kwargs(row_count=-1))


def _report_kwargs(**overrides: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "source_id": "nppes",
        "checked_at": datetime(2026, 1, 1, tzinfo=UTC),
        "missing_columns": [],
        "schema_drift": [],
        "null_rate_per_column": {"npi": 0.0, "state": 0.01},
        "duplicate_key_rate": 0.0,
        "date_range_sanity_ok": True,
        "verdict": Verdict.PASS_,
    }
    kwargs.update(overrides)
    return kwargs


def test_validation_report_constructs_with_valid_data() -> None:
    report = ValidationReport.model_validate(_report_kwargs())
    assert report.verdict is Verdict.PASS_
    assert report.row_count_delta is None


def test_validation_report_rejects_unknown_verdict() -> None:
    with pytest.raises(ValidationError):
        ValidationReport.model_validate(_report_kwargs(verdict="maybe"))


def test_validation_report_rejects_out_of_range_duplicate_rate() -> None:
    with pytest.raises(ValidationError):
        ValidationReport.model_validate(_report_kwargs(duplicate_key_rate=1.5))


def test_validation_report_fail_verdict_on_schema_corruption() -> None:
    report = ValidationReport.model_validate(
        _report_kwargs(
            missing_columns=["npi"],
            schema_drift=["state: expected str, got int"],
            verdict=Verdict.FAIL,
        )
    )
    assert report.verdict is Verdict.FAIL
    assert "npi" in report.missing_columns
