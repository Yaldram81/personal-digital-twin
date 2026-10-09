from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pdt.core.llm import PromptRegistry
from pdt.engine.model_retrieval import RetrievedModelContext


@dataclass(frozen=True)
class SimulationResult:
    reasoning: str
    dominant_factors: list[str]


def simulate_reasoning(
    query_text: str,
    options: list[str] | None,
    context: RetrievedModelContext,
    llm: Any,
    query_type: str,
    perturb: dict[str, float] | None = None,
) -> SimulationResult:
    registry = PromptRegistry()
    patterns = _characteristic_patterns(context)
    rendered = registry.render(
        "simulated_reasoning",
        version="v1",
        value_hierarchy=json.dumps(context.value_hierarchy, sort_keys=True),
        decision_style=json.dumps(context.decision_style, sort_keys=True),
        domain_beliefs=", ".join(context.beliefs[:8]) or "none yet",
        historical_traces=json.dumps([trace.get("id") for trace in context.traces]),
        characteristic_patterns="\n".join(f"- {item}" for item in patterns),
        domain=context.domain.value,
        options="\n".join(options or [query_text]),
    )
    response = llm.complete(
        [
            {"role": "system", "content": rendered},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "query_type": query_type,
                        "query": query_text,
                        "options": options,
                        "perturb": perturb,
                    },
                    sort_keys=True,
                ),
            },
        ],
        temperature=0.0,
    )
    dominant = _dominant_factors(context)
    reasoning = _fallback_reasoning(query_text, options, context, query_type, perturb)
    if response.provider != "mock":
        reasoning = response.text
    return SimulationResult(reasoning=reasoning, dominant_factors=dominant)


def _dominant_factors(context: RetrievedModelContext) -> list[str]:
    ranked = sorted(context.value_hierarchy.items(), key=lambda item: item[1], reverse=True)
    return [name for name, _ in ranked[:3]]


def _characteristic_patterns(context: RetrievedModelContext) -> list[str]:
    factors: list[str] = []
    for trace in context.traces:
        for factor in trace.get("factors_cited", []):
            factor_name = factor.get("factor") if isinstance(factor, dict) else str(factor)
            if factor_name:
                factors.append(str(factor_name))
    unique: list[str] = []
    for factor in factors:
        if factor not in unique:
            unique.append(factor)
    if unique:
        return [f"They often prioritize {factor}" for factor in unique[:4]]
    return ["They default to weighing growth, risk, and fit in that order."]


def _fallback_reasoning(
    query_text: str,
    options: list[str] | None,
    context: RetrievedModelContext,
    query_type: str,
    perturb: dict[str, float] | None,
) -> str:
    top_values = ", ".join(_dominant_factors(context)) or "available evidence"
    beliefs = ", ".join(context.beliefs[:3]) or "no strong belief cluster yet"
    cited = ", ".join(context.citations[:2]) or "your prior traces"
    if query_type == "counterfactual" and perturb:
        perturbed = next(iter(perturb.items()))
        return (
            f"Holding everything else constant, if {perturbed[0]} shifted to {perturbed[1]:.2f}, "
            f"you would likely re-weigh this around {top_values}. "
            f"That still sits next to {beliefs}, "
            f"similar to {cited}."
        )
    option_text = ", ".join(options or [query_text])
    return (
        f"You would probably think through {option_text} by first checking {top_values}. "
        f"Your current belief cluster suggests {beliefs}. Similar patterns show up in {cited}."
    )


__all__ = ["SimulationResult", "simulate_reasoning"]
