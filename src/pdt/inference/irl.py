from __future__ import annotations

import math
from dataclasses import dataclass

from pdt.core.schemas import SCHWARTZ_DIMENSIONS
from pdt.inference.features import trace_to_feature_vector


@dataclass(frozen=True)
class IRLResult:
    theta: dict[str, float]
    confidence: dict[str, float]
    n_traces: int
    last_trace_id: str
    converged: bool


def _normalize(theta: dict[str, float]) -> dict[str, float]:
    values = {key: max(0.0, value) for key, value in theta.items()}
    total = sum(values.values()) or 1.0
    return {key: value / total for key, value in values.items()}


def fit(trace_jsons: list[str], steps: int = 200, learning_rate: float = 0.2) -> IRLResult:
    observed = dict.fromkeys(SCHWARTZ_DIMENSIONS, 0.0)
    last_trace_id = ""
    for trace_json in trace_jsons:
        features = trace_to_feature_vector(trace_json)
        for dim, value in features.items():
            observed[dim] += value
        import json as _json

        last_trace_id = str(_json.loads(trace_json).get("id", last_trace_id))
    n_traces = max(len(trace_jsons), 1)
    observed = {dim: value / n_traces for dim, value in observed.items()}

    theta = {dim: 1.0 / len(SCHWARTZ_DIMENSIONS) for dim in SCHWARTZ_DIMENSIONS}
    converged = False
    for _ in range(steps):
        exp_scores = {dim: math.exp(theta[dim]) for dim in SCHWARTZ_DIMENSIONS}
        z = sum(exp_scores.values()) or 1.0
        policy = {dim: exp_scores[dim] / z for dim in SCHWARTZ_DIMENSIONS}
        gradient = {dim: observed[dim] - policy[dim] for dim in SCHWARTZ_DIMENSIONS}
        max_step = 0.0
        for dim in SCHWARTZ_DIMENSIONS:
            step = learning_rate * gradient[dim]
            theta[dim] += step
            max_step = max(max_step, abs(step))
        theta = _normalize(theta)
        if max_step < 1e-4:
            converged = True
            break

    confidence = {
        dim: max(0.05, 0.5 / math.sqrt(n_traces))
        for dim in SCHWARTZ_DIMENSIONS
    }
    return IRLResult(
        theta=theta,
        confidence=confidence,
        n_traces=n_traces,
        last_trace_id=last_trace_id,
        converged=converged,
    )


def update(
    trace_jsons: list[str],
    current_theta: dict[str, float] | None = None,
    current_confidence: dict[str, float] | None = None,
) -> IRLResult:
    result = fit(trace_jsons, steps=20, learning_rate=0.1)
    if current_theta is None or current_confidence is None:
        return result
    blended: dict[str, float] = {}
    for dim in SCHWARTZ_DIMENSIONS:
        confidence_scale = max(0.05, min(0.5, current_confidence.get(dim, 0.3)))
        step_size = 0.2 * confidence_scale
        blended[dim] = current_theta.get(dim, 0.1) + step_size * (
            result.theta[dim] - current_theta.get(dim, 0.1)
        )
    return IRLResult(
        theta=_normalize(blended),
        confidence=result.confidence,
        n_traces=result.n_traces,
        last_trace_id=result.last_trace_id,
        converged=result.converged,
    )
