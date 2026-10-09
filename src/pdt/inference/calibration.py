from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CalibrationPoint:
    lower: float
    upper: float
    mean_predicted: float
    empirical_accuracy: float
    count: int


@dataclass
class CalibrationTracker:
    records: list[tuple[str, float, bool]] = field(default_factory=list)

    def record(self, prediction_id: str, confidence: float, correct: bool) -> None:
        bounded = max(0.0, min(1.0, confidence))
        self.records.append((prediction_id, bounded, correct))

    def reliability_diagram(self, bins: int = 5) -> list[CalibrationPoint]:
        if bins <= 0:
            raise ValueError("bins must be positive")
        width = 1.0 / bins
        bucketed: list[list[tuple[str, float, bool]]] = [[] for _ in range(bins)]
        for record in self.records:
            _, confidence, _ = record
            idx = min(int(confidence / width), bins - 1)
            bucketed[idx].append(record)
        points: list[CalibrationPoint] = []
        for idx, rows in enumerate(bucketed):
            lower = idx * width
            upper = lower + width
            if not rows:
                points.append(CalibrationPoint(lower, upper, 0.0, 0.0, 0))
                continue
            mean_predicted = sum(item[1] for item in rows) / len(rows)
            empirical_accuracy = sum(1.0 for item in rows if item[2]) / len(rows)
            points.append(
                CalibrationPoint(
                    lower=lower,
                    upper=upper,
                    mean_predicted=mean_predicted,
                    empirical_accuracy=empirical_accuracy,
                    count=len(rows),
                )
            )
        return points


__all__ = ["CalibrationPoint", "CalibrationTracker"]
