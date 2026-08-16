"""Offline tests for `agents/_grounding.py` — the generic numeric-grounding
check shared by `graph_investigation.py` and `case_reporter.py` (M5, debt
D-14 cleared).
"""

from __future__ import annotations

from specter.agents._grounding import numbers_in, numeric_violations


def test_numbers_in_finds_ints_and_floats() -> None:
    assert numbers_in("value 8.0, degree 3, distance -12.5") == {"8.0", "3", "-12.5"}


def test_numeric_violations_empty_when_fully_grounded() -> None:
    evidence = {"fired_signals": [{"signal_type": "address_degree", "value": 8.0}]}
    assert numeric_violations(["value of 8.0 fired."], evidence) == []


def test_numeric_violations_catches_a_fabricated_number() -> None:
    evidence = {"fired_signals": [{"signal_type": "address_degree", "value": 8.0}]}
    violations = numeric_violations(["shares its address with 47 other providers."], evidence)
    assert violations == ["47"]


def test_numeric_violations_checks_every_text_in_the_list() -> None:
    evidence = {"signal_count": 3}
    violations = numeric_violations(["grounded text.", "exhibits 5 indicators."], evidence)
    assert violations == ["5"]
