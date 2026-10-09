from __future__ import annotations

from pdt.engine.model_retrieval import RetrievedModelContext


def handle_crossdomain(query_text: str, contexts: list[RetrievedModelContext]) -> dict[str, object]:
    domains = [context.domain.value for context in contexts]
    beliefs = [belief for context in contexts for belief in context.beliefs[:2]]
    belief_text = ", ".join(beliefs[:4]) or "available evidence"
    return {
        "query": query_text,
        "domains": domains,
        "narrative": (
            f"This spans {', '.join(domains)}. The tradeoff is broader than a "
            f"single-domain answer, so uncertainty should widen across beliefs "
            f"like {belief_text}."
        ),
    }


__all__ = ["handle_crossdomain"]
