"""M11: `tools/maps_tools.classify` is pure and deterministic, and
`fetch_address_record` fails loudly.

Fully offline — no live Maps call, ever, in the suite. The fixtures below are
the module's record of what an Address Validation response is believed to look
like; see the UNVERIFIED note in `maps_tools`'s docstring. **When the first real
call is made, replace these with a captured real response** — if the shape
differs, these tests are what will tell you, which is the point.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from specter.tools import maps_tools

# A UPS Store: USPS flags it as a Commercial Mail Receiving Agency.
_CMRA: dict[str, Any] = {
    "result": {
        "address": {"formattedAddress": "1234 Biscayne Blvd Ste 100, Miami, FL 33132-1000"},
        "metadata": {"business": True, "poBox": False, "residential": False},
        "uspsData": {"dpvCmra": "Y", "dpvConfirmation": "Y"},
    }
}

_RESIDENTIAL: dict[str, Any] = {
    "result": {
        "address": {"formattedAddress": "100 Residential Ct, Miami, FL 33101-0100"},
        "metadata": {"business": False, "poBox": False, "residential": True},
        "uspsData": {"dpvCmra": "N", "dpvConfirmation": "Y"},
    }
}

_COMMERCIAL: dict[str, Any] = {
    "result": {
        "address": {"formattedAddress": "1611 NW 12th Ave, Miami, FL 33136-1005"},
        "metadata": {"business": True, "poBox": False, "residential": False},
        "uspsData": {"dpvCmra": "N", "dpvConfirmation": "Y"},
    }
}

_PO_BOX: dict[str, Any] = {
    "result": {
        "address": {"formattedAddress": "PO Box 900, Miami, FL 33101-0900"},
        "metadata": {"business": False, "poBox": True, "residential": False},
        "uspsData": {"dpvCmra": "N"},
    }
}

# Google returns a `result` with no metadata at all for an address it cannot
# resolve — which is exactly what a fabricated synthetic street would produce.
_NO_MATCH: dict[str, Any] = {"result": {"address": {}, "metadata": {}}}


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        (_CMRA, "mailbox_store"),
        (_RESIDENTIAL, "residential"),
        (_COMMERCIAL, "commercial"),
        (_PO_BOX, "po_box"),
        (_NO_MATCH, "unclassified"),
    ],
)
def test_classify_maps_each_response_shape(record: dict[str, Any], expected: str) -> None:
    assert maps_tools.classify("k", record).location_type == expected


def test_cmra_beats_business_flag() -> None:
    """A mailbox store is flagged `business: true` as well. CMRA has to win, or
    every UPS Store classifies as an ordinary commercial premises.
    """
    assert _CMRA["result"]["metadata"]["business"] is True
    assert maps_tools.classify("k", _CMRA).location_type == "mailbox_store"


def test_unmatched_address_is_a_result_not_an_error() -> None:
    """Amendment 3's precedent for `zip_centroid` returning None: never
    substitute a guess, never raise.
    """
    result = maps_tools.classify("k", _NO_MATCH)
    assert result.location_type == "unclassified"
    assert result.matched_formatted_address is None
    assert "no residential/business/poBox/CMRA" in result.classification_reason


def test_missing_usps_block_is_disclosed() -> None:
    """Without CASS data the strongest discriminator was unavailable — the
    classification must say so rather than look equally well-evidenced.
    """
    no_usps = {"result": {"address": {}, "metadata": {"residential": True}}}
    result = maps_tools.classify("k", no_usps)
    assert result.location_type == "residential"
    assert "no_usps_cass_data" in result.known_limitations
    assert "no_usps_cass_data" not in maps_tools.classify("k", _RESIDENTIAL).known_limitations


def test_classify_is_pure() -> None:
    """Same input twice -> byte-identical output. No clock, no randomness, no
    I/O — this is what lets a Maps-derived number be called deterministic.
    """
    first = maps_tools.classify("k", _RESIDENTIAL).model_dump_json()
    second = maps_tools.classify("k", _RESIDENTIAL).model_dump_json()
    assert first == second


def test_every_classification_carries_the_disclosure() -> None:
    for record in (_CMRA, _RESIDENTIAL, _COMMERCIAL, _PO_BOX, _NO_MATCH):
        limitations = maps_tools.classify("k", record).known_limitations
        assert "places_type_heuristic" in limitations
        assert "not_field_verified" in limitations


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

    def _denied(*_args: object, **_kwargs: object) -> httpx.Response:
        return httpx.Response(403, text='{"error":{"message":"API key not valid"}}')

    monkeypatch.setattr(httpx, "post", _denied)
    with pytest.raises(RuntimeError, match="403"):
        maps_tools.fetch_address_record("100 Main St, Miami, FL 33101", "bad-key")


def test_fetch_returns_decoded_json_unmodified(monkeypatch: pytest.MonkeyPatch) -> None:
    def _ok(*_args: object, **_kwargs: object) -> httpx.Response:
        return httpx.Response(200, json=_RESIDENTIAL)

    monkeypatch.setattr(httpx, "post", _ok)
    assert maps_tools.fetch_address_record("x", "k") == _RESIDENTIAL
