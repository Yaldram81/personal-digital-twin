from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pdt.core.schemas import Domain, EvidenceSource
from pdt.engine.domain_classifier import DomainClassification
from pdt.inference.drift import analyze as analyze_drift
from pdt.inference.uncertainty import Contribution
from pdt.memory.drift_log import build_drift_log_for_param
from pdt.memory.retrieval import retrieve_context
from pdt.model.belief_graph import cluster_beliefs_by_domain
from pdt.model.confidence import ConfidenceInterval
from pdt.model.parameter_store import ParameterEstimate, group_parameter_estimates

_MIN_CONFIDENCE_FOR_PERSONA = 0.3


@dataclass(frozen=True)
class RetrievedModelContext:
    domain: Domain
    domain_confidence: float
    value_hierarchy: dict[str, float]
    decision_style: dict[str, float]
    beliefs: list[str]
    traces: list[dict[str, Any]]
    citations: list[str]
    vocabulary: list[str]
    contributions: list[Contribution]
    extrapolation_flags: list[str]
    tensions: list[dict[str, Any]]
    drift_summary: dict[str, Any]


_VALUE_KEYS = {
    "self_direction",
    "stimulation",
    "hedonism",
    "achievement",
    "power",
    "security",
    "conformity",
    "tradition",
    "benevolence",
    "universalism",
}

_DECISION_KEYS = {
    "risk_tolerance",
    "time_horizon",
    "information_seeking",
    "reasoning_mode",
    "construal_level",
    "loss_aversion",
    "social_proof_weight",
    "ambiguity_tolerance",
}


def assemble_model_context(
    query_text: str,
    classification: DomainClassification,
    state: Any,
    token_budget: int = 250,
    top_k: int = 5,
) -> RetrievedModelContext:
    exported = state.store.export_bundle()["params"]
    estimates: list[ParameterEstimate] = []
    for item in exported:
        item_domain = item.get("domain")
        if (
            item_domain not in {None, "", classification.domain.value}
            and item["param_key"] not in _VALUE_KEYS
        ):
            continue
        estimates.append(
            ParameterEstimate(
                param=str(item["param_key"]),
                domain=None if item_domain in {None, ""} else Domain(str(item_domain)),
                value=float(item["value"]),
                confidence=float(item["confidence"]),
                n=int(item["n_observations"]),
                source=EvidenceSource(str(item["source"])),
                evidence_ids=[],
                timestamp=datetime.fromisoformat(str(item["created_at"])),
            )
        )
    grouped = group_parameter_estimates(estimates)

    value_hierarchy: dict[str, float] = {}
    decision_style: dict[str, float] = {}
    contributions: list[Contribution] = []
    extrapolation_flags: list[str] = []
    for (param, domain), rows in grouped.items():
        latest = rows[-1]
        if param in _VALUE_KEYS:
            value_hierarchy[param] = latest.value
        if param in _DECISION_KEYS and domain in {None, classification.domain}:
            decision_style[param] = latest.value
        if domain in {None, classification.domain}:
            contributions.append(
                Contribution(
                    param=param,
                    weight=1.0,
                    ci=ConfidenceInterval(
                        center=latest.value,
                        half_width=latest.confidence,
                        effective_n=float(latest.n),
                        consistency=max(0.0, 1.0 - latest.confidence),
                        recency_decay=0.1,
                    ),
                )
            )
            if latest.confidence >= 0.2 or latest.n < 3:
                extrapolation_flags.append(
                    f"I'm extrapolating on {param} because the evidence is still thin."
                )

    trace_jsons = state.store.list_traces(domain=classification.domain.value, limit=10_000)
    belief_graph = cluster_beliefs_by_domain(trace_jsons, classification.domain)
    beliefs = [node.id for node in belief_graph.nodes]
    traces = [json.loads(item) for item in trace_jsons[:top_k]]
    citations = [str(trace.get("id", "")) for trace in traces if trace.get("id")]

    retrieved_items = retrieve_context(
        query=query_text,
        llm=state.get_llm(),
        structured_store=state.store,
        vector_store=state.get_vector_store(),
        domain=classification.domain.value,
        top_k=top_k,
        token_budget=token_budget,
    )
    vocabulary = _extract_vocabulary(traces, retrieved_items)
    tensions = _collect_tensions(exported, classification.domain)

    drift_param = next(iter(decision_style or value_hierarchy), None)
    drift_summary = {}
    if drift_param is not None:
        drift_log = build_drift_log_for_param(exported, drift_param)
        changepoint = analyze_drift(
            drift_param,
            [item for item in exported if str(item["param_key"]) == drift_param],
        )
        drift_summary = {
            "log": drift_log.model_dump(mode="json"),
            "changepoint": changepoint.__dict__,
        }

    if not contributions:
        contributions.append(
            Contribution(
                param="domain_confidence",
                weight=1.0,
                ci=ConfidenceInterval(
                    center=classification.confidence,
                    half_width=0.35,
                    effective_n=1.0,
                    consistency=classification.confidence,
                    recency_decay=0.2,
                ),
            )
        )
    if len(traces) < 2:
        extrapolation_flags.append(
            "I'm extrapolating here — you've rarely decided in this area."
        )

    if classification.confidence < _MIN_CONFIDENCE_FOR_PERSONA:
        extrapolation_flags.append(
            "I'm extrapolating here because the domain match itself is ambiguous."
        )

    return RetrievedModelContext(
        domain=classification.domain,
        domain_confidence=classification.confidence,
        value_hierarchy=value_hierarchy,
        decision_style=decision_style,
        beliefs=beliefs,
        traces=traces,
        citations=citations,
        vocabulary=vocabulary,
        contributions=contributions,
        extrapolation_flags=list(dict.fromkeys(extrapolation_flags)),
        tensions=tensions,
        drift_summary=drift_summary,
    )


def _extract_vocabulary(traces: list[dict[str, Any]], retrieved_items: list[Any]) -> list[str]:
    words: list[str] = []
    for trace in traces:
        words.extend(str(trace.get("stated_reasons", "")).lower().split())
    for item in retrieved_items:
        words.extend(item.text.lower().split())
    filtered = [word.strip(".,!?;:") for word in words if len(word.strip(".,!?;:")) > 4]
    seen: set[str] = set()
    ordered: list[str] = []
    for word in filtered:
        if word not in seen:
            seen.add(word)
            ordered.append(word)
    return ordered[:12]


def _collect_tensions(exported: list[dict[str, Any]], domain: Domain) -> list[dict[str, Any]]:
    tensions: list[dict[str, Any]] = []
    by_param: dict[str, dict[str, float]] = {}
    for item in exported:
        if item.get("domain") not in {None, "", domain.value}:
            continue
        by_param.setdefault(str(item["param_key"]), {})[str(item["source"])] = float(item["value"])
    for param, values in by_param.items():
        if "self_report" in values and "inferred" in values:
            magnitude = abs(values["self_report"] - values["inferred"])
            if magnitude > 0.25:
                tensions.append({"param": param, "magnitude": magnitude})
    return tensions


__all__ = ["RetrievedModelContext", "assemble_model_context"]
