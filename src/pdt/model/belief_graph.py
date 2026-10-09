from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from typing import Any, Literal

from pdt.core.schemas import BeliefEdge, BeliefGraph, BeliefNode, Domain, Stability


def _normalize_belief_id(text: str) -> str:
    return text.strip().lower().replace(" ", "_").replace("-", "_")


def build_belief_graph_from_traces(trace_jsons: list[str]) -> BeliefGraph:
    node_evidence: dict[str, dict[str, Any]] = {}
    edge_weights: dict[tuple[str, str, Literal["correlates"]], float] = defaultdict(float)

    for trace_json in trace_jsons:
        trace = json.loads(trace_json)
        beliefs = trace.get("implicit_beliefs", []) or trace.get("inferred_values", [])
        normalized = [_normalize_belief_id(str(item)) for item in beliefs if str(item).strip()]
        for belief_id in normalized:
            if belief_id not in node_evidence:
                node_evidence[belief_id] = {
                    "count": 0,
                    "first": date.today(),
                    "last": date.today(),
                }
            node_evidence[belief_id]["count"] = int(node_evidence[belief_id]["count"]) + 1
        for i, source in enumerate(normalized):
            for target in normalized[i + 1 :]:
                edge_weights[(source, target, "correlates")] += 1.0
                edge_weights[(target, source, "correlates")] += 1.0

    nodes = [
        BeliefNode(
            id=belief_id,
            confidence=min(1.0, 0.4 + (int(meta["count"]) * 0.1)),
            stability=(
                Stability.STABLE
                if int(meta["count"]) >= 5
                else Stability.MEDIUM
                if int(meta["count"]) >= 2
                else Stability.VOLATILE
            ),
            first_observed=meta["first"],
            last_reinforced=meta["last"],
            evidence_count=int(meta["count"]),
        )
        for belief_id, meta in node_evidence.items()
    ]
    edges = [
        BeliefEdge(
            source=source,
            target=target,
            relation=relation,
            weight=min(1.0, weight / 5.0),
        )
        for (source, target, relation), weight in edge_weights.items()
        if weight >= 1.0
    ]
    return BeliefGraph(nodes=nodes, edges=edges)


def cluster_beliefs_by_domain(trace_jsons: list[str], domain: Domain) -> BeliefGraph:
    domain_traces = [
        trace_json
        for trace_json in trace_jsons
        if json.loads(trace_json).get("domain") == domain.value
    ]
    return build_belief_graph_from_traces(domain_traces)
