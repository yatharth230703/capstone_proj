"""Synthetic scenario generator (plan §5.5). Ten planted scenarios (S01-S10)
plus 150 benign controls that superficially resemble positives — without
these, precision numbers are meaningless and the Skeptic agent has nothing
to catch (plan's own framing).

Generation is deterministic (fixed `_SEED`), not fetched from anywhere —
`fetch()` generates rather than downloads, which is the honest reading of
`Connector.fetch()`'s contract for a locally-generated source.

Two connectors share one generator: `SyntheticProvidersConnector` (Provider-
shaped rows, NPPES-schema-compatible) and `SyntheticExclusionsConnector`
(the excluded peers that S05/S06/S10 need). Column shapes for each are
documented at the top of `_generate_providers`/`_generate_exclusions`.

Per-scenario signal mapping against the 9 real `signal_tools.py` detectors
(plan §8). **S01 gained a detector in M11** — `physical_existence`, the Maps
address-type classifier CLAUDE.md Amendment 3 deferred and Amendment 4(c)
authorized — so it is no longer signal-less. **S08 still is**: no utilization
data exists in Phase 1 (plan's own admission in §15: "S08 missed because
Phase 1 has no utilization data"), and a test asserting *no* signal fires is
the correct test for it, not a bug to work around.

    S01 shell-at-residential      -> physical_existence  (M11; real addresses)
    S02 shared phone               -> phone_degree
    S03 address cluster            -> address_degree, enumeration_burst
    S04 officer reuse              -> officer_degree
    S05 near an excluded peer      -> exclusion_proximity
    S06 phoenix entity             -> phoenix_pattern
    S07 rapid address churn        -> address_churn
    S08 dormant reactivation       -> (none — no utilization data, by design)
    S09 geographic implausibility  -> geographic_spread
    S10 dense excluded community   -> community_exclusion_density
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import structlog

from specter.core.contracts import SourceConfig, SourceManifest, ValidationReport
from specter.core.enums import FreshnessStatus, Verdict
from specter.ingest.base import Connector

logger = structlog.get_logger(__name__)

GENERATOR_VERSION = "1.0.0"
# Anchored to generation time, not a fixed calendar date: signals like
# address_churn/enumeration_burst/phoenix_pattern check trailing windows
# relative to "now", so a hardcoded past date would silently drift these
# scenarios out of their own detection windows as real time passes.
_SEED_DATE = date.today()

_PROVIDER_COLUMNS = frozenset(
    {
        "npi", "organization_name", "entity_type", "state", "enumeration_date",
        "last_updated", "status", "address_1", "city", "postal_code",
        "telephone_number", "authorized_official_first_name",
        "authorized_official_last_name", "taxonomy_code", "taxonomy_desc",
        "latitude", "longitude", "scenario_id", "generator_version",
        "expected_signals", "prior_addresses", "first_activity_date",
    }
)
_EXCLUSION_COLUMNS = frozenset({"bus_name", "npi", "excl_date", "scenario_id", "generator_version"})


def _npi(block: int, index: int) -> str:
    """Deterministic fake NPI. Real NPIs always start with 1 or 2 (CMS
    spec) — starting with 9 guarantees zero collision with real data and is
    self-documenting as synthetic.
    """
    return f"9{block:02d}{index:07d}"


def _base_provider(
    npi: str,
    name: str,
    address_1: str,
    city: str,
    state: str,
    zip5: str,
    phone: str,
    officer_first: str,
    officer_last: str,
    enumeration_date: date,
    scenario_id: str | None,
    expected_signals: list[str],
    latitude: float | None = None,
    longitude: float | None = None,
    prior_addresses: list[dict[str, str]] | None = None,
    first_activity_date: date | None = None,
) -> dict[str, Any]:
    return {
        "npi": npi,
        "organization_name": name,
        "entity_type": "organization",
        "state": state,
        "enumeration_date": enumeration_date.isoformat(),
        "last_updated": enumeration_date.isoformat(),
        "status": "A",
        "address_1": address_1,
        "city": city,
        "postal_code": zip5,
        "telephone_number": phone,
        "authorized_official_first_name": officer_first,
        "authorized_official_last_name": officer_last,
        "taxonomy_code": "332B00000X",
        "taxonomy_desc": "Durable Medical Equipment & Medical Supplies",
        "latitude": latitude,
        "longitude": longitude,
        "scenario_id": scenario_id,
        "generator_version": GENERATOR_VERSION,
        "expected_signals": expected_signals,
        "prior_addresses": json.dumps(prior_addresses or []),
        "first_activity_date": first_activity_date.isoformat() if first_activity_date else None,
    }


# Real single-family residential addresses in the Miami area, used by S01.
#
# M11 (BUILD_MILESTONES.md D-26, operator-approved) replaced the previous
# fabricated streets (`"{100+i} Residential Ct Apt {i}", Miami FL 33101`).
# Those did not geocode, so the address-type classifier M11 shipped returned
# `unclassified` and S01 — the one scenario planted specifically for that
# classifier — could never fire.
#
# The *street* is real; the *provider* is not. `data_origin` stays `synthetic`
# on every Provider and Address node generated here, and the Maps artifact
# describing the street is `public` evidence about a real place. That split is
# the honest one and it is exactly what CLAUDE.md hard rule 5 asks for —
# labelled, not merged.
#
# Each was verified live against the real classifier on 2026-08-18 and returned
# `residential` with **0 establishments within 50m**. Candidates that came back
# `commercial`/`commercial_medical` were discarded rather than forced. If Google's
# data shifts and one of these stops classifying residential, that is a real
# change to observe, not something to paper over — re-verify, don't re-pick to
# preserve a passing test.
_S01_ADDRESSES: list[tuple[str, str, str]] = [
    ("7920 SW 102nd St", "Miami", "33173"),
    ("1145 NE 96th St", "Miami Shores", "33138"),
    ("8330 SW 142nd Ave", "Miami", "33183"),
    ("630 NE 92nd St", "Miami Shores", "33138"),
    ("1250 NE 103rd St", "Miami Shores", "33138"),
]


def _scenario_01(rows: list[dict[str, Any]]) -> None:
    """Shell providers at real residential addresses — each isolated, no
    sharing with anything. Every *structural* detector (degree, burst, churn,
    proximity) must stay silent; the only thing that should fire is M11's
    `physical_existence`, which is the whole point of the scenario.
    """
    for i, (street, city, zip5) in enumerate(_S01_ADDRESSES):
        rows.append(
            _base_provider(
                _npi(1, i), f"S01 Shell Provider {i}", street,
                city, "FL", zip5, f"305555{1000 + i:04d}", "Pat", f"Resident{i}",
                _SEED_DATE, "S01", ["physical_existence"],
            )
        )


def _scenario_02(rows: list[dict[str, Any]]) -> None:
    """5 providers sharing one phone number -> phone_degree."""
    shared_phone = "3055559000"
    for i in range(5):
        rows.append(
            _base_provider(
                _npi(2, i), f"S02 Shared Phone Provider {i}", f"{200 + i} Commerce Way",
                "Houston", "TX", "77002", shared_phone, f"Officer{i}", f"S02Last{i}",
                _SEED_DATE, "S02", ["phone_degree"],
            )
        )


def _scenario_03(rows: list[dict[str, Any]]) -> None:
    """8 providers at one address, all enumerated within a 90-day window ->
    address_degree AND enumeration_burst.
    """
    for i in range(8):
        rows.append(
            _base_provider(
                _npi(3, i), f"S03 Cluster Provider {i}", "8000 Synthetic Cluster Plaza",
                "Miami", "FL", "33199", f"305555{2000 + i:04d}", f"Officer{i}", f"S03Last{i}",
                _SEED_DATE - timedelta(days=70) + timedelta(days=i * 10), "S03",
                ["address_degree", "enumeration_burst"],
            )
        )


def _scenario_04(rows: list[dict[str, Any]]) -> None:
    """4 orgs sharing one officer -> officer_degree."""
    for i in range(4):
        rows.append(
            _base_provider(
                _npi(4, i), f"S04 Officer Reuse Org {i}", f"{400 + i} Startup Blvd",
                "Austin", "TX", "78701", f"512555{4000 + i:04d}", "Repeat", "Incorporator",
                _SEED_DATE + timedelta(days=i * 20), "S04", ["officer_degree"],
            )
        )


def _scenario_05(rows: list[dict[str, Any]], exclusions: list[dict[str, Any]]) -> None:
    """A flagged provider shares an address with a directly-excluded peer:
    Flagged -[LOCATED_AT]-> Address <-[LOCATED_AT]- ExcludedPeer
    -[EXCLUDED_BY]-> Exclusion. 3 hops, within the <=3 threshold.
    """
    shared_address = "975 BAPTIST WY"
    flagged_npi = _npi(5, 0)
    excluded_npi = _npi(5, 1)
    rows.append(
        _base_provider(
            flagged_npi, "S05 Flagged Provider", shared_address, "Miami", "FL", "33033",
            "3055559100", "Alex", "Flagged", _SEED_DATE, "S05", ["exclusion_proximity"],
        )
    )
    rows.append(
        _base_provider(
            excluded_npi, "S05 Excluded Peer", shared_address, "Miami", "FL", "33033",
            "3055559101", "Sam", "Excluded", _SEED_DATE, "S05", [],
        )
    )
    exclusions.append(
        {
            "bus_name": "S05 Excluded Peer",
            "npi": excluded_npi,
            "excl_date": (_SEED_DATE - timedelta(days=200)).isoformat(),
            "scenario_id": "S05",
            "generator_version": GENERATOR_VERSION,
        }
    )


def _scenario_06(rows: list[dict[str, Any]], exclusions: list[dict[str, Any]]) -> None:
    """A new org shares address+officer with an org excluded <24 months
    prior -> phoenix_pattern.
    """
    shared_address = "6595 NW 36TH ST"
    excluded_npi = _npi(6, 0)
    new_npi = _npi(6, 1)
    exclusion_date = _SEED_DATE - timedelta(days=200)  # ~6.5 months before enumeration
    rows.append(
        _base_provider(
            excluded_npi, "S06 Excluded Predecessor Org", shared_address, "Miami", "FL",
            "33166", "3055559200", "Pat", "Phoenix", exclusion_date - timedelta(days=365),
            "S06", [],
        )
    )
    rows.append(
        _base_provider(
            new_npi, "S06 Phoenix Successor Org", shared_address, "Miami", "FL", "33166",
            "3055559201", "Pat", "Phoenix", exclusion_date + timedelta(days=30), "S06",
            ["phoenix_pattern"],
        )
    )
    exclusions.append(
        {
            "bus_name": "S06 Excluded Predecessor Org",
            "npi": excluded_npi,
            "excl_date": exclusion_date.isoformat(),
            "scenario_id": "S06",
            "generator_version": GENERATOR_VERSION,
        }
    )


def _scenario_07(rows: list[dict[str, Any]]) -> None:
    """One provider with 4 addresses over the trailing 12 months (3 changes)
    -> address_churn.
    """
    npi = _npi(7, 0)
    addresses = [
        {"address_1": "10 First Move St", "city": "Dallas", "state": "TX", "zip5": "75201",
         "changed_at": (_SEED_DATE - timedelta(days=300)).isoformat()},
        {"address_1": "20 Second Move Ave", "city": "Dallas", "state": "TX", "zip5": "75202",
         "changed_at": (_SEED_DATE - timedelta(days=200)).isoformat()},
        {"address_1": "30 Third Move Rd", "city": "Dallas", "state": "TX", "zip5": "75203",
         "changed_at": (_SEED_DATE - timedelta(days=100)).isoformat()},
    ]
    rows.append(
        _base_provider(
            npi, "S07 Address Churn Provider", "40 Fourth Move Ln", "Dallas", "TX", "75204",
            "2145559300", "Chase", "Address", _SEED_DATE, "S07", ["address_churn"],
            prior_addresses=addresses,
        )
    )


def _scenario_08(rows: list[dict[str, Any]]) -> None:
    """Long enumeration-to-first-activity gap. No utilization data in Phase
    1 -> deliberately no detector, deliberately no expected signal.
    """
    npi = _npi(8, 0)
    rows.append(
        _base_provider(
            npi, "S08 Dormant Reactivation Provider", "50 Sleepy Hollow Dr", "Orlando",
            "FL", "32801", "4075559400", "Rip", "VanWinkle", _SEED_DATE - timedelta(days=2000),
            "S08", [], first_activity_date=_SEED_DATE,
        )
    )


def _scenario_09(rows: list[dict[str, Any]]) -> None:
    """Same officer, two orgs >1500km apart -> geographic_spread."""
    officer_first, officer_last = "Roam", "Ing"
    rows.append(
        _base_provider(
            _npi(9, 0), "S09 Miami Org", "60 Ocean Dr", "Miami", "FL", "33139",
            "3055559500", officer_first, officer_last, _SEED_DATE, "S09",
            ["geographic_spread"], latitude=25.7617, longitude=-80.1918,
        )
    )
    rows.append(
        _base_provider(
            _npi(9, 1), "S09 LA Org", "70 Sunset Blvd", "Los Angeles", "CA", "90028",
            "3235559501", officer_first, officer_last, _SEED_DATE, "S09",
            ["geographic_spread"], latitude=34.0522, longitude=-118.2437,
        )
    )


def _scenario_10(rows: list[dict[str, Any]], exclusions: list[dict[str, Any]]) -> None:
    """Two 3-provider address cliques bridged by one shared officer (6
    providers total, none crossing address_degree/officer_degree thresholds
    individually), 2 of the 6 excluded -> community_exclusion_density
    (2/6 = 0.33, above the 0.15 threshold) without also tripping the
    address/officer degree signals.
    """
    address_a, address_b = "80 Cluster Ave", "81 Cluster Ave"
    npis = [_npi(10, i) for i in range(6)]
    # Bridge officer: identical (first, last) on provider index 2 (Group A)
    # and provider index 3 (Group B) so they resolve to the same Officer
    # node and connect the two address cliques.
    bridge_first, bridge_last = "Bridge", "Officer"
    for i in range(3):
        officer_first, officer_last = (bridge_first, bridge_last) if i == 2 else (f"A{i}", "GroupA")
        rows.append(
            _base_provider(
                npis[i], f"S10 Group A Provider {i}", address_a, "San Diego", "CA", "92101",
                f"619555{6000 + i:04d}", officer_first, officer_last,
                _SEED_DATE, "S10", ["community_exclusion_density"] if i == 0 else [],
            )
        )
    for i in range(3):
        officer_first, officer_last = (bridge_first, bridge_last) if i == 0 else (f"B{i}", "GroupB")
        rows.append(
            _base_provider(
                npis[3 + i], f"S10 Group B Provider {i}", address_b, "San Diego", "CA",
                "92102", f"619555{6100 + i:04d}", officer_first, officer_last,
                _SEED_DATE, "S10", [],
            )
        )
    for i in (0, 3):
        exclusions.append(
            {
                "bus_name": f"S10 Excluded Member {i}",
                "npi": npis[i],
                "excl_date": (_SEED_DATE - timedelta(days=150)).isoformat(),
                "scenario_id": "S10",
                "generator_version": GENERATOR_VERSION,
            }
        )


def _benign_controls(rows: list[dict[str, Any]]) -> None:
    """150 benign controls that superficially resemble positives without
    actually being anomalous. Without these, precision is meaningless.
    """
    # 75: legitimate multi-tenant medical building — high address degree,
    # but a stable, multi-year enumeration spread (not a burst).
    building_address = "9000 Medical Plaza Dr"
    for i in range(75):
        rows.append(
            _base_provider(
                _npi(90, i), f"Benign Building Tenant {i}", building_address, "Tampa",
                "FL", "33602", f"813555{7000 + i:04d}", f"Tenant{i}", f"Physician{i}",
                _SEED_DATE - timedelta(days=i * 60), None, [],
            )
        )
    # 75: legitimate multi-site chain — officer reuse, but old and stable
    # (incorporated years apart, not rapid).
    chain_officer_first, chain_officer_last = "Chain", "Owner"
    for i in range(75):
        rows.append(
            _base_provider(
                _npi(91, i), f"Benign Chain Site {i}", f"{9100 + i} Franchise Row",
                "Sacramento", "CA", "95814", f"916555{7500 + i:04d}",
                chain_officer_first, chain_officer_last,
                _SEED_DATE - timedelta(days=i * 120), None, [],
            )
        )


def _generate_providers() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    _scenario_01(rows)
    _scenario_02(rows)
    _scenario_03(rows)
    _scenario_04(rows)
    _scenario_05(rows, exclusions)
    _scenario_06(rows, exclusions)
    _scenario_07(rows)
    _scenario_08(rows)
    _scenario_09(rows)
    _scenario_10(rows, exclusions)
    _benign_controls(rows)
    return rows


def _generate_exclusions() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    _scenario_05([], exclusions)
    _scenario_06([], exclusions)
    _scenario_10([], exclusions)
    rows.extend(exclusions)
    return rows


class SyntheticProvidersConnector(Connector):
    source_id = "synthetic_providers"
    expected_columns = _PROVIDER_COLUMNS

    def fetch(self, cfg: SourceConfig) -> Path:
        cfg.raw_dir.mkdir(parents=True, exist_ok=True)
        out_path = cfg.raw_dir / "synthetic_providers_raw.jsonl"
        rows = _generate_providers()
        with out_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, sort_keys=True))
                f.write("\n")
        logger.info("synthetic_providers.fetch complete", row_count=len(rows))
        return out_path

    def parse(self, raw: Path) -> pl.DataFrame:
        rows = [json.loads(line) for line in raw.read_text().splitlines()]
        return pl.DataFrame(rows)

    def validate(self, df: pl.DataFrame) -> ValidationReport:
        missing_columns = sorted(self.expected_columns - set(df.columns))
        null_rates = (
            {col: df[col].null_count() / df.height for col in df.columns} if df.height else {}
        )
        verdict = Verdict.FAIL if missing_columns or df.height == 0 else Verdict.PASS_
        return ValidationReport(
            source_id=self.source_id, checked_at=datetime.now(UTC),
            missing_columns=missing_columns, schema_drift=[], null_rate_per_column=null_rates,
            duplicate_key_rate=0.0, row_count_delta=None, date_range_sanity_ok=True,
            verdict=verdict,
        )

    def build_manifest(
        self, cfg: SourceConfig, raw_path: Path, checksum: str, df: pl.DataFrame,
        report: ValidationReport,
    ) -> SourceManifest:
        return SourceManifest(
            source_id=self.source_id, dataset_name="Synthetic Scenario Providers",
            original_publisher="Project Specter (generated)",
            access_provider="ingest/synthetic.py", source_url="generated:local",
            license_or_terms="n/a (synthetic)", snapshot_date=date.today(),
            retrieved_at=datetime.now(UTC), checksum_sha256=checksum,
            schema_version=GENERATOR_VERSION,
            coverage={"scenarios": "S01-S10", "benign_controls": 150},
            freshness_status=FreshnessStatus.CURRENT,
            known_limitations=[
                "S01 (shell at residential address) and S08 (dormant reactivation) have no "
                "corresponding Phase 1 detector — no address-type classifier, no utilization "
                "data. expected_signals is deliberately empty for both."
            ],
            row_count=df.height,
        )


class SyntheticExclusionsConnector(Connector):
    source_id = "synthetic_exclusions"
    expected_columns = _EXCLUSION_COLUMNS

    def fetch(self, cfg: SourceConfig) -> Path:
        cfg.raw_dir.mkdir(parents=True, exist_ok=True)
        out_path = cfg.raw_dir / "synthetic_exclusions_raw.jsonl"
        rows = _generate_exclusions()
        with out_path.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, sort_keys=True))
                f.write("\n")
        logger.info("synthetic_exclusions.fetch complete", row_count=len(rows))
        return out_path

    def parse(self, raw: Path) -> pl.DataFrame:
        rows = [json.loads(line) for line in raw.read_text().splitlines()]
        return pl.DataFrame(rows)

    def validate(self, df: pl.DataFrame) -> ValidationReport:
        missing_columns = sorted(self.expected_columns - set(df.columns))
        verdict = Verdict.FAIL if missing_columns or df.height == 0 else Verdict.PASS_
        return ValidationReport(
            source_id=self.source_id, checked_at=datetime.now(UTC),
            missing_columns=missing_columns, schema_drift=[], null_rate_per_column={},
            duplicate_key_rate=0.0, row_count_delta=None, date_range_sanity_ok=True,
            verdict=verdict,
        )

    def build_manifest(
        self, cfg: SourceConfig, raw_path: Path, checksum: str, df: pl.DataFrame,
        report: ValidationReport,
    ) -> SourceManifest:
        return SourceManifest(
            source_id=self.source_id, dataset_name="Synthetic Scenario Exclusions",
            original_publisher="Project Specter (generated)",
            access_provider="ingest/synthetic.py", source_url="generated:local",
            license_or_terms="n/a (synthetic)", snapshot_date=date.today(),
            retrieved_at=datetime.now(UTC), checksum_sha256=checksum,
            schema_version=GENERATOR_VERSION, coverage={"scenarios": "S05, S06, S10"},
            freshness_status=FreshnessStatus.CURRENT, known_limitations=[],
            row_count=df.height,
        )
