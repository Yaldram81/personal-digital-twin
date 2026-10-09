from __future__ import annotations

from datetime import UTC, datetime

from pdt.core.schemas import EvidenceSource, EvidenceStrength, ScoredScalar
from pdt.model.confidence import compute_confidence_interval

SOURCE_RELIABILITY: dict[EvidenceSource, float] = {
    EvidenceSource.SELF_REPORT: 1.0,
    EvidenceSource.BEHAVIORAL: 2.0,
    EvidenceSource.INFERRED: 1.5,
}


def fuse_scored_scalars(estimates: list[ScoredScalar]) -> ScoredScalar:
    if not estimates:
        raise ValueError("at least one estimate is required")

    values = [estimate.value for estimate in estimates]
    weights = [
        max(
            0.1,
            SOURCE_RELIABILITY[estimate.source]
            * estimate.n_observations
            / (estimate.confidence + 0.05),
        )
        for estimate in estimates
    ]
    timestamps = [
        datetime.combine(estimate.last_updated, datetime.min.time(), tzinfo=UTC)
        for estimate in estimates
    ]
    ci = compute_confidence_interval(values, weights, timestamps)
    n_total = sum(estimate.n_observations for estimate in estimates)
    source = max(estimates, key=lambda item: SOURCE_RELIABILITY[item.source]).source
    if n_total < 3:
        strength = EvidenceStrength.WEAK
    elif n_total < 8:
        strength = EvidenceStrength.MODERATE
    else:
        strength = EvidenceStrength.STRONG
    return ScoredScalar(
        value=ci.center,
        confidence=ci.half_width,
        n_observations=n_total,
        last_updated=max(estimate.last_updated for estimate in estimates),
        source=source,
        evidence_strength=strength,
    )
