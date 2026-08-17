"""Address-type classification via Google Maps Platform (M11, CLAUDE.md
Amendment 4(c)) — the "Physical Existence" signal `phase_1_build_plan.md`
Amendment 3 explicitly deferred to Phase 2.

A deterministic tool, not an agent. `classify()` is pure: no I/O, no network,
no clock, no randomness — same response in, byte-identical classification out.
An LLM is never asked what kind of place an address is.

**Amendment 3 is not repealed.** `geographic_spread` keeps using the offline
ZCTA centroids (`entity_tools.zip_centroid`/`haversine_km`). Maps is used here
for one thing only: residential / mailbox-store / commercial discrimination.

Classification runs ONCE, offline, in `scripts/60_classify_addresses.py`, and
is persisted onto the `Address` node. It is never called from inside a signal
detector — an external rate-limited HTTP call inside the 4-way-concurrent
250-provider screening fan-out is the exact failure shape
`NOTES_API_DEVIATIONS.md` D23 documents.

## ⚠ THIS MODULE IS SUPERSEDED PENDING A REWRITE — read `NOTES_API_DEVIATIONS.md` D25

It was written against the Address Validation API before a key existed. **The
key now exists and the API was measured live on 2026-08-18. It does not
deliver the discriminator this signal needs.** Specifically, across nine real
addresses:

- `uspsData.dpvCmra` — the USPS Commercial Mail Receiving Agency flag this
  module treats as its strongest evidence — **is never returned at all.** The
  `uspsData` block contains only `cassProcessed`, `dpvFootnote`,
  `standardizedAddress` and sometimes `carrierRoute`. `dpvFootnote` is `"A1"`
  (ZIP+4 matched, *not* delivery-point confirmed) for every address tried.
- `metadata` is frequently `{}` — including for a genuine suburban house.
- When populated, `metadata.residential` is `false` and `business` is `true`
  even for a Manhattan apartment. It appears to describe "is there a business
  POI here", not "is this a residence".

Net effect: a UPS Store and a hospital classify identically (`commercial`), and
a house classifies as `unclassified`. That is the exact opposite of useful for
a signal whose whole job is separating those cases.

**The replacement is the Places API (New) `searchText`**, whose `types` /
`primaryType` genuinely distinguish `post_office`/shipping stores from
`hospital`/`doctor`/`pharmacy`, and where "no establishment at this address" is
itself reasonable residential evidence. It is currently blocked —
`403 API_KEY_SERVICE_BLOCKED` — because the API is not enabled on the project.
**Do not rewrite this module against Places until that is enabled and real
responses have been captured**; writing a classifier against a guessed response
shape is precisely the mistake that produced this warning.

Field paths are named once, in `_FIELD_PATHS`, so the blast radius is small.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from specter.core.contracts import AddressClassification, LocationType

logger = structlog.get_logger(__name__)

_ENDPOINT = "https://addressvalidation.googleapis.com/v1:validateAddress"
_TIMEOUT_SECONDS = 20.0

# Every response field this module reads, named once. See the UNVERIFIED note
# in the module docstring.
_FIELD_PATHS = {
    "formatted_address": ("result", "address", "formattedAddress"),
    "residential": ("result", "metadata", "residential"),
    "business": ("result", "metadata", "business"),
    "po_box": ("result", "metadata", "poBox"),
    "dpv_cmra": ("result", "uspsData", "dpvCmra"),
}

# Attached to every Maps-derived signal, mirroring Amendment 3's disclosure
# rule for `zcta_centroid`. Google's metadata flags are inferred from address
# records, not from anyone visiting the building.
CLASSIFICATION_LIMITATIONS = ["places_type_heuristic", "not_field_verified"]


def _dig(record: dict[str, Any], path: tuple[str, ...]) -> Any:
    """Walk a dotted path, returning None if any level is missing. Missing
    fields are normal here — the API omits `uspsData` entirely for an address
    it could not CASS-standardize.
    """
    node: Any = record
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


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
    (CLAUDE.md, address normalization) and is not stored on the Address node,
    only on the `LOCATED_AT` edge. Classifying at building granularity is the
    correct level for this signal anyway.
    """
    street = " ".join(p for p in (street_number, street_name, street_type) if p)
    tail = " ".join(p for p in (state, zip5) if p)
    return ", ".join(p for p in (street, city, tail) if p)


def fetch_address_record(address_line: str, api_key: str) -> dict[str, Any]:
    """One HTTPS call to the Address Validation API. Returns the raw decoded
    JSON, unmodified, so the artifact stored from it is the real response.

    Raises on any non-200 (CLAUDE.md hard rule 7 — no silent fallback that
    masks a broken credential). A quota or auth failure must stop the batch,
    not quietly classify 7,000 addresses as `unclassified`.
    """
    response = httpx.post(
        _ENDPOINT,
        params={"key": api_key},
        json={
            "address": {"regionCode": "US", "addressLines": [address_line]},
            # USPS CASS is what populates `uspsData.dpvCmra`, the strongest
            # mailbox-store discriminator available. Without it this call
            # degrades to metadata flags only.
            "enableUspsCass": True,
        },
        timeout=_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Address Validation API returned {response.status_code} for "
            f"{address_line!r}: {response.text[:300]}"
        )
    decoded: dict[str, Any] = response.json()
    return decoded


def classify(normalized_key: str, record: dict[str, Any]) -> AddressClassification:
    """Pure. Map an Address Validation response onto a `LocationType`.

    Precedence is deliberate and ordered strongest-evidence-first:

    1. `uspsData.dpvCmra == "Y"` — USPS's own Commercial Mail Receiving Agency
       flag. This is the single most direct "this is a mailbox store, not a
       place of business" signal that exists in US address data.
    2. `metadata.poBox` — a PO box is not a practice location.
    3. `metadata.residential` — a house.
    4. `metadata.business` — a commercial premises. Note this does NOT
       distinguish a medical office from a nail salon; Address Validation has
       no business-category data. Distinguishing them would need the Places
       API, and Phase 2's narrow scope does not require it — the signal only
       gates on the implausible types.
    5. Anything else — `unclassified`. Not an error.
    """
    formatted = _dig(record, _FIELD_PATHS["formatted_address"])
    cmra = _dig(record, _FIELD_PATHS["dpv_cmra"])
    po_box = _dig(record, _FIELD_PATHS["po_box"])
    residential = _dig(record, _FIELD_PATHS["residential"])
    business = _dig(record, _FIELD_PATHS["business"])

    location_type: LocationType
    if cmra == "Y":
        location_type, reason = "mailbox_store", "uspsData.dpvCmra=Y (USPS CMRA)"
    elif po_box is True:
        location_type, reason = "po_box", "metadata.poBox=true"
    elif residential is True:
        location_type, reason = "residential", "metadata.residential=true"
    elif business is True:
        location_type, reason = "commercial", "metadata.business=true"
    else:
        location_type, reason = (
            "unclassified",
            "no residential/business/poBox/CMRA flag present in the response",
        )

    limitations = list(CLASSIFICATION_LIMITATIONS)
    if cmra is None:
        # No `uspsData` block: the address was not CASS-standardized, so the
        # strongest discriminator was unavailable for this one. Say so rather
        # than letting a weaker verdict look equally well-evidenced.
        limitations.append("no_usps_cass_data")

    return AddressClassification(
        normalized_key=normalized_key,
        location_type=location_type,
        matched_formatted_address=formatted if isinstance(formatted, str) else None,
        classification_reason=reason,
        known_limitations=limitations,
    )
