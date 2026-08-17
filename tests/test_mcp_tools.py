from __future__ import annotations

from typing import Any

import pytest

from specter.tools.mcp_tools import (
    UnsafeCypherError,
    ensure_limit_clause,
    reject_unsafe_cypher,
    run_guarded_cypher,
)


@pytest.mark.parametrize(
    "query",
    [
        "CREATE (n:Provider {npi: '123'}) RETURN n",
        "MATCH (n) DETACH DELETE n",
        "MATCH (n:Provider {npi: $npi}) SET n.flagged = true",
        "MATCH (n:Provider) REMOVE n.flagged",
        "DROP INDEX provider_npi",
        "MATCH (n:Provider) MERGE (a:Address {key: n.zip})",
        "CALL apoc.create.node(['Foo'], {})",
    ],
)
def test_reject_unsafe_cypher_blocks_write_verbs(query: str) -> None:
    with pytest.raises(UnsafeCypherError):
        reject_unsafe_cypher(query)


@pytest.mark.parametrize(
    "query",
    [
        "MATCH (n:Provider) RETURN n.npi",
        "MATCH (n:Provider)-[:HAS_OFFICER]->(o) RETURN o.officer_id LIMIT 10",
    ],
)
def test_reject_unsafe_cypher_allows_reads(query: str) -> None:
    reject_unsafe_cypher(query)  # does not raise


def test_word_boundary_does_not_false_positive_on_property_names() -> None:
    # "created_at" contains "create" as a substring but is not the CREATE
    # clause; \b keeps this from being blocked.
    reject_unsafe_cypher("MATCH (n:Provider) RETURN n.created_at")


def test_string_literal_collision_is_blocked_not_bypassed() -> None:
    # A write-verb word inside a string literal still trips the regex.
    # Deliberate over-blocking, not a bug: CLAUDE.md hard rule 7 ("fail
    # loudly") makes over-rejection the safe failure direction for an
    # injection surface — see module docstring.
    with pytest.raises(UnsafeCypherError):
        reject_unsafe_cypher("MATCH (n:Provider) WHERE n.name = 'CREATE MEDICAL SUPPLY' RETURN n")


def test_ensure_limit_clause_appends_when_missing() -> None:
    assert ensure_limit_clause("MATCH (n) RETURN n") == "MATCH (n) RETURN n LIMIT 100"


def test_ensure_limit_clause_appends_custom_limit() -> None:
    assert ensure_limit_clause("MATCH (n) RETURN n", limit=25) == "MATCH (n) RETURN n LIMIT 25"


def test_ensure_limit_clause_leaves_existing_limit_alone() -> None:
    query = "MATCH (n) RETURN n LIMIT 5"
    assert ensure_limit_clause(query) == query


def test_ensure_limit_clause_strips_trailing_semicolon() -> None:
    assert ensure_limit_clause("MATCH (n) RETURN n;") == "MATCH (n) RETURN n LIMIT 100"


class _FakeRecord:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def data(self) -> dict[str, Any]:
        return self._data


class _FakeResult:
    def __iter__(self) -> Any:
        return iter([_FakeRecord({"npi": "123"})])


class _FakeSession:
    def __init__(self) -> None:
        self.ran_with: Any = None

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def run(self, query: Any) -> _FakeResult:
        self.ran_with = query
        return _FakeResult()


class _FakeDriver:
    def __init__(self) -> None:
        self.session_calls: list[dict[str, Any]] = []
        self.fake_session = _FakeSession()

    def session(self, **kwargs: Any) -> _FakeSession:
        self.session_calls.append(kwargs)
        return self.fake_session


def test_run_guarded_cypher_rejects_before_touching_driver() -> None:
    driver = _FakeDriver()
    with pytest.raises(UnsafeCypherError):
        run_guarded_cypher(driver, "CREATE (n) RETURN n")  # type: ignore[arg-type]
    assert driver.session_calls == []


def test_run_guarded_cypher_opens_read_only_session_with_timeout_and_limit() -> None:
    driver = _FakeDriver()
    rows = run_guarded_cypher(driver, "MATCH (n) RETURN n", timeout_seconds=10.0)  # type: ignore[arg-type]
    assert rows == [{"npi": "123"}]
    assert driver.session_calls == [{"default_access_mode": "READ"}]
    ran_query = driver.fake_session.ran_with
    assert ran_query.text == "MATCH (n) RETURN n LIMIT 100"
    assert ran_query.timeout == 10.0
