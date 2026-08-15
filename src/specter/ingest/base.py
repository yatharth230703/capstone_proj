"""Connector ABC (plan §5.4). `run()` is the template method: fetch -> hash ->
parse -> validate -> manifest. Raises `ConnectorValidationError` on FAIL.

`build_manifest` is an addition beyond the plan's literal fetch/parse/validate
trio: CLAUDE.md Amendment 1 requires one connector class to back three
independently-manifested `state_medicaid` instances (FL/TX/CA), each with its
own publisher/URL/limitations. Those per-instance fields can't be class-level
constants, so each connector assembles its own `SourceManifest` from
`cfg.params` instead of the base class guessing at a one-size-fits-all shape.

`source_id` and `expected_columns` are plain (not `ClassVar`) attributes for
the same reason: single-instance connectors (NPPES, LEIE, DOJ) set them as
class attributes, but `StateMedicaidConnector` sets `source_id` per-instance
in `__init__` since it varies by jurisdiction.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import polars as pl

from specter.core.contracts import SourceConfig, SourceManifest, ValidationReport
from specter.core.enums import Verdict
from specter.core.errors import ConnectorValidationError
from specter.core.hashing import sha256_file


class Connector(ABC):
    source_id: str
    expected_columns: frozenset[str]

    @abstractmethod
    def fetch(self, cfg: SourceConfig) -> Path:
        """Download/write the raw source artifact under `cfg.raw_dir` and
        return its path. Must not transform the data.
        """

    @abstractmethod
    def parse(self, raw: Path) -> pl.DataFrame:
        """Parse the raw artifact into a Polars DataFrame."""

    @abstractmethod
    def validate(self, df: pl.DataFrame) -> ValidationReport:
        """Check `df` against `expected_columns` and data-quality rules."""

    @abstractmethod
    def build_manifest(
        self,
        cfg: SourceConfig,
        raw_path: Path,
        checksum: str,
        df: pl.DataFrame,
        report: ValidationReport,
    ) -> SourceManifest:
        """Assemble the `SourceManifest` for this run."""

    def run(self, cfg: SourceConfig) -> tuple[pl.DataFrame, SourceManifest]:
        raw_path = self.fetch(cfg)
        checksum = sha256_file(raw_path)
        df = self.parse(raw_path)
        report = self.validate(df)
        if report.verdict is Verdict.FAIL:
            raise ConnectorValidationError(self.source_id, report)
        manifest = self.build_manifest(cfg, raw_path, checksum, df, report)
        return df, manifest
