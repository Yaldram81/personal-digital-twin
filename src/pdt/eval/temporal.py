"""Temporal tracking metric (blueprint §9, `to_do/PHASE_6.md` task 3).

Compares twin prediction accuracy computed from an *early* slice of the
model's history against the *current, full* history, on the same
chronologically-later held-out traces. If the model is genuinely learning
as data accrues, accuracy on that fixed held-out set should not get worse
as more history is available to it — ideally it improves.

Honesty note: because this system doesn't snapshot historical parameter
posteriors, "the model as it looked at time T" is approximated by filtering
the *current* store's traces/params to `created_at <= cutoff`. This is a
faithful proxy for "how much evidence the model had accumulated by T", but
it is not a literal replay of a past model version. `docs/phase6-benchmark-report.md`
carries the same caveat as the other benchmark metrics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pdt.eval.holdout import HoldoutPrediction, leave_one_out_predictions


class _CutoffStore:
    """Read-only view of a structured store, filtered to `created_at <= cutoff`.

    Only implements the surface `engine.pipeline.answer` actually touches
    during a query (`list_traces`, `export_bundle`); anything else is
    delegated to the real store via `__getattr__`.
    """

    def __init__(self, inner: Any, cutoff: str) -> None:
        self._inner = inner
        self._cutoff = cutoff

    def list_traces(
        self,
        domain: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[str]:
        traces = self._inner.list_traces(domain=domain, limit=10_000, offset=0)
        filtered = [item for item in traces if _trace_date(item) <= self._cutoff]
        return filtered[offset : offset + limit]

    def export_bundle(self) -> dict[str, Any]:
        bundle = dict(self._inner.export_bundle())
        bundle["params"] = [
            item
            for item in bundle["params"]
            if str(item.get("created_at", ""))[:10] <= self._cutoff
        ]
        bundle["traces"] = [
            item
            for item in bundle["traces"]
            if str(item.get("timestamp", ""))[:10] <= self._cutoff
        ]
        return bundle

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _CutoffState:
    """Duck-typed `state` wrapper that swaps in a `_CutoffStore`."""

    def __init__(self, inner: Any, cutoff: str) -> None:
        self._inner = inner
        self.store = _CutoffStore(inner.store, cutoff)
        self.calibration_tracker = inner.calibration_tracker
        self.consent_store = getattr(inner, "consent_store", None)

    def get_llm(self) -> Any:
        return self._inner.get_llm()

    def get_vector_store(self) -> Any:
        return self._inner.get_vector_store()


def _trace_date(trace_json: str) -> str:
    try:
        data = json.loads(trace_json)
    except (TypeError, ValueError):
        return ""
    return str(data.get("timestamp", ""))[:10]


@dataclass(frozen=True)
class TemporalTrackingReport:
    early_accuracy: float
    late_accuracy: float
    improved: bool
    early_n: int
    late_n: int


def _accuracy(predictions: list[HoldoutPrediction]) -> float:
    if not predictions:
        return 0.0
    return sum(1.0 for item in predictions if item.correct) / len(predictions)


def temporal_tracking_report(state: Any) -> TemporalTrackingReport:
    """Compare early-window vs. full-history accuracy on the same held-out set.

    *AC (PHASE_6.md task 3): metric computed over a longitudinal fixture or
    real rolling data; improvement is demonstrable.*
    """
    trace_jsons = state.store.list_traces(limit=10_000)
    traces = [json.loads(item) for item in trace_jsons]
    dated = sorted(
        (item for item in traces if item.get("timestamp")),
        key=lambda item: str(item["timestamp"]),
    )
    if len(dated) < 4:
        return TemporalTrackingReport(0.0, 0.0, False, 0, 0)

    midpoint = len(dated) // 2
    cutoff = str(dated[midpoint]["timestamp"])[:10]
    held_out_late = dated[midpoint:]

    early_state = _CutoffState(state, cutoff)
    early_predictions = leave_one_out_predictions(early_state, traces_override=held_out_late)
    late_predictions = leave_one_out_predictions(state, traces_override=held_out_late)

    early_accuracy = _accuracy(early_predictions)
    late_accuracy = _accuracy(late_predictions)
    return TemporalTrackingReport(
        early_accuracy=early_accuracy,
        late_accuracy=late_accuracy,
        improved=late_accuracy >= early_accuracy,
        early_n=len(early_predictions),
        late_n=len(late_predictions),
    )


__all__ = ["TemporalTrackingReport", "temporal_tracking_report"]
