"""DOJ press-release connector (plan §5.2).

`justice.gov/news`'s own search UI is behind an Akamai JS challenge — `curl`
gets only the challenge shell, confirmed live. The RSS feed at
`justice.gov/news/rss?type=press_release` is unprotected and returns real
items, but two things make it a *partial* source for M1, not the full one:
it silently ignores topic/keyword query params (always the same generic
latest-releases list), and it only carries a shallow recent window (~25 items
covering a day or two), not the deep archive the plan's ~300-500 estimate
implies. Client-side keyword filtering stands in for the ignored server-side
filter; the deep archive is a plan §9.6/§14 Playwright MCP job (M7) — this
connector's `known_limitations` says so explicitly rather than pretending
today's thin feed is the whole picture.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
import polars as pl
import structlog

from specter.core.contracts import SourceConfig, SourceManifest, ValidationReport
from specter.core.enums import FreshnessStatus, Verdict
from specter.ingest.base import Connector

logger = structlog.get_logger(__name__)

_RSS_URL = "https://www.justice.gov/news/rss?type=press_release"

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

    def fetch(self, cfg: SourceConfig) -> Path:
        cfg.raw_dir.mkdir(parents=True, exist_ok=True)
        out_path = cfg.raw_dir / "doj_raw.xml"
        response = httpx.get(_RSS_URL, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        out_path.write_bytes(response.content)
        logger.info("doj.fetch complete", size_bytes=len(response.content))
        return out_path

    def parse(self, raw: Path) -> pl.DataFrame:
        tree = ET.parse(raw)
        rows = []
        for item in tree.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            description = (item.findtext("description") or "").strip()
            if not _is_healthcare_fraud(title, description):
                continue
            pub_date_raw = item.findtext("pubDate")
            pub_date = None
            if pub_date_raw:
                try:
                    pub_date = parsedate_to_datetime(pub_date_raw)
                except (TypeError, ValueError):
                    pub_date = None
            rows.append(
                {
                    "title": title,
                    "link": item.findtext("link"),
                    "description": description,
                    "pub_date": pub_date,
                    "guid": item.findtext("guid"),
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
            "RSS feed covers only a shallow recent window (~1-2 days); server-side "
            "topic/keyword filters are ignored by the feed, so filtering is done "
            "client-side against title+description",
            "deep archive coverage (plan's ~300-500 release estimate) requires "
            "Playwright MCP against justice.gov/news, which is Akamai-protected "
            "against plain HTTP clients — deferred to M7",
        ]
        return SourceManifest(
            source_id=self.source_id,
            dataset_name="DOJ Press Releases (healthcare-fraud filtered)",
            original_publisher="U.S. Department of Justice",
            access_provider="justice.gov RSS feed",
            source_url=_RSS_URL,
            license_or_terms="public domain (U.S. Government Work)",
            snapshot_date=date.today(),
            retrieved_at=datetime.now(UTC),
            checksum_sha256=checksum,
            schema_version="doj-rss-2.0",
            coverage={"topic_filter": "healthcare_fraud", "window": "recent (~1-2 days)"},
            freshness_status=FreshnessStatus.CURRENT,
            known_limitations=known_limitations,
            row_count=df.height,
        )
