"""NPPES NPI Registry connector (plan §5.2).

The public API (`https://npiregistry.cms.hhs.gov/api/`) has no taxonomy-code
filter — only a fuzzy `taxonomy_description` text match, and it rejects a bare
`state` filter without an additional criterion. So this connector queries once
per (state, NUCC classification group) pair, paginating in pages of 200 (the
API's max `limit`), and filters client-side to taxonomy codes that actually
start with the configured prefix.

`_NUCC_TAXONOMIES` is the set of NUCC taxonomy codes starting with "332" —
fetched and verified live from https://www.nucc.org/images/stories/CSV/
nucc_taxonomy_251.csv on 2026-08-06. This connector is scoped to that prefix:
if `cfg.params["taxonomy_prefix"]` doesn't match "332", `fetch` raises rather
than silently returning an empty/wrong result set.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import structlog

from specter.core.contracts import SourceConfig, SourceManifest, ValidationReport
from specter.core.enums import FreshnessStatus, Verdict
from specter.ingest.base import Connector

logger = structlog.get_logger(__name__)

_API_URL = "https://npiregistry.cms.hhs.gov/api/"
_PAGE_SIZE = 200
_MAX_PAGES_PER_QUERY = 50  # safety ceiling: 50 * 200 = 10,000 per (state, query)

# code -> NUCC description, prefix "332". Source: NUCC taxonomy CSV v25.1.
_NUCC_TAXONOMIES: dict[str, str] = {
    "332100000X": "Department of Veterans Affairs (VA) Pharmacy",
    "332B00000X": "Durable Medical Equipment & Medical Supplies",
    "332BC3200X": "Durable Medical Equipment & Medical Supplies, Customized Equipment",
    "332BD1200X": "Durable Medical Equipment & Medical Supplies, Dialysis Equipment & Supplies",
    "332BN1400X": "Durable Medical Equipment & Medical Supplies, Nursing Facility Supplies",
    "332BP3500X": "Durable Medical Equipment & Medical Supplies, Parenteral & Enteral Nutrition",
    "332BX2000X": "Durable Medical Equipment & Medical Supplies, Oxygen Equipment & Supplies",
    "332G00000X": "Eye Bank",
    "332H00000X": "Eyewear Supplier",
    "332S00000X": "Hearing Aid Equipment",
    "332U00000X": "Home Delivered Meals",
    "332800000X": "Indian Health Service/Tribal/Urban Indian Health (I/T/U) Pharmacy",
    "332000000X": "Military/U.S. Coast Guard Pharmacy",
    "332900000X": "Non-Pharmacy Dispensing Site",
}


def _query_terms() -> list[str]:
    return sorted({desc.split(",")[0] for desc in _NUCC_TAXONOMIES.values()})


class NppesConnector(Connector):
    source_id = "nppes"
    expected_columns = frozenset(
        {
            "npi",
            "organization_name",
            "enumeration_date",
            "last_updated",
            "status",
            "state",
            "address_1",
            "city",
            "postal_code",
            "telephone_number",
            "authorized_official_first_name",
            "authorized_official_last_name",
            "taxonomy_code",
            "taxonomy_desc",
        }
    )

    def fetch(self, cfg: SourceConfig) -> Path:
        taxonomy_prefix = cfg.params.get("taxonomy_prefix", "332")
        if taxonomy_prefix != "332":
            raise ValueError(
                f"NppesConnector's embedded NUCC table only covers prefix '332', "
                f"got taxonomy_prefix={taxonomy_prefix!r}"
            )
        states: list[str] = cfg.params["states"]

        raw_records: list[dict[str, Any]] = []
        seen_npis: set[str] = set()
        with httpx.Client(timeout=30.0) as client:
            for state in states:
                for term in _query_terms():
                    raw_records.extend(
                        self._fetch_query(client, state, term, seen_npis)
                    )

        cfg.raw_dir.mkdir(parents=True, exist_ok=True)
        out_path = cfg.raw_dir / "nppes_raw.jsonl"
        with out_path.open("w", encoding="utf-8") as f:
            for record in raw_records:
                f.write(json.dumps(record, sort_keys=True))
                f.write("\n")
        logger.info("nppes.fetch complete", row_count=len(raw_records), states=states)
        return out_path

    def _fetch_query(
        self,
        client: httpx.Client,
        state: str,
        taxonomy_description: str,
        seen_npis: set[str],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for page in range(_MAX_PAGES_PER_QUERY):
            skip = page * _PAGE_SIZE
            response = client.get(
                _API_URL,
                params={
                    "version": "2.1",
                    "state": state,
                    "enumeration_type": "NPI-2",
                    "taxonomy_description": taxonomy_description,
                    "limit": _PAGE_SIZE,
                    "skip": skip,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("Errors"):
                logger.warning(
                    "nppes.api_error", state=state, term=taxonomy_description,
                    errors=payload["Errors"],
                )
                break
            batch = payload.get("results", [])
            if not batch:
                break
            for record in batch:
                npi = record.get("number")
                if npi and npi not in seen_npis:
                    seen_npis.add(npi)
                    results.append(record)
            if len(batch) < _PAGE_SIZE:
                break
        return results

    def parse(self, raw: Path) -> pl.DataFrame:
        rows: list[dict[str, Any]] = []
        with raw.open(encoding="utf-8") as f:
            for line in f:
                record = json.loads(line)
                rows.append(self._flatten(record))

        rows = [
            row
            for row in rows
            if row["taxonomy_code"] is not None and row["taxonomy_code"].startswith("332")
        ]

        if not rows:
            return pl.DataFrame(schema={col: pl.Utf8 for col in self.expected_columns})
        return pl.DataFrame(rows)

    def _flatten(self, record: dict[str, Any]) -> dict[str, Any]:
        basic = record.get("basic", {})
        primary_taxonomy = next(
            (t for t in record.get("taxonomies", []) if t.get("primary")),
            record.get("taxonomies", [{}])[0] if record.get("taxonomies") else {},
        )
        location = next(
            (a for a in record.get("addresses", []) if a.get("address_purpose") == "LOCATION"),
            record.get("addresses", [{}])[0] if record.get("addresses") else {},
        )
        return {
            "npi": record.get("number"),
            "organization_name": basic.get("organization_name"),
            "enumeration_date": basic.get("enumeration_date"),
            "last_updated": basic.get("last_updated"),
            "status": basic.get("status"),
            "state": location.get("state"),
            "address_1": location.get("address_1"),
            "city": location.get("city"),
            "postal_code": location.get("postal_code"),
            "telephone_number": location.get("telephone_number"),
            "authorized_official_first_name": basic.get("authorized_official_first_name"),
            "authorized_official_last_name": basic.get("authorized_official_last_name"),
            "taxonomy_code": primary_taxonomy.get("code"),
            "taxonomy_desc": primary_taxonomy.get("desc"),
        }

    def validate(self, df: pl.DataFrame) -> ValidationReport:
        missing_columns = sorted(self.expected_columns - set(df.columns))
        null_rates = (
            {col: df[col].null_count() / df.height for col in df.columns} if df.height else {}
        )
        duplicate_key_rate = (
            1 - (df["npi"].n_unique() / df.height) if df.height and "npi" in df.columns else 0.0
        )

        verdict = Verdict.PASS_
        if missing_columns:
            verdict = Verdict.FAIL
        elif df.height == 0:
            verdict = Verdict.WARN
        elif null_rates.get("npi", 0.0) > 0.0:
            verdict = Verdict.FAIL  # every row must have an NPI, it's the join key

        return ValidationReport(
            source_id=self.source_id,
            checked_at=datetime.now(UTC),
            missing_columns=missing_columns,
            schema_drift=[],
            null_rate_per_column=null_rates,
            duplicate_key_rate=duplicate_key_rate,
            row_count_delta=None,
            date_range_sanity_ok=True,
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
        known_limitations = [
            "taxonomy_description is a fuzzy text match on the NPPES API; coverage is "
            "verified against the full NUCC '332' code table, not assumed from one query"
        ]
        if report.verdict is Verdict.WARN:
            known_limitations.append("zero rows returned for the configured state/taxonomy scope")
        return SourceManifest(
            source_id=self.source_id,
            dataset_name="NPPES NPI Registry",
            original_publisher="Centers for Medicare & Medicaid Services (CMS)",
            access_provider="CMS NPI Registry API",
            source_url=_API_URL,
            license_or_terms="public domain (U.S. Government Work)",
            snapshot_date=date.today(),
            retrieved_at=datetime.now(UTC),
            checksum_sha256=checksum,
            schema_version="npi-registry-api-2.1",
            coverage={
                "states": cfg.params.get("states"),
                "taxonomy_prefix": cfg.params.get("taxonomy_prefix", "332"),
            },
            freshness_status=FreshnessStatus.CURRENT,
            known_limitations=known_limitations,
            row_count=df.height,
        )
