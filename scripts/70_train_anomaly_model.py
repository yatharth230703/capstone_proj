#!/usr/bin/env python
"""Offline anomaly-model trainer (BUILD_MILESTONES.md M12, CLAUDE.md
Amendment 4(b)).

    python scripts/70_train_anomaly_model.py

Fits `IsolationForest` **unsupervised** on the real (`data_origin='public'`)
taxonomy-332 FL/TX/CA cohort — no fraud labels used in fitting, CLAUDE.md
hard rule 1 read the way Amendment 4(b) authorizes: a trained model computing
a number through a documented, versioned, reproducible function is a
deterministic tool, not an LLM inventing one.

The 36 planted synthetic scenario providers (S01-S10) and 150 synthetic
benign controls are held out and used **only** for a post-hoc sanity
evaluation — "does the score rank planted anomalies above controls?" —
never for fitting. The real number is printed and recorded honestly
(BUILD_MILESTONES.md M12 Result), favourable or not.

No network calls, no LLM calls. Only Neo4j.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml
from neo4j import Driver, GraphDatabase
from sklearn.metrics import roc_auc_score

from specter.settings import get_settings
from specter.tools.ml_tools import (
    extract_features,
    load_ml_config,
    persist_model,
    score_matrix,
    train,
)
from specter.tools.signal_tools import load_thresholds
from specter.workflow.state import cohort_select

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _REPO_ROOT / "config" / "screening.yaml"
_MODEL_DIR = _REPO_ROOT / "data" / "models"
_EVIDENCE_DIR = _REPO_ROOT / "data" / "evidence"


def _synthetic_npis(driver: Driver) -> list[tuple[str, str | None]]:
    """(npi, scenario_id) for every synthetic provider — 36 scenario rows
    (S01-S10) + 150 benign controls (`scenario_id IS NULL`), CLAUDE.md debt
    D-17: queried by `data_origin` directly, never via `cohort_select`
    (synthetic providers carry no `HAS_TAXONOMY` edge).
    """
    with driver.session() as session:
        return [
            (r["npi"], r["scenario_id"])
            for r in session.run(
                "MATCH (p:Provider {data_origin: 'synthetic'}) "
                "RETURN p.npi AS npi, p.scenario_id AS scenario_id ORDER BY npi"
            )
        ]


def main(limit: int | None) -> None:
    settings = get_settings()
    driver = GraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value())
    )
    try:
        thresholds = load_thresholds(_CONFIG_PATH)
        ml_config = load_ml_config(_CONFIG_PATH)
        cohort_cfg = yaml.safe_load(_CONFIG_PATH.read_text())["cohort"]

        train_npis = cohort_select(
            driver, cohort_cfg["taxonomy_prefix"], cohort_cfg["states"], limit=limit
        )
        print(f"selected={len(train_npis)} real cohort providers for unsupervised fitting")
        train_df = extract_features(driver, train_npis, thresholds, ml_config)

        model = train(train_df, ml_config)

        description = (
            f"IsolationForest fit unsupervised on {len(train_npis)} real "
            f"(data_origin='public') taxonomy-{cohort_cfg['taxonomy_prefix']} "
            f"{'/'.join(cohort_cfg['states'])} cohort providers. No fraud labels used in "
            "fitting. Evaluated post-hoc against a held-out synthetic set (36 planted "
            "scenario providers S01-S10 vs 150 synthetic benign controls) — see "
            "BUILD_MILESTONES.md M12 Result for the real separation number. Not a fraud "
            "probability (phase_1_build_plan.md §16)."
        )
        artifact_id = persist_model(
            model,
            ml_config,
            trained_rows=len(train_npis),
            training_set_description=description,
            evidence_dir=_EVIDENCE_DIR,
            model_dir=_MODEL_DIR,
        )
        print(
            f"trained_rows={len(train_npis)} features={ml_config.feature_order} "
            f"model_version={ml_config.model_version}"
        )
        print(f"artifact_id={artifact_id}")

        synthetic = _synthetic_npis(driver)
        synthetic_npis = [npi for npi, _ in synthetic]
        labels = [1 if scenario_id is not None else 0 for _, scenario_id in synthetic]
        eval_df = extract_features(driver, synthetic_npis, thresholds, ml_config)
        scores = score_matrix(model, eval_df, ml_config.feature_order)

        auc = roc_auc_score(labels, scores)
        n_scenario = sum(labels)
        ranked = sorted(zip(scores.tolist(), labels, strict=True), reverse=True)
        top_k = ranked[:n_scenario]
        precision_at_k = sum(1 for _, label in top_k if label == 1) / n_scenario

        print(
            f"held_out_synthetic_eval: auc={auc:.3f} "
            f"precision_at_{n_scenario}={precision_at_k:.3f} "
            f"(scenario_providers={n_scenario} controls={len(labels) - n_scenario})"
        )
    finally:
        driver.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="max real cohort providers to train on (default: the full cohort)",
    )
    args = parser.parse_args()
    main(args.limit)
