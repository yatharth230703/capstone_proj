"""M1 checkpoint (CLAUDE.md Amendment 1): deliberate schema corruption yields
FAIL for every connector. Offline/deterministic — does not hit the network.
"""

import polars as pl
import pytest

from specter.core.enums import Verdict
from specter.core.errors import ConnectorValidationError
from specter.ingest.doj import DojConnector
from specter.ingest.leie import LeieConnector
from specter.ingest.nppes import NppesConnector
from specter.ingest.state_medicaid import StateMedicaidConnector
from specter.ingest.synthetic import SyntheticExclusionsConnector, SyntheticProvidersConnector

CONNECTORS = [
    NppesConnector(),
    LeieConnector(),
    DojConnector(),
    StateMedicaidConnector("CA"),
    StateMedicaidConnector("FL"),
    StateMedicaidConnector("TX"),
    SyntheticProvidersConnector(),
    SyntheticExclusionsConnector(),
]


@pytest.mark.parametrize("connector", CONNECTORS, ids=lambda c: c.source_id)
def test_validate_fails_on_missing_columns(connector: object) -> None:
    corrupted = pl.DataFrame({"totally_unexpected_column": [1, 2, 3]})
    report = connector.validate(corrupted)  # type: ignore[attr-defined]
    assert report.verdict is Verdict.FAIL
    assert report.missing_columns


@pytest.mark.parametrize("connector", CONNECTORS, ids=lambda c: c.source_id)
def test_expected_columns_nonempty(connector: object) -> None:
    assert connector.expected_columns  # type: ignore[attr-defined]


def test_leie_fails_on_empty_dataframe() -> None:
    connector = LeieConnector()
    empty = pl.DataFrame(schema={col: pl.Utf8 for col in connector.expected_columns})
    report = connector.validate(empty)
    assert report.verdict is Verdict.FAIL


def test_state_medicaid_ca_rejects_unknown_jurisdiction() -> None:
    with pytest.raises(ValueError, match="unknown state_medicaid jurisdiction"):
        StateMedicaidConnector("NY")


def test_connector_validation_error_raised_on_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path

    from specter.core.contracts import SourceConfig

    connector = LeieConnector()
    monkeypatch.setattr(connector, "fetch", lambda cfg: Path("/dev/null"))
    monkeypatch.setattr(
        connector, "parse", lambda raw: pl.DataFrame({"totally_unexpected_column": [1]})
    )
    with pytest.raises(ConnectorValidationError):
        connector.run(SourceConfig(source_id="leie", raw_dir=Path("/tmp"), params={}))
