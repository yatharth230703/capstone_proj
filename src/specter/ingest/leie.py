"""HHS OIG LEIE connector (plan §5.2) — single national CSV, no state filter:
an excluded individual/entity registered in one state can still be an officer
or address-mate of a cohort provider in another, so downstream matching needs
the full file, not a pre-filtered slice.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import httpx
import polars as pl
import structlog

from specter.core.contracts import SourceConfig, SourceManifest, ValidationReport
from specter.core.enums import FreshnessStatus, Verdict
from specter.ingest.base import Connector

logger = structlog.get_logger(__name__)

_CSV_URL = "https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv"

_RAW_TO_SNAKE = {
    "LASTNAME": "last_name",
    "FIRSTNAME": "first_name",
    "MIDNAME": "mid_name",
    "BUSNAME": "bus_name",
    "GENERAL": "general",
    "SPECIALTY": "specialty",
    "UPIN": "upin",
    "NPI": "npi",
    "DOB": "dob",
    "ADDRESS": "address",
    "CITY": "city",
    "STATE": "state",
    "ZIP": "zip",
    "EXCLTYPE": "excl_type",
    "EXCLDATE": "excl_date",
    "REINDATE": "rein_date",
    "WAIVERDATE": "waiver_date",
    "WVRSTATE": "wvr_state",
}

_DATE_COLUMNS = ("excl_date", "rein_date", "waiver_date")
_MIN_SANE_DATE = date(1977, 1, 1)  # LEIE program predates this; earlier = data-quality bug


class LeieConnector(Connector):
    source_id = "leie"
    expected_columns = frozenset(_RAW_TO_SNAKE.values())

    def fetch(self, cfg: SourceConfig) -> Path:
        cfg.raw_dir.mkdir(parents=True, exist_ok=True)
        out_path = cfg.raw_dir / "leie_raw.csv"
        with httpx.stream("GET", _CSV_URL, timeout=60.0, follow_redirects=True) as response:
            response.raise_for_status()
            with out_path.open("wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
        logger.info("leie.fetch complete", size_bytes=out_path.stat().st_size)
        return out_path

    def parse(self, raw: Path) -> pl.DataFrame:
        df = pl.read_csv(raw, infer_schema_length=0)  # everything as str; LEIE has no header types
        df = df.rename({k: v for k, v in _RAW_TO_SNAKE.items() if k in df.columns})

        df = df.with_columns(
            pl.when(pl.col("npi") == "0000000000").then(None).otherwise(pl.col("npi")).alias("npi")
        )
        for col in _DATE_COLUMNS:
            df = df.with_columns(
                pl.when(pl.col(col) == "00000000")
                .then(None)
                .otherwise(pl.col(col))
                .str.strptime(pl.Date, "%Y%m%d", strict=False)
                .alias(col)
            )
        return df

    def validate(self, df: pl.DataFrame) -> ValidationReport:
        missing_columns = sorted(self.expected_columns - set(df.columns))
        null_rates = (
            {col: df[col].null_count() / df.height for col in df.columns} if df.height else {}
        )
        duplicate_key_rate = (
            float(df.is_duplicated().sum()) / df.height if df.height else 0.0
        )

        date_range_sanity_ok = True
        date_range_notes = None
        if df.height and "excl_date" in df.columns:
            max_date = cast("date | None", df["excl_date"].drop_nulls().max())
            min_date = cast("date | None", df["excl_date"].drop_nulls().min())
            today = date.today()
            if (min_date is not None and min_date < _MIN_SANE_DATE) or (
                max_date is not None and max_date > today
            ):
                date_range_sanity_ok = False
                date_range_notes = f"excl_date range [{min_date}, {max_date}] outside sane bounds"

        verdict = Verdict.PASS_
        if missing_columns or df.height == 0:
            verdict = Verdict.FAIL
        elif not date_range_sanity_ok:
            verdict = Verdict.WARN

        return ValidationReport(
            source_id=self.source_id,
            checked_at=datetime.now(UTC),
            missing_columns=missing_columns,
            schema_drift=[],
            null_rate_per_column=null_rates,
            duplicate_key_rate=duplicate_key_rate,
            row_count_delta=None,
            date_range_sanity_ok=date_range_sanity_ok,
            date_range_notes=date_range_notes,
            verdict=verdict,
        )

    def build_manifest(
        self,
        cfg: SourceConfig,
        raw_path: Path,
        checksum: str,
        df: pl.DataFrame,
        report: ValidationReport,
    ) -> SourceManifest:
        return SourceManifest(
            source_id=self.source_id,
            dataset_name="HHS OIG List of Excluded Individuals/Entities (LEIE)",
            original_publisher="HHS Office of Inspector General",
            access_provider="HHS OIG",
            source_url=_CSV_URL,
            license_or_terms="public domain (U.S. Government Work)",
            snapshot_date=date.today(),
            retrieved_at=datetime.now(UTC),
            checksum_sha256=checksum,
            schema_version="leie-updated-csv-v1",
            coverage={"jurisdiction": "US", "scope": "national, all states"},
            freshness_status=FreshnessStatus.CURRENT,
            known_limitations=[
                "npi is frequently null (LEIE predates NPI and many entries are individuals "
                "without an NPI on file) — never auto-link an exclusion lacking an NPI"
            ],
            row_count=df.height,
        )
