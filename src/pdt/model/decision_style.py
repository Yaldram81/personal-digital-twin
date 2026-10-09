from __future__ import annotations

from datetime import date

from pdt.core.schemas import (
    DECISION_STYLE_DIMENSIONS,
    DecisionStyle,
    EvidenceSource,
    EvidenceStrength,
    ScoredScalar,
)


def build_decision_style_prior(
    scored: dict[str, ScoredScalar],
    as_of: date | None = None,
) -> DecisionStyle:
    today = as_of or date.today()
    dims: dict[str, ScoredScalar] = {}
    for dim in DECISION_STYLE_DIMENSIONS:
        dims[dim] = scored.get(
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
    return DecisionStyle(dimensions=dims)
