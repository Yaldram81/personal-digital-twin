from __future__ import annotations

from datetime import date

from pdt.core.schemas import (
    SCHWARTZ_DIMENSIONS,
    EvidenceSource,
    EvidenceStrength,
    ScoredScalar,
    ValueHierarchy,
)


def build_value_hierarchy_prior(
    scored: dict[str, ScoredScalar],
    as_of: date | None = None,
) -> ValueHierarchy:
    today = as_of or date.today()
    values: dict[str, ScoredScalar] = {}
    for dim in SCHWARTZ_DIMENSIONS:
        values[dim] = scored.get(
            dim,
            ScoredScalar(
                value=0.5,
                confidence=0.35,
                n_observations=0,
                last_updated=today,
                source=EvidenceSource.SELF_REPORT,
                evidence_strength=EvidenceStrength.WEAK,
            ),
        )
    return ValueHierarchy(
        values=values,
        stability_score=ScoredScalar(
            value=0.5,
            confidence=0.35,
            n_observations=0,
            last_updated=today,
            source=EvidenceSource.SELF_REPORT,
            evidence_strength=EvidenceStrength.WEAK,
        ),
    )
