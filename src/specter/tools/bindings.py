"""Model-facing tool bindings (plan §8).

Every function in `graph_tools`/`signal_tools`/`entity_tools`/`evidence_tools`
takes infrastructure as its first arguments — a `neo4j.Driver`, a
`ScreeningThresholds`, an evidence directory. None of that may ever reach an
LLM: the model must not be able to choose a threshold (it would be choosing a
number, violating CLAUDE.md hard rule 1) and cannot meaningfully supply a
driver at all.

This module binds those arguments and re-exposes each tool with a clean,
model-facing signature. ADK auto-wraps bare callables in `FunctionTool`
(`llm_agent.py:204`), deriving the tool name from `__name__` and the
description from the docstring — so the docstrings here are written for the
model, not for a Python reader.

Return shape: every binding returns a `dict`. ADK only recognises a tool
failure when the return value is a dict with a truthy `"error"` key
(`function_tool.py:328`), and a dict keeps numeric values greppable for the
numeric-grounding check in `judge/deterministic_checks.py` (M9).

`from __future__ import annotations` is load-bearing here: it makes
`inspect.signature` report annotations as plain strings (`"str"`, not
`"<class 'str'>"`), which is what keeps the generated B0 block byte-stable
across machines and Python builds. B0 sits above the cache boundary — a
representation change there silently zeroes the cache hit rate.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from neo4j import Driver
from pydantic import BaseModel

from specter.core.contracts import ScreeningThresholds
from specter.tools import entity_tools, evidence_tools, graph_tools
from specter.tools.signal_bindings import build_signal_bindings


def _dump(model: BaseModel | None) -> dict[str, Any] | None:
    return None if model is None else model.model_dump(mode="json")


def build_tool_bindings(
    driver: Driver, thresholds: ScreeningThresholds, evidence_dir: Path
) -> list[Callable[..., Any]]:
    """Bind infrastructure into every tool and return the model-facing list.

    The returned order is stable (definition order), and `generate_b0_tool_schemas`
    sorts by name regardless, so B0 is deterministic either way.
    """

    # ---- graph tools -------------------------------------------------

    def get_provider_profile(npi: str) -> dict[str, Any]:
        """Look up one provider's full identity record: legal name, entity type,
        state, enumeration date, addresses, phones, authorized officers,
        taxonomies, and any exclusions attached to it.

        This is the first call to make when investigating a provider. Every
        value it returns is read directly from the knowledge graph.

        Args:
            npi: the provider's 10-digit National Provider Identifier.

        Returns:
            {"found": bool, "profile": {...} | None}. `found` is False when no
            provider with that NPI exists in the graph — that is a valid
            answer, not an error, and you must not invent a profile for it.
        """
        profile = graph_tools.get_provider_profile(driver, npi)
        return {"found": profile is not None, "profile": _dump(profile)}

    def expand_neighborhood(npi: str, hops: int = 2, limit: int = 50) -> dict[str, Any]:
        """Return the subgraph around a provider: every node reachable within
        `hops` relationships, plus the edges connecting them.

        Use this to see a provider's structural context — who shares its
        address, phone, or officers, and what those entities connect to in turn.

        Args:
            npi: the provider's 10-digit NPI.
            hops: relationship depth, 1-3. Values above 3 are clamped to 3.
            limit: maximum nodes returned, up to 200. Higher values are clamped.

        Returns:
            {"center_npi": str, "nodes": [...], "edges": [...], "node_count": int,
             "edge_count": int}. Counts are computed here, not by you.
        """
        subgraph = graph_tools.expand_neighborhood(driver, npi, hops, limit)
        return {
            **subgraph.model_dump(mode="json"),
            "node_count": len(subgraph.nodes),
            "edge_count": len(subgraph.edges),
        }

    def find_shared_attribute_peers(npi: str, attribute: str) -> dict[str, Any]:
        """List the other providers that share a given attribute with this one.

        Sharing an address or phone number is a fact, not a finding: legitimate
        medical office buildings and multi-site practices produce the same
        pattern. Report what is shared and let the counter-evidence step judge it.

        Args:
            npi: the provider's 10-digit NPI.
            attribute: exactly one of "address", "phone", or "officer".

        Returns:
            {"peers": [...], "peer_count": int} where each peer carries the
            shared value and its source_ids. On an invalid `attribute` value,
            returns {"error": "..."} — pass one of the three literal strings.
        """
        if attribute not in ("address", "phone", "officer"):
            return {
                "error": (
                    f"attribute must be 'address', 'phone', or 'officer', got {attribute!r}"
                )
            }
        peers = graph_tools.find_shared_attribute_peers(driver, npi, attribute)  # type: ignore[arg-type]
        return {
            "peers": [peer.model_dump(mode="json") for peer in peers],
            "peer_count": len(peers),
        }

    def shortest_path_to_exclusion(npi: str, max_hops: int = 4) -> dict[str, Any]:
        """Find the shortest relationship path from this provider to any excluded
        individual or organization in the graph.

        A short path is a proximity fact, never an accusation: it says this
        provider is N relationships away from an entity that carries an
        exclusion, and nothing about this provider's own conduct.

        Args:
            npi: the provider's 10-digit NPI.
            max_hops: maximum path length to search, default 4.

        Returns:
            {"found": bool, "path": {...} | None}. `found` False means no
            exclusion is reachable within `max_hops` — report that as the
            absence of a signal, not as evidence of anything.
        """
        path = graph_tools.shortest_path_to_exclusion(driver, npi, max_hops)
        return {"found": path is not None, "path": _dump(path)}

    def get_community_context(npi: str) -> dict[str, Any]:
        """Return the graph community this provider belongs to, with the
        deterministic structural facts about it (member count, shared
        attributes, excluded-member count) and, when available, a written
        characterization of the community.

        Args:
            npi: the provider's 10-digit NPI.

        Returns:
            {"found": bool, "community": {...} | None}. Providers not in any
            community return found=False — most providers are isolated and
            that is unremarkable.
        """
        summary = graph_tools.get_community_context(driver, npi)
        return {"found": summary is not None, "community": _dump(summary)}

    def search_enforcement_cases(query: str, k: int = 10) -> dict[str, Any]:
        """Search the stored corpus of enforcement cases (DOJ press releases and
        related records) for text matching `query`.

        Results are candidate reading material, not matches to your provider. A
        case mentioning a similar name or scheme is not evidence that this
        provider is connected to it — treat any linkage as requiring explicit
        disambiguation.

        Args:
            query: free-text search terms, e.g. "durable medical equipment
                billing scheme Florida".
            k: maximum number of cases to return, default 10.

        Returns:
            {"hits": [...], "hit_count": int}, each hit carrying case_id, title,
            a snippet, and source_ids.
        """
        hits = graph_tools.search_enforcement_cases(driver, query, k)
        return {
            "hits": [hit.model_dump(mode="json") for hit in hits],
            "hit_count": len(hits),
        }

    # ---- entity + evidence tools -------------------------------------

    def normalize_address(raw: str) -> dict[str, Any]:
        """Parse a raw U.S. address into its deterministic collision key.

        Suite and unit are deliberately excluded from the key, so two providers
        in different suites of one building share a key. That is correct
        behaviour and must not be worked around.

        Args:
            raw: a raw address string, e.g. "1500 Biscayne Blvd Unit 3B, Miami, FL 33132".

        Returns:
            The parsed address, including `normalized_key` and a
            `parse_confidence` of "high" or "low".
        """
        return entity_tools.normalize_address(raw).model_dump(mode="json")

    def name_similarity(a: str, b: str) -> dict[str, Any]:
        """Score how similar two organization or person names are, 0-100.

        A high score is a reason to investigate whether two records refer to one
        entity. It is never on its own a reason to link them, and a common name
        matching a sanctioned party is not a match.

        Args:
            a: the first name.
            b: the second name.

        Returns:
            {"score": float} on a 0-100 scale.
        """
        return {"score": entity_tools.name_similarity(a, b)}

    def propose_entity_matches(npi: str, candidates: list[str]) -> dict[str, Any]:
        """Compute the deterministic match features between this provider and
        each candidate NPI: name similarity, and whether they share an address,
        phone, or officer.

        This returns features only — it deliberately does not decide whether the
        records match. That adjudication is yours, and a false merge is far more
        damaging than a missed match.

        Args:
            npi: the provider's 10-digit NPI.
            candidates: NPIs to compare against.

        Returns:
            {"proposals": [...], "proposal_count": int}.
        """
        proposals = entity_tools.propose_entity_matches(driver, npi, candidates)
        return {
            "proposals": [p.model_dump(mode="json") for p in proposals],
            "proposal_count": len(proposals),
        }

    def validate_citations(source_ids: list[str]) -> dict[str, Any]:
        """Check that every source id resolves to a stored evidence artifact or
        an existing graph node.

        Run this before finalizing any output that carries citations. An
        unresolved source id is a bug in the claim, not a formatting problem.

        Args:
            source_ids: the source ids to verify.

        Returns:
            {"total_citations": int, "resolved_citations": int,
             "unresolved_source_ids": [...], "all_resolved": bool}.
        """
        report = evidence_tools.validate_citations(source_ids, driver, evidence_dir)
        return report.model_dump(mode="json")

    return [
        get_provider_profile,
        expand_neighborhood,
        find_shared_attribute_peers,
        shortest_path_to_exclusion,
        get_community_context,
        search_enforcement_cases,
        *build_signal_bindings(driver, thresholds),
        normalize_address,
        name_similarity,
        propose_entity_matches,
        validate_citations,
    ]
