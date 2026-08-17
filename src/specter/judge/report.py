"""`JudgeReport.md` (plan §12.3, M9). Opens with the verbatim CLAUDE.md
Amendment 2 limitation block — deterministic-primary/LLM-secondary is the
report's structure, not just a sentence in it: deterministic results are
rendered before any rubric score.
"""

from __future__ import annotations

from specter.core.contracts import CalibrationCase, DetectionEvalReport, JudgeVerdict

_LOW_SCORE_CAUGHT_THRESHOLD = 2  # mean score <= this counts as "caught" the defect


_LIMITATION_BLOCK = """JUDGE INDEPENDENCE: LIMITED.
The rubric judge (gpt-5.4) shares a model family with the agents it grades,
introducing self-preference bias. LLM rubric scores are therefore reported as
SECONDARY. Primary evaluation is deterministic (citation validity, numeric
grounding, entity existence) and does not involve an LLM.
Judge accuracy on injected-defect calibration cases: {n_caught}/8.
Cross-family validation (Kimi K2.6 or Claude) deferred to Phase 2."""


def _mean_score(verdict: JudgeVerdict, criterion: str) -> float | None:
    scores = [
        c.score for sample in verdict.samples for c in sample.criteria if c.criterion == criterion
    ]
    return sum(scores) / len(scores) if scores else None


def calibration_accuracy(
    calibration: list[tuple[CalibrationCase, JudgeVerdict]]
) -> tuple[int, list[str]]:
    """Returns `(n_caught, notes)`. Only C01-C08 count toward the
    denominator — C09/C10 are controls, never graded on "caught a defect".
    "Caught" here means the expected criterion's mean score across samples is
    low (<=2/5); whether `weakness_found` actually *names* the injected
    problem (the Action Plan's fuller definition) still needs a human glance
    at the quoted text below, not just the number.
    """
    caught = 0
    notes: list[str] = []
    for cal_case, verdict in calibration:
        if cal_case.expected_criterion is None:
            continue
        mean = _mean_score(verdict, cal_case.expected_criterion)
        did_catch = mean is not None and mean <= _LOW_SCORE_CAUGHT_THRESHOLD
        if did_catch:
            caught += 1
        notes.append(
            f"- **{cal_case.fixture_id}** ({cal_case.description}): expected criterion "
            f"`{cal_case.expected_criterion}` mean score {mean if mean is not None else 'N/A'} "
            f"— {'CAUGHT' if did_catch else 'MISSED'}"
        )
    return caught, notes


def _detection_table(report: DetectionEvalReport) -> str:
    lines = ["| k | precision@k |", "|---|---|"]
    for k, value in sorted(report.precision_at_k.items(), key=lambda kv: int(kv[0])):
        lines.append(f"| {k} | {value:.2f} |")
    lines.append("")
    lines.append(
        f"Real positives: **{report.real_positive_count}** out of "
        f"**{report.real_positive_denominator}** real providers loaded "
        "(BUILD_MILESTONES.md debt D-21 — this denominator is thin by design, "
        "not a bug in this evaluation)."
    )
    if report.false_positive_rate is not None:
        lines.append(
            f"\nFalse positive rate on synthetic controls: {report.false_positive_rate:.2%}"
        )
    lines.append(f"\nRanking method: `{report.ranking_method}`.")
    return "\n".join(lines)


def _scenario_table(report: DetectionEvalReport) -> str:
    lines = [
        "| Scenario | Expected signals | Fired signals | Detector exists | Recall hit |",
        "|---|---|---|---|---|",
    ]
    for r in report.scenario_recall:
        lines.append(
            f"| {r.scenario_id} | {', '.join(r.expected_signals) or '—'} | "
            f"{', '.join(r.fired_signal_types) or '—'} | "
            f"{'yes' if r.detector_exists else 'no (by design)'} | "
            f"{'✅' if r.recall_hit else '❌'} |"
        )
    with_detector = [r for r in report.scenario_recall if r.detector_exists]
    hits = sum(1 for r in with_detector if r.recall_hit)
    lines.append("")
    lines.append(
        f"**Headline: {hits}/{len(with_detector)} scenarios with a Phase 1 detector "
        "were detected.** The remaining scenarios have no Phase 1 detector by design "
        "(no address-type classification, no utilization data) and are reported "
        "separately above rather than folded into a misleading 10/10."
    )
    return "\n".join(lines)


def _rubric_distribution(verdicts: dict[str, JudgeVerdict]) -> str:
    if not verdicts:
        return "No case corpus had a rubric judgment run."
    lines = ["| Provider NPI | " + " | ".join(sorted({
        c for v in verdicts.values() for s in v.samples for c in {sc.criterion for sc in s.criteria}
    })) + " | Low-reliability criteria |"]
    lines.append("|---" * (len(lines[0].split("|")) - 2) + "|")
    for npi, verdict in sorted(verdicts.items()):
        criteria = sorted(verdict.aggregate_scores)
        scores = " | ".join(f"{verdict.aggregate_scores[c]:.1f}" for c in criteria)
        lines.append(f"| {npi} | {scores} | {', '.join(verdict.low_reliability_criteria) or '—'} |")
    return "\n".join(lines)


def _worst_cases(verdicts: dict[str, JudgeVerdict], n: int = 3) -> str:
    def overall(v: JudgeVerdict) -> float:
        if not v.aggregate_scores:
            return 0.0
        return sum(v.aggregate_scores.values()) / len(v.aggregate_scores)

    ranked = sorted(verdicts.items(), key=lambda kv: overall(kv[1]))[:n]
    if not ranked:
        return "No cases judged."
    blocks = []
    for npi, verdict in ranked:
        reasons = []
        for sample in verdict.samples:
            for c in sample.criteria:
                if c.score <= _LOW_SCORE_CAUGHT_THRESHOLD:
                    reasons.append(f"  - `{c.criterion}` ({c.score}/5): {c.weakness_found}")
        blocks.append(f"### {npi} (overall {overall(verdict):.1f}/5)\n" + "\n".join(reasons[:5]))
    return "\n\n".join(blocks)


def render_report(
    *,
    detection: DetectionEvalReport,
    deterministic_summary: dict[str, dict[str, int]],
    judge_verdicts: dict[str, JudgeVerdict],
    calibration: list[tuple[CalibrationCase, JudgeVerdict]],
    disagreements: dict[str, list[str]],
) -> str:
    n_caught, calibration_notes = calibration_accuracy(calibration)

    det_lines = ["| Provider NPI | citations OK | numbers OK | entities OK |", "|---|---|---|---|"]
    for npi, summary in sorted(deterministic_summary.items()):
        det_lines.append(
            f"| {npi} | {summary.get('citations_ok', 0)}/{summary.get('citations_total', 0)} | "
            f"{summary.get('numeric_violations', 0)} violations | "
            f"{summary.get('entities_ok', 0)}/{summary.get('entities_total', 0)} |"
        )

    disagreement_lines = (
        [f"- **{npi}**: {d}" for npi, ds in sorted(disagreements.items()) for d in ds]
        or ["None observed."]
    )

    return "\n\n".join([
        _LIMITATION_BLOCK.format(n_caught=n_caught),
        "## Deterministic checks (PRIMARY)\n\n" + "\n".join(det_lines),
        "## Detection evaluation\n\n" + _detection_table(detection),
        "## Per-scenario recall\n\n" + _scenario_table(detection),
        "## Calibration accuracy (C01-C08, judge's own accuracy metric)\n\n"
        + "\n".join(calibration_notes),
        "## Rubric judge scores (SECONDARY)\n\n" + _rubric_distribution(judge_verdicts),
        "## Deterministic-vs-LLM disagreement\n\n" + "\n".join(disagreement_lines),
        "## Three worst-scoring cases\n\n" + _worst_cases(judge_verdicts),
    ]) + "\n"
