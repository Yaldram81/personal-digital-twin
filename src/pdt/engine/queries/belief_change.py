from __future__ import annotations

from pdt.engine.model_retrieval import RetrievedModelContext


def handle_belief_change(
    query_text: str,
    context: RetrievedModelContext,
    belief_id: str,
) -> dict[str, object]:
    return {
        "query": query_text,
        "belief_id": belief_id,
        "narrative": (
            f"Hypothetically, if '{belief_id}' shifted, your reasoning might move as well. "
            "This is an extrapolation from your current belief cluster, "
            "not a confident prediction."
        ),
    }


__all__ = ["handle_belief_change"]
