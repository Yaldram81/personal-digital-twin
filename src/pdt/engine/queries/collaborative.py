from __future__ import annotations

from pdt.engine.model_retrieval import RetrievedModelContext


def handle_collaborative(
    primary: RetrievedModelContext,
    secondary: RetrievedModelContext,
    query_text: str,
) -> dict[str, object]:
    primary_beliefs = ", ".join(primary.beliefs[:2]) or "their priors"
    secondary_beliefs = ", ".join(secondary.beliefs[:2]) or "their priors"
    return {
        "query": query_text,
        "narrative": (
            f"Jointly, one person brings {primary_beliefs} while the other brings "
            f"{secondary_beliefs}. The resulting decision shows tradeoff "
            "and dominance dynamics."
        ),
    }


__all__ = ["handle_collaborative"]
