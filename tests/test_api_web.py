"""M14 checkpoint (BUILD_MILESTONES.md): the judge-facing HTML UI renders
real M13 data, never shadows the JSON API's own paths, never fires the
research write path automatically, and every hardcoded template string
stays clear of CLAUDE.md hard rule 9's banned vocabulary.

Same Group A (offline, monkeypatched paths) / Group B (skip if Neo4j or a
real artifact is unreachable) split `tests/test_api.py` (M13) established.
`/ui/cases/{npi}` for a *found* case needs `api.ml.score_or_error`, which
needs live Neo4j + the persisted model — offline coverage here is limited
to the 404 path (raised before `score_or_error` is ever called); full
content coverage is Group B, same reasoning as M13.
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
from specter.core.banned_vocabulary import find_banned_phrases
from specter.core.contracts import CasePacket, CitationReport, CounterEvidence
from specter.settings import get_settings

CASES_DIR = Path("data/cases")
LEDGER_PATH = Path("data/ledger.sqlite")
JUDGE_REPORT_PATH = Path("JudgeReport.md")
MODEL_PATH = Path("data/models/anomaly_isoforest-v1.joblib")

_TEMPLATES_DIR = Path(__file__).parent.parent / "src" / "specter" / "api" / "templates"
_TEMPLATE_FILES = sorted(_TEMPLATES_DIR.glob("*.html"))


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


def _empty_ledger(tmp_path: Path) -> Path:
    from specter.core.contracts import LlmCallRecord
    from specter.core.enums import CacheLayer
    from specter.llm.ledger import CostLedger

    db_path = tmp_path / "ledger.sqlite"
    ledger = CostLedger(db_path)
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
    return db_path


# --- Group A: offline, monkeypatched paths -----------------------------


def test_ui_paths_never_shadow_the_json_api() -> None:
    """/cohort, /cases/{npi}, /judge stay JSON; /ui/... is the only HTML
    surface. A route collision here would silently break M13's API.
    """
    schema = app.openapi()["paths"]
    for path in ("/cohort", "/cases/{npi}", "/judge"):
        assert "get" in schema[path]
        assert "application/json" in schema[path]["get"]["responses"]["200"]["content"]
    for path in ("/ui", "/ui/cases/{npi}", "/ui/judge"):
        assert path in schema


def test_root_redirects_to_ui() -> None:
    with TestClient(app, follow_redirects=False) as client:
        resp = client.get("/")
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "/ui"


def test_cohort_page_renders_html_with_real_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    case_dir = tmp_path / "cases"
    case_dir.mkdir()
    (case_dir / "1111111111.json").write_text(_empty_case("1111111111").model_dump_json())
    monkeypatch.setattr(cases_module, "CASES_DIR", case_dir)
    monkeypatch.setattr(costs_module, "LEDGER_PATH", _empty_ledger(tmp_path))

    with TestClient(app) as client:
        resp = client.get("/ui")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    assert "1111111111" in body
    assert "D-23" in body  # priority_tier_approximation_note, verbatim
    assert "escalation gate" in body.lower()  # D-24 explanatory caption present
    assert find_banned_phrases(body) == []


def test_cohort_page_fails_loudly_when_cases_dir_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(cases_module, "CASES_DIR", tmp_path / "does-not-exist")
    with TestClient(app) as client:
        resp = client.get("/ui")
    # Same SpecterError -> JSON 500 as the /cohort JSON endpoint — the UI
    # layer doesn't swallow the error into a blank/broken page.
    assert resp.status_code == 500
    assert "scripts/40_screen.py" in resp.json()["detail"]


def test_case_page_404s_on_unknown_npi(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cases_module, "CASES_DIR", tmp_path)
    with TestClient(app) as client:
        resp = client.get("/ui/cases/0000000000")
    assert resp.status_code == 404


def test_judge_page_renders_limitation_block_verbatim(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fixture = tmp_path / "JudgeReport.md"
    fixture.write_text(
        "JUDGE INDEPENDENCE: LIMITED.\n"
        "The rubric judge (gpt-5.4) shares a model family with the agents it grades.\n"
        "Judge accuracy on injected-defect calibration cases: 8/8.\n\n"
        "## Deterministic checks (PRIMARY)\n\n| a | b |\n|---|---|\n"
    )
    monkeypatch.setattr(judge_module, "JUDGE_REPORT_PATH", fixture)
    with TestClient(app) as client:
        resp = client.get("/ui/judge")
    assert resp.status_code == 200
    assert "JUDGE INDEPENDENCE: LIMITED." in resp.text
    assert "Deterministic checks (PRIMARY)" in resp.text
    assert find_banned_phrases(resp.text) == []


def test_judge_page_fails_loudly_when_report_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(judge_module, "JUDGE_REPORT_PATH", tmp_path / "no-report.md")
    with TestClient(app) as client:
        resp = client.get("/ui/judge")
    assert resp.status_code == 500
    assert "scripts/50_judge.py" in resp.json()["detail"]


def test_research_trigger_only_fires_on_explicit_click() -> None:
    """Amendment 4(a): never on page load, never polled. `runResearch()`
    must appear only inside an `onclick` attribute — not in a
    `DOMContentLoaded`/`window.onload`/bare top-level call that would fire
    it automatically when the page (or a poller re-fetching it) loads.
    """
    template = (_TEMPLATES_DIR / "case_detail.html").read_text()
    assert 'onclick="runResearch()"' in template
    assert "DOMContentLoaded" not in template
    assert "setInterval" not in template
    assert "onload" not in template.lower().replace("onclick", "")


@pytest.mark.parametrize("template_path", _TEMPLATE_FILES, ids=lambda p: p.name)
def test_static_template_text_has_no_banned_vocabulary(template_path: Path) -> None:
    # Every literal word in the template source, banned-vocabulary check
    # included — Jinja `{{ }}`/`{% %}` blocks are live-data placeholders at
    # render time, but checking the raw source is a superset check (it also
    # catches banned words an author typed directly into HTML prose) and
    # costs nothing extra.
    assert find_banned_phrases(template_path.read_text()) == []


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


def test_case_page_real_case_renders_d28_disclosure_and_no_banned_words(
    driver: Driver, real_case_npi: str
) -> None:
    if not MODEL_PATH.exists():
        pytest.skip(f"{MODEL_PATH} missing — run `python scripts/70_train_anomaly_model.py` first")
    with TestClient(app) as client:
        resp = client.get(f"/ui/cases/{real_case_npi}")
    assert resp.status_code == 200
    body = resp.text
    assert real_case_npi in body
    assert "not_a_fraud_probability" in body
    assert "D-28" in body or "AUC 0.556" in body
    assert "priority_tier recomputed" in body  # D-23 note
    assert find_banned_phrases(body) == []


def test_cohort_page_real_corpus_renders_all_cases_linked(driver: Driver) -> None:
    if not CASES_DIR.exists() or not any(CASES_DIR.glob("*.json")):
        pytest.skip(f"{CASES_DIR} missing or empty — run `python scripts/40_screen.py` first")
    if not LEDGER_PATH.exists():
        pytest.skip(f"{LEDGER_PATH} missing — run a live agent script first")
    with TestClient(app) as client:
        resp = client.get("/ui")
    assert resp.status_code == 200
    n_links = resp.text.count('href="/ui/cases/')
    assert n_links == len(list(CASES_DIR.glob("*.json")))


def test_judge_page_real_report_renders(driver: Driver) -> None:
    if not JUDGE_REPORT_PATH.exists():
        pytest.skip(f"{JUDGE_REPORT_PATH} missing — run `python scripts/50_judge.py` first")
    with TestClient(app) as client:
        resp = client.get("/ui/judge")
    assert resp.status_code == 200
    assert "JUDGE INDEPENDENCE: LIMITED." in resp.text
