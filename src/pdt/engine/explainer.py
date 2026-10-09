from __future__ import annotations

from typing import Any

from pdt.core.llm import PromptRegistry
from pdt.engine.model_retrieval import RetrievedModelContext


def explain_simulation(simulation_text: str, context: RetrievedModelContext, llm: Any) -> str:
    registry = PromptRegistry()
    rendered = registry.render(
        "explanation",
        version="v1",
        simulation_output=simulation_text,
        user_vocabulary=", ".join(context.vocabulary) or "direct, reflective, growth-oriented",
        trace_citations=", ".join(context.citations) or "none",
    )
    response = llm.complete(
        [
            {"role": "system", "content": rendered},
            {"role": "user", "content": simulation_text},
        ],
        temperature=0.0,
    )
    if response.provider != "mock":
        return str(response.text)
    vocabulary = ", ".join(context.vocabulary[:3])
    citation = context.citations[0] if context.citations else "trace-history"
    prefix = f"Using your usual framing around {vocabulary}, " if vocabulary else ""
    return f"{prefix}{simulation_text} Similar to how you weighed this in [{citation}]."


__all__ = ["explain_simulation"]
