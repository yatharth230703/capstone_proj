"""CLAUDE.md: 'Twenty real-world collision test cases must pass before the
graph loader is considered done.' Ten pairs that must collide (same building,
different unit/suite or spelling variant), ten that must not.
"""

import pytest

from specter.tools.entity_tools import normalize_address, normalize_phone

MUST_COLLIDE = [
    ("123 Main Street Suite 100, Miami, FL 33101", "123 Main Street Suite 400, Miami, FL 33101"),
    ("456 Oak Ave Apt 2B, Houston, TX 77002", "456 Oak Avenue #2B, Houston, TX 77002"),
    ("789 Elm St, Los Angeles, CA 90001", "789 Elm Street, Los Angeles, CA 90001"),
    ("100 N Main St, Tampa, FL 33602", "100 North Main Street, Tampa, FL 33602"),
    ("200 W 5th Ave, Dallas, TX 75201", "200 West 5th Avenue, Dallas, TX 75201"),
    (
        "300 Park Blvd Ste 10, San Diego, CA 92101",
        "300 Park Boulevard Suite 10, San Diego, CA 92101",
    ),
    ("1500 Biscayne Blvd Unit 3B, Miami, FL 33132", "1500 Biscayne Boulevard #3B, Miami, FL 33132"),
    ("42 Sunset Dr, Austin, TX 78701", "42 Sunset Drive, Austin, TX 78701"),
    ("77 Ocean Way, San Francisco, CA 94111", "77 Ocean Wy, San Francisco, CA 94111"),
    ("88 Coral Ct, Orlando, FL 32801", "88 Coral Court, Orlando, FL 32801"),
]

MUST_NOT_COLLIDE = [
    ("123 Main Street, Miami, FL 33101", "123 Main Avenue, Miami, FL 33101"),
    ("123 Main St, Miami, FL 33101", "124 Main St, Miami, FL 33101"),
    ("500 Elm St, Houston, TX 77002", "500 Elm St, Dallas, TX 75201"),
    ("10 First Ave, Los Angeles, CA 90001", "10 First Ave, Los Angeles, CA 90002"),
    ("200 Broadway, New York, NY 10001", "200 Broadway, New York, NY 10007"),
    ("300 Palm Dr, Tampa, FL 33602", "300 Palm Ave, Tampa, FL 33602"),
    ("45 Lake Rd, Austin, TX 78701", "450 Lake Rd, Austin, TX 78701"),
    ("9 Pine St, San Diego, CA 92101", "9 Pine Ln, San Diego, CA 92101"),
    ("1000 Commerce Way, Orlando, FL 32801", "1000 Commerce Way, Miami, FL 33101"),
    ("55 Bay St Suite 5, Sacramento, CA 95814", "550 Bay St Suite 5, Sacramento, CA 95814"),
]


@pytest.mark.parametrize("addr_a,addr_b", MUST_COLLIDE)
def test_addresses_collide(addr_a: str, addr_b: str) -> None:
    a = normalize_address(addr_a)
    b = normalize_address(addr_b)
    assert a.normalized_key == b.normalized_key, f"{addr_a!r} vs {addr_b!r}: {a} != {b}"
    assert a.parse_confidence == "high"
    assert b.parse_confidence == "high"


@pytest.mark.parametrize("addr_a,addr_b", MUST_NOT_COLLIDE)
def test_addresses_do_not_collide(addr_a: str, addr_b: str) -> None:
    a = normalize_address(addr_a)
    b = normalize_address(addr_b)
    assert a.normalized_key != b.normalized_key, (
        f"{addr_a!r} vs {addr_b!r} collided: {a.normalized_key}"
    )


def test_unit_excluded_from_key() -> None:
    result = normalize_address("1500 Biscayne Blvd Unit 3B, Miami, FL 33132")
    assert "3B" not in result.normalized_key
    assert result.unit == "3B"


def test_unparseable_address_falls_back_low_confidence() -> None:
    result = normalize_address("asdf ###!!! not an address at all")
    assert result.parse_confidence == "low"
    assert result.normalized_key.startswith("UNPARSED|")


def test_normalize_phone_e164() -> None:
    assert normalize_phone("(305) 555-0198") == "+13055550198"
    assert normalize_phone("305-555-0198") == "+13055550198"


def test_normalize_phone_invalid_raises() -> None:
    with pytest.raises(ValueError, match="invalid phone number"):
        normalize_phone("123")
