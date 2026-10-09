from __future__ import annotations

from pdt.engine.model_retrieval import RetrievedModelContext


def handle_priority(context: RetrievedModelContext) -> dict[str, object]:
    ranked = sorted(context.value_hierarchy.items(), key=lambda item: item[1], reverse=True)
    return {
        "priorities": [name for name, _ in ranked[:5]],
        "weights": dict(ranked[:5]),
    }
