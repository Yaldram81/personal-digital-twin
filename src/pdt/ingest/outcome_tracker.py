from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class Outcome:
    prediction_id: str | None
    trace_id: str
    actual_choice: str | None
    retrospective: Literal["satisfied", "neutral", "regret"] | None
    free_text: str | None
    timestamp: datetime


def record_outcome(outcome: Outcome, state) -> None:  # type: ignore[no-untyped-def]
    if not state.consent_store.status("outcomes"):
        raise PermissionError("outcome collection is not consented")
    state.store.insert_event("outcome", json.dumps(_outcome_row(outcome)))
    if outcome.retrospective == "regret":
        _apply_regret_update(outcome, state)


def _apply_regret_update(outcome: Outcome, state) -> None:  # type: ignore[no-untyped-def]
    """Widen confidence on the parameter most relevant to the regretted decision.

    Ties the update to the *actual* trace's domain (looked up via
    `outcome.trace_id`) rather than a hardcoded domain, so a regret on a
    financial or relational decision doesn't silently widen a career
    parameter instead (PHASE_6.md task 5: "a regretted decision widens the CI
    on the relevant params").
    """
    domain = _trace_domain(outcome.trace_id, state)
    exported = state.store.export_bundle()["params"]
    candidate_domains = {domain, None, ""} if domain is not None else {None, ""}
    for item in exported:
        if item.get("domain") in candidate_domains:
            widened_confidence = min(1.0, float(item["confidence"]) + 0.05)
            state.store.insert_param(
                str(item["param_key"]),
                float(item["value"]),
                widened_confidence,
                int(item["n_observations"]),
                str(item["source"]),
                domain=item.get("domain"),
            )
            break


def _trace_domain(trace_id: str, state) -> str | None:  # type: ignore[no-untyped-def]
    """Resolve a trace's domain, whether `trace_id` is a store row id or the
    trace's own embedded `ReasoningTrace.id` (the id used everywhere else —
    citations, outcome reports — as the user-facing trace identifier).
    """
    trace_json = state.store.get_trace(trace_id)
    if trace_json is None:
        for candidate in state.store.list_traces(limit=10_000):
            try:
                data = json.loads(candidate)
            except (TypeError, ValueError):
                continue
            if str(data.get("id")) == trace_id:
                trace_json = candidate
                break
    if trace_json is None:
        return None
    try:
        data = json.loads(trace_json)
    except (TypeError, ValueError):
        return None
    domain = data.get("domain")
    return str(domain) if domain else None


def _outcome_row(outcome: Outcome) -> dict[str, object]:
    return {
        "prediction_id": outcome.prediction_id,
        "trace_id": outcome.trace_id,
        "actual_choice": outcome.actual_choice,
        "retrospective": outcome.retrospective,
        "free_text": outcome.free_text,
        "timestamp": outcome.timestamp.isoformat(),
    }


__all__ = ["Outcome", "record_outcome"]
