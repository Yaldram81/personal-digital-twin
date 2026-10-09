from __future__ import annotations

from pdt.engine.model_retrieval import RetrievedModelContext
from pdt.engine.simulator import SimulationResult


def handle_prediction(
    query_text: str,
    context: RetrievedModelContext,
    simulation: SimulationResult,
) -> dict[str, object]:
    return {
        "result": simulation.reasoning,
        "active_values": simulation.dominant_factors,
        "domain": context.domain.value,
        "query_text": query_text,
    }
