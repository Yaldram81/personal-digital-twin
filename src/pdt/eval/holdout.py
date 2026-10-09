from __future__ import annotations

import json
from dataclasses import dataclass
from statistics import mean
from typing import Any

from pdt.engine.pipeline import TwinQuery, answer


@dataclass(frozen=True)
class HoldoutPrediction:
    correct: bool
    confidence: float
    wide_ci: bool


def leave_one_out_predictions(  # type: ignore[no-untyped-def]
    state,
    traces_override: list[dict[str, Any]] | None = None,
) -> list[HoldoutPrediction]:
    traces = (
        traces_override
        if traces_override is not None
        else [json.loads(item) for item in state.store.list_traces(limit=10_000)]
    )
    predictions: list[HoldoutPrediction] = []
    for trace in traces:
        query = TwinQuery(
            query_type="prediction",
            text=f"How would I evaluate {trace.get('context', 'this decision')}?",
            domain_hint=None,
            options=list(trace.get("options", [])) or None,
        )
        result = answer(query, state)
        query_text = result.narrative.lower()
        chosen = str(trace.get("chosen_option", "")).lower().replace("_", " ")
        correct = chosen[:12] in query_text if chosen else False
        wide_ci = result.confidence < 0.75
        predictions.append(HoldoutPrediction(correct, result.confidence, wide_ci))
    return predictions


def expected_calibration_error(predictions: list[HoldoutPrediction], bins: int = 5) -> float:
    if not predictions:
        return 0.0
    width = 1.0 / bins
    ece = 0.0
    for idx in range(bins):
        lower = idx * width
        upper = lower + width
        bucket = [pred for pred in predictions if lower <= pred.confidence <= upper]
        if not bucket:
            continue
        accuracy = sum(1.0 for pred in bucket if pred.correct) / len(bucket)
        confidence = mean(pred.confidence for pred in bucket)
        ece += (len(bucket) / len(predictions)) * abs(accuracy - confidence)
    return ece


__all__ = ["HoldoutPrediction", "expected_calibration_error", "leave_one_out_predictions"]
