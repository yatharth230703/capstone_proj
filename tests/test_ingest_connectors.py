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


_FL_HEADER = (
    "Florida Medicaid Provider ID,Provider Name,DBA Name,Provider Type Code,"
    "Provider Specialty Code,Taxonomy Code,Service Location Address 1     ,"
    "Service Location Address 2     ,Service Location Address City  ,"
    "Service Location Address State ,Service Location Address zip+4 ,Enrollment Type,"
    "NPI Type 1 = Individual 2 = Organization U = Unknown,NPI,NPI Effective Date,"
    "NPI End Date,NPI Status A = Active I = Inactive ,Individual or Organizational Provider,"
    "License,Current Medicaid Enrollment Status A = Active I = Inactive E = Ineligible,"
    "Medicaid Claims Eligibility Effective Date,Medicaid Claims Eligibility End Date,"
    "Next Revalidation Date"
)


def _fl_row(pid: str, name: str, npi: str, status: str) -> str:
    """One FLMMIS PML row in the source's Excel-CSV-wrapped shape."""
    return (
        f'="{pid}","{name}","",="39",="096","251C00000X","1 MAIN ST","",'
        f'"MIAMI","FL",="33143-6636",ENROLLMENT,="1",="{npi}",2008-06-13,'
        f'2299-12-31,A,"O",="X1",{status},2009-01-16,2026-06-06,2028-07-04'
    )


def test_state_medicaid_fl_parse(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """FL path: keep only Ineligible rows, unwrap `="..."`, never guess a date."""
    raw = tmp_path / "fl.csv"
    raw.write_text(
        "\n".join(
            [
                _FL_HEADER,
                _fl_row("000000900", "ACTIVE               ONE", "1508023334", "A"),
                _fl_row("000001000", "INELIGIBLE           TWO", "1245298314", "E"),
                # same provider, one segment carrying the NPI and one not:
                # the null-NPI row is redundant and must collapse away.
                _fl_row("000001100", "INELIGIBLE           THREE", "1285773010", "E"),
                _fl_row("000001100", "INELIGIBLE           THREE", "", "E"),
                # continuation row for an extra service location: blank status.
                _fl_row("000001200", "CONTINUATION         FOUR", "", " "),
            ]
        ),
        encoding="utf-8",
    )
    df = StateMedicaidConnector("FL").parse(raw)

    assert df.height == 2
    assert sorted(df["state_provider_number"].to_list()) == ["000001000", "000001100"]
    assert sorted(df["npi"].to_list()) == ["1245298314", "1285773010"]
    # whitespace collapsed, Excel wrapper gone, jurisdiction/authority stamped
    assert "INELIGIBLE TWO" in df["provider_name"].to_list()
    assert df["address"].to_list()[0] == "1 MAIN ST, MIAMI, FL, 33143-6636"
    assert df["provider_type"].to_list() == ["39", "39"]
    assert set(df["jurisdiction"].to_list()) == {"FL"}
    # this source records no termination date; it must not be invented
    assert df["action_date"].null_count() == df.height
    assert set(df.columns) == set(StateMedicaidConnector("FL").expected_columns)


def test_state_medicaid_fl_parse_missing_npi_kept_as_null(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A blank NPI is null, not "", so Amendment 1's no-auto-link rule can see it."""
    raw = tmp_path / "fl.csv"
    raw.write_text(
        "\n".join([_FL_HEADER, _fl_row("000002000", "NO NPI HERE", "", "E")]),
        encoding="utf-8",
    )
    df = StateMedicaidConnector("FL").parse(raw)
    assert df.height == 1
    assert df["npi"].to_list() == [None]


def test_state_medicaid_tx_parse(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """TX path: drop reinstated providers, coalesce company vs person names.

    The workbook is a legacy `.xls` that no installed library can *write*, so
    the sheet `read_excel` would return is injected directly. What is under
    test is the mapping, which is where the reinstatement trap lives.
    """
    sheet = pl.DataFrame(
        {
            "CompanyName": [None, "ACME HOME HEALTH LLC", None],
            "LastName": ["Excluded", None, "Reinstated"],
            "FirstName": ["Ann", None, "Bob"],
            "MidInitial": ["Q", None, None],
            "Occupation": ["RN", "Agency", "LVN"],
            "LicenseNumber": ["550376", None, "142862"],
            "NPI": [None, "1245298314", None],
            "StartDate": ["1994-02-22 00:00:00", "2021-07-01 00:00:00", "1996-11-15 00:00:00"],
            "ReinstatedDate": [None, None, "5/5/2004"],
            "WebComments": ["Conviction", "Board action", "LICENSE REVOKED"],
        }
    )
    monkeypatch.setattr(pl, "read_excel", lambda *a, **k: {"EXCEL_Destination": sheet})
    raw = tmp_path / "tx.xls"
    raw.write_bytes(b"not-really-xls-read_excel-is-patched")
    df = StateMedicaidConnector("TX").parse(raw)

    # the reinstated provider is history, not a current exclusion
    assert df.height == 2
    assert "Reinstated" not in " ".join(df["provider_name"].to_list())
    # individuals get their name assembled, companies use CompanyName as-is
    assert df["provider_name"].to_list() == ["Ann Q Excluded", "ACME HOME HEALTH LLC"]
    assert df["npi"].to_list() == [None, "1245298314"]
    assert [str(d) for d in df["action_date"].to_list()] == ["1994-02-22", "2021-07-01"]
    # this source carries no address column at all
    assert df["address"].null_count() == df.height
    assert set(df["jurisdiction"].to_list()) == {"TX"}
    assert set(df.columns) == set(StateMedicaidConnector("TX").expected_columns)


def test_state_medicaid_tx_parse_rejects_multi_sheet(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    """An unexpected second sheet halts the run rather than picking one (rule 7)."""
    two = {"a": pl.DataFrame(), "b": pl.DataFrame()}
    monkeypatch.setattr(pl, "read_excel", lambda *a, **k: two)
    raw = tmp_path / "tx.xls"
    raw.write_bytes(b"not-really-xls-read_excel-is-patched")
    with pytest.raises(ValueError, match="expected exactly 1"):
        StateMedicaidConnector("TX").parse(raw)


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
