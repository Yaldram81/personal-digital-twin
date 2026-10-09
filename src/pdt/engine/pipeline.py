from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from pdt.core.schemas import Domain
from pdt.engine.domain_classifier import classify_domain
from pdt.engine.explainer import explain_simulation
from pdt.engine.model_retrieval import RetrievedModelContext, assemble_model_context
from pdt.engine.queries.blindspot import handle_blindspot
from pdt.engine.queries.counterfactual import handle_counterfactual
from pdt.engine.queries.drift import handle_drift
from pdt.engine.queries.prediction import handle_prediction
from pdt.engine.queries.priority import handle_priority
from pdt.engine.queries.reaction import handle_reaction
from pdt.engine.simulator import simulate_reasoning
from pdt.inference.uncertainty import build_prediction_contract

QueryType = Literal["prediction", "priority", "reaction", "counterfactual", "drift", "blindspot"]

# MODEL_BEHAVIOR_RULES.md, Decision Logic: "If confidence < threshold -> fallback
# to neutral LLM behavior." Below this floor the propagated confidence is so
# low (near-zero evidence, maximal-uncertainty contributing params) that
# persona-conditioned narrative would be confident fiction (blueprint §7.4).
# The system degrades to an explicit, non-personalized answer instead.
NEUTRAL_FALLBACK_CONFIDENCE = 0.15


@dataclass(frozen=True)
class TwinQuery:
    query_type: QueryType
    text: str
    domain_hint: Domain | None = None
    options: list[str] | None = None
    perturb: dict[str, float] | None = None


@dataclass(frozen=True)
class TwinAnswer:
    query_type: str
    domain: Domain
    domain_confidence: float
    narrative: str
    citations: list[str]
    confidence: float
    extrapolation_flags: list[str]
    contributing_params: list[Any]
    feedback_token: str


@dataclass(frozen=True)
class FeedbackRecord:
    prediction_id: str
    user_said_actually: str
    free_text: str


@dataclass(frozen=True)
class PredictionEnvelope:
    payload: dict[str, object]
    context: RetrievedModelContext


def answer(query: TwinQuery, state: Any) -> TwinAnswer:
    classification = classify_domain(query.text, hint=query.domain_hint)
    context = assemble_model_context(query.text, classification, state)
    simulation = simulate_reasoning(
        query.text,
        query.options,
        context,
        state.get_llm(),
        query.query_type,
        perturb=query.perturb,
    )
    envelope = _dispatch_query(query, context, simulation, state)
    explained = explain_simulation(str(envelope.payload), envelope.context, state.get_llm())
    prediction = build_prediction_contract(
        result=envelope.payload,
        contributions=envelope.context.contributions,
        extrapolation_flags=envelope.context.extrapolation_flags,
        composition_fn=None,
        linear=True,
    )
    feedback_token = str(uuid.uuid4())
    state.calibration_tracker.record(feedback_token, prediction.confidence, True)
    narrative = explained
    extrapolation_flags = list(envelope.context.extrapolation_flags)
    if prediction.confidence < NEUTRAL_FALLBACK_CONFIDENCE:
        narrative = (
            "I don't have reliable evidence about you in this area, so I can't "
            "responsibly simulate your reasoning here. Falling back to neutral, "
            f"non-personalized guidance instead: {explained}"
        )
        extrapolation_flags.append("neutral_fallback_low_confidence")
    return TwinAnswer(
        query_type=query.query_type,
        domain=classification.domain,
        domain_confidence=classification.confidence,
        narrative=narrative,
        citations=envelope.context.citations,
        confidence=prediction.confidence,
        extrapolation_flags=extrapolation_flags,
        contributing_params=envelope.context.contributions,
        feedback_token=feedback_token,
    )


def feedback(
    prediction_id: str,
    user_said_actually: str,
    free_text: str,
    state: Any,
) -> FeedbackRecord:
    record = FeedbackRecord(
        prediction_id=prediction_id,
        user_said_actually=user_said_actually,
        free_text=free_text,
    )
    state.store.insert_event(
        "twin_feedback",
        json.dumps(record.__dict__),
    )
    state.calibration_tracker.record(prediction_id, 0.2, False)
    return record


def _dispatch_query(
    query: TwinQuery,
    context: RetrievedModelContext,
    simulation: Any,
    state: Any,
) -> PredictionEnvelope:
    if query.query_type == "prediction":
        payload = handle_prediction(query.text, context, simulation)
    elif query.query_type == "priority":
        payload = handle_priority(context)
    elif query.query_type == "reaction":
        payload = handle_reaction(query.text, context)
    elif query.query_type == "counterfactual":
        payload = handle_counterfactual(query.text, context, query.perturb)
    elif query.query_type == "drift":
        payload = handle_drift(context)
    else:
        payload = handle_blindspot(query.text, context, state.get_llm())
    return PredictionEnvelope(payload=payload, context=context)


__all__ = [
    "FeedbackRecord",
    "PredictionEnvelope",
    "TwinAnswer",
    "TwinQuery",
    "answer",
    "feedback",
]
