from __future__ import annotations

from pdt.core.llm import LLMClient, PromptRegistry
from pdt.engine.model_retrieval import RetrievedModelContext

_TYPICAL_FACTORS: dict[str, tuple[str, ...]] = {
    "career": ("compensation", "commute", "team quality", "learning", "manager"),
    "financial": ("cash flow", "risk", "fees", "taxes", "liquidity"),
    "relational": ("trust", "time", "repair", "compatibility", "family impact"),
    "creative": ("taste", "audience", "sustainability", "craft", "distribution"),
    "ethical": ("harm", "fairness", "integrity", "consent", "power dynamics"),
    "health": ("sleep", "consistency", "recovery", "cost", "medical guidance"),
}


def handle_blindspot(
    query_text: str,
    context: RetrievedModelContext,
    llm: LLMClient,
) -> dict[str, object]:
    typical = list(_TYPICAL_FACTORS.get(context.domain.value, ("tradeoffs", "constraints")))
    user_factors = {
        str(factor.get("factor", "")).lower()
        for trace in context.traces
        for factor in trace.get("factors_cited", [])
        if isinstance(factor, dict)
    }
    missing = [factor for factor in typical if factor.lower() not in user_factors]
    registry = PromptRegistry()
    rendered = registry.render(
        "blindspot_detection",
        version="v1",
        domain=context.domain.value,
        typical_factors=", ".join(typical),
        user_factors=", ".join(sorted(user_factors)) or "none",
    )
    response = llm.complete(
        [
            {"role": "system", "content": rendered},
            {"role": "user", "content": query_text},
        ],
        temperature=0.0,
    )
    narrative = response.text if response.provider != "mock" else (
        f"A possible blind spot is {missing[0] if missing else typical[0]} — it shows up often in "
        f"{context.domain.value} decisions but rarely in your recorded reasoning."
    )
    return {
        "blindspots": missing[:3],
        "narrative": narrative,
    }
