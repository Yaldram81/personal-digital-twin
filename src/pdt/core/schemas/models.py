"""Pydantic schemas for the five model components in blueprint §3.

Design rule enforced here: **no scalar is stored without an uncertainty
estimate.** Every numeric parameter is a `ScoredScalar` carrying a value,
a confidence (CI half-width), an observation count, and provenance. A
payload missing the confidence field fails validation.

All model components are frozen (immutable): the system is append-only —
"memory never overwrites truth" (MEMORY_STRATEGY.md). Updates are new rows,
not in-place mutations.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


class Domain(StrEnum):
    """Decision domains, per blueprint §6.1 Step 1."""

    CAREER = "career"
    FINANCIAL = "financial"
    RELATIONAL = "relational"
    CREATIVE = "creative"
    ETHICAL = "ethical"
    HEALTH = "health"
    CROSS_DOMAIN = "cross_domain"


class Stability(StrEnum):
    """Belief/parameter stability tier, per blueprint §5.3."""

    STABLE = "stable"
    MEDIUM = "medium"
    VOLATILE = "volatile"


class EvidenceSource(StrEnum):
    """Where a parameter estimate came from."""

    SELF_REPORT = "self_report"
    BEHAVIORAL = "behavioral"
    INFERRED = "inferred"


class EvidenceStrength(StrEnum):
    """How much weight an estimate deserves."""

    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"


class ScoredScalar(BaseModel):
    """A single numeric parameter value with its uncertainty.

    This is the atomic unit of the model. The confidence field is the CI
    half-width (or 1 - stderr); wider = less certain. A confidence of 0.0
    means "we have no idea"; the field is mandatory and must be set even
    when the system has no data, so uncertainty is never silently dropped.
    """

    model_config = ConfigDict(frozen=True)

    value: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="CI half-width; lower = less certain."
    )
    n_observations: int = Field(0, ge=0)
    last_updated: date
    source: EvidenceSource = EvidenceSource.SELF_REPORT
    evidence_strength: EvidenceStrength = EvidenceStrength.WEAK

    @field_validator("confidence")
    @classmethod
    def _confidence_required(cls, v: float) -> float:
        # Field is mandatory by Pydantic; this validator exists so the error
        # message is explicit about *why* confidence is non-optional.
        if v is None:  # pragma: no cover — Pydantic blocks None before this
            raise ValueError("confidence is required: no scalar may be stored without uncertainty.")
        return v


# ---------------------------------------------------------------------------
# §3.1 Value Hierarchy (Schwartz 10 dimensions)
# ---------------------------------------------------------------------------

SCHWARTZ_DIMENSIONS: tuple[str, ...] = (
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
)


class ValueHierarchy(BaseModel):
    """Real-valued vector over the Schwartz value dimensions (blueprint §3.1)."""

    model_config = ConfigDict(frozen=True)

    values: dict[str, ScoredScalar] = Field(..., description="Keys must be Schwartz dimensions.")
    stability_score: ScoredScalar | None = Field(
        default=None, description="How much the hierarchy has changed over 12 months."
    )

    @field_validator("values")
    @classmethod
    def _validate_dims(cls, v: dict[str, ScoredScalar]) -> dict[str, ScoredScalar]:
        missing = set(SCHWARTZ_DIMENSIONS) - set(v)
        extra = set(v) - set(SCHWARTZ_DIMENSIONS)
        if missing:
            raise ValueError(f"Missing Schwartz dimensions: {sorted(missing)}")
        if extra:
            raise ValueError(f"Unknown dimensions (not Schwartz): {sorted(extra)}")
        return v


# ---------------------------------------------------------------------------
# §3.2 Decision Style Profile
# ---------------------------------------------------------------------------

DECISION_STYLE_DIMENSIONS: tuple[str, ...] = (
    "risk_tolerance",  # 0 = risk averse, 1 = risk seeking
    "time_horizon",  # 0 = immediate, 1 = long-term
    "information_seeking",  # 0 = satisficer, 1 = maximizer
    "reasoning_mode",  # 0 = intuitive, 1 = analytical
    "construal_level",  # 0 = concrete, 1 = abstract
    "loss_aversion",  # 0 = loss-neutral, 1 = strongly loss-averse
    "social_proof_weight",  # how much others' opinions shift decisions
    "ambiguity_tolerance",  # comfort with incomplete information
)


class DecisionStyle(BaseModel):
    """Scalar scores on validated cognitive-style dimensions (blueprint §3.2)."""

    model_config = ConfigDict(frozen=True)

    dimensions: dict[str, ScoredScalar] = Field(
        ..., description="Keys must be decision-style dimensions."
    )

    @field_validator("dimensions")
    @classmethod
    def _validate_dims(cls, v: dict[str, ScoredScalar]) -> dict[str, ScoredScalar]:
        missing = set(DECISION_STYLE_DIMENSIONS) - set(v)
        extra = set(v) - set(DECISION_STYLE_DIMENSIONS)
        if missing:
            raise ValueError(f"Missing decision-style dimensions: {sorted(missing)}")
        if extra:
            raise ValueError(f"Unknown dimensions: {sorted(extra)}")
        return v


# ---------------------------------------------------------------------------
# §3.3 Belief Graph
# ---------------------------------------------------------------------------


class BeliefNode(BaseModel):
    """A personal credence — not a world fact (blueprint §3.3)."""

    model_config = ConfigDict(frozen=True)

    id: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    stability: Stability
    first_observed: date
    last_reinforced: date
    evidence_count: int = Field(0, ge=0)


class BeliefEdge(BaseModel):
    """A relation between two beliefs (blueprint §3.3)."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(..., description="Belief id the edge originates from.")
    target: str = Field(..., description="Belief id the edge points to.")
    relation: Literal["supports", "contradicts", "causes", "correlates"]
    weight: float = Field(..., ge=0.0, le=1.0)


class BeliefGraph(BaseModel):
    """Probabilistic knowledge graph of held beliefs (blueprint §3.3)."""

    model_config = ConfigDict(frozen=True)

    nodes: list[BeliefNode] = Field(default_factory=list)
    edges: list[BeliefEdge] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# §3.4 Reasoning Trace Library
# ---------------------------------------------------------------------------


class TraceFactor(BaseModel):
    """A factor cited in a decision, with its inferred weight and direction."""

    model_config = ConfigDict(frozen=True)

    factor: str
    weight: Literal["HIGH", "MEDIUM", "LOW"]
    direction: str = Field(..., description="e.g. a chosen-option id, or 'toward_X'.")
    explicitly_discounted: bool = False


class ReasoningTrace(BaseModel):
    """A structured record of a past decision (blueprint §3.4).

    The raw training data for the IRL component (Phase 3).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    timestamp: date
    domain: Domain
    context: str = Field(..., description="e.g. 'evaluating new job offer'.")
    options: list[str]
    factors_cited: list[TraceFactor]
    chosen_option: str
    stated_reasons: str
    inferred_values: list[str] = Field(default_factory=list)
    low_signal: bool = False


# ---------------------------------------------------------------------------
# §3.5 Temporal Drift Log
# ---------------------------------------------------------------------------


class DriftLogEntry(BaseModel):
    """A single point in a parameter's time series (blueprint §3.5)."""

    model_config = ConfigDict(frozen=True)

    timestamp: date
    value: float = Field(..., ge=0.0, le=1.0)


class DriftLog(BaseModel):
    """Time-series log of how a parameter has changed (blueprint §3.5)."""

    model_config = ConfigDict(frozen=True)

    parameter: str
    history: list[DriftLogEntry] = Field(default_factory=list)
    inflection_detected: date | None = None
    inflection_trigger: str | None = None
    trend: Literal["increasing", "decreasing", "stable"] = "stable"
    rate_of_change: Literal["slow", "moderate", "fast"] = "slow"


class ChangePointResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    param: str
    most_likely_t: datetime | None = None
    posterior: list[float] = Field(default_factory=list)
    run_length_dist: list[float] = Field(default_factory=list)
    detected: bool = False
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class ConfidenceIntervalModel(BaseModel):
    model_config = ConfigDict(frozen=True)

    center: float = Field(..., ge=0.0)
    half_width: float = Field(..., ge=0.0)
    effective_n: float = Field(..., ge=0.0)
    consistency: float = Field(..., ge=0.0, le=1.0)
    recency_decay: float = Field(..., ge=0.0, le=1.0)


class Contribution(BaseModel):
    model_config = ConfigDict(frozen=True)

    param: str
    weight: float
    ci: ConfidenceIntervalModel


class Prediction(BaseModel):
    model_config = ConfigDict(frozen=True)

    result: Any = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    contributing_params: list[Contribution] = Field(default_factory=list)
    extrapolation_flags: list[str] = Field(default_factory=list)


__all__ = [
    "DECISION_STYLE_DIMENSIONS",
    "SCHWARTZ_DIMENSIONS",
    "BeliefEdge",
    "BeliefGraph",
    "BeliefNode",
    "ChangePointResult",
    "ConfidenceIntervalModel",
    "Contribution",
    "DecisionStyle",
    "Domain",
    "DriftLog",
    "DriftLogEntry",
    "EvidenceSource",
    "EvidenceStrength",
    "ReasoningTrace",
    "Prediction",
    "ScoredScalar",
    "Stability",
    "TraceFactor",
    "ValueHierarchy",
]
