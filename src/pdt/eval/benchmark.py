from __future__ import annotations

import time
from dataclasses import dataclass

from pdt.engine.pipeline import TwinQuery, answer
from pdt.eval.explanation_study import run_blind_ab
from pdt.eval.harness import EvalReport, run_holdout
from pdt.eval.temporal import TemporalTrackingReport, temporal_tracking_report

_GENERIC_SYSTEM_PROMPT = (
    "You are a generic helpful assistant with no personal information about "
    "this user. Answer with general best-practice advice only."
)


@dataclass(frozen=True)
class ThresholdStatus:
    metric: str
    target: str
    observed: float | None
    passed: bool
    note: str


@dataclass(frozen=True)
class BenchmarkReport:
    holdout: EvalReport
    consistency_score: float | None
    p95_latency_seconds: float | None
    temporal_tracking: TemporalTrackingReport
    threshold_statuses: list[ThresholdStatus]


def consistency_score_for_queries(state, queries: list[TwinQuery]) -> float | None:  # type: ignore[no-untyped-def]
    if not queries:
        return None
    stable = 0
    for query in queries:
        first = answer(query, state)
        second = answer(query, state)
        if first.narrative == second.narrative:
            stable += 1
    return stable / len(queries)


def p95_latency_for_queries(state, queries: list[TwinQuery]) -> float | None:  # type: ignore[no-untyped-def]
    if not queries:
        return None
    samples: list[float] = []
    for query in queries:
        start = time.perf_counter()
        answer(query, state)
        samples.append(time.perf_counter() - start)
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, int(0.95 * len(ordered)) - 1))
    return ordered[index]


def generic_answer_for_query(state, query: TwinQuery) -> str:  # type: ignore[no-untyped-def]
    """A non-personalized baseline answer, for a genuine blind A/B comparison.

    Unlike the twin's answer, this carries no persona context, no retrieved
    traces, and no citations — it is the honest "generic LLM" side of the
    explanation-recognition study (PHASE_6.md task 2).
    """
    response = state.get_llm().complete(
        [
            {"role": "system", "content": _GENERIC_SYSTEM_PROMPT},
            {"role": "user", "content": query.text},
        ],
        temperature=0.0,
    )
    return str(response.text)


def build_phase6_benchmark_report(state, queries: list[TwinQuery]) -> BenchmarkReport:  # type: ignore[no-untyped-def]
    holdout = run_holdout(state)
    consistency = consistency_score_for_queries(state, queries)
    latency = p95_latency_for_queries(state, queries)
    temporal = temporal_tracking_report(state)
    explanation = run_blind_ab(
        [answer(query, state).narrative for query in queries],
        [generic_answer_for_query(state, query) for query in queries],
    )
    threshold_statuses = [
        ThresholdStatus(
            metric="memory_recall_accuracy",
            target="> 0.75",
            observed=holdout.recall,
            passed=holdout.recall > 0.75,
            note="Measured via leave-one-out holdout recall.",
        ),
        ThresholdStatus(
            metric="response_consistency_score",
            target="> 0.80",
            observed=consistency,
            passed=(consistency or 0.0) > 0.80,
            note="Measured as exact-repeat stability on deterministic twin queries.",
        ),
        ThresholdStatus(
            metric="p95_latency_seconds",
            target="< 2.0",
            observed=latency,
            passed=(latency or float("inf")) < 2.0,
            note="Measured in-process on standard twin queries.",
        ),
        ThresholdStatus(
            metric="recognition_score",
            target="> 0.50",
            observed=explanation.twin_win_rate,
            passed=explanation.twin_win_rate > 0.50,
            note="Blind A/B scaffold baseline; above-chance twin recognition.",
        ),
    ]
    threshold_statuses.append(
        ThresholdStatus(
            metric="temporal_tracking_improves",
            target=">= early-window accuracy",
            observed=temporal.late_accuracy,
            passed=temporal.improved,
            note=(
                "Compares leave-one-out accuracy on a fixed held-out set using an "
                "early-history cutoff vs. the full current history (PHASE_6.md task 3)."
            ),
        )
    )
    return BenchmarkReport(
        holdout=holdout,
        consistency_score=consistency,
        p95_latency_seconds=latency,
        temporal_tracking=temporal,
        threshold_statuses=threshold_statuses,
    )


__all__ = [
    "BenchmarkReport",
    "ThresholdStatus",
    "build_phase6_benchmark_report",
    "consistency_score_for_queries",
    "p95_latency_for_queries",
]
