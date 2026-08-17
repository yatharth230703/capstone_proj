"""Address-type classification via Google Maps Platform (M11, CLAUDE.md
Amendment 4(c)) — the "Physical Existence" signal `phase_1_build_plan.md`
Amendment 3 explicitly deferred to Phase 2, including the "facility-density
comparison" that amendment named by hand.

A deterministic tool, not an agent. `classify()` is pure: no I/O, no network,
no clock, no randomness — same response in, byte-identical classification out.
An LLM is never asked what kind of place an address is.

**Amendment 3 is not repealed.** `geographic_spread` keeps using the offline
ZCTA centroids (`entity_tools.zip_centroid`/`haversine_km`). Maps is used here
for one thing only: residential / mailbox-store / medical / commercial
discrimination.

Classification runs ONCE, offline, in `scripts/60_classify_addresses.py`, and
is persisted onto the `Address` node. It is never called from inside a signal
detector — an external rate-limited HTTP call inside the 4-way-concurrent
250-provider screening fan-out is the exact failure shape
`NOTES_API_DEVIATIONS.md` D23 documents.

## Why two calls, and why these two APIs — measured, not assumed (D25)

Three candidates were tested live against nine real addresses on 2026-08-18.

**Address Validation alone does not work.** `uspsData.dpvCmra` — the USPS
Commercial Mail Receiving Agency flag, the obvious mailbox-store
discriminator — is never returned on this project (`dpvFootnote` is `"A1"`,
ZIP+4 matched but delivery point unconfirmed, on every address tried).
`metadata` is frequently `{}`, including for a real suburban house, and where
populated reports `residential: false, business: true` for a Manhattan
apartment. It cannot tell a UPS Store from a hospital.

**Places API (New) is blocked** on this project (`403
API_KEY_SERVICE_BLOCKED`) and is not needed.

**What works is the pair below**, and it is what this module uses:

1. `addressvalidation.googleapis.com` → `result.geocode.location` (lat/lng).
   Used *only* as a geocoder; none of its metadata flags are trusted.
2. Legacy Places **Nearby Search** at that point with a small radius → the
   establishments actually at the address.

Real measured behaviour that makes this discriminate:

    suburban house, Burbank CA   ->  0 establishments within 40m
    hospital, Miami FL           -> 20 establishments, most typed `doctor`/`health`
    commercial strip, Berkeley   -> 20 establishments, none medical
    real cohort address (La Jolla) -> 18 establishments, 18 medical

`route`/`locality`/`political` results are returned alongside real POIs and are
NOT establishments — they are filtered on the presence of `"establishment"` in
`types`, which is what makes "zero establishments" a meaningful signal.

## The honest limitation, carried on every signal

**Establishment density is a proxy for land use, and it is weakest exactly
where population density is highest.** A Manhattan apartment sits inside a
dense commercial block and returns ~20 establishments, so it classifies
`commercial` — a false negative for residential. The signal is therefore
reliable for suburban and exurban addresses and weak in dense urban cores.
That is disclosed via `known_limitations` on every classification rather than
hidden, in the same spirit as Amendment 3's `centroid_precision_only`.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from specter.core.contracts import AddressClassification, LocationType, ScreeningThresholds

logger = structlog.get_logger(__name__)

_VALIDATE_URL = "https://addressvalidation.googleapis.com/v1:validateAddress"
_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
_TIMEOUT_SECONDS = 25.0

# Attached to every Maps-derived classification, mirroring Amendment 3's
# disclosure rule for `zcta_centroid`. Nobody visited these buildings.
CLASSIFICATION_LIMITATIONS = [
    "places_density_heuristic",
    "not_field_verified",
    "unreliable_in_dense_urban_cores",
]


def build_address_line(
    street_number: str | None,
    street_name: str | None,
    street_type: str | None,
    city: str | None,
    state: str | None,
    zip5: str | None,
) -> str:
    """Reassemble an `Address` node's components into one query line. Pure.

    Unit/suite is deliberately absent — it is excluded from `normalized_key`
    (CLAUDE.md, address normalization) and lives on the `LOCATED_AT` edge, not
    the node. Building granularity is the right level for this signal anyway.
    """
    street = " ".join(p for p in (street_number, street_name, street_type) if p)
    tail = " ".join(p for p in (state, zip5) if p)
    return ", ".join(p for p in (street, city, tail) if p)


def _post_json(url: str, api_key: str, payload: dict[str, Any], label: str) -> dict[str, Any]:
    response = httpx.post(url, params={"key": api_key}, json=payload, timeout=_TIMEOUT_SECONDS)
    if response.status_code != 200:
        raise RuntimeError(f"{label} returned {response.status_code}: {response.text[:300]}")
    decoded: dict[str, Any] = response.json()
    return decoded


def fetch_address_record(
    address_line: str, api_key: str, radius_m: int
) -> dict[str, Any]:
    """Both live calls for one address, returned as one record so a single
    stored `EvidenceArtifact` holds the complete provenance of the verdict.

    Raises on any non-200 and on any Places `status` that is neither `OK` nor
    `ZERO_RESULTS` (CLAUDE.md hard rule 7 — a quota or auth failure must stop
    the batch, not quietly classify 7,000 addresses as `unclassified`).
    `ZERO_RESULTS` is a real answer here, and an important one: it is what a
    genuinely residential address looks like.
    """
    validation = _post_json(
        _VALIDATE_URL,
        api_key,
        {"address": {"regionCode": "US", "addressLines": [address_line]}},
        "Address Validation API",
    )
    location = (
        validation.get("result", {}).get("geocode", {}).get("location")
        if isinstance(validation.get("result"), dict)
        else None
    )
    nearby: dict[str, Any] = {"status": "NO_GEOCODE", "results": []}
    if isinstance(location, dict) and "latitude" in location:
        response = httpx.get(
            _NEARBY_URL,
            params={
                "location": f"{location['latitude']},{location['longitude']}",
                "radius": radius_m,
                "key": api_key,
            },
            timeout=_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Places Nearby Search returned {response.status_code}: {response.text[:300]}"
            )
        nearby = response.json()
        status = nearby.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            raise RuntimeError(
                f"Places Nearby Search status={status!r} for {address_line!r}: "
                f"{nearby.get('error_message', '')}"
            )
    return {"address_validation": validation, "nearby": nearby, "radius_m": radius_m}


def _establishments(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Real POIs only. Nearby Search also returns `route`/`locality`/
    `political` entries for the surrounding street and city; counting those
    would make every address look occupied and destroy the zero-establishment
    signal that identifies a residence.
    """
    results = record.get("nearby", {}).get("results", [])
    if not isinstance(results, list):
        return []
    return [
        r
        for r in results
        if isinstance(r, dict) and "establishment" in (r.get("types") or [])
    ]


def classify(
    normalized_key: str, record: dict[str, Any], thresholds: ScreeningThresholds
) -> AddressClassification:
    """Pure. Map a fetched record onto a `LocationType`.

    Precedence, strongest evidence first:

    1. No geocode at all -> `unclassified`. A fabricated street (every
       synthetic scenario address) lands here, which is correct.
    2. A mail-service establishment is present -> `mailbox_store`. Detected by
       the `post_office` place type OR a name matching one of the configured
       mail-service patterns. Both are needed: measured live, a UPS Authorized
       Shipping Outlet carries only `['establishment', 'point_of_interest']`
       and a PostNet only adds `store`, so the type alone misses most of them,
       while `post_office` alone would miss a real USPS branch's neighbours.
    3. Zero establishments -> `residential`. The load-bearing case.
    4. Any medical establishment -> `commercial_medical`. A DME supplier in a
       medical office building is the ordinary, innocent configuration.
    5. Establishments but none medical -> `commercial`.
    """
    establishments = _establishments(record)
    names = [str(e.get("name", "")).lower() for e in establishments]
    all_types = [set(e.get("types") or []) for e in establishments]
    has_geocode = (
        record.get("address_validation", {})
        .get("result", {})
        .get("geocode", {})
        .get("location")
        is not None
    )

    mail_patterns = [p.lower() for p in thresholds.physical_existence_mail_service_patterns]
    medical_types = set(thresholds.physical_existence_medical_place_types)

    location_type: LocationType
    if not has_geocode:
        location_type, reason = "unclassified", "address did not geocode"
    elif any("post_office" in t for t in all_types) or any(
        p in n for n in names for p in mail_patterns
    ):
        location_type, reason = "mailbox_store", "a mail-service establishment is present"
    elif not establishments:
        location_type, reason = (
            "residential",
            f"no establishment within {record.get('radius_m')}m",
        )
    elif any(medical_types & t for t in all_types):
        medical = sum(1 for t in all_types if medical_types & t)
        location_type, reason = (
            "commercial_medical",
            f"{medical}/{len(establishments)} nearby establishments are medical",
        )
    else:
        location_type, reason = (
            "commercial",
            f"{len(establishments)} nearby establishments, none medical",
        )

    limitations = list(CLASSIFICATION_LIMITATIONS)
    if record.get("nearby", {}).get("status") == "ZERO_RESULTS":
        limitations.append("zero_results_from_places")

    formatted = (
        record.get("address_validation", {})
        .get("result", {})
        .get("address", {})
        .get("formattedAddress")
    )
    return AddressClassification(
        normalized_key=normalized_key,
        location_type=location_type,
        matched_formatted_address=formatted if isinstance(formatted, str) else None,
        establishment_count=len(establishments),
        medical_establishment_count=sum(1 for t in all_types if medical_types & t),
        classification_reason=reason,
        known_limitations=limitations,
    )
