from __future__ import annotations

from pdt.engine.model_retrieval import RetrievedModelContext


def handle_counterfactual(
    query_text: str,
    context: RetrievedModelContext,
    perturb: dict[str, float] | None,
) -> dict[str, object]:
    perturb = perturb or {}
    changed = next(iter(perturb.items()), ("nothing", 0.0))
    baseline = sorted(context.value_hierarchy.items(), key=lambda item: item[1], reverse=True)[:3]
    adjusted = []
    for name, value in baseline:
        adjusted_value = changed[1] if name == changed[0] else value
        adjusted.append((name, adjusted_value))
    adjusted.sort(key=lambda item: item[1], reverse=True)
    return {
        "counterfactual": (
            f"If only {changed[0]} changed, your likely priority order becomes "
            f"{', '.join(name for name, _ in adjusted)} while the rest of the context stays fixed."
        ),
        "query_text": query_text,
    }
