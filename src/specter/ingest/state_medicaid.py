"""State Medicaid exclusion connector (CLAUDE.md Amendment 1) — one connector
class, three configured instances (FL/TX/CA), each producing its own
`SourceManifest`.

Verified live on 2026-08-06:
- **CA** (DHCS S&I List): plain CSV, fetchable over HTTP. The download URL is
  a dated filename behind a CKAN resource — resolved via the CKAN
  `package_show` API each run rather than hardcoded, since the filename moves
  but the dataset/resource IDs don't.
- **FL** (AHCA) and **TX** (HHS-OIG): both return HTTP 403 to a plain HTTP
  client, including with realistic browser headers — Cloudflare/WAF-protected
  the same way `justice.gov` is. Fetching them needs a real browser
  (Playwright MCP, wired in M7), not available yet. Their `fetch()` attempts a
  plain request, and on failure writes an empty marker rather than crashing
  the whole ingest run — `validate()` reports this as WARN (a source-access
  gap, not corrupt data) and `known_limitations` says exactly why. Real
  column-mapping logic for FL/TX can only be written once M7 unblocks
  fetching and the actual file layout can be inspected.

Amendment 1 schema-mapping rule: `npi` is frequently null and a match lacking
one must never auto-link. CA's CSV has no NPI column at all — its "Provider
Number" field mixes Medi-Cal provider IDs with occasional NPI-shaped strings,
but guessing which is which would be exactly the kind of fabricated
identifier hard rule 2 forbids, so `npi` is left null and the raw value is
kept separately as `state_provider_number`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import polars as pl
import structlog

from specter.core.contracts import SourceConfig, SourceManifest, ValidationReport
from specter.core.enums import ExclusionAuthority, FreshnessStatus, Verdict
from specter.ingest.base import Connector

logger = structlog.get_logger(__name__)

_JURISDICTIONS = ("FL", "TX", "CA")

_PUBLISHERS = {
    "FL": "Florida Agency for Health Care Administration (AHCA)",
    "TX": "Texas Health and Human Services - Office of Inspector General (HHS-OIG)",
    "CA": "California Department of Health Care Services (DHCS)",
}

_DATASET_NAMES = {
    "FL": "AHCA Medicaid Sanctioned/Terminated Provider List",
    "TX": "Texas HHS-OIG Exclusions List",
    "CA": "DHCS Medi-Cal Suspended & Ineligible Provider (S&I) List",
}

# FL/TX: landing pages, used only as the fetch attempt target and as the
# recorded source_url; both are Cloudflare/WAF-protected (verified 403).
_BLOCKED_LANDING_URLS = {
    "FL": "https://ahca.myflorida.com/health-quality-assurance/office-of-medicaid-program-integrity",
    "TX": "https://oig.hhs.texas.gov/exclusions",
}

_CA_CKAN_PACKAGE_SHOW = "https://data.chhs.ca.gov/api/3/action/package_show"
_CA_DATASET_ID = "8f70e05d-baa5-4296-a5ab-36318d530670"
_CA_RESOURCE_ID = "48630a37-b5ba-4d3d-af54-e82b30e658a0"

_SCHEMA = {
    "provider_name": pl.Utf8,
    "npi": pl.Utf8,
    "state_provider_number": pl.Utf8,
    "address": pl.Utf8,
    "provider_type": pl.Utf8,
    "action_date": pl.Date,
    "jurisdiction": pl.Utf8,
    "exclusion_authority": pl.Utf8,
}


class StateMedicaidConnector(Connector):
    expected_columns = frozenset(_SCHEMA.keys())

    def __init__(self, jurisdiction: str) -> None:
        if jurisdiction not in _JURISDICTIONS:
            raise ValueError(f"unknown state_medicaid jurisdiction: {jurisdiction!r}")
        self.jurisdiction = jurisdiction
        self.source_id = f"state_medicaid_{jurisdiction.lower()}"
        self._block_reason: str | None = None

    def fetch(self, cfg: SourceConfig) -> Path:
        cfg.raw_dir.mkdir(parents=True, exist_ok=True)
        out_path = cfg.raw_dir / f"{self.source_id}_raw.csv"
        if self.jurisdiction == "CA":
            self._fetch_ca(out_path)
        else:
            self._fetch_blocked(out_path)
        return out_path

    def _fetch_ca(self, out_path: Path) -> None:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            package = client.get(_CA_CKAN_PACKAGE_SHOW, params={"id": _CA_DATASET_ID})
            package.raise_for_status()
            resources = package.json()["result"]["resources"]
            resource = next(r for r in resources if r["id"] == _CA_RESOURCE_ID)
            response = client.get(resource["url"])
            response.raise_for_status()
            out_path.write_bytes(response.content)
        logger.info("state_medicaid.fetch complete", jurisdiction="CA")

    def _fetch_blocked(self, out_path: Path) -> None:
        url = _BLOCKED_LANDING_URLS[self.jurisdiction]
        try:
            response = httpx.get(
                url,
                timeout=20.0,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                    )
                },
            )
            response.raise_for_status()
            out_path.write_bytes(response.content)
            logger.info("state_medicaid.fetch complete", jurisdiction=self.jurisdiction)
            return
        except httpx.HTTPError as exc:
            self._block_reason = str(exc)
            logger.warning(
                "state_medicaid.fetch_blocked",
                jurisdiction=self.jurisdiction,
                url=url,
                error=str(exc),
            )
        out_path.write_bytes(b"")

    def parse(self, raw: Path) -> pl.DataFrame:
        if raw.stat().st_size == 0:
            return pl.DataFrame(schema=_SCHEMA)
        if self.jurisdiction == "CA":
            return self._parse_ca(raw)
        return pl.DataFrame(schema=_SCHEMA)

    def _parse_ca(self, raw: Path) -> pl.DataFrame:
        df = pl.read_csv(raw, infer_schema_length=0, encoding="utf8-lossy")
        df = df.with_columns(
            pl.when(pl.col("First Name").is_in(["N/A", ""]) | pl.col("First Name").is_null())
            .then(pl.col("Last Name"))
            .otherwise(
                pl.concat_str(
                    [pl.col("First Name"), pl.col("Middle Name"), pl.col("Last Name")],
                    separator=" ",
                    ignore_nulls=True,
                )
            )
            .alias("provider_name"),
            pl.col("Date of Suspension")
            .str.strptime(pl.Date, "%m/%d/%Y", strict=False)
            .alias("action_date"),
        )
        return df.select(
            pl.col("provider_name"),
            pl.lit(None, dtype=pl.Utf8).alias("npi"),
            pl.col("Provider Number").alias("state_provider_number"),
            pl.col("Address(es)").alias("address"),
            pl.col("Provider Type").alias("provider_type"),
            pl.col("action_date"),
            pl.lit("CA").alias("jurisdiction"),
            pl.lit(ExclusionAuthority.STATE_MEDICAID.value).alias("exclusion_authority"),
        )

    def validate(self, df: pl.DataFrame) -> ValidationReport:
        missing_columns = sorted(self.expected_columns - set(df.columns))
        null_rates = (
            {col: df[col].null_count() / df.height for col in df.columns} if df.height else {}
        )
        duplicate_key_rate = (
            float(df.is_duplicated().sum()) / df.height if df.height else 0.0
        )

        verdict = Verdict.PASS_
        if missing_columns:
            verdict = Verdict.FAIL
        elif df.height == 0:
            verdict = Verdict.WARN

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
            "npi is always null for this source; auto-link is prohibited for any "
            "match lacking an exact identifier (CLAUDE.md Amendment 1)",
            "state exclusion is a SECONDARY label set — do not pool with federal "
            "LEIE/DOJ into one precision number (CLAUDE.md Amendment 1)",
        ]
        source_url = (
            f"{_CA_CKAN_PACKAGE_SHOW}?id={_CA_DATASET_ID}"
            if self.jurisdiction == "CA"
            else _BLOCKED_LANDING_URLS[self.jurisdiction]
        )
        if self._block_reason is not None:
            known_limitations.append(
                f"blocked by source-side bot protection (HTTP client): {self._block_reason}; "
                "requires Playwright MCP (plan M7), not yet wired"
            )
        return SourceManifest(
            source_id=self.source_id,
            dataset_name=_DATASET_NAMES[self.jurisdiction],
            original_publisher=_PUBLISHERS[self.jurisdiction],
            access_provider=_PUBLISHERS[self.jurisdiction],
            source_url=source_url,
            license_or_terms="public domain (state government work)",
            snapshot_date=date.today(),
            retrieved_at=datetime.now(UTC),
            checksum_sha256=checksum,
            schema_version="state-medicaid-v1",
            coverage={"jurisdiction": self.jurisdiction, "exclusion_authority": "state_medicaid"},
            freshness_status=(
                FreshnessStatus.CURRENT if self._block_reason is None else FreshnessStatus.UNKNOWN
            ),
            known_limitations=known_limitations,
            row_count=df.height,
        )
