from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from pdt.model.parameter_store import ParameterEstimate


@dataclass(frozen=True)
class Tension:
    stated: ParameterEstimate
    inferred: ParameterEstimate
    magnitude: float
    domain: str | None
    surfaced: bool
    phrasing_version: str
    created_at: datetime


def detect_tensions(
    stated: list[ParameterEstimate],
    inferred: list[ParameterEstimate],
    threshold: float = 0.25,
    min_n: int = 3,
) -> list[Tension]:
    inferred_map = {(item.param, item.domain): item for item in inferred if item.n >= min_n}
    tensions: list[Tension] = []
    for item in stated:
        other = inferred_map.get((item.param, item.domain))
        if other is None:
            continue
        magnitude = abs(item.value - other.value)
        if magnitude > threshold:
            tensions.append(
                Tension(
                    stated=item,
                    inferred=other,
                    magnitude=magnitude,
                    domain=other.domain.value if other.domain is not None else None,
                    surfaced=False,
                    phrasing_version="v1",
                    created_at=datetime.now(UTC),
                )
            )
    return tensions


def surface_tension(tension: Tension) -> str:
    return (
        f"Your actions suggest {tension.inferred.param} in {tension.domain or 'general'} "
        f"may matter more than your stated preference indicates."
    )
