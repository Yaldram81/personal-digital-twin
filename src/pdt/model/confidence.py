from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import sqrt


@dataclass(frozen=True)
class ConfidenceInterval:
    center: float
    half_width: float
    effective_n: float
    consistency: float
    recency_decay: float


def recency_decay_factor(timestamps: list[datetime], now: datetime | None = None) -> float:
    if not timestamps:
        return 1.0
    current = now or datetime.now(UTC)
    ages = [max((current - ts).days, 0) for ts in timestamps]
    mean_age_days = sum(ages) / len(ages)
    return min(mean_age_days / 365.0, 1.0)


def compute_confidence_interval(
    values: list[float],
    weights: list[float],
    timestamps: list[datetime],
    now: datetime | None = None,
) -> ConfidenceInterval:
    if not values or len(values) != len(weights) or len(values) != len(timestamps):
        raise ValueError("values, weights, and timestamps must be non-empty and aligned")
    total_weight = sum(weights)
    if total_weight <= 0:
        raise ValueError("total weight must be positive")

    center = (
        sum(value * weight for value, weight in zip(values, weights, strict=True))
        / total_weight
    )
    variance = (
        sum(weight * (value - center) ** 2 for value, weight in zip(values, weights, strict=True))
        / total_weight
    )
    consistency = max(0.0, min(1.0, 1.0 - variance))
    recency_decay = recency_decay_factor(timestamps, now=now)
    base_half_width = 0.5 / sqrt(max(total_weight, 1.0))
    half_width = base_half_width * (1.0 + (1.0 - consistency)) * (1.0 + recency_decay)
    return ConfidenceInterval(
        center=max(0.0, min(1.0, center)),
        half_width=max(0.0, min(1.0, half_width)),
        effective_n=total_weight,
        consistency=consistency,
        recency_decay=recency_decay,
    )
