from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pdt.model.confidence import ConfidenceInterval


@dataclass(frozen=True)
class Contribution:
    param: str
    weight: float
    ci: ConfidenceInterval


@dataclass(frozen=True)
class Prediction:
    result: Any
    confidence: float
    contributing_params: list[Contribution]
    extrapolation_flags: list[str]
    output_ci: ConfidenceInterval


def propagate_linear(contributions: list[Contribution]) -> ConfidenceInterval:
    if not contributions:
        raise ValueError("at least one contribution is required")
    center = sum(item.weight * item.ci.center for item in contributions)
    variance = sum((item.weight * item.ci.half_width / 1.96) ** 2 for item in contributions)
    effective_n = sum(item.ci.effective_n for item in contributions)
    consistency = sum(item.ci.consistency for item in contributions) / len(contributions)
    recency_decay = sum(item.ci.recency_decay for item in contributions) / len(contributions)
    return ConfidenceInterval(
        center=center,
        half_width=1.96 * math.sqrt(variance),
        effective_n=effective_n,
        consistency=consistency,
        recency_decay=recency_decay,
    )


def propagate_monte_carlo(
    contributions: list[Contribution],
    composition_fn: Callable[[list[float]], float],
    samples: int = 4000,
    seed: int = 7,
) -> ConfidenceInterval:
    if not contributions:
        raise ValueError("at least one contribution is required")
    rng = random.Random(seed)
    outputs: list[float] = []
    for _ in range(samples):
        drawn = [
            max(0.0, min(1.0, rng.gauss(item.ci.center, max(item.ci.half_width / 1.96, 1e-3))))
            for item in contributions
        ]
        outputs.append(composition_fn(drawn))
    outputs.sort()
    center = sum(outputs) / len(outputs)
    lower = outputs[int(0.025 * (len(outputs) - 1))]
    upper = outputs[int(0.975 * (len(outputs) - 1))]
    return ConfidenceInterval(
        center=center,
        half_width=max(center - lower, upper - center),
        effective_n=sum(item.ci.effective_n for item in contributions),
        consistency=sum(item.ci.consistency for item in contributions) / len(contributions),
        recency_decay=sum(item.ci.recency_decay for item in contributions) / len(contributions),
    )


def propagate(
    contributions: list[Contribution],
    composition_fn: Callable[[list[float]], float] | None = None,
    linear: bool = True,
) -> ConfidenceInterval:
    if linear or composition_fn is None:
        return propagate_linear(contributions)
    return propagate_monte_carlo(contributions, composition_fn)


def build_prediction_contract(
    result: Any,
    contributions: list[Contribution],
    extrapolation_flags: list[str],
    composition_fn: Callable[[list[float]], float] | None = None,
    linear: bool = True,
) -> Prediction:
    output_ci = propagate(contributions, composition_fn=composition_fn, linear=linear)
    confidence = max(0.0, min(1.0, 1.0 - output_ci.half_width))
    return Prediction(
        result=result,
        confidence=confidence,
        contributing_params=contributions,
        extrapolation_flags=extrapolation_flags,
        output_ci=output_ci,
    )


__all__ = [
    "Contribution",
    "Prediction",
    "build_prediction_contract",
    "propagate",
    "propagate_linear",
    "propagate_monte_carlo",
]
