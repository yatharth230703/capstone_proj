"""M12 checkpoint (BUILD_MILESTONES.md, CLAUDE.md Amendment 4(b)):
`ml_tools.score_provider` is deterministic at inference, feature ordering is
read from `config/screening.yaml` rather than hardcoded, a missing model
artifact fails loudly instead of returning a default score, and
`AnomalyScore` always carries a non-empty training-set disclosure.

Trains a throwaway toy model on a 15-provider real-cohort slice into a
pytest tmp dir — fast, live-Neo4j integration test, same
skip-if-unreachable pattern `test_signal_tools.py` uses. Never touches the
real `data/models/` artifact `scripts/70_train_anomaly_model.py` produces.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from neo4j import Driver, GraphDatabase

from specter.core.contracts import AnomalyScore, MlConfig, ScreeningThresholds
from specter.core.errors import SpecterError
from specter.settings import get_settings
from specter.tools import ml_tools as mt
from specter.tools.signal_tools import load_thresholds
from specter.workflow.state import cohort_select

CONFIG_PATH = Path("config/screening.yaml")


@pytest.fixture(scope="module")
def driver() -> Iterator[Driver]:
    settings = get_settings()
    drv = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value())
    )
    try:
        drv.verify_connectivity()
    except Exception:
        pytest.skip("Neo4j not reachable — start it with `docker compose up -d`")
    yield drv
    drv.close()


@pytest.fixture(scope="module")
def thresholds() -> ScreeningThresholds:
    return load_thresholds(CONFIG_PATH)


@pytest.fixture(scope="module")
def ml_config() -> MlConfig:
    return mt.load_ml_config(CONFIG_PATH)


@pytest.fixture(scope="module")
def train_npis(driver: Driver) -> list[str]:
    cohort_cfg = yaml.safe_load(CONFIG_PATH.read_text())["cohort"]
    npis = cohort_select(driver, cohort_cfg["taxonomy_prefix"], cohort_cfg["states"], limit=15)
    if len(npis) < 5:
        pytest.skip("real cohort too small in this graph to fit a toy model")
    return npis


@pytest.fixture(scope="module")
def toy_model(
    tmp_path_factory: pytest.TempPathFactory,
    driver: Driver,
    thresholds: ScreeningThresholds,
    ml_config: MlConfig,
    train_npis: list[str],
) -> tuple[Path, Path]:
    model_dir = tmp_path_factory.mktemp("ml_models")
    evidence_dir = tmp_path_factory.mktemp("ml_evidence")
    df = mt.extract_features(driver, train_npis, thresholds, ml_config)
    model = mt.train(df, ml_config)
    mt.persist_model(
        model,
        ml_config,
        trained_rows=len(train_npis),
        training_set_description="test fixture — a toy model, not the real trained one",
        evidence_dir=evidence_dir,
        model_dir=model_dir,
    )
    return model_dir, evidence_dir


def test_score_provider_is_deterministic(
    driver: Driver,
    thresholds: ScreeningThresholds,
    ml_config: MlConfig,
    train_npis: list[str],
    toy_model: tuple[Path, Path],
) -> None:
    model_dir, evidence_dir = toy_model
    npi = train_npis[0]
    kwargs = {
        "driver": driver,
        "thresholds": thresholds,
        "ml_config": ml_config,
        "model_dir": model_dir,
        "evidence_dir": evidence_dir,
    }
    first = mt.score_provider(npi, **kwargs)
    second = mt.score_provider(npi, **kwargs)
    assert first.anomaly_score == second.anomaly_score
    assert first.model_dump(exclude={"scored_at"}) == second.model_dump(exclude={"scored_at"})


def test_feature_order_is_read_from_config_not_hardcoded(
    driver: Driver, thresholds: ScreeningThresholds, ml_config: MlConfig, train_npis: list[str]
) -> None:
    reordered = ml_config.model_copy(
        update={"feature_order": list(reversed(ml_config.feature_order))}
    )
    default_df = mt.extract_features(driver, train_npis[:3], thresholds, ml_config)
    reordered_df = mt.extract_features(driver, train_npis[:3], thresholds, reordered)
    assert list(default_df.columns[1:]) == ml_config.feature_order
    assert list(reordered_df.columns[1:]) == reordered.feature_order
    assert list(reordered_df.columns[1:]) != list(default_df.columns[1:])


def test_scoring_against_a_reordered_matrix_raises(
    driver: Driver, thresholds: ScreeningThresholds, ml_config: MlConfig, train_npis: list[str]
) -> None:
    """A model trained on one column order scored against another must fail
    loudly, not produce confident nonsense (M12 Action Plan Traps)."""
    df = mt.extract_features(driver, train_npis[:3], thresholds, ml_config)
    reordered_order = list(reversed(ml_config.feature_order))
    with pytest.raises(SpecterError):
        mt._matrix(df, reordered_order)


def test_missing_model_file_raises(
    driver: Driver,
    thresholds: ScreeningThresholds,
    ml_config: MlConfig,
    train_npis: list[str],
    tmp_path: Path,
) -> None:
    with pytest.raises(SpecterError):
        mt.score_provider(
            train_npis[0],
            driver=driver,
            thresholds=thresholds,
            ml_config=ml_config,
            model_dir=tmp_path,
            evidence_dir=tmp_path,
        )


def test_anomaly_score_requires_a_nonempty_training_set_description(
    driver: Driver,
    thresholds: ScreeningThresholds,
    ml_config: MlConfig,
    train_npis: list[str],
    toy_model: tuple[Path, Path],
) -> None:
    model_dir, evidence_dir = toy_model
    result = mt.score_provider(
        train_npis[0],
        driver=driver,
        thresholds=thresholds,
        ml_config=ml_config,
        model_dir=model_dir,
        evidence_dir=evidence_dir,
    )
    assert result.training_set_description.strip() != ""

    with pytest.raises(ValueError, match="training_set_description"):
        AnomalyScore(
            provider_npi="0000000000",
            anomaly_score=0.0,
            model_version="test",
            source_ids=["graph:provider:0000000000"],
            training_set_description="",
            known_limitations=[],
            data_origin="public",
            scored_at="2026-08-18T00:00:00Z",
        )
