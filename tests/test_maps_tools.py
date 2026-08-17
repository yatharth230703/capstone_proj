"""M11: `tools/maps_tools.classify` is pure and deterministic, and the fetch
path fails loudly.

Fully offline — no live Maps call in the suite. **The fixtures below are real
captured responses**, trimmed to the fields `classify` reads, from live calls
made 2026-08-18 against the addresses named in each constant. They are not
invented shapes: an earlier version of this module was written against a
documented-but-unobserved response and was wrong in the load-bearing way
(`NOTES_API_DEVIATIONS.md` D25). If Google changes the response, these are what
will say so.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from specter.core.contracts import ScreeningThresholds
from specter.tools import maps_tools
from specter.tools.signal_tools import load_thresholds

THRESHOLDS_PATH = Path("config/screening.yaml")


@pytest.fixture(scope="module")
def thresholds() -> ScreeningThresholds:
    return load_thresholds(THRESHOLDS_PATH)


def _record(results: list[dict[str, Any]], *, geocode: bool = True, status: str = "OK") -> dict:
    validation: dict[str, Any] = {
        "result": {"address": {"formattedAddress": "123 Test St, Miami, FL 33101, USA"}}
    }
    if geocode:
        validation["result"]["geocode"] = {"location": {"latitude": 25.7, "longitude": -80.1}}
    return {
        "address_validation": validation,
        "nearby": {"status": status, "results": results},
        "radius_m": 50,
    }


# --- real captured shapes -------------------------------------------------
# 1005 Bel Aire Dr, Burbank CA — a genuine suburban house. Nearby Search
# returns only the street and the city, neither of which is an establishment.
_HOUSE = _record(
    [
        {"name": "918-998 N Bel Aire Dr", "types": ["route"]},
        {"name": "Burbank", "types": ["locality", "political"]},
    ]
)

# 1611 NW 12th Ave, Miami FL — Jackson Memorial medical campus.
_HOSPITAL = _record(
    [
        {"name": "Miami", "types": ["locality", "political"]},
        {
            "name": "Alkalay Idan MD",
            "types": ["doctor", "point_of_interest", "health", "establishment"],
        },
        {
            "name": "Dr. Eduard Ghersin, MD",
            "types": ["doctor", "point_of_interest", "health", "establishment"],
        },
    ]
)

# 2261 Market St, San Francisco CA — commercial strip, nothing medical.
_COMMERCIAL = _record(
    [
        {"name": "2297-2261 Market St", "types": ["route"]},
        {"name": "Photoworks SF", "types": ["point_of_interest", "establishment"]},
        {
            "name": "Dinosaurs Sandwiches",
            "types": ["restaurant", "food", "point_of_interest", "establishment"],
        },
    ]
)

# A UPS Authorized Shipping Outlet carries NO post_office type — measured.
# This is why name patterns are needed alongside the type check.
_MAILBOX_BY_NAME = _record(
    [{"name": "The UPS Store", "types": ["establishment", "point_of_interest", "store"]}]
)
_MAILBOX_BY_TYPE = _record(
    [
        {
            "name": "Mailboxes - UPS - FedEx - DHL",
            "types": ["establishment", "finance", "point_of_interest", "post_office", "store"],
        }
    ]
)

_NO_GEOCODE = _record([], geocode=False, status="NO_GEOCODE")


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (_HOUSE, "residential"),
        (_HOSPITAL, "commercial_medical"),
        (_COMMERCIAL, "commercial"),
        (_MAILBOX_BY_NAME, "mailbox_store"),
        (_MAILBOX_BY_TYPE, "mailbox_store"),
        (_NO_GEOCODE, "unclassified"),
    ],
)
def test_classify_discriminates_real_shapes(
    record: dict[str, Any], expected: str, thresholds: ScreeningThresholds
) -> None:
    assert maps_tools.classify("k", record, thresholds).location_type == expected


def test_route_and_locality_are_not_establishments(thresholds: ScreeningThresholds) -> None:
    """The load-bearing filter. Nearby Search returns the surrounding street
    and city alongside real POIs; counting those would make every address look
    occupied and destroy the zero-establishment signal that finds a residence.
    """
    result = maps_tools.classify("k", _HOUSE, thresholds)
    assert result.establishment_count == 0
    assert result.location_type == "residential"


def test_medical_beats_generic_commercial(thresholds: ScreeningThresholds) -> None:
    """A DME supplier in a medical office building is the ordinary, innocent
    configuration — it must not land in an implausible bucket.
    """
    result = maps_tools.classify("k", _HOSPITAL, thresholds)
    assert result.location_type == "commercial_medical"
    assert result.medical_establishment_count == 2
    assert result.location_type not in thresholds.physical_existence_implausible_types


def test_mailbox_store_detected_without_post_office_type(
    thresholds: ScreeningThresholds,
) -> None:
    """Measured live: a UPS Authorized Shipping Outlet carries only
    ['establishment', 'point_of_interest']. Type-only detection misses it.
    """
    assert "post_office" not in _MAILBOX_BY_NAME["nearby"]["results"][0]["types"]
    assert maps_tools.classify("k", _MAILBOX_BY_NAME, thresholds).location_type == "mailbox_store"


def test_unclassified_is_a_result_not_an_error(thresholds: ScreeningThresholds) -> None:
    """Amendment 3's precedent for `zip_centroid` returning None: never
    substitute a guess, never raise. Every fabricated synthetic address lands
    here.
    """
    result = maps_tools.classify("k", _NO_GEOCODE, thresholds)
    assert result.location_type == "unclassified"
    assert "did not geocode" in result.classification_reason


def test_counts_are_reported_so_a_verdict_can_be_checked(
    thresholds: ScreeningThresholds,
) -> None:
    result = maps_tools.classify("k", _COMMERCIAL, thresholds)
    assert (result.establishment_count, result.medical_establishment_count) == (2, 0)


def test_classify_is_pure(thresholds: ScreeningThresholds) -> None:
    """Same input twice -> byte-identical output. No clock, no randomness, no
    I/O — this is what lets a Maps-derived verdict be called deterministic.
    """
    first = maps_tools.classify("k", _HOSPITAL, thresholds).model_dump_json()
    second = maps_tools.classify("k", _HOSPITAL, thresholds).model_dump_json()
    assert first == second


def test_every_classification_carries_the_disclosure(
    thresholds: ScreeningThresholds,
) -> None:
    for record in (_HOUSE, _HOSPITAL, _COMMERCIAL, _MAILBOX_BY_NAME, _NO_GEOCODE):
        limitations = maps_tools.classify("k", record, thresholds).known_limitations
        assert "places_density_heuristic" in limitations
        assert "not_field_verified" in limitations
        # The dense-urban false-negative is real and must travel with every
        # verdict, not live only in a docstring.
        assert "unreliable_in_dense_urban_cores" in limitations


def test_build_address_line_omits_missing_parts() -> None:
    assert (
        maps_tools.build_address_line("100", "MAIN", "ST", "MIAMI", "FL", "33101")
        == "100 MAIN ST, MIAMI, FL 33101"
    )
    assert maps_tools.build_address_line("100", "MAIN", None, None, "FL", None) == "100 MAIN, FL"


def test_fetch_raises_on_non_200(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hard rule 7: no silent fallback that masks a broken credential. A 403
    must stop the batch, not classify 7,000 addresses as `unclassified`.
    """

    def _denied(*_a: object, **_kw: object) -> httpx.Response:
        return httpx.Response(403, text='{"error":{"message":"API key not valid"}}')

    monkeypatch.setattr(httpx, "post", _denied)
    with pytest.raises(RuntimeError, match="403"):
        maps_tools.fetch_address_record("100 Main St, Miami, FL 33101", "bad-key", 50)


def test_fetch_raises_on_bad_places_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """`OVER_QUERY_LIMIT` arrives as HTTP 200 with a status field. Treating it
    as "no establishments here" would silently classify the rest of the batch
    as residential — the worst possible failure for this signal.
    """

    def _ok_post(*_a: object, **_kw: object) -> httpx.Response:
        return httpx.Response(
            200, json={"result": {"geocode": {"location": {"latitude": 1.0, "longitude": 2.0}}}}
        )

    def _quota_get(*_a: object, **_kw: object) -> httpx.Response:
        return httpx.Response(200, json={"status": "OVER_QUERY_LIMIT", "results": []})

    monkeypatch.setattr(httpx, "post", _ok_post)
    monkeypatch.setattr(httpx, "get", _quota_get)
    with pytest.raises(RuntimeError, match="OVER_QUERY_LIMIT"):
        maps_tools.fetch_address_record("x", "k", 50)


def test_zero_results_is_accepted_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    """ZERO_RESULTS is the single most important *successful* answer this
    signal can get — it is what a residence looks like.
    """

    def _ok_post(*_a: object, **_kw: object) -> httpx.Response:
        return httpx.Response(
            200, json={"result": {"geocode": {"location": {"latitude": 1.0, "longitude": 2.0}}}}
        )

    def _empty_get(*_a: object, **_kw: object) -> httpx.Response:
        return httpx.Response(200, json={"status": "ZERO_RESULTS", "results": []})

    monkeypatch.setattr(httpx, "post", _ok_post)
    monkeypatch.setattr(httpx, "get", _empty_get)
    record = maps_tools.fetch_address_record("x", "k", 50)
    assert record["nearby"]["status"] == "ZERO_RESULTS"
