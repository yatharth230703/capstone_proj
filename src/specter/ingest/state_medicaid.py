"""State Medicaid exclusion connector (CLAUDE.md Amendment 1) — one connector
class, three configured instances (FL/TX/CA), each producing its own
`SourceManifest`.

Verified live on 2026-08-06:
- **CA** (DHCS S&I List): plain CSV, fetchable over HTTP. The download URL is
  a dated filename behind a CKAN resource — resolved via the CKAN
  `package_show` API each run rather than hardcoded, since the filename moves
  but the dataset/resource IDs don't.

**FL — cleared 2026-08-17 via a different host (D-1 closed for FL).** The
originally-planned source, `ahca.myflorida.com`, is behind a zone-wide
Cloudflare block that a real headless Chromium does not get through either
(see the TX note below — the same investigation covered both). It is not used
at all any more. FL now reads the **Florida Medicaid Web Portal**
(`portal.flmmis.com`, a different host, no WAF) "Provider Master List": a
stable-named ZIP holding one ~93.5MB / 458,905-row CSV of every enrolled FL
Medicaid provider. Its `Current Medicaid Enrollment Status` column is valued
`A`/`I`/`E`, and `E` (Ineligible) is Florida's excluded-provider signal —
265 rows live, of which 232 carry a real NPI. That NPI column is what makes
this worth the 93MB: it is rare among state sources (CA's equivalent has
none) and is the only thing that permits anything better than a name match.

The file is *not* malformed, contrary to the earlier D21 writeup: `pl.read_csv`
parses all 458,905 rows cleanly. The failure recorded there was a truncated
download being parsed as if complete, so `_fetch_fl` verifies the ZIP opens
and holds exactly one CSV member before writing anything. Parsing stays strict
on purpose (hard rule 7) — a genuinely ragged future revision must raise, not
be smoothed over by a tolerant reader.

**TX — cleared 2026-08-17 via a mirror of the publisher's own file.** Both
official OIG hosts stay unusable: `oig.hhs.texas.gov` returns Akamai's block
page (title "Access Denied", referencing `errors.edgesuite.net`), an explicit
WAF decision confirmed against a real headless Chromium, and the older
`oig.hhsc.state.tx.us` doesn't accept a TCP connection at all. TMHP, the Texas
MMIS portal, was checked as the direct analogue of FL's FLMMIS win and is a
dead end — it is reachable but hosts no file, deferring to the same dead OIG
host. `data.texas.gov`'s Socrata catalog has no Medicaid exclusions dataset.

What does work is **OpenSanctions**, which mirrors the OIG's own `source.xls`
and refreshes it on the 1st and 15th. This is the publisher's file, not a
re-derivation, so `original_publisher` stays the Texas OIG and OpenSanctions
is recorded as `access_provider` only. Two consequences to keep in view:
the data is CC-BY-NC 4.0 (fine for this project's academic use, **not** for
commercial use), and the workbook is a full *history* — ~11% of its rows are
providers since reinstated, filtered out on parse so we never report someone
in good standing as excluded.

Its NPI column is sparse (~4.6% of current exclusions) where FL's is dense,
but it carries what FL lacks entirely: a real exclusion `StartDate` on every
row and a `WebComments` reason that distinguishes a conviction from a board
action from a licence revocation. See `NOTES_API_DEVIATIONS.md` D21a/D21b.

Amendment 1 schema-mapping rule: `npi` is frequently null and a match lacking
one must never auto-link. CA's CSV has no NPI column at all — its "Provider
Number" field mixes Medi-Cal provider IDs with occasional NPI-shaped strings,
but guessing which is which would be exactly the kind of fabricated
identifier hard rule 2 forbids, so `npi` is left null and the raw value is
kept separately as `state_provider_number`.
"""

from __future__ import annotations

import io
import zipfile
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

_ACCESS_PROVIDERS = {
    "FL": "Florida Medicaid Web Portal (FLMMIS, portal.flmmis.com)",
    "TX": "OpenSanctions (mirror of the Texas OIG workbook)",
}

_PUBLISHERS = {
    "FL": "Florida Agency for Health Care Administration (AHCA)",
    "TX": "Texas Health and Human Services - Office of Inspector General (HHS-OIG)",
    "CA": "California Department of Health Care Services (DHCS)",
}

_DATASET_NAMES = {
    "FL": "Florida Medicaid Provider Master List (FLMMIS) - Ineligible providers",
    "TX": "Texas HHS-OIG Exclusions List",
    "CA": "DHCS Medi-Cal Suspended & Ineligible Provider (S&I) List",
}

# TX: the official OIG hosts are unusable (see module docstring), so the file
# is taken from OpenSanctions, which mirrors the OIG's own `source.xls`
# byte-for-byte and refreshes it on the 1st and 15th. The artifact URL carries
# a run timestamp, so it is resolved from the catalog each run rather than
# hardcoded — the same reason CA resolves through CKAN.
_TX_CATALOG_INDEX = (
    "https://data.opensanctions.org/datasets/latest/us_tx_med_exclusions/index.json"
)
_TX_SOURCE_RESOURCE = "source.xls"

_CA_CKAN_PACKAGE_SHOW = "https://data.chhs.ca.gov/api/3/action/package_show"
_CA_DATASET_ID = "8f70e05d-baa5-4296-a5ab-36318d530670"
_CA_RESOURCE_ID = "48630a37-b5ba-4d3d-af54-e82b30e658a0"

_FL_PML_ZIP_URL = (
    "https://portal.flmmis.com/FLPublic/Portals/0/StaticContent/Public/"
    "Managed%20Care/prw19000.zip"
)
# Header names carry trailing spaces in the source file; `parse` strips them.
_FL_STATUS_COL = (
    "Current Medicaid Enrollment Status A = Active I = Inactive E = Ineligible"
)
_FL_INELIGIBLE = "E"
# Fields arrive Excel-CSV-wrapped: `="000000900"` rather than `000000900`.
_EXCEL_WRAPPER = r'^="|"$'

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


def _tx_field(column: str) -> pl.Expr:
    """One Texas OIG workbook column, whitespace-trimmed with blank as null."""
    cleaned = pl.col(column).cast(pl.Utf8).str.replace_all(r"\s+", " ").str.strip_chars()
    return pl.when(cleaned == "").then(None).otherwise(cleaned)


def _fl_field(column: str) -> pl.Expr:
    """Unwrap one Excel-CSV-wrapped FLMMIS column: strip the `="..."` wrapper,
    collapse the source's column-padding whitespace, and map blank to null so a
    missing NPI reads as null rather than as an empty string.
    """
    cleaned = (
        pl.col(column)
        .str.replace_all(_EXCEL_WRAPPER, "")
        .str.replace_all(r"\s+", " ")
        .str.strip_chars()
    )
    return pl.when(cleaned == "").then(None).otherwise(cleaned)


class StateMedicaidConnector(Connector):
    expected_columns = frozenset(_SCHEMA.keys())

    def __init__(self, jurisdiction: str) -> None:
        if jurisdiction not in _JURISDICTIONS:
            raise ValueError(f"unknown state_medicaid jurisdiction: {jurisdiction!r}")
        self.jurisdiction = jurisdiction
        self.source_id = f"state_medicaid_{jurisdiction.lower()}"

    def fetch(self, cfg: SourceConfig) -> Path:
        cfg.raw_dir.mkdir(parents=True, exist_ok=True)
        suffix = "xls" if self.jurisdiction == "TX" else "csv"
        out_path = cfg.raw_dir / f"{self.source_id}_raw.{suffix}"
        if self.jurisdiction == "CA":
            self._fetch_ca(out_path)
        elif self.jurisdiction == "FL":
            self._fetch_fl(out_path)
        else:
            self._fetch_tx(out_path)
        return out_path

    def _fetch_fl(self, out_path: Path) -> None:
        """Download the FLMMIS Provider Master List ZIP and extract its single
        CSV member.

        The ZIP is opened and its member list checked *before* anything is
        written: the D21 "malformed CSV" finding was a truncated download being
        parsed as though it were complete, and a short read of a ZIP fails
        loudly here (`BadZipFile`) instead of silently downstream.
        """
        with httpx.Client(timeout=180.0, follow_redirects=True) as client:
            response = client.get(_FL_PML_ZIP_URL)
            response.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            members = [n for n in archive.namelist() if n.lower().endswith(".csv")]
            if len(members) != 1:
                raise ValueError(
                    f"FLMMIS PML ZIP held {len(members)} CSV members, expected exactly 1: "
                    f"{sorted(archive.namelist())}"
                )
            out_path.write_bytes(archive.read(members[0]))
        logger.info(
            "state_medicaid.fetch complete",
            jurisdiction="FL",
            member=members[0],
            bytes=out_path.stat().st_size,
        )

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

    def _fetch_tx(self, out_path: Path) -> None:
        """Download the Texas HHSC OIG exclusions workbook via OpenSanctions.

        Both official OIG hosts are unreachable (see module docstring), so this
        takes the `source.xls` artifact OpenSanctions mirrors from the OIG —
        the publisher's own file, not a re-derived one. The artifact URL embeds
        the mirror run's timestamp, so it is resolved from the catalog index
        each run; hardcoding it would break on the next refresh.
        """
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            index = client.get(_TX_CATALOG_INDEX)
            index.raise_for_status()
            resources = index.json()["resources"]
            resource = next(
                (r for r in resources if r["name"] == _TX_SOURCE_RESOURCE), None
            )
            if resource is None:
                raise ValueError(
                    f"OpenSanctions catalog no longer publishes {_TX_SOURCE_RESOURCE!r}; "
                    f"available: {sorted(r['name'] for r in resources)}"
                )
            response = client.get(resource["url"])
            response.raise_for_status()
            out_path.write_bytes(response.content)
        logger.info(
            "state_medicaid.fetch complete",
            jurisdiction="TX",
            resolved_url=resource["url"],
            bytes=out_path.stat().st_size,
        )

    def parse(self, raw: Path) -> pl.DataFrame:
        if raw.stat().st_size == 0:
            return pl.DataFrame(schema=_SCHEMA)
        if self.jurisdiction == "CA":
            return self._parse_ca(raw)
        if self.jurisdiction == "FL":
            return self._parse_fl(raw)
        return self._parse_tx(raw)

    def _parse_tx(self, raw: Path) -> pl.DataFrame:
        """Map the Texas OIG exclusions workbook, keeping only live exclusions.

        `ReinstatedDate` is the trap here: ~11% of rows are providers who were
        excluded and have since been reinstated. They are history, not current
        exclusions, and carrying them would manufacture false positives against
        providers in good standing.
        """
        sheets = pl.read_excel(raw, sheet_id=0, infer_schema_length=0)
        if len(sheets) != 1:
            raise ValueError(
                f"TX exclusions workbook held {len(sheets)} sheets, expected exactly 1: "
                f"{sorted(sheets)}"
            )
        df = next(iter(sheets.values()))

        current = df.filter(_tx_field("ReinstatedDate").is_null())
        individual = pl.concat_str(
            [_tx_field("FirstName"), _tx_field("MidInitial"), _tx_field("LastName")],
            separator=" ",
            ignore_nulls=True,
        )
        mapped = current.select(
            # 3.9% of rows are companies and carry no personal-name fields.
            pl.coalesce(_tx_field("CompanyName"), individual).alias("provider_name"),
            _tx_field("NPI").alias("npi"),
            # Not a Medicaid provider number — this file doesn't carry one. See
            # the `state_provider_number` entry in known_limitations.
            _tx_field("LicenseNumber").alias("state_provider_number"),
            # This source has no address column at all.
            pl.lit(None, dtype=pl.Utf8).alias("address"),
            _tx_field("Occupation").alias("provider_type"),
            _tx_field("StartDate")
            .str.head(10)
            .str.strptime(pl.Date, "%Y-%m-%d", strict=False)
            .alias("action_date"),
            pl.lit("TX").alias("jurisdiction"),
            pl.lit(ExclusionAuthority.STATE_MEDICAID.value).alias("exclusion_authority"),
        ).filter(pl.col("provider_name").is_not_null())

        logger.info(
            "state_medicaid.tx_parsed",
            rows_scanned=df.height,
            reinstated_excluded=df.height - current.height,
            current_exclusions=mapped.height,
            with_npi=mapped.filter(pl.col("npi").is_not_null()).height,
            with_action_date=mapped.filter(pl.col("action_date").is_not_null()).height,
        )
        return mapped

    def _parse_fl(self, raw: Path) -> pl.DataFrame:
        """Filter the FLMMIS Provider Master List to Ineligible (`E`) providers.

        `read_csv` is deliberately strict — it parses this file's 458,905 rows
        cleanly today, and hard rule 7 wants a future ragged revision to raise
        rather than be quietly repaired by a tolerant reader.
        """
        df = pl.read_csv(raw, infer_schema_length=0, encoding="utf8-lossy").rename(str.strip)
        excluded = df.filter(pl.col(_FL_STATUS_COL).str.strip_chars() == _FL_INELIGIBLE)

        mapped = excluded.select(
            _fl_field("Provider Name").alias("provider_name"),
            _fl_field("NPI").alias("npi"),
            _fl_field("Florida Medicaid Provider ID").alias("state_provider_number"),
            pl.concat_str(
                [
                    _fl_field("Service Location Address 1"),
                    _fl_field("Service Location Address 2"),
                    _fl_field("Service Location Address City"),
                    _fl_field("Service Location Address State"),
                    _fl_field("Service Location Address zip+4"),
                ],
                separator=", ",
                ignore_nulls=True,
            ).alias("address"),
            # The raw type code, not a label: there is no code->name lookup
            # published with this file and inventing one is hard rule 2.
            _fl_field("Provider Type Code").alias("provider_type"),
            # This file records enrollment-eligibility dates, not a termination
            # or action date. Mapping one to the other would assert a semantic
            # the source never states, so action_date stays null.
            pl.lit(None, dtype=pl.Date).alias("action_date"),
            pl.lit("FL").alias("jurisdiction"),
            pl.lit(ExclusionAuthority.STATE_MEDICAID.value).alias("exclusion_authority"),
        )

        # One provider ID can carry several `E` rows — separate NPI/enrollment
        # segments for the same provider (verified live: 14 such IDs, none with
        # a differing service address). Two distinct shapes, collapsed
        # differently on purpose:
        #   - a null-NPI row shadowing a real-NPI row for the same provider:
        #     drop the null one, it adds nothing the other doesn't carry;
        #   - a provider listed under two *different* real NPIs: keep both.
        #     No provider in the current file is (verified live: 0), but
        #     deduping on provider id alone would silently discard a stated
        #     identifier if one ever were, and this costs nothing to get right.
        # `unique()` then collapses rows that are identical in every field.
        deduped = mapped.filter(
            pl.col("npi").is_not_null()
            | pl.col("npi").is_null().all().over("state_provider_number")
        ).unique(maintain_order=True)
        if deduped.height < mapped.height:
            logger.info(
                "state_medicaid.fl_deduplicated",
                rows_in=mapped.height,
                rows_out=deduped.height,
                reason="redundant E rows per provider id, same service location",
            )
        logger.info(
            "state_medicaid.fl_parsed",
            rows_scanned=df.height,
            ineligible=deduped.height,
            with_npi=deduped.filter(pl.col("npi").is_not_null()).height,
        )
        return deduped

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
            "state exclusion is a SECONDARY label set — do not pool with federal "
            "LEIE/DOJ into one precision number (CLAUDE.md Amendment 1)",
        ]
        if self.jurisdiction == "FL":
            with_npi = (
                df.filter(pl.col("npi").is_not_null()).height if "npi" in df.columns else 0
            )
            known_limitations += [
                "derived from the FLMMIS Provider Master List, an enrollment file, "
                "not a published sanctions list: the exclusion signal is "
                "Current Medicaid Enrollment Status == 'E' (Ineligible)",
                "the source states no reason for ineligibility, so these rows may be "
                "administrative (e.g. failure to revalidate) rather than "
                "fraud-related — weight below a federal OIG exclusion "
                "(CLAUDE.md Amendment 1)",
                "action_date is always null: the file carries enrollment-eligibility "
                "dates only, never a termination or action date",
                "provider_type is the raw FLMMIS Provider Type Code; no code->name "
                "lookup is published with the file and none is invented (hard rule 2)",
                f"npi is present on {with_npi} of {df.height} rows; rows without one "
                "must never auto-link (CLAUDE.md Amendment 1)",
                "AHCA's own sanctions list at ahca.myflorida.com remains "
                "Cloudflare-blocked; this portal.flmmis.com file is a different "
                "source with different semantics, not a mirror of it",
            ]
        elif self.jurisdiction == "CA":
            known_limitations.append(
                "npi is always null for this source; auto-link is prohibited for any "
                "match lacking an exact identifier (CLAUDE.md Amendment 1)"
            )
        elif self.jurisdiction == "TX":
            with_npi = (
                df.filter(pl.col("npi").is_not_null()).height if "npi" in df.columns else 0
            )
            known_limitations += [
                "obtained via OpenSanctions, which mirrors the Texas OIG's own "
                "source.xls — both official OIG hosts are unreachable "
                "(oig.hhs.texas.gov WAF-blocks, oig.hhsc.state.tx.us times out at "
                "TCP). The publisher is the OIG; OpenSanctions is only the "
                "access provider",
                "OpenSanctions data is CC-BY-NC 4.0: free for this project's "
                "academic/research use, but COMMERCIAL use of this source would "
                "require a paid licence. Phase 2 must re-source it if that changes",
                f"npi is present on only {with_npi} of {df.height} rows "
                f"({100 * with_npi / df.height:.1f}%) — far sparser than FL; the "
                "great majority must route through entity resolution and may never "
                "auto-link (CLAUDE.md Amendment 1)",
                "address is always null: this source carries no address column, so "
                "these rows cannot contribute to address-cluster signals",
                "state_provider_number holds a professional LicenseNumber, NOT a "
                "Medicaid provider number — this file carries none. Do not compare "
                "it against FL/CA provider numbers",
                "reinstated providers are filtered out on parse (ReinstatedDate "
                "non-null); the workbook is a full history, not a current-state list",
                "~17% of rows are reason-coded 'Federal mandated exclusion' and are "
                "federal LEIE exclusions mirrored into the state list — they OVERLAP "
                "the leie source. Ground-truth work must dedupe against LEIE rather "
                "than count them as independent state evidence (Amendment 1)",
            ]
        source_url = {
            "CA": f"{_CA_CKAN_PACKAGE_SHOW}?id={_CA_DATASET_ID}",
            "FL": _FL_PML_ZIP_URL,
            "TX": _TX_CATALOG_INDEX,
        }[self.jurisdiction]
        return SourceManifest(
            source_id=self.source_id,
            dataset_name=_DATASET_NAMES[self.jurisdiction],
            original_publisher=_PUBLISHERS[self.jurisdiction],
            access_provider=_ACCESS_PROVIDERS.get(
                self.jurisdiction, _PUBLISHERS[self.jurisdiction]
            ),
            source_url=source_url,
            license_or_terms=(
                # The underlying records are a public-domain state government
                # work, but TX reaches us through OpenSanctions, whose
                # compilation is CC-BY-NC. The stricter term is the one that
                # binds, so it is the one recorded.
                "CC-BY-NC 4.0 (OpenSanctions compilation of a public-domain "
                "state government work) — non-commercial use only"
                if self.jurisdiction == "TX"
                else "public domain (state government work)"
            ),
            snapshot_date=date.today(),
            retrieved_at=datetime.now(UTC),
            checksum_sha256=checksum,
            schema_version="state-medicaid-v1",
            coverage={"jurisdiction": self.jurisdiction, "exclusion_authority": "state_medicaid"},
            freshness_status=FreshnessStatus.CURRENT,
            known_limitations=known_limitations,
            row_count=df.height,
        )
