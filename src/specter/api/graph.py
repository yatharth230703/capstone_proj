"""Graph-neighborhood endpoint (M14 addendum, 2026-08-19) — wraps
`tools/graph_tools.expand_neighborhood`, which now returns real edges (it
silently always returned `edges: []` until this session; see the function's
own docstring). Read-only, same `app.state.driver` every other GET endpoint
uses.

`Taxonomy` nodes are dropped from the response, not from the underlying
tool: DME taxonomy code 332B00000X is shared by thousands of unrelated
providers in this cohort, so at `hops=2` it dominates the neighborhood with
noise that isn't an investigative signal — officer/address/phone-sharing
and exclusion-proximity are. This filtering is a rendering choice for the
dashboard's graph view, not a change to what the tool hands an LLM agent.

Dropping the `Taxonomy` hub also orphans every "other provider" whose only
path into the neighborhood *was* that shared taxonomy code — those nodes
are filtered out too, not left floating with no edge to anything. Keeping
them would render as a scatter of disconnected dots that look like data,
but aren't a real structural connection to this provider at all.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from specter.tools.graph_tools import expand_neighborhood, get_provider_profile

router = APIRouter()

_NOISY_TYPES = {"Taxonomy"}


@router.get("/graph/{npi}")
def get_graph(npi: str, request: Request, hops: int = 2, limit: int = 50) -> dict[str, Any]:
    driver = request.app.state.driver
    profile = get_provider_profile(driver, npi)
    if profile is None:
        return {
            "center_npi": npi,
            "found": False,
            "nodes": [],
            "edges": [],
        }
    center_ref = f"graph:provider:{npi}"
    subgraph = expand_neighborhood(driver, npi, hops=hops, limit=limit)
    candidate_nodes = [n for n in subgraph.nodes if n["item_type"] not in _NOISY_TYPES]
    candidate_refs = {center_ref} | {n["ref"] for n in candidate_nodes}
    edges = [
        e for e in subgraph.edges if e["source"] in candidate_refs and e["target"] in candidate_refs
    ]
    connected_refs = {e["source"] for e in edges} | {e["target"] for e in edges}
    nodes = [n for n in candidate_nodes if n["ref"] in connected_refs]
    center = {
        "ref": center_ref,
        "item_type": "Provider",
        "hop_distance": 0,
        "npi": npi,
        "organization_name": profile.organization_name,
    }
    return {
        "center_npi": npi,
        "found": True,
        "nodes": [center, *nodes],
        "edges": edges,
    }
