"""MCP integration (plan §8, CLAUDE.md M7): Playwright MCP for bot-blocked
sources and a self-authored Neo4j Cypher MCP server carrying CLAUDE.md's
four mandatory guardrails as one deterministic choke point.

**Why a self-authored Neo4j MCP server, not a third-party one.** CLAUDE.md's
guardrails (regex reject, forced LIMIT, timeout, read-only connection) must
sit *between* a generated Cypher string and execution. A third-party MCP
server gives no hook for that — the only controllable choke point is a
server we write ourselves. `neo4j_mcp_server()` below is that server; the
guardrail functions are plain, offline-testable Python, not MCP-only logic.

**Read-only enforcement without Enterprise RBAC.** This project's Neo4j is
Community Edition (`docker-compose.yml`), which does not support
`CREATE ROLE`/`GRANT` (`Neo.ClientError.Statement.UnsupportedAdministrationCommand`,
verified live this session). CLAUDE.md asks for "the read-only role
(`NEO4J_READONLY_USER`)" — the closest available equivalent in CE is a
dedicated `specter_ro` **user** (CE supports `CREATE USER`) combined with
every guarded query running in a session opened with
`default_access_mode="READ"`. That access mode *is* enforced by the server
itself, independent of RBAC — verified live: a `CREATE` sent through a READ
session raises `Neo.ClientError.Statement.AccessMode`. It is weaker than a
true Enterprise read-only role (a mis-tagged procedure could in principle
still write), so the regex reject stays as a second, independent layer
rather than being treated as redundant. See `NOTES_API_DEVIATIONS.md`.

**Timeout trap.** `Session.run(query, **kwargs)` treats unrecognized kwargs
as *Cypher parameters*, not transaction config — `session.run(q, timeout=10)`
silently does nothing (confirmed live: a query well past a 2s "timeout" ran
to completion with no error). The real mechanism is `neo4j.Query(text,
timeout=...)` passed as the query itself; verified live to raise
`Neo.ClientError.Transaction.TransactionTimedOutClientConfiguration`.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
from pathlib import Path
from typing import Any

import structlog
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.fastmcp import FastMCP
from neo4j import Driver, Query
from opentelemetry import trace

from specter.core.contracts import EvidenceArtifact
from specter.tools.evidence_tools import store_artifact

logger = structlog.get_logger(__name__)
tracer = trace.get_tracer(__name__)

_PLAYWRIGHT_MCP_ARGS = ["-y", "@playwright/mcp@latest", "--headless", "--isolated"]

# CLAUDE.md "Neo4j MCP guardrails": reject before execution. Word-boundary,
# case-insensitive; over-blocking a rare string-literal collision is the
# safe failure direction for an injection surface (CLAUDE.md hard rule 7).
_WRITE_VERB_PATTERN = re.compile(
    r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP)\b|CALL\s+apoc\.", re.IGNORECASE
)
_HAS_LIMIT_PATTERN = re.compile(r"\bLIMIT\s+\d+\b", re.IGNORECASE)

DEFAULT_QUERY_TIMEOUT_SECONDS = 10.0
DEFAULT_ROW_LIMIT = 100


class UnsafeCypherError(ValueError):
    """A generated Cypher string matched a forbidden write/APOC verb."""


# --- Neo4j Cypher MCP guardrails -------------------------------------------


def reject_unsafe_cypher(query: str) -> None:
    match = _WRITE_VERB_PATTERN.search(query)
    if match:
        raise UnsafeCypherError(
            f"rejected write-capable Cypher (matched {match.group()!r}): {query}"
        )


def ensure_limit_clause(query: str, limit: int = DEFAULT_ROW_LIMIT) -> str:
    if _HAS_LIMIT_PATTERN.search(query):
        return query
    return f"{query.rstrip().rstrip(';')} LIMIT {limit}"


def run_guarded_cypher(
    driver: Driver,
    query: str,
    *,
    timeout_seconds: float = DEFAULT_QUERY_TIMEOUT_SECONDS,
    limit: int = DEFAULT_ROW_LIMIT,
) -> list[dict[str, Any]]:
    """The single choke point CLAUDE.md's guardrails section mandates: reject
    write verbs, force-append LIMIT, log the generated Cypher to the trace
    span, then execute read-only with a hard timeout. Raises
    `UnsafeCypherError` before ever touching the driver.
    """
    reject_unsafe_cypher(query)
    guarded_query = ensure_limit_clause(query, limit)

    span = trace.get_current_span()
    span.set_attribute("specter.cypher", guarded_query)

    with driver.session(default_access_mode="READ") as session:
        result = session.run(Query(guarded_query, timeout=timeout_seconds))
        return [record.data() for record in result]


def neo4j_mcp_server(driver: Driver) -> FastMCP:
    """Build the stdio MCP server exposing `read_cypher` as the only tool.
    Run standalone (`python -m specter.tools.mcp_tools`) or connect to it
    from ADK via `McpToolset(connection_params=StdioConnectionParams(...))`.
    """
    server = FastMCP("specter-neo4j-cypher")

    @server.tool()
    def read_cypher(query: str) -> str:
        """Run a read-only Cypher query against the Specter graph. Write
        verbs and APOC calls are rejected; results are capped at 100 rows
        unless the query specifies its own LIMIT; queries time out after
        10 seconds.
        """
        rows = run_guarded_cypher(driver, query)
        return json.dumps(rows, default=str, sort_keys=True)

    return server


# --- Playwright MCP: real-browser fetch for WAF/Akamai-blocked sources -----


async def fetch_rendered(
    url: str, *, wait_seconds: float = 0.0
) -> tuple[str, bytes, dict[str, Any]]:
    """Navigate `url` in a real headless Chromium via `@playwright/mcp` and
    return `(html, screenshot_png_bytes, page_info)`. `page_info` carries
    the real HTTP status/title the MCP server reported, for callers that
    need to distinguish a genuine page from a WAF block page.
    """
    params = StdioServerParameters(command="npx", args=_PLAYWRIGHT_MCP_ARGS)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        nav_result = await session.call_tool("browser_navigate", {"url": url})
        if wait_seconds:
            await session.call_tool("browser_wait_for", {"time": wait_seconds})
        html = await evaluate(session, "() => document.documentElement.outerHTML")
        screenshot_result = await session.call_tool(
            "browser_take_screenshot", {"type": "png"}
        )
        png_bytes = _first_image_bytes(screenshot_result)
        return html, png_bytes, {"navigation": _first_text(nav_result)}


async def evaluate(session: ClientSession, js_function: str) -> Any:
    """Run `js_function` in the page already open on `session` and return
    its JSON-decoded result (falls back to raw text if not JSON)."""
    result = await session.call_tool("browser_evaluate", {"function": js_function})
    text = _first_text(result)
    if text is None:
        return None
    marker = "### Result\n"
    payload = text.split(marker, 1)[1].split("\n### ", 1)[0] if marker in text else text
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return payload.strip()


async def evaluate_paginated(
    base_url_fn: Any, js_function: str, *, pages: int, wait_seconds: float = 0.0
) -> list[Any]:
    """Drive one browser session across `pages` navigations, calling
    `js_function` on each and concatenating the (list-shaped) results.
    `base_url_fn(page_index)` builds each page's URL. Used by the DOJ
    deep-archive fetch to paginate a real-browser-only search endpoint.
    """
    params = StdioServerParameters(command="npx", args=_PLAYWRIGHT_MCP_ARGS)
    collected: list[Any] = []
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        for page_index in range(pages):
            await session.call_tool("browser_navigate", {"url": base_url_fn(page_index)})
            if wait_seconds:
                await session.call_tool("browser_wait_for", {"time": wait_seconds})
            page_rows = await evaluate(session, js_function)
            if isinstance(page_rows, list):
                collected.extend(page_rows)
    return collected


def fetch_rendered_sync(
    url: str, *, wait_seconds: float = 0.0
) -> tuple[str, bytes, dict[str, Any]]:
    return asyncio.run(fetch_rendered(url, wait_seconds=wait_seconds))


def evaluate_paginated_sync(
    base_url_fn: Any, js_function: str, *, pages: int, wait_seconds: float = 0.0
) -> list[Any]:
    return asyncio.run(
        evaluate_paginated(base_url_fn, js_function, pages=pages, wait_seconds=wait_seconds)
    )


def store_playwright_evidence(
    url: str, source_id: str, evidence_dir: Path, *, wait_seconds: float = 0.0
) -> tuple[EvidenceArtifact, EvidenceArtifact]:
    """Fetch `url` for real and store both the rendered HTML and a
    screenshot as `EvidenceArtifact`s (`extraction_method="playwright_mcp"`).
    """
    html, png_bytes, _page_info = fetch_rendered_sync(url, wait_seconds=wait_seconds)
    html_artifact = store_artifact(html, "text/html", source_id, evidence_dir, "playwright_mcp")
    screenshot_artifact = store_artifact(
        base64.b64encode(png_bytes).decode("ascii"),
        "image/png;base64",
        source_id,
        evidence_dir,
        "playwright_mcp",
    )
    return html_artifact, screenshot_artifact


def _first_text(result: Any) -> str | None:
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            return str(text)
    return None


def _first_image_bytes(result: Any) -> bytes:
    for block in result.content:
        data = getattr(block, "data", None)
        if data:
            return base64.b64decode(data)
    raise ValueError("browser_take_screenshot returned no image content")


if __name__ == "__main__":
    from neo4j import GraphDatabase

    from specter.settings import get_settings

    settings = get_settings()
    live_driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_readonly_user, settings.neo4j_readonly_password.get_secret_value()),
    )
    neo4j_mcp_server(live_driver).run()
