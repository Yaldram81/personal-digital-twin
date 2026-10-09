from __future__ import annotations

from pdt.engine.model_retrieval import RetrievedModelContext


def handle_longhorizon(
    query_text: str,
    context: RetrievedModelContext,
    horizon_months: int = 24,
) -> dict[str, object]:
    return {
        "query": query_text,
        "horizon_months": horizon_months,
        "narrative": (
            f"Over roughly {horizon_months} months, your reasoning may drift "
            "gradually, but this is speculative. Confidence should widen over "
            "time, especially where current evidence is thin."
        ),
    }


__all__ = ["handle_longhorizon"]
