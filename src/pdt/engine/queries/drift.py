from __future__ import annotations

from pdt.engine.model_retrieval import RetrievedModelContext


def handle_drift(context: RetrievedModelContext) -> dict[str, object]:
    return {
        "drift": context.drift_summary,
    }
