from __future__ import annotations

import json
from collections import defaultdict
from datetime import date

from pdt.core.schemas import Domain, EvidenceSource, EvidenceStrength, ScoredScalar, ValueHierarchy
from pdt.model.value_hierarchy import build_value_hierarchy_prior

SUPPORTED_CONTEXT_DOMAINS: tuple[Domain, ...] = (
    Domain.CAREER,
    Domain.RELATIONAL,
    Domain.HEALTH,
    Domain.FINANCIAL,
    Domain.CREATIVE,
)


def contextual_value_hierarchies(
    priors_by_domain: dict[Domain, dict[str, ScoredScalar]],
) -> dict[Domain, ValueHierarchy]:
    return {
        domain: build_value_hierarchy_prior(scored)
        for domain, scored in priors_by_domain.items()
        if domain in SUPPORTED_CONTEXT_DOMAINS
    }


def learn_contextual_values_from_traces(
    trace_jsons: list[str],
    today: date | None = None,
) -> dict[Domain, ValueHierarchy]:
    as_of = today or date.today()
    domain_scores: dict[Domain, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for trace_json in trace_jsons:
        trace = json.loads(trace_json)
        domain_raw = str(trace.get("domain", "cross_domain"))
        try:
            domain = Domain(domain_raw)
        except ValueError:
            continue
        if domain not in SUPPORTED_CONTEXT_DOMAINS:
            continue
        for value_name in trace.get("inferred_values", []):
            domain_scores[domain][str(value_name)].append(1.0)

    result: dict[Domain, ValueHierarchy] = {}
    for domain, scores in domain_scores.items():
        scored: dict[str, ScoredScalar] = {}
        for value_name, observations in scores.items():
            scored[value_name] = ScoredScalar(
                value=sum(observations) / len(observations),
                confidence=max(0.05, 0.3 / max(len(observations), 1)),
                n_observations=len(observations),
                last_updated=as_of,
                source=EvidenceSource.BEHAVIORAL,
                evidence_strength=(
                    EvidenceStrength.MODERATE if len(observations) < 3 else EvidenceStrength.STRONG
                ),
            )
        result[domain] = build_value_hierarchy_prior(scored, as_of=as_of)
    return result
