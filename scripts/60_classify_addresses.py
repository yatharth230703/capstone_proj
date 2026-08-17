#!/usr/bin/env python
"""Batch address-type classifier (BUILD_MILESTONES.md M11, CLAUDE.md
Amendment 4(c)).

    python scripts/60_classify_addresses.py --limit 25          # cheap first pass
    python scripts/60_classify_addresses.py --screened-only     # the 244 demo cases
    python scripts/60_classify_addresses.py --limit 8000        # everything

Calls Google's Address Validation API once per unclassified `Address` node,
stores the raw response as an `EvidenceArtifact`, and writes `location_type`,
`location_type_source_id`, `location_type_reason` and `classified_at` back onto
the node. `tools/signal_tools.physical_existence` then reads those properties
with no network call at screening time.

Idempotent and resumable: the selection query skips anything already carrying a
`location_type`, and orders deterministically, so re-running after an
interruption picks up exactly where it stopped.

Only `data_origin='public'` addresses are classified. Synthetic addresses are
never sent to Google — they are fabricated streets Google cannot classify, and
storing a `public` Maps result against a `synthetic` provider would mix origins
inside one case packet, which CLAUDE.md hard rule 5 calls a hard failure.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import structlog
from neo4j import Driver, GraphDatabase

from specter.settings import Settings, get_settings
from specter.tools.evidence_tools import store_artifact
from specter.tools.maps_tools import build_address_line, classify, fetch_address_record
from specter.tools.signal_tools import load_thresholds

logger = structlog.get_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_EVIDENCE_DIR = _REPO_ROOT / "data" / "evidence"
_CASES_DIR = _REPO_ROOT / "data" / "cases"

# Deterministic ordering makes the run resumable and the `--limit` slice
# reproducible, the same discipline `workflow/state.cohort_select` uses.
_SELECT = """
MATCH (a:Address)
WHERE a.data_origin = 'public' AND a.location_type IS NULL
  AND a.street_number IS NOT NULL AND a.street_name IS NOT NULL
  AND a.zip5 IS NOT NULL
  AND ($keys IS NULL OR a.normalized_key IN $keys)
RETURN a.normalized_key AS normalized_key, a.street_number AS street_number,
       a.street_name AS street_name, a.street_type AS street_type,
       a.city AS city, a.state AS state, a.zip5 AS zip5
ORDER BY a.normalized_key
LIMIT $limit
"""

_WRITE = """
MATCH (a:Address {normalized_key: $normalized_key})
SET a.location_type = $location_type,
    a.location_type_source_id = $artifact_id,
    a.location_type_reason = $reason,
    a.establishment_count = $establishment_count,
    a.medical_establishment_count = $medical_establishment_count,
    a.classified_at = $classified_at
"""


def _confirm_maps_key_alive(settings: Settings) -> str:
    """Prove the credential with a real call before spending a batch on it —
    the same discipline `scripts/40_screen.py:_confirm_azure_key_alive` uses.
    A 250-address run that dies on address 1 with a 403 is cheap; one that dies
    at address 200 is not.
    """
    if settings.google_maps_api_key is None:
        raise RuntimeError(
            "GOOGLE_MAPS_API_KEY is not set. CLAUDE.md Amendment 4(c): this is a "
            "Maps Platform API key, NOT a role on the Vertex service account. "
            "Create one under APIs & Services -> Credentials and enable the "
            "Address Validation API on the project."
        )
    key = settings.google_maps_api_key.get_secret_value()
    record = fetch_address_record(
        "1600 Amphitheatre Parkway, Mountain View, CA 94043", key, 50
    )
    if "result" not in record["address_validation"]:
        raise RuntimeError(
            f"Maps key check returned 200 but no `result` block: {json.dumps(record)[:300]} — "
            "aborting before the batch starts, not partway through it."
        )
    return key


def _rows(driver: Driver, limit: int, keys: list[str] | None) -> list[dict[str, str | None]]:
    with driver.session() as session:
        return [dict(r) for r in session.run(_SELECT, limit=limit, keys=keys)]


def _screened_keys(driver: Driver) -> list[str]:
    """The addresses of the providers that already have a persisted CasePacket
    — the set the M14 dashboard will actually render, and so the cheapest path
    to a complete demo.
    """
    npis = sorted(p.stem for p in _CASES_DIR.glob("*.json"))
    if not npis:
        raise RuntimeError(
            f"--screened-only found no case packets in {_CASES_DIR}. Run "
            "`python scripts/40_screen.py --limit 250` first."
        )
    with driver.session() as session:
        return [
            r["key"]
            for r in session.run(
                """
                UNWIND $npis AS npi
                MATCH (:Provider {npi: npi})-[:LOCATED_AT]->(a:Address)
                RETURN DISTINCT a.normalized_key AS key
                """,
                npis=npis,
            )
        ]


def main(limit: int, screened_only: bool) -> None:
    settings = get_settings()
    print("Confirming Google Maps key is live...")
    api_key = _confirm_maps_key_alive(settings)
    print("Maps key OK.")

    thresholds = load_thresholds(_REPO_ROOT / "config" / "screening.yaml")
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )
    try:
        keys = _screened_keys(driver) if screened_only else None
        rows = _rows(driver, limit, keys)
        print(f"selected={len(rows)} addresses to classify")

        counts: dict[str, int] = {}
        for i, row in enumerate(rows, start=1):
            address_line = build_address_line(
                row["street_number"], row["street_name"], row["street_type"],
                row["city"], row["state"], row["zip5"],
            )
            try:
                record = fetch_address_record(
                    address_line, api_key, thresholds.physical_existence_radius_m
                )
            except httpx.HTTPError as exc:
                # Fail loudly (hard rule 7). A transport failure mid-batch must
                # stop the run — everything classified so far is already
                # committed, and the `location_type IS NULL` filter makes the
                # re-run resume rather than redo.
                raise RuntimeError(
                    f"Maps call failed at address {i}/{len(rows)} "
                    f"({row['normalized_key']}): {exc}"
                ) from exc

            # `sort_keys=True` so the stored artifact — and therefore its
            # content-addressed artifact_id — is stable across runs. The queried
            # line is included so two addresses with identical API responses
            # still produce distinct artifacts.
            content = json.dumps(
                {"queried_address": address_line, "response": record}, sort_keys=True, indent=2
            )
            artifact = store_artifact(
                content=content,
                content_type="application/json",
                source_id=f"maps:{row['normalized_key']}",
                evidence_dir=_EVIDENCE_DIR,
                extraction_method="google_maps_validation_plus_nearby",
            )
            classification = classify(str(row["normalized_key"]), record, thresholds)

            with driver.session() as session:
                session.run(
                    _WRITE,
                    normalized_key=row["normalized_key"],
                    location_type=classification.location_type,
                    artifact_id=artifact.artifact_id,
                    reason=classification.classification_reason,
                    establishment_count=classification.establishment_count,
                    medical_establishment_count=classification.medical_establishment_count,
                    classified_at=datetime.now(UTC).isoformat(),
                )
            counts[classification.location_type] = (
                counts.get(classification.location_type, 0) + 1
            )
            logger.info(
                "maps.classified",
                normalized_key=row["normalized_key"],
                location_type=classification.location_type,
                reason=classification.classification_reason,
                establishment_count=classification.establishment_count,
                medical_establishment_count=classification.medical_establishment_count,
            )

        print(f"classified={sum(counts.values())}")
        for location_type, count in sorted(counts.items(), key=lambda kv: -kv[1]):
            print(f"  {location_type}: {count}")
    finally:
        driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit", type=int, default=25, help="max addresses to classify this run"
    )
    parser.add_argument(
        "--screened-only",
        action="store_true",
        help="only the addresses of providers with a persisted CasePacket",
    )
    args = parser.parse_args()
    main(args.limit, args.screened_only)
