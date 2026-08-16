from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from neo4j import Driver, GraphDatabase

from specter.settings import get_settings
from specter.tools.evidence_tools import cite, store_artifact, validate_citations


@pytest.fixture(scope="module")
def driver() -> Iterator[Driver]:
    settings = get_settings()
    drv = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value())
    )
    try:
        drv.verify_connectivity()
    except Exception:
        pytest.skip("Neo4j not reachable — start it with `docker compose up -d`")
    yield drv
    drv.close()


def test_store_artifact_writes_file_and_hashes_content(tmp_path: Path) -> None:
    artifact = store_artifact("some evidence text", "text/plain", "doj", tmp_path, "direct")
    assert artifact.stored_path.exists()
    assert artifact.stored_path.read_text() == "some evidence text"
    assert len(artifact.artifact_id) == 64  # sha256 hex digest


def test_store_artifact_same_content_same_id(tmp_path: Path) -> None:
    a = store_artifact("identical content", "text/plain", "doj", tmp_path, "direct")
    b = store_artifact("identical content", "text/plain", "leie", tmp_path, "direct")
    assert a.artifact_id == b.artifact_id


def test_cite_builds_citation() -> None:
    citation = cite("abc123", "the provider is located at this address")
    assert citation.artifact_id == "abc123"
    assert citation.claim == "the provider is located at this address"


def test_validate_citations_resolves_real_graph_node(driver: Driver, tmp_path: Path) -> None:
    report = validate_citations(["graph:provider:9020000000"], driver, tmp_path)
    assert report.all_resolved
    assert report.resolved_citations == 1
    assert report.unresolved_source_ids == []


def test_validate_citations_flags_nonexistent_graph_node(driver: Driver, tmp_path: Path) -> None:
    report = validate_citations(["graph:provider:0000000000"], driver, tmp_path)
    assert not report.all_resolved
    assert "graph:provider:0000000000" in report.unresolved_source_ids


def test_validate_citations_resolves_stored_artifact(driver: Driver, tmp_path: Path) -> None:
    artifact = store_artifact("evidence content", "text/plain", "doj", tmp_path, "direct")
    report = validate_citations([artifact.artifact_id], driver, tmp_path)
    assert report.all_resolved


def test_validate_citations_flags_unknown_source_type(driver: Driver, tmp_path: Path) -> None:
    report = validate_citations(["graph:not_a_real_type:xyz"], driver, tmp_path)
    assert not report.all_resolved


def test_validate_citations_mixed_resolved_and_unresolved(driver: Driver, tmp_path: Path) -> None:
    report = validate_citations(
        ["graph:provider:9020000000", "graph:provider:doesnotexist"], driver, tmp_path
    )
    assert report.total_citations == 2
    assert report.resolved_citations == 1
    assert not report.all_resolved
