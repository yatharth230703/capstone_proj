"""Specter's exception hierarchy. CLAUDE.md hard rule 7: fail loudly, no bare
`except:`, no fallback that masks a broken source.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from specter.core.contracts import ValidationReport


class SpecterError(Exception):
    """Base for all Specter-raised exceptions."""


class ConnectorValidationError(SpecterError):
    """Raised by `Connector.run()` when `validate()` returns a FAIL verdict.
    Carries the report so callers can report exactly why the run halted.
    """

    def __init__(self, source_id: str, report: ValidationReport) -> None:
        self.source_id = source_id
        self.report = report
        super().__init__(
            f"{source_id}: validation FAILed — "
            f"missing_columns={report.missing_columns}, "
            f"schema_drift={report.schema_drift}"
        )
