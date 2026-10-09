from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any, Literal

from pdt.core.schemas import DECISION_STYLE_DIMENSIONS, SCHWARTZ_DIMENSIONS, DriftLog, DriftLogEntry
from pdt.inference.changepoint import run_bocpd

StabilityTier = Literal["core", "situational", "surface"]


@dataclass(frozen=True)
class ChangePointResult:
    param: str
    most_likely_t: datetime | None
    posterior: list[float]
    run_length_dist: list[float]
    detected: bool
    confidence: float


@dataclass(frozen=True)
class LifeEventWindow:
    start: date
    end: date
    intensity: float
    triggers: list[str]


def tier(param: str, domain: str | None = None) -> StabilityTier:
    if param in SCHWARTZ_DIMENSIONS:
        return "core"
    if domain is not None or param in DECISION_STYLE_DIMENSIONS:
        return "situational"
    return "surface"


def smoothing_alpha(stability_tier: StabilityTier) -> float:
    return {"core": 0.08, "situational": 0.22, "surface": 0.45}[stability_tier]


def smooth_series(values: list[float], stability_tier: StabilityTier) -> list[float]:
    if not values:
        return []
    alpha = smoothing_alpha(stability_tier)
    smoothed = [values[0]]
    for value in values[1:]:
        smoothed.append((alpha * value) + ((1.0 - alpha) * smoothed[-1]))
    return smoothed


def build_drift_log(param: str, history: list[dict[str, Any]]) -> DriftLog:
    entries = [
        DriftLogEntry(
            timestamp=date.fromisoformat(str(item["created_at"]).split(" ")[0]),
            value=float(str(item["value"])),
        )
        for item in history
    ]
    values = [entry.value for entry in entries]
    change = analyze(param, history)
    trend = _trend(values)
    rate = _rate_of_change(values)
    return DriftLog(
        parameter=param,
        history=entries,
        inflection_detected=(change.most_likely_t.date() if change.most_likely_t else None),
        inflection_trigger="bocpd_mean_shift" if change.detected else None,
        trend=trend,
        rate_of_change=rate,
    )


def analyze(param: str, history: list[dict[str, Any]]) -> ChangePointResult:
    if not history:
        return ChangePointResult(param, None, [], [], False, 0.0)
    values = [float(str(item["value"])) for item in history]
    stability_tier = tier(param, _domain_from_history(history))
    likelihood = "student_t" if stability_tier == "surface" else "gaussian"
    result = run_bocpd(values, likelihood=likelihood)
    if result.most_likely_index is None:
        return ChangePointResult(param, None, result.posterior, result.run_length_dist, False, 0.0)
    timestamp = datetime.fromisoformat(str(history[result.most_likely_index]["created_at"]))
    return ChangePointResult(
        param=param,
        most_likely_t=timestamp,
        posterior=result.posterior,
        run_length_dist=result.run_length_dist,
        detected=result.detected,
        confidence=result.confidence,
    )


def detect_major_life_event_window(trace_jsons: list[str]) -> LifeEventWindow | None:
    if len(trace_jsons) < 3:
        return None
    traces = [json.loads(item) for item in trace_jsons]
    domains = [str(trace.get("domain", "")) for trace in traces]
    timestamps = [date.fromisoformat(str(trace.get("timestamp", "2025-01-01"))) for trace in traces]
    recent = domains[-3:]
    prior = domains[:-3]
    if not prior:
        return None
    prior_mode = max(set(prior), key=prior.count)
    recent_new = [domain for domain in recent if domain != prior_mode]
    if len(recent_new) < 2:
        return None
    start = timestamps[-3]
    end = timestamps[-1] + timedelta(days=30)
    intensity = min(1.0, 0.4 + (len(set(recent_new)) * 0.2))
    return LifeEventWindow(
        start=start,
        end=end,
        intensity=intensity,
        triggers=["domain_shift_burst"],
    )


def evidence_weight_for_date(observed_at: date, window: LifeEventWindow | None) -> float:
    if window is None:
        return 1.0
    if window.start <= observed_at <= window.end:
        return 1.0 + window.intensity
    return 1.0


def _trend(values: list[float]) -> Literal["increasing", "decreasing", "stable"]:
    if len(values) < 2:
        return "stable"
    delta = values[-1] - values[0]
    if delta > 0.08:
        return "increasing"
    if delta < -0.08:
        return "decreasing"
    return "stable"


def _rate_of_change(values: list[float]) -> Literal["slow", "moderate", "fast"]:
    if len(values) < 2:
        return "slow"
    diffs = [
        abs(right - left)
        for left, right in zip(values, values[1:], strict=False)
    ]
    avg = mean(diffs) if diffs else 0.0
    if avg > 0.15:
        return "fast"
    if avg > 0.06:
        return "moderate"
    return "slow"


def _domain_from_history(history: list[dict[str, Any]]) -> str | None:
    for item in history:
        domain = item.get("domain")
        if domain not in {None, ""}:
            return str(domain)
    return None


__all__ = [
    "ChangePointResult",
    "LifeEventWindow",
    "StabilityTier",
    "analyze",
    "build_drift_log",
    "detect_major_life_event_window",
    "evidence_weight_for_date",
    "smooth_series",
    "smoothing_alpha",
    "tier",
]
