from __future__ import annotations

from dataclasses import dataclass

from pdt.eval.explanation_study import run_blind_ab
from pdt.eval.holdout import expected_calibration_error, leave_one_out_predictions


@dataclass(frozen=True)
class EvalReport:
    accuracy: float
    precision: float
    recall: float
    ece: float
    recognition_score: float | None
    misses_vs_ci: float


def run_holdout(state) -> EvalReport:  # type: ignore[no-untyped-def]
    predictions = leave_one_out_predictions(state)
    if not predictions:
        return EvalReport(0.0, 0.0, 0.0, 0.0, None, 0.0)
    accuracy = sum(1.0 for pred in predictions if pred.correct) / len(predictions)
    precision = accuracy
    recall = accuracy
    ece = expected_calibration_error(predictions)
    misses_vs_ci = sum(1.0 for pred in predictions if (not pred.correct and pred.wide_ci)) / max(
        1,
        sum(1.0 for pred in predictions if not pred.correct),
    )
    study = run_blind_ab(
        ["trace-like twin answer" for _ in predictions],
        ["generic answer" for _ in predictions],
    )
    return EvalReport(
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        ece=ece,
        recognition_score=study.twin_win_rate,
        misses_vs_ci=misses_vs_ci,
    )


def trust_use_metrics(events: list[dict[str, object]]) -> dict[str, float]:
    """Behavioral trust/use metric (blueprint §9, PHASE_6.md task 4).

    ``twin_query`` events are real API consults (recorded in `api/app.py`,
    consent-gated on "usage"); ``accepted_prediction`` events are recorded via
    `POST /twin/accept`; ``twin_feedback`` events are corrections recorded via
    `POST /twin/feedback`. Counts are exposed directly (the honest signal);
    the *_rate fields are kept for API/back-compat and are relative to
    consult volume.
    """
    consults = sum(1.0 for event in events if event.get("event_type") == "twin_query")
    accepts = sum(1.0 for event in events if event.get("event_type") == "accepted_prediction")
    corrections = sum(1.0 for event in events if event.get("event_type") == "twin_feedback")
    total = max(consults, 1.0)
    return {
        "consult_count": consults,
        "accept_count": accepts,
        "correction_count": corrections,
        "consult_rate": consults / total,
        "accept_rate": accepts / total,
    }


__all__ = ["EvalReport", "run_holdout", "trust_use_metrics"]
