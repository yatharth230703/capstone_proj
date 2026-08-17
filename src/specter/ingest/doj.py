"""DOJ press-release connector (plan §5.2, M7 — narrows but does not fully
clear debt D-2; see NOTES_API_DEVIATIONS.md and BUILD_MILESTONES.md §4).

`justice.gov/news`'s own search UI is behind an Akamai JS challenge to a
plain HTTP client — `curl` gets only the challenge shell, confirmed live.
The RSS feed at `justice.gov/news/rss?type=press_release` is unprotected but
only carries a shallow recent window (~25 items, a day or two) and silently
ignores topic/keyword query params.

**M7 fix, verified live: real rendering, not real depth.**
`justice.gov/news/press-releases?keys=<terms>` renders fine through a real
headless Chromium (`@playwright/mcp`) where `curl` gets only the Akamai
challenge shell at the identical URL — genuine progress, not a workaround.
But the deep archive this was meant to unlock is **not actually reachable**:
`&page=1` (and every page beyond it) returns a hard Akamai "Access Denied",
confirmed live three independent ways — direct navigation, a fresh session's
very first request, and a real in-page click on the pager's own "Page 2"
link (correct Referer, real click event, not a constructed URL). All three
were blocked identically. `keys=`/`field_pr_topic=` are also confirmed
no-ops server-side (the exact same ~12-item "most recent" list comes back
regardless of the term), matching what the RSS feed's own query params
already did. Net effect: this connector's real reachable universe is one
page of DOJ's current recent-releases list, the same shape RSS already gave
it, not the plan's ~300-500 estimate. `_is_healthcare_fraud` still filters
client-side, same as before.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import quote_plus

import polars as pl
import structlog

from specter.core.contracts import SourceConfig, SourceManifest, ValidationReport
from specter.core.enums import FreshnessStatus, Verdict
from specter.ingest.base import Connector
from specter.tools.mcp_tools import evaluate_paginated_sync

logger = structlog.get_logger(__name__)

_PRESS_RELEASES_URL = "https://www.justice.gov/news/press-releases"
_SEARCH_KEYWORDS = "health care fraud"
# page>=1 is hard-blocked by Akamai regardless of navigation method (see
# module docstring) — default is deliberately 1, not a bug. Left as a
# constructor param, not hardcoded, in case the block is ever lifted.
_DEFAULT_PAGES = 1

_ROW_EXTRACTION_JS = """() => Array.from(document.querySelectorAll('.views-row')).map(r => ({
  title: (r.querySelector('h2.news-title a')?.textContent || '').trim(),
  link: r.querySelector('h2.news-title a')?.getAttribute('href') || null,
  description: (r.querySelector('.field_teaser')?.textContent || '').trim(),
  pub_date: r.querySelector('.node-date time')?.getAttribute('datetime') || null,
}))"""

_HEALTH_TERMS = (
    "health care",
    "healthcare",
    "medicare",
    "medicaid",
    "durable medical equipment",
    " dme ",
)
_FRAUD_TERMS = ("fraud", "kickback", "scheme", "false claims", "billing")

# Below this, the RSS feed's shallow window is very likely the whole reason —
# not a broken query — so the manifest gets WARN, not FAIL.
_THIN_COVERAGE_THRESHOLD = 3


def _is_healthcare_fraud(title: str, description: str) -> bool:
    text = f"{title} {description}".lower()
    return any(h in text for h in _HEALTH_TERMS) and any(f in text for f in _FRAUD_TERMS)


class DojConnector(Connector):
    source_id = "doj"
    expected_columns = frozenset({"title", "link", "description", "pub_date", "guid"})

    def __init__(self, pages: int = _DEFAULT_PAGES) -> None:
        self.pages = pages

    def fetch(self, cfg: SourceConfig) -> Path:
        cfg.raw_dir.mkdir(parents=True, exist_ok=True)
        out_path = cfg.raw_dir / "doj_raw.json"

        def page_url(page_index: int) -> str:
            return f"{_PRESS_RELEASES_URL}?keys={quote_plus(_SEARCH_KEYWORDS)}&page={page_index}"

        raw_rows = evaluate_paginated_sync(page_url, _ROW_EXTRACTION_JS, pages=self.pages)
        out_path.write_text(json.dumps(raw_rows), encoding="utf-8")
        logger.info("doj.fetch complete", pages=self.pages, raw_row_count=len(raw_rows))
        return out_path

    def parse(self, raw: Path) -> pl.DataFrame:
        raw_rows = json.loads(raw.read_text(encoding="utf-8"))
        rows = []
        for item in raw_rows:
            title = (item.get("title") or "").strip()
            description = (item.get("description") or "").strip()
            if not _is_healthcare_fraud(title, description):
                continue
            link = item.get("link")
            absolute_link = (
                f"https://www.justice.gov{link}" if link and link.startswith("/") else link
            )
            pub_date_raw = item.get("pub_date")
            pub_date = None
            if pub_date_raw:
                try:
                    pub_date = datetime.fromisoformat(pub_date_raw.replace("Z", "+00:00"))
                except ValueError:
                    pub_date = None
            rows.append(
                {
                    "title": title,
                    "link": absolute_link,
                    "description": description,
                    "pub_date": pub_date,
                    "guid": absolute_link,
                }
            )
        if not rows:
            return pl.DataFrame(
                schema={
                    "title": pl.Utf8,
                    "link": pl.Utf8,
                    "description": pl.Utf8,
                    "pub_date": pl.Datetime(time_zone="UTC"),
                    "guid": pl.Utf8,
                }
            )
        return pl.DataFrame(rows)

    def validate(self, df: pl.DataFrame) -> ValidationReport:
        missing_columns = sorted(self.expected_columns - set(df.columns))
        null_rates = (
            {col: df[col].null_count() / df.height for col in df.columns} if df.height else {}
        )
        duplicate_key_rate = (
            1 - (df["guid"].n_unique() / df.height) if df.height and "guid" in df.columns else 0.0
        )

        verdict = Verdict.PASS_
        if missing_columns:
            verdict = Verdict.FAIL
        elif df.height < _THIN_COVERAGE_THRESHOLD:
            verdict = Verdict.WARN

        return ValidationReport(
            source_id=self.source_id,
            checked_at=datetime.now(UTC),
            missing_columns=missing_columns,
            schema_drift=[],
            null_rate_per_column=null_rates,
            duplicate_key_rate=duplicate_key_rate,
            row_count_delta=None,
            date_range_sanity_ok=True,
            verdict=verdict,
        )

    def build_manifest(
        self,
        cfg: SourceConfig,
        raw_path: Path,
        checksum: str,
        df: pl.DataFrame,
        report: ValidationReport,
    ) -> SourceManifest:
        known_limitations = [
            "fetched via Playwright MCP (real headless Chromium — the search UI 403s to a "
            "plain HTTP client); `keys=`/`field_pr_topic=` are confirmed no-ops server-side "
            "(same list regardless of term), so the client-side title+description "
            "AND-filter is still authoritative, same as the RSS-based predecessor",
            "deep archive coverage (plan's ~300-500 release estimate) is NOT reachable: "
            "page>=1 returns a hard Akamai 'Access Denied', confirmed live via direct "
            "navigation, a fresh session's first request, and a real click on the pager's "
            "own 'Page 2' link — not a request-construction bug, a site-side block. This "
            "connector's real universe is one page of the current recent-releases list, "
            "the same shape RSS already provided. See NOTES_API_DEVIATIONS.md.",
        ]
        return SourceManifest(
            source_id=self.source_id,
            dataset_name="DOJ Press Releases (healthcare-fraud filtered)",
            original_publisher="U.S. Department of Justice",
            access_provider="justice.gov press-releases search (Playwright MCP)",
            source_url=f"{_PRESS_RELEASES_URL}?keys={quote_plus(_SEARCH_KEYWORDS)}",
            license_or_terms="public domain (U.S. Government Work)",
            snapshot_date=date.today(),
            retrieved_at=datetime.now(UTC),
            checksum_sha256=checksum,
            schema_version="doj-playwright-mcp-1.0",
            coverage={
                "topic_filter": "healthcare_fraud",
                "pages_fetched": str(self.pages),
                "fetch_method": "playwright_mcp",
            },
            freshness_status=FreshnessStatus.CURRENT,
            known_limitations=known_limitations,
            row_count=df.height,
        )
