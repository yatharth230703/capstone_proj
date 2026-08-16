"""Structural tests for `workflow/screening.build_screening_workflow` (M6).
`Workflow` validates its graph at construction time (edges resolved into
nodes, routes checked for shape) — no LLM call needed to prove the graph is
wired correctly, only to prove the graph does the right thing once a real
call happens (BUILD_MILESTONES.md M6's own `scripts/40_screen.py` checkpoint
covers that, live).

CLAUDE.md/NOTES_API_DEVIATIONS.md D9: an unmatched conditional route ends
that branch with a `logging.warning`, not an exception — every routing map
needs an explicit `DEFAULT_ROUTE`. `test_every_conditional_source_has_a_
default_route` is a real structural proof of that, not a restatement.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from pathlib import Path

import pytest
from google.adk.workflow import DEFAULT_ROUTE
from neo4j import Driver, GraphDatabase

from specter.agents._base import build_runtime
from specter.settings import get_settings
from specter.tools.signal_tools import load_thresholds
from specter.workflow.screening import build_screening_workflow

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FAMILIES = {
    "address_anomaly": ["address_degree", "enumeration_burst", "address_churn"],
    "network_anomaly": ["phone_degree", "officer_degree", "geographic_spread"],
    "adverse_history": ["exclusion_proximity", "community_exclusion_density", "phoenix_pattern"],
}


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


@pytest.fixture(scope="module")
def workflow(driver: Driver, tmp_path_factory: pytest.TempPathFactory):
    settings = get_settings()
    thresholds = load_thresholds(_REPO_ROOT / "config" / "screening.yaml")
    runtime = build_runtime(
        run_id="test-screening-workflow",
        repo_root=_REPO_ROOT,
        graph_version="test",
        settings=settings,
    )
    tmp_dir = tmp_path_factory.mktemp("screening_workflow")
    return build_screening_workflow(
        driver=driver,
        runtime=runtime,
        thresholds=thresholds,
        evidence_dir=tmp_dir / "evidence",
        cases_dir=tmp_dir / "cases",
        snapshot_dir=_REPO_ROOT / "data" / "snapshot",
        taxonomy_prefix="332",
        states=["FL", "TX", "CA"],
        signal_families=_FAMILIES,
        min_independent_signal_families=3,
        evidence_freshness_days=180,
        cohort_limit=1,
    )


def test_expected_nodes_present(workflow) -> None:
    names = {n.name for n in workflow.graph.nodes}
    assert {"data_quality_gate", "halt_node", "cohort_select_node", "screen_provider"} <= names


def test_workflow_root_is_not_an_llm_agent_sub_agent(workflow) -> None:
    # NOTES_API_DEVIATIONS.md D9: Workflow cannot be an LlmAgent sub-agent —
    # asserting it is a bare BaseNode (not a BaseAgent) is the structural
    # proxy for "this is built to be the root, not nested".
    from google.adk.agents import BaseAgent

    assert not isinstance(workflow, BaseAgent)


def test_every_conditional_source_has_a_default_route(workflow) -> None:
    routes_by_source: dict[str, list] = defaultdict(list)
    for edge in workflow.graph.edges:
        if edge.route is not None:
            routes_by_source[edge.from_node.name].append(edge.route)

    assert routes_by_source, "expected at least one conditional edge (the data-quality gate)"
    for source, routes in routes_by_source.items():
        assert DEFAULT_ROUTE in routes, f"{source}: routes {routes} have no DEFAULT_ROUTE"


def test_fail_route_leads_to_halt_node_default_route_leads_onward(workflow) -> None:
    routes = {
        edge.route: edge.to_node.name
        for edge in workflow.graph.edges
        if edge.from_node.name == "data_quality_gate"
    }
    assert routes["fail"] == "halt_node"
    assert routes[DEFAULT_ROUTE] == "cohort_select_node"


def test_screen_provider_is_a_bounded_parallel_worker(workflow) -> None:
    screen_provider = next(n for n in workflow.graph.nodes if n.name == "screen_provider")
    assert getattr(screen_provider, "max_parallel_workers", None) == 4
