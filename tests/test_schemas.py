"""Tests for the Pydantic schemas (blueprint §3 components)."""

from __future__ import annotations

import json
from datetime import date

import pytest
from pydantic import ValidationError

from pdt.core.schemas import (
    SCHWARTZ_DIMENSIONS,
    BeliefEdge,
    BeliefGraph,
    BeliefNode,
    DecisionStyle,
    Domain,
    DriftLog,
    DriftLogEntry,
    EvidenceSource,
    EvidenceStrength,
    ReasoningTrace,
    ScoredScalar,
    Stability,
    TraceFactor,
    ValueHierarchy,
)


class TestScoredScalar:
    """The atomic unit: every scalar must carry uncertainty."""

    def test_valid_scored_scalar(self, today: date) -> None:
        s = ScoredScalar(value=0.84, confidence=0.06, n_observations=147, last_updated=today)
        assert s.value == 0.84
        assert s.confidence == 0.06

    def test_confidence_is_required(self, today: date) -> None:
        """Exit criterion: reject a payload missing the confidence field."""
        with pytest.raises(ValidationError):
            ScoredScalar.model_validate(  # type: ignore[call-arg]
                {"value": 0.5, "n_observations": 10, "last_updated": str(today)}
            )

    def test_value_out_of_range_rejected(self, today: date) -> None:
        with pytest.raises(ValidationError):
            ScoredScalar(value=1.5, confidence=0.1, last_updated=today)

    def test_confidence_out_of_range_rejected(self, today: date) -> None:
        with pytest.raises(ValidationError):
            ScoredScalar(value=0.5, confidence=1.5, last_updated=today)

    def test_negative_observations_rejected(self, today: date) -> None:
        with pytest.raises(ValidationError):
            ScoredScalar(value=0.5, confidence=0.1, n_observations=-1, last_updated=today)

    def test_frozen_immutable(self, today: date) -> None:
        """Exit criterion: append-only — model components are immutable."""
        s = ScoredScalar(value=0.5, confidence=0.1, last_updated=today)
        with pytest.raises(ValidationError):
            s.value = 0.9  # type: ignore[misc]

    def test_serialization_roundtrip(self, today: date) -> None:
        s = ScoredScalar(value=0.5, confidence=0.1, n_observations=5, last_updated=today)
        data = json.loads(s.model_dump_json())
        s2 = ScoredScalar.model_validate(data)
        assert s == s2


class TestValueHierarchy:
    def _make_values(self, today: date) -> dict[str, ScoredScalar]:
        return {
            dim: ScoredScalar(value=0.5, confidence=0.1, last_updated=today)
            for dim in SCHWARTZ_DIMENSIONS
        }

    def test_valid_hierarchy(self, today: date) -> None:
        vh = ValueHierarchy(values=self._make_values(today))
        assert len(vh.values) == 10

    def test_missing_dimension_rejected(self, today: date) -> None:
        vals = self._make_values(today)
        del vals["power"]
        with pytest.raises(ValidationError, match="Missing"):
            ValueHierarchy(values=vals)

    def test_extra_dimension_rejected(self, today: date) -> None:
        vals = self._make_values(today)
        vals["bogus"] = ScoredScalar(value=0.5, confidence=0.1, last_updated=today)
        with pytest.raises(ValidationError, match="Unknown"):
            ValueHierarchy(values=vals)


class TestDecisionStyle:
    def test_valid_style(self, today: date) -> None:
        from pdt.core.schemas import DECISION_STYLE_DIMENSIONS

        dims = {
            d: ScoredScalar(value=0.5, confidence=0.1, last_updated=today)
            for d in DECISION_STYLE_DIMENSIONS
        }
        ds = DecisionStyle(dimensions=dims)
        assert len(ds.dimensions) == 8

    def test_missing_dimension_rejected(self, today: date) -> None:
        dims = {
            "risk_tolerance": ScoredScalar(value=0.5, confidence=0.1, last_updated=today),
        }
        with pytest.raises(ValidationError, match="Missing"):
            DecisionStyle(dimensions=dims)


class TestBeliefGraph:
    def test_valid_graph(self, today: date) -> None:
        n1 = BeliefNode(
            id="remote_work_preferred",
            confidence=0.81,
            stability=Stability.MEDIUM,
            first_observed=today,
            last_reinforced=today,
            evidence_count=23,
        )
        n2 = BeliefNode(
            id="growth_over_salary",
            confidence=0.91,
            stability=Stability.STABLE,
            first_observed=today,
            last_reinforced=today,
            evidence_count=67,
        )
        e = BeliefEdge(
            source="growth_over_salary",
            target="remote_work_preferred",
            relation="supports",
            weight=0.43,
        )
        g = BeliefGraph(nodes=[n1, n2], edges=[e])
        assert len(g.nodes) == 2
        assert len(g.edges) == 1

    def test_empty_graph_ok(self) -> None:
        g = BeliefGraph()
        assert g.nodes == []
        assert g.edges == []

    def test_edge_weight_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            BeliefEdge(source="a", target="b", relation="supports", weight=1.5)


class TestReasoningTrace:
    def test_valid_trace(self, today: date) -> None:
        t = ReasoningTrace(
            id="trace-001",
            timestamp=today,
            domain=Domain.CAREER,
            context="evaluating job offer",
            options=["startup", "big_tech"],
            factors_cited=[
                TraceFactor(factor="learning", weight="HIGH", direction="toward_startup")
            ],
            chosen_option="startup",
            stated_reasons="Wanted to learn more.",
        )
        assert t.chosen_option == "startup"

    def test_serialization_roundtrip(self, today: date) -> None:
        t = ReasoningTrace(
            id="trace-001",
            timestamp=today,
            domain=Domain.CAREER,
            context="test",
            options=["a", "b"],
            factors_cited=[],
            chosen_option="a",
            stated_reasons="reasons",
        )
        data = t.model_dump_json()
        t2 = ReasoningTrace.model_validate_json(data)
        assert t == t2


class TestDriftLog:
    def test_valid_drift_log(self, today: date) -> None:
        dl = DriftLog(
            parameter="risk_tolerance",
            history=[
                DriftLogEntry(timestamp=today, value=0.51),
                DriftLogEntry(timestamp=today, value=0.68),
            ],
            inflection_detected=today,
            trend="increasing",
            rate_of_change="moderate",
        )
        assert len(dl.history) == 2
        assert dl.trend == "increasing"


class TestEvidenceEnums:
    def test_source_values(self) -> None:
        assert EvidenceSource.SELF_REPORT.value == "self_report"
        assert EvidenceSource.BEHAVIORAL.value == "behavioral"
        assert EvidenceSource.INFERRED.value == "inferred"

    def test_strength_values(self) -> None:
        assert EvidenceStrength.WEAK.value == "weak"
        assert EvidenceStrength.STRONG.value == "strong"
