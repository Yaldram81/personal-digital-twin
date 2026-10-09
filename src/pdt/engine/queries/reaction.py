from __future__ import annotations

from pdt.engine.model_retrieval import RetrievedModelContext


def handle_reaction(query_text: str, context: RetrievedModelContext) -> dict[str, object]:
    belief = context.beliefs[0] if context.beliefs else "uncertain assumptions"
    style = (
        next(iter(context.decision_style), "reasoning_mode")
        if context.decision_style
        else "reasoning_mode"
    )
    return {
        "reaction": (
            f"You would likely react to '{query_text}' through the lens of {belief} "
            f"with your usual {style} style."
        )
    }
