"""Deterministic entity-normalization tools (plan §8, §6.2). No LLM calls —
every function here is pure/deterministic; the graph loader and, later, ADK
`FunctionTool`s both call these directly. `propose_entity_matches` computes
FEATURES only — the match-probability judgment call is the Entity
Resolution Agent's job (plan §9.3, M5), never this tool's.

Address normalization is the load-bearing signal in the whole system
(CLAUDE.md): `normalized_key = street_number|street_name_normalized|
street_type_abbrev|zip5`. Unit/suite is deliberately excluded from the key.
"""

from __future__ import annotations

import re

import phonenumbers
import structlog
import usaddress
from neo4j import Driver
from rapidfuzz import fuzz

from specter.core.contracts import MatchProposal, NormalizedAddress

logger = structlog.get_logger(__name__)

# USPS-style street-suffix abbreviations. Keys cover both the spelled-out and
# already-abbreviated forms so "Street"/"St"/"St." all normalize the same way.
_STREET_TYPES: dict[str, str] = {}
for _full, _abbrev in [
    ("STREET", "ST"),
    ("AVENUE", "AVE"),
    ("BOULEVARD", "BLVD"),
    ("DRIVE", "DR"),
    ("LANE", "LN"),
    ("ROAD", "RD"),
    ("COURT", "CT"),
    ("CIRCLE", "CIR"),
    ("PLACE", "PL"),
    ("WAY", "WY"),
    ("TERRACE", "TER"),
    ("TRAIL", "TRL"),
    ("PARKWAY", "PKWY"),
    ("HIGHWAY", "HWY"),
    ("SQUARE", "SQ"),
    ("LOOP", "LOOP"),
    ("POINT", "PT"),
    ("RIDGE", "RDG"),
    ("RUN", "RUN"),
]:
    _STREET_TYPES[_full] = _abbrev
    _STREET_TYPES[_abbrev] = _abbrev

_DIRECTIONALS: dict[str, str] = {}
for _full, _abbrev in [
    ("NORTH", "N"),
    ("SOUTH", "S"),
    ("EAST", "E"),
    ("WEST", "W"),
    ("NORTHEAST", "NE"),
    ("NORTHWEST", "NW"),
    ("SOUTHEAST", "SE"),
    ("SOUTHWEST", "SW"),
]:
    _DIRECTIONALS[_full] = _abbrev
    _DIRECTIONALS[_abbrev] = _abbrev


def _clean_token(value: str | None) -> str:
    return (value or "").strip().upper().rstrip(".")


def normalize_address(raw: str) -> NormalizedAddress:
    """Parse a raw U.S. mailing address into a deterministic, collision-safe
    key. Two providers in different suites of the same building get the same
    normalized_key (unit/suite is deliberately excluded from it) — that is
    correct, not a bug, and callers should not try to work around it.

    Args:
        raw: a raw address string, e.g. "1500 Biscayne Blvd Unit 3B, Miami, FL 33132".

    Returns:
        NormalizedAddress with normalized_key, parsed components, and a
        parse_confidence of "high" (usaddress parsed it cleanly) or "low"
        (fell back to a coarser deterministic key for malformed input).
    """
    try:
        tagged, addr_type = usaddress.tag(raw)
    except usaddress.RepeatedLabelError:
        return _fallback(raw)

    street_number = tagged.get("AddressNumber")
    street_name = tagged.get("StreetName")
    if addr_type != "Street Address" or not street_number or not street_name:
        return _fallback(raw)

    pre_dir_token = _clean_token(tagged.get("StreetNamePreDirectional"))
    pre_dir = _DIRECTIONALS.get(pre_dir_token, pre_dir_token)
    post_type_token = _clean_token(tagged.get("StreetNamePostType"))
    street_type_abbrev = _STREET_TYPES.get(post_type_token, post_type_token)

    street_name_normalized = " ".join(p for p in [pre_dir, street_name.strip().upper()] if p)

    zip_raw = tagged.get("ZipCode")
    zip5 = zip_raw[:5] if zip_raw else None

    normalized_key = "|".join(
        [street_number, street_name_normalized, street_type_abbrev, zip5 or ""]
    )

    return NormalizedAddress(
        normalized_key=normalized_key,
        street_number=street_number,
        street_name=street_name_normalized,
        street_type=street_type_abbrev or None,
        unit=tagged.get("OccupancyIdentifier"),
        city=tagged.get("PlaceName"),
        state=tagged.get("StateName"),
        zip5=zip5,
        raw=raw,
        parse_confidence="high",
    )


def _fallback(raw: str) -> NormalizedAddress:
    """usaddress couldn't confidently parse this. Rather than crash the whole
    graph load over one malformed address (hard rule 7 is about masking a
    *broken source*, not tolerating expected real-world noise), fall back to
    a coarser but still deterministic key — visibly marked low-confidence.
    """
    logger.warning("normalize_address.fallback", raw=raw)
    collapsed = re.sub(r"[^A-Z0-9]+", " ", raw.upper()).strip()
    return NormalizedAddress(
        normalized_key=f"UNPARSED|{collapsed}",
        street_number=None,
        street_name=None,
        street_type=None,
        unit=None,
        city=None,
        state=None,
        zip5=None,
        raw=raw,
        parse_confidence="low",
    )


def normalize_phone(raw: str, region: str = "US") -> str:
    """Parse a raw phone number into E.164 format for use as a Phone node's
    collision key (e.g. phone_degree signal: distinct providers sharing one
    e164 number).

    Args:
        raw: a raw phone number string, e.g. "(305) 555-0198".
        region: default region for numbers without a country code.

    Returns:
        The number in E.164 format, e.g. "+13055550198".

    Raises:
        ValueError: if the number cannot be parsed as a valid number for
            the given region — never silently drop an invalid number.
    """
    parsed = phonenumbers.parse(raw, region)
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError(f"invalid phone number: {raw!r}")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def name_similarity(a: str, b: str) -> float:
    """Token-set similarity (0-100), order- and duplicate-word-insensitive —
    "Acme Medical Supply LLC" vs "Medical Supply Acme" score identically to
    "Acme Medical Supply LLC" vs itself.
    """
    return fuzz.token_set_ratio(a, b)


def propose_entity_matches(
    driver: Driver, npi: str, candidates: list[str]
) -> list[MatchProposal]:
    """Deterministic match features between `npi` and each of `candidates`.
    Does not decide whether they're the same entity — see module docstring.
    """
    with driver.session() as session:
        base_record = session.run(
            "MATCH (p:Provider {npi: $npi}) RETURN p.organization_name AS name", npi=npi
        ).single()
    if base_record is None:
        return []
    base_name = base_record["name"] or ""

    proposals: list[MatchProposal] = []
    with driver.session() as session:
        for candidate_npi in candidates:
            record = session.run(
                """
                MATCH (p:Provider {npi: $npi})
                MATCH (c:Provider {npi: $candidate_npi})
                OPTIONAL MATCH (p)-[:LOCATED_AT]->(a:Address)<-[:LOCATED_AT]-(c)
                OPTIONAL MATCH (p)-[:HAS_PHONE]->(ph:Phone)<-[:HAS_PHONE]-(c)
                OPTIONAL MATCH (p)-[:HAS_OFFICER]->(o:Officer)<-[:HAS_OFFICER]-(c)
                RETURN c.organization_name AS candidate_name,
                       a IS NOT NULL AS shares_address,
                       ph IS NOT NULL AS shares_phone,
                       o IS NOT NULL AS shares_officer
                """,
                npi=npi, candidate_npi=candidate_npi,
            ).single()
            if record is None:
                continue
            proposals.append(
                MatchProposal(
                    npi=npi,
                    candidate_npi=candidate_npi,
                    name_similarity=name_similarity(base_name, record["candidate_name"] or ""),
                    shares_address=record["shares_address"],
                    shares_phone=record["shares_phone"],
                    shares_officer=record["shares_officer"],
                    source_ids=[f"graph:provider:{npi}", f"graph:provider:{candidate_npi}"],
                )
            )
    return proposals
