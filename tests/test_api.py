"""M13 checkpoint (BUILD_MILESTONES.md): the dashboard data API returns the
real artifacts as JSON, fails loudly (not with an empty-list placeholder)
when a gitignored run artifact is missing, and carries the D-23/D-28
caveats in every response that needs them — not just in the happy path.

Group A (offline, no external services) monkeypatches each router's data
path to a controlled fixture/missing location — this is what actually
exercises the fail-loudly behavior CLAUDE.md hard rule 7 requires, since the
real `data/` artifacts exist in this dev session and would otherwise mask
the missing-artifact code path entirely.

Group B (skip if Neo4j unreachable) hits the real, already-generated
`data/cases/`, `data/ledger.sqlite`, `JudgeReport.md`, and
`data/models/anomaly_isoforest-v1.joblib` this session already has —
same skip-if-unreachable pattern `test_ml_tools.py`/`test_signal_tools.py`
use. `POST /research` makes a real, billed Vertex call and is deliberately
never exercised by the automated suite (same convention as
`scripts/45_smoke_grounded_research.py` — "run by hand").
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from neo4j import Driver, GraphDatabase

from specter.api import cases as cases_module
from specter.api import costs as costs_module
from specter.api import judge as judge_module
from specter.api.app import app
from specter.core.contracts import CasePacket, CitationReport, CounterEvidence
from specter.core.enums import CacheLayer
from specter.llm.ledger import CostLedger
from specter.settings import get_settings

CASES_DIR = Path("data/cases")
LEDGER_PATH = Path("data/ledger.sqlite")
JUDGE_REPORT_PATH = Path("JudgeReport.md")
MODEL_PATH = Path("data/models/anomaly_isoforest-v1.joblib")


def _empty_case(npi: str) -> CasePacket:
    return CasePacket(
        provider_npi=npi,
        narrative="no signals fired for this provider",
        signals=[],
        enforcement_matches=[],
        legal_status_per_match=[],
        counter_evidence=CounterEvidence(
            per_signal=[], unresolved_conflicts=[], confidence_adjustment=0.0
        ),
        citation_report=CitationReport(
            total_citations=0, resolved_citations=0, unresolved_source_ids=[], all_resolved=True
        ),
        created_at=datetime.now(UTC),
    )


# --- Group A: offline, monkeypatched paths -----------------------------


def test_research_endpoint_is_post_only_never_get() -> None:
    """CLAUDE.md Amendment 4(a): the one write endpoint must never fire on
    page load — structurally, a GET to /research must not be a registered
    route. Reads the OpenAPI schema rather than `app.routes` directly: newer
    FastAPI wraps `include_router`-mounted routes in an opaque
    `_IncludedRouter` that doesn't expose `.path`/`.methods` until resolved.
    """
    methods = set(app.openapi()["paths"]["/research"])
    assert methods == {"post"}


def test_cohort_fails_loudly_when_cases_dir_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cases_module, "CASES_DIR", tmp_path / "does-not-exist")
    with TestClient(app) as client:
        resp = client.get("/cohort")
    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert "does-not-exist" in detail
    assert "scripts/40_screen.py" in detail


def test_cohort_fails_loudly_when_cases_dir_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    empty_dir = tmp_path / "cases"
    empty_dir.mkdir()
    monkeypatch.setattr(cases_module, "CASES_DIR", empty_dir)
    with TestClient(app) as client:
        resp = client.get("/cohort")
    assert resp.status_code == 500
    assert "scripts/40_screen.py" in resp.json()["detail"]


def test_case_detail_404s_on_unknown_npi_not_500(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A bad npi is a client error, not a broken source — distinct from the
    SpecterError fail-loud path above.
    """
    monkeypatch.setattr(cases_module, "CASES_DIR", tmp_path)
    with TestClient(app) as client:
        resp = client.get("/cases/0000000000")
    assert resp.status_code == 404


def test_cohort_marks_priority_tier_as_approximate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    case_dir = tmp_path / "cases"
    case_dir.mkdir()
    (case_dir / "1111111111.json").write_text(_empty_case("1111111111").model_dump_json())
    monkeypatch.setattr(cases_module, "CASES_DIR", case_dir)
    with TestClient(app) as client:
        resp = client.get("/cohort")
    assert resp.status_code == 200
    body = resp.json()
    assert body["priority_tier_approximate"] is True
    assert "D-23" in body["priority_tier_approximation_note"]
    assert body["total_cases"] == 1
    assert sum(body["priority_tier_counts"].values()) == 1


def test_costs_fails_loudly_when_ledger_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(costs_module, "LEDGER_PATH", tmp_path / "no-ledger.sqlite")
    with TestClient(app) as client:
        resp = client.get("/costs")
    assert resp.status_code == 500
    assert "no-ledger.sqlite" in resp.json()["detail"]


def test_costs_renders_null_cost_never_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    db_path = tmp_path / "ledger.sqlite"
    ledger = CostLedger(db_path)
    from specter.core.contracts import LlmCallRecord

    ledger.record(
        LlmCallRecord(
            ts=datetime.now(UTC),
            run_id="test",
            agent="skeptic",
            task_class="test_task",
            tier="T2_reasoning",
            model="gpt-5.4",
            prompt_tokens=500,
            cached_tokens=0,
            completion_tokens=10,
            latency_ms=100.0,
            cost_usd=None,
            cache_layer=CacheLayer.NONE,
            escalated=False,
        )
    )
    monkeypatch.setattr(costs_module, "LEDGER_PATH", db_path)
    with TestClient(app) as client:
        resp = client.get("/costs")
    assert resp.status_code == 200
    row = resp.json()["rows"][0]
    assert row["cost_usd"] is None


def test_judge_fails_loudly_when_report_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(judge_module, "JUDGE_REPORT_PATH", tmp_path / "no-report.md")
    with TestClient(app) as client:
        resp = client.get("/judge")
    assert resp.status_code == 500
    assert "scripts/50_judge.py" in resp.json()["detail"]


def test_judge_splits_real_report_shape_into_sections(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = tmp_path / "JudgeReport.md"
    fixture.write_text(
        "JUDGE INDEPENDENCE: LIMITED.\n"
        "The rubric judge (gpt-5.4) shares a model family with the agents it grades.\n"
        "Judge accuracy on injected-defect calibration cases: 8/8.\n\n"
        "## Deterministic checks (PRIMARY)\n\nsome table\n\n"
        "## Detection evaluation\n\nsome numbers\n"
    )
    monkeypatch.setattr(judge_module, "JUDGE_REPORT_PATH", fixture)
    with TestClient(app) as client:
        resp = client.get("/judge")
    assert resp.status_code == 200
    body = resp.json()
    assert "JUDGE INDEPENDENCE: LIMITED." in body["limitation_block"]
    assert "8/8" in body["limitation_block"]
    assert set(body["sections"]) == {
        "Deterministic checks (PRIMARY)",
        "Detection evaluation",
    }
    assert body["sections"]["Deterministic checks (PRIMARY)"] == "some table"


# --- Group B: live Neo4j + real, already-generated artifacts -----------


@pytest.fixture(scope="module")
def driver() -> Iterator[Driver]:
    settings = get_settings()
    drv = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_readonly_user, settings.neo4j_readonly_password.get_secret_value()),
    )
    try:
        drv.verify_connectivity()
    except Exception:
        pytest.skip("Neo4j not reachable — start it with `docker compose up -d`")
    yield drv
    drv.close()


@pytest.fixture(scope="module")
def real_case_npi() -> str:
    if not CASES_DIR.exists():
        pytest.skip(f"{CASES_DIR} missing — run `python scripts/40_screen.py` first")
    paths = sorted(CASES_DIR.glob("*.json"))
    if not paths:
        pytest.skip(f"{CASES_DIR} has no case files")
    return paths[0].stem


def test_cohort_real_corpus_tier_counts_sum_to_total(driver: Driver) -> None:
    if not CASES_DIR.exists() or not any(CASES_DIR.glob("*.json")):
        pytest.skip(f"{CASES_DIR} missing or empty — run `python scripts/40_screen.py` first")
    with TestClient(app) as client:
        resp = client.get("/cohort")
    assert resp.status_code == 200
    body = resp.json()
    assert sum(body["priority_tier_counts"].values()) == body["total_cases"]
    # D-23: some cases in the real corpus may have an exact, persisted score
    # (workflow/screening.py writes <npi>.score.json since the fix landed)
    # and some may still be falling back to the approximate recompute (cases
    # screened before that fix) — either is valid, but the two counts must
    # be internally consistent and the flag/count must agree.
    assert 0 <= body["cases_with_exact_priority_tier"] <= body["total_cases"]
    assert body["priority_tier_approximate"] == (
        body["cases_with_exact_priority_tier"] < body["total_cases"]
    )
    for label in ("provider", "address", "community", "exclusion"):
        assert body["graph_counts"][label] >= 0


def test_case_detail_real_case_carries_d28_limitations_verbatim(
    driver: Driver, real_case_npi: str
) -> None:
    if not MODEL_PATH.exists():
        pytest.skip(
            f"{MODEL_PATH} missing — run `python scripts/70_train_anomaly_model.py` first "
            "(~19 minutes)"
        )
    with TestClient(app) as client:
        resp = client.get(f"/cases/{real_case_npi}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["case"]["provider_npi"] == real_case_npi
    # D-23: True (recomputed, no <npi>.score.json yet) or False (exact,
    # persisted by a live screening run) are both valid — the note just has
    # to match which one actually happened.
    assert isinstance(body["priority_tier_approximate"], bool)
    if body["priority_tier_approximate"]:
        assert "D-23" in body["priority_tier_approximation_note"]
    else:
        assert "persisted" in body["priority_tier_approximation_note"]
    anomaly = body["anomaly_score"]
    assert anomaly["training_set_description"] != ""
    assert "not_a_fraud_probability" in anomaly["known_limitations"]


def test_ml_endpoint_matches_score_provider_directly(driver: Driver, real_case_npi: str) -> None:
    if not MODEL_PATH.exists():
        pytest.skip(f"{MODEL_PATH} missing — run `python scripts/70_train_anomaly_model.py` first")
    from specter.tools.ml_tools import score_provider

    direct = score_provider(real_case_npi, driver=driver)
    with TestClient(app) as client:
        resp = client.get(f"/ml/{real_case_npi}")
    assert resp.status_code == 200
    assert resp.json()["anomaly_score"] == pytest.approx(direct.anomaly_score)


def test_costs_real_ledger_has_no_zero_substituted_for_null(driver: Driver) -> None:
    if not LEDGER_PATH.exists():
        pytest.skip(f"{LEDGER_PATH} missing — run a live agent script first")
    with TestClient(app) as client:
        resp = client.get("/costs")
    assert resp.status_code == 200
    body = resp.json()
    for row in body["rows"]:
        if row["cost_usd"] is not None:
            assert row["cost_usd"] != 0  # D-8: real pricing unset means null, never a bare 0


def test_judge_real_report_carries_limitation_block(driver: Driver) -> None:
    if not JUDGE_REPORT_PATH.exists():
        pytest.skip(f"{JUDGE_REPORT_PATH} missing — run `python scripts/50_judge.py` first")
    with TestClient(app) as client:
        resp = client.get("/judge")
    assert resp.status_code == 200
    body = resp.json()
    assert "JUDGE INDEPENDENCE: LIMITED." in body["limitation_block"]
    assert "Deterministic checks (PRIMARY)" in body["sections"]
