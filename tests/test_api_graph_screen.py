"""M14-addendum checkpoint (BUILD_MILESTONES.md, 2026-08-19): the graph
neighborhood endpoint returns real, connected data (no floating nodes with
no surviving edge), and the live-screening endpoint is POST-only, fails
loudly on a dead Azure key before touching the graph, and 404s on an
unknown npi rather than crashing deep in the agent chain.

Same skip-if-unreachable / offline-vs-live split the rest of `tests/
test_api*.py` uses. The screening endpoint's actual success path (a real,
billed multi-agent run) is never exercised here — same "run by hand"
convention `POST /research` already established.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from neo4j import Driver, GraphDatabase

from specter.api import screen as screen_module
from specter.api.app import app
from specter.settings import get_settings


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
    with drv.session() as session:
        record = session.run(
            "MATCH (p:Provider) WHERE p.scenario_id = 'S02' RETURN count(p) AS c"
        ).single()
    if record is None or record["c"] == 0:
        pytest.skip("Synthetic scenarios not loaded — run scripts/20_build_graph.py first")
    yield drv
    drv.close()


# --- /graph/{npi} (read-only) -------------------------------------------


def test_graph_endpoint_unknown_npi_returns_found_false(driver: Driver) -> None:
    with TestClient(app) as client:
        resp = client.get("/graph/0000000000")
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is False
    assert body["nodes"] == []
    assert body["edges"] == []


def test_graph_endpoint_real_provider_has_connected_nodes_only(driver: Driver) -> None:
    with TestClient(app) as client:
        resp = client.get("/graph/9020000000")
    assert resp.status_code == 200
    body = resp.json()
    assert body["found"] is True
    refs = {n["ref"] for n in body["nodes"]}
    assert "graph:provider:9020000000" in refs
    # No Taxonomy nodes ever survive the rendering filter (api/graph.py).
    assert all(n["item_type"] != "Taxonomy" for n in body["nodes"])
    # Every returned node — the center included — is an endpoint of some
    # edge; no orphaned "shares a taxonomy code" scatter dots.
    connected = {e["source"] for e in body["edges"]} | {e["target"] for e in body["edges"]}
    for n in body["nodes"]:
        assert n["ref"] in connected


# --- POST /screen (the second write path) -------------------------------


def test_screen_endpoint_is_post_only_never_get() -> None:
    methods = set(app.openapi()["paths"]["/screen"])
    assert methods == {"post"}


def test_screen_rejects_a_malformed_npi_before_touching_anything() -> None:
    with TestClient(app) as client:
        resp = client.post("/screen", json={"npi": "not-an-npi"})
    assert resp.status_code == 422


def test_screen_fails_loudly_when_azure_is_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    def _dead_key(settings: object) -> None:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="Azure key check failed (401): simulated")

    monkeypatch.setattr(screen_module, "_confirm_azure_key_alive", _dead_key)
    with TestClient(app) as client:
        resp = client.post("/screen", json={"npi": "1003001439"})
    assert resp.status_code == 503
    assert "Azure key check failed" in resp.json()["detail"]
