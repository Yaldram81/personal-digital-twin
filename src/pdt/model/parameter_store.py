from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from pdt.core.schemas import Domain, EvidenceSource, EvidenceStrength, ScoredScalar
from pdt.model.fusion import fuse_scored_scalars


@dataclass(frozen=True)
class ParameterEstimate:
    param: str
    domain: Domain | None
    value: float
    confidence: float
    n: int
    source: EvidenceSource
    evidence_ids: list[str]
    timestamp: datetime

    def to_scored_scalar(self) -> ScoredScalar:
        strength = (
            EvidenceStrength.WEAK
            if self.n < 2
            else EvidenceStrength.MODERATE
            if self.n < 5
            else EvidenceStrength.STRONG
        )
        return ScoredScalar(
            value=self.value,
            confidence=self.confidence,
            n_observations=self.n,
            last_updated=date.fromisoformat(self.timestamp.date().isoformat()),
            source=self.source,
            evidence_strength=strength,
        )

    def to_row(self) -> dict[str, object]:
        return {
            "param": self.param,
            "domain": self.domain.value if self.domain is not None else None,
            "value": self.value,
            "confidence": self.confidence,
            "n": self.n,
            "source": self.source.value,
            "evidence_ids": self.evidence_ids,
            "timestamp": self.timestamp.isoformat(),
        }


def fuse_parameter_estimates(estimates: list[ParameterEstimate]) -> ScoredScalar:
    return fuse_scored_scalars([estimate.to_scored_scalar() for estimate in estimates])


def group_parameter_estimates(
    estimates: list[ParameterEstimate],
) -> dict[tuple[str, Domain | None], list[ParameterEstimate]]:
    grouped: dict[tuple[str, Domain | None], list[ParameterEstimate]] = {}
    for estimate in estimates:
        grouped.setdefault((estimate.param, estimate.domain), []).append(estimate)
    return grouped
