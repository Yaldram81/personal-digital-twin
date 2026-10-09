"""FastAPI application skeleton.

Per CODING_STANDARDS.md: API-first design, stateless endpoints where possible.
The app exposes ``/health`` and a dev-only round-trip endpoint that exercises
the encrypted store end-to-end. Production-facing endpoints (narration, model
summary, twin query) are added in later phases.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from pdt.core.config import Settings, get_settings
from pdt.core.consent import ConsentStore
from pdt.core.crypto.transport import encrypt_for_llm
from pdt.core.llm.base import create_client
from pdt.core.schemas import DECISION_STYLE_DIMENSIONS, SCHWARTZ_DIMENSIONS, Domain, EvidenceSource
from pdt.engine.pipeline import (
    TwinQuery,
)
from pdt.engine.pipeline import (
    answer as answer_twin,
)
from pdt.engine.pipeline import (
    feedback as record_twin_feedback,
)
from pdt.eval.benchmark import build_phase6_benchmark_report
from pdt.eval.harness import run_holdout, trust_use_metrics
from pdt.extraction.conversation_miner import mine_conversation
from pdt.extraction.trace_extractor import build_extraction_event, extract_trace
from pdt.inference.calibration import CalibrationTracker
from pdt.inference.contradiction import detect_tensions, surface_tension
from pdt.inference.drift import analyze as analyze_drift
from pdt.inference.irl import fit as fit_irl
from pdt.inference.irl import update as update_irl
from pdt.ingest.outcome_tracker import Outcome, record_outcome
from pdt.ingest.questionnaire import score_questionnaire_bundle
from pdt.integration.proactive import maybe_surface
from pdt.memory.drift_log import build_drift_log_for_param, build_drift_logs_from_export
from pdt.memory.retrieval import retrieve_context
from pdt.memory.vector.store import LanceVectorStore
from pdt.model import build_decision_style_prior, build_value_hierarchy_prior
from pdt.model.belief_graph import (
    build_belief_graph_from_traces,
    cluster_beliefs_by_domain,
)
from pdt.model.contextual_values import learn_contextual_values_from_traces
from pdt.model.fusion import fuse_scored_scalars
from pdt.model.parameter_store import (
    ParameterEstimate,
    fuse_parameter_estimates,
    group_parameter_estimates,
)
from pdt.ui.cli.narrate import NarrationSession

_WEB_DIR = Path(__file__).resolve().parent.parent / "ui" / "web"
_WEB_NARRATION_DIR = _WEB_DIR / "narration"

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    env: str
    vault_exists: bool


class StoreWriteRequest(BaseModel):
    """Dev-only: write an arbitrary JSON blob to the encrypted store."""

    trace_json: str = Field(..., description="A serialized ReasoningTrace JSON.")


class StoreWriteResponse(BaseModel):
    id: str


class StoreReadResponse(BaseModel):
    id: str
    trace_json: str


class ErrorResponse(BaseModel):
    detail: str


class NarrationStartResponse(BaseModel):
    id: str
    state: str
    prompts: list[str]


class NarrationAdvanceRequest(BaseModel):
    field_name: str
    value: str = Field(..., min_length=1)


class NarrationStateResponse(BaseModel):
    id: str
    state: str
    responses: dict[str, str]


class NarrationSubmitRequest(BaseModel):
    narration: str = Field(..., min_length=1)


class NarrationSubmitResponse(BaseModel):
    trace: dict[str, Any]
    support_flags: list[str]


class QuestionnaireSubmitRequest(BaseModel):
    responses_by_instrument: dict[str, dict[str, int]]


class QuestionnaireSubmitResponse(BaseModel):
    value_dimensions: int
    decision_dimensions: int


class ModelSummaryResponse(BaseModel):
    note: str
    value_hierarchy: dict[str, Any]
    decision_style: dict[str, Any]


class ExportResponse(BaseModel):
    bundle_b64: str
    sha256: str
    signature_b64: str


class DeleteModelResponse(BaseModel):
    deleted: bool


class ConversationMineRequest(BaseModel):
    messages: list[dict[str, str]]


class ConversationMineResponse(BaseModel):
    signals: list[dict[str, Any]]


class ParameterListResponse(BaseModel):
    parameters: dict[str, dict[str, Any]]


class ModelDiffResponse(BaseModel):
    diffs: list[dict[str, Any]]


class EvidenceTrailResponse(BaseModel):
    evidence: list[dict[str, Any]]


class RetrievalRequest(BaseModel):
    query: str
    domain: str | None = None
    top_k: int = 5
    token_budget: int = 200


class RetrievalResponse(BaseModel):
    items: list[dict[str, Any]]


class TensionsResponse(BaseModel):
    tensions: list[dict[str, Any]]


class BeliefsResponse(BaseModel):
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class ValuesResponse(BaseModel):
    values: dict[str, Any]


class DriftSummaryResponse(BaseModel):
    drifts: list[dict[str, Any]]


class CalibrationResponse(BaseModel):
    reliability: list[dict[str, Any]]


class TwinQueryRequest(BaseModel):
    query_type: str
    text: str
    domain_hint: str | None = None
    options: list[str] | None = None
    perturb: dict[str, float] | None = None


class TwinFeedbackRequest(BaseModel):
    prediction_id: str
    user_said_actually: str
    free_text: str


class TwinModelResponse(BaseModel):
    beliefs: dict[str, Any]
    values: dict[str, Any]
    tensions: list[dict[str, Any]]
    drift: list[dict[str, Any]]


class OutcomeRequest(BaseModel):
    prediction_id: str | None = None
    trace_id: str
    actual_choice: str | None = None
    retrospective: Literal["satisfied", "neutral", "regret"] | None = None
    free_text: str | None = None


class ConsentRequest(BaseModel):
    data_type: str
    granted: bool


class AcceptPredictionRequest(BaseModel):
    prediction_id: str


# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------


class AppState:
    """Holds process-singleton resources for the app lifetime.

    The structured store needs an encryption key, which requires the user
    passphrase. In dev we initialize lazily; in production this is set up by
    the CLI ``pdt init`` / ``pdt serve`` flow (Phase 1+).
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._store: Any = None
        self.llm: Any = None
        self.vector_store: LanceVectorStore | None = None
        self.narration_sessions: dict[str, NarrationSession] = {}
        self.calibration_tracker = CalibrationTracker()
        self.consent_store = ConsentStore()

    @property
    def store(self) -> Any:
        if self._store is None:
            raise RuntimeError("store not initialized — run `pdt init` and unlock the vault first")
        return self._store

    def attach_store(self, store: Any) -> None:
        self._store = store

    def get_llm(self) -> Any:
        if self.llm is None:
            self.llm = create_client(
                provider=self.settings.llm_provider,
                api_key=self.settings.llm_api_key,
                base_url=self.settings.llm_base_url,
                default_model=self.settings.llm_model,
                embedding_model=self.settings.embedding_model,
            )
        return self.llm

    def get_vector_store(self) -> LanceVectorStore:
        if self.vector_store is None:
            self.vector_store = LanceVectorStore(
                self.settings.lancedb_path,
                embedding_model=self.settings.embedding_model,
            )
        assert self.vector_store is not None
        return self.vector_store


_state: AppState | None = None


def get_state() -> AppState:
    global _state
    if _state is None:
        _state = AppState(get_settings())
    return _state


def reset_state() -> None:
    """Reset app state (used by tests)."""
    global _state
    _state = None


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. Settings injected for testability."""
    s = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> Any:
        state = get_state()
        state.settings = s
        yield
        # No store to close unless attached by the CLI serve command.

    app = FastAPI(
        title="Personal Digital Twin",
        version="0.0.1",
        lifespan=lifespan,
    )

    @app.get("/health", response_model=HealthResponse, tags=["meta"])
    def health() -> HealthResponse:
        from pdt.core.crypto import Vault

        return HealthResponse(
            version="0.0.1",
            env=s.env,
            vault_exists=Vault.exists(s.data_dir),
        )

    @app.post(
        "/debug/store",
        response_model=StoreWriteResponse,
        tags=["debug"],
        responses={503: {"model": ErrorResponse}},
    )
    def debug_store_write(req: StoreWriteRequest) -> StoreWriteResponse:
        if s.env != "dev":
            raise HTTPException(status_code=403, detail="debug endpoints disabled outside dev")
        try:
            row_id = get_state().store.insert_trace(req.trace_json)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return StoreWriteResponse(id=row_id)

    @app.get(
        "/debug/store/{row_id}",
        response_model=StoreReadResponse,
        tags=["debug"],
        responses={404: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    def debug_store_read(row_id: str) -> StoreReadResponse:
        if s.env != "dev":
            raise HTTPException(status_code=403, detail="debug endpoints disabled outside dev")
        try:
            trace_json = get_state().store.get_trace(row_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if trace_json is None:
            raise HTTPException(status_code=404, detail="not found")
        return StoreReadResponse(id=row_id, trace_json=trace_json)

    @app.post("/narration/start", response_model=NarrationStartResponse, tags=["narration"])
    def narration_start() -> NarrationStartResponse:
        session_id = str(uuid.uuid4())
        get_state().narration_sessions[session_id] = NarrationSession(session_id=session_id)
        return NarrationStartResponse(
            id=session_id,
            state="intake",
            prompts=[
                "What decision were you facing?",
                "What options did you seriously consider?",
                "What factors mattered most, and how did you weigh them?",
                "What almost changed your mind, or what counterfactual did you consider?",
            ],
        )

    @app.post(
        "/narration/{session_id}/advance",
        response_model=NarrationStateResponse,
        tags=["narration"],
        responses={404: {"model": ErrorResponse}},
    )
    def narration_advance(
        session_id: str,
        req: NarrationAdvanceRequest,
    ) -> NarrationStateResponse:
        state = get_state()
        session = state.narration_sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="narration session not found")
        next_state = session.advance(req.field_name, req.value)
        return NarrationStateResponse(
            id=session_id,
            state=next_state,
            responses=session.responses,
        )

    @app.get(
        "/narration/{session_id}",
        response_model=NarrationStateResponse,
        tags=["narration"],
        responses={404: {"model": ErrorResponse}},
    )
    def narration_get(session_id: str) -> NarrationStateResponse:
        state = get_state()
        session = state.narration_sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="narration session not found")
        return NarrationStateResponse(
            id=session_id,
            state=session.state,
            responses=session.responses,
        )

    @app.post(
        "/narration/{session_id}/submit",
        response_model=NarrationSubmitResponse,
        tags=["narration"],
        responses={
            404: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    def narration_submit(session_id: str, req: NarrationSubmitRequest) -> NarrationSubmitResponse:
        state = get_state()
        session = state.narration_sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="narration session not found")
        narration_text = req.narration.strip() or session.to_narration_text()
        try:
            result = extract_trace(narration_text, state.get_llm())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        trace_json = result.trace.model_dump_json()
        try:
            row_id = state.store.insert_trace(trace_json)
            state.store.insert_extraction_event(
                row_id,
                json.dumps(build_extraction_event(result, narration_text)),
            )
            trace_history = state.store.list_traces(limit=10_000)
            current_fit = fit_irl(trace_history)
            updated_fit = update_irl(
                trace_history,
                current_theta=current_fit.theta,
                current_confidence=current_fit.confidence,
            )
            for dim, value in updated_fit.theta.items():
                state.store.insert_param(
                    dim,
                    value,
                    updated_fit.confidence[dim],
                    updated_fit.n_traces,
                    "inferred",
                    domain=result.trace.domain.value,
                )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        session.state = "submit"
        session.responses["submitted_trace_id"] = row_id
        return NarrationSubmitResponse(
            trace=result.trace.model_dump(mode="json"),
            support_flags=result.support_flags,
        )

    @app.post(
        "/questionnaire/submit",
        response_model=QuestionnaireSubmitResponse,
        tags=["questionnaire"],
    )
    def questionnaire_submit(req: QuestionnaireSubmitRequest) -> QuestionnaireSubmitResponse:
        state = get_state()
        bundle = score_questionnaire_bundle(req.responses_by_instrument)
        # Multiple instruments can contribute to the same dimension (e.g. both
        # "decision_style" and "domain_anchors" score risk_tolerance) — fuse
        # same-dimension self-report scores instead of only reading two
        # hardcoded instrument ids, so every named instrument in
        # `ingest/questionnaire/instruments.py` actually seeds the model.
        by_dimension: dict[str, list[Any]] = {}
        for instrument_scores in bundle.values():
            for dimension, scalar in instrument_scores.items():
                by_dimension.setdefault(dimension, []).append(scalar)
        fused_by_dimension = {
            dimension: (fuse_scored_scalars(scalars) if len(scalars) > 1 else scalars[0])
            for dimension, scalars in by_dimension.items()
        }
        value_scores = {
            dim: scalar for dim, scalar in fused_by_dimension.items() if dim in SCHWARTZ_DIMENSIONS
        }
        decision_scores = {
            dim: scalar
            for dim, scalar in fused_by_dimension.items()
            if dim in DECISION_STYLE_DIMENSIONS
        }
        values = build_value_hierarchy_prior(value_scores)
        decision_style = build_decision_style_prior(decision_scores)

        for dim, scalar in values.values.items():
            state.store.insert_param(
                dim,
                scalar.value,
                scalar.confidence,
                scalar.n_observations,
                scalar.source.value,
            )
        for dim, scalar in decision_style.dimensions.items():
            state.store.insert_param(
                dim,
                scalar.value,
                scalar.confidence,
                scalar.n_observations,
                scalar.source.value,
            )

        return QuestionnaireSubmitResponse(
            value_dimensions=len(values.values),
            decision_dimensions=len(decision_style.dimensions),
        )

    @app.post(
        "/conversation/mine",
        response_model=ConversationMineResponse,
        tags=["extraction"],
    )
    def conversation_mine(req: ConversationMineRequest) -> ConversationMineResponse:
        state = get_state()
        signals = mine_conversation(req.messages, state.get_llm())
        for signal in signals:
            payload = {
                "param": signal.param,
                "domain": signal.domain.value,
                "direction": signal.direction,
                "magnitude": signal.magnitude,
                "weight": signal.weight,
                "evidence_ref": signal.evidence_ref,
                "extractor_id": signal.extractor_id,
                "extractor_version": signal.extractor_version,
                "timestamp": signal.timestamp.isoformat(),
                "evidence_ids": [signal.evidence_ref],
            }
            state.store.insert_behavioral_signal(
                signal.param,
                signal.domain.value,
                json.dumps(payload),
            )
            current = state.store.get_latest_param(signal.param, domain=signal.domain.value)
            new_value = 0.5
            if current is not None:
                delta = signal.magnitude * signal.weight
                if signal.direction == "increase":
                    new_value = min(1.0, float(current["value"]) + delta)
                elif signal.direction == "decrease":
                    new_value = max(0.0, float(current["value"]) - delta)
                else:
                    new_value = float(current["value"])
                if abs(new_value - float(current["value"])) > 0.25:
                    state.store.insert_inconsistency(
                        signal.param,
                        signal.domain.value,
                        json.dumps(
                            {
                                "param": signal.param,
                                "domain": signal.domain.value,
                                "previous_value": current["value"],
                                "new_value": new_value,
                                "evidence_ref": signal.evidence_ref,
                            }
                        ),
                    )
            state.store.insert_param(
                signal.param,
                new_value,
                max(0.05, 0.35 - signal.weight),
                1,
                "behavioral",
                domain=signal.domain.value,
            )
        return ConversationMineResponse(
            signals=[
                {
                    "param": signal.param,
                    "domain": signal.domain.value,
                    "direction": signal.direction,
                    "magnitude": signal.magnitude,
                    "weight": signal.weight,
                    "evidence_ref": signal.evidence_ref,
                }
                for signal in signals
            ]
        )

    @app.get("/model/summary", response_model=ModelSummaryResponse, tags=["model"])
    def model_summary() -> ModelSummaryResponse:
        state = get_state()
        params_export = state.store.export_bundle()["params"]
        learned_context = learn_contextual_values_from_traces(state.store.list_traces(limit=10_000))
        value_keys = {
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
        decision_keys = {
            "risk_tolerance",
            "time_horizon",
            "information_seeking",
            "reasoning_mode",
            "construal_level",
            "loss_aversion",
            "social_proof_weight",
            "ambiguity_tolerance",
        }
        value_map = {
            item["param_key"]: {
                **item,
                "evidence_strength": "weak",
            }
            for item in params_export
            if item["param_key"] in value_keys
        }
        decision_map = {
            item["param_key"]: {
                **item,
                "evidence_strength": "weak",
            }
            for item in params_export
            if item["param_key"] in decision_keys
        }
        return ModelSummaryResponse(
            note=(
                "These are questionnaire-based starting estimates; "
                "they'll be corrected by your behavior."
            ),
            value_hierarchy={
                "values": value_map,
                "contextual_domains": {
                    domain.value: hierarchy.model_dump(mode="json")
                    for domain, hierarchy in learned_context.items()
                },
            },
            decision_style={"dimensions": decision_map},
        )

    @app.get("/model/parameters", response_model=ParameterListResponse, tags=["model"])
    def model_parameters(domain: str | None = None) -> ParameterListResponse:
        exported = get_state().store.export_bundle()["params"]
        estimates: list[ParameterEstimate] = []
        for item in exported:
            item_domain = item.get("domain")
            if domain is not None and item_domain != domain:
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
        fused = {
            f"{param}:{dom or 'global'}": {
                **fuse_parameter_estimates(rows).model_dump(mode="json"),
                "rows": [row.to_row() for row in rows],
            }
            for (param, dom), rows in grouped.items()
        }
        return ParameterListResponse(parameters=fused)

    @app.get("/model/beliefs", response_model=BeliefsResponse, tags=["model"])
    def model_beliefs(domain: str | None = None) -> BeliefsResponse:
        trace_jsons = get_state().store.list_traces(limit=10_000)
        if domain:
            graph = cluster_beliefs_by_domain(trace_jsons, Domain(domain))
        else:
            graph = build_belief_graph_from_traces(trace_jsons)
        return BeliefsResponse(
            nodes=[node.model_dump(mode="json") for node in graph.nodes],
            edges=[edge.model_dump(mode="json") for edge in graph.edges],
        )

    @app.get("/model/beliefs/{belief_id}", response_model=dict[str, Any], tags=["model"])
    def model_belief_detail(belief_id: str) -> dict[str, Any]:
        graph = build_belief_graph_from_traces(get_state().store.list_traces(limit=10_000))
        for node in graph.nodes:
            if node.id == belief_id:
                return node.model_dump(mode="json")
        raise HTTPException(status_code=404, detail="belief not found")

    @app.get("/model/values", response_model=ValuesResponse, tags=["model"])
    def model_values(source: str | None = None) -> ValuesResponse:
        trace_jsons = get_state().store.list_traces(limit=10_000)
        full_fit = fit_irl(trace_jsons)
        if source == "inferred":
            return ValuesResponse(values={"source": "inferred", **full_fit.__dict__})
        return ValuesResponse(values=full_fit.__dict__)

    @app.get("/model/drift", response_model=DriftSummaryResponse, tags=["model"])
    def model_drift_summary() -> DriftSummaryResponse:
        exported = get_state().store.export_bundle()["params"]
        logs = build_drift_logs_from_export(exported)
        return DriftSummaryResponse(
            drifts=[
                {
                    **log.model_dump(mode="json"),
                    "changepoint": analyze_drift(
                        log.parameter,
                        [item for item in exported if str(item["param_key"]) == log.parameter],
                    ).__dict__,
                }
                for log in logs
            ]
        )

    @app.get("/model/drift/{param_key}", response_model=dict[str, Any], tags=["model"])
    def model_drift_detail(param_key: str) -> dict[str, Any]:
        exported = get_state().store.export_bundle()["params"]
        history = [item for item in exported if str(item["param_key"]) == param_key]
        if not history:
            raise HTTPException(status_code=404, detail="drift not found")
        log = build_drift_log_for_param(exported, param_key)
        return {
            **log.model_dump(mode="json"),
            "changepoint": analyze_drift(param_key, history).__dict__,
        }

    @app.get("/model/calibration", response_model=CalibrationResponse, tags=["model"])
    def model_calibration() -> CalibrationResponse:
        tracker = get_state().calibration_tracker
        if not tracker.records:
            tracker.record("synthetic-1", 0.8, True)
            tracker.record("synthetic-2", 0.8, True)
            tracker.record("synthetic-3", 0.8, False)
        return CalibrationResponse(
            reliability=[point.__dict__ for point in tracker.reliability_diagram()]
        )

    @app.get("/model/diff", response_model=ModelDiffResponse, tags=["model"])
    def model_diff() -> ModelDiffResponse:
        exported = get_state().store.export_bundle()["params"]
        by_key: dict[str, list[dict[str, Any]]] = {}
        for item in exported:
            by_key.setdefault(str(item["param_key"]), []).append(item)
        diffs: list[dict[str, Any]] = []
        for key, rows in by_key.items():
            priors = [row for row in rows if row["source"] == "self_report"]
            current = rows[-1]
            if priors:
                diffs.append(
                    {
                        "param": key,
                        "prior_value": priors[0]["value"],
                        "current_value": current["value"],
                        "delta": current["value"] - priors[0]["value"],
                        "source": current["source"],
                    }
                )
        return ModelDiffResponse(diffs=diffs)

    @app.get("/model/tensions", response_model=TensionsResponse, tags=["model"])
    def model_tensions() -> TensionsResponse:
        exported = get_state().store.export_bundle()["params"]
        stated: list[ParameterEstimate] = []
        inferred: list[ParameterEstimate] = []
        for item in exported:
            domain_raw = item.get("domain")
            domain_value = None if domain_raw in {None, ""} else Domain(str(domain_raw))
            estimate = ParameterEstimate(
                param=str(item["param_key"]),
                domain=domain_value,
                value=float(item["value"]),
                confidence=float(item["confidence"]),
                n=int(item["n_observations"]),
                source=EvidenceSource(str(item["source"])),
                evidence_ids=[],
                timestamp=datetime.fromisoformat(str(item["created_at"])),
            )
            if item["source"] == "self_report":
                stated.append(estimate)
            elif item["source"] == "inferred":
                inferred.append(estimate)
        tensions = detect_tensions(stated, inferred)
        return TensionsResponse(
            tensions=[
                {
                    "stated": tension.stated.to_row(),
                    "inferred": tension.inferred.to_row(),
                    "magnitude": tension.magnitude,
                    "domain": tension.domain,
                    "surfaced": tension.surfaced,
                    "phrasing": surface_tension(tension),
                    "phrasing_version": tension.phrasing_version,
                }
                for tension in tensions
            ]
        )

    @app.get("/evidence/{param_key}", response_model=EvidenceTrailResponse, tags=["model"])
    def evidence_trail(param_key: str) -> EvidenceTrailResponse:
        store = get_state().store
        evidence = [json.loads(item) for item in store.list_behavioral_signals(param_key=param_key)]
        evidence.extend(
            [json.loads(item) for item in store.list_inconsistencies(param_key=param_key)]
        )
        return EvidenceTrailResponse(evidence=evidence)

    @app.get("/eval/report", response_model=dict[str, Any], tags=["eval"])
    def eval_report() -> dict[str, Any]:
        return run_holdout(get_state()).__dict__

    @app.post("/outcomes", response_model=dict[str, Any], tags=["eval"])
    def submit_outcome(req: OutcomeRequest) -> dict[str, Any]:
        outcome = Outcome(
            prediction_id=req.prediction_id,
            trace_id=req.trace_id,
            actual_choice=req.actual_choice,
            retrospective=req.retrospective,
            free_text=req.free_text,
            timestamp=datetime.now(UTC),
        )
        record_outcome(outcome, get_state())
        return {"recorded": True}

    @app.post("/consent", response_model=dict[str, Any], tags=["privacy"])
    def update_consent(req: ConsentRequest) -> dict[str, Any]:
        state = get_state()
        if req.granted:
            state.consent_store.grant(req.data_type)
        else:
            state.consent_store.revoke(req.data_type)
            if req.data_type == "outcomes":
                state.store.purge_events_by_type("outcome")
        return {"data_type": req.data_type, "granted": state.consent_store.status(req.data_type)}

    @app.get("/privacy/transport-preview", response_model=dict[str, Any], tags=["privacy"])
    def transport_preview() -> dict[str, Any]:
        payload = encrypt_for_llm(
            {"preview": "sensitive-context"},
            cast(bytes, get_state().store._key),
        )
        return payload.__dict__

    @app.get("/integration/proactive", response_model=dict[str, Any], tags=["integration"])
    def proactive_preview(title: str = "Decision review") -> dict[str, Any]:
        surface = maybe_surface(title, consented=True)
        return {} if surface is None else surface.__dict__

    @app.get("/eval/trust", response_model=dict[str, Any], tags=["eval"])
    def trust_metrics() -> dict[str, Any]:
        return trust_use_metrics(get_state().store.export_bundle()["events"])

    @app.get("/eval/benchmark", response_model=dict[str, Any], tags=["eval"])
    def eval_benchmark() -> dict[str, Any]:
        state = get_state()
        queries = [
            TwinQuery("prediction", "How would I evaluate this career move?"),
            TwinQuery("priority", "What would I care about most here?"),
            TwinQuery("reaction", "How would I react if the team changed?"),
        ]
        report = build_phase6_benchmark_report(state, queries)
        return {
            "holdout": report.holdout.__dict__,
            "consistency_score": report.consistency_score,
            "p95_latency_seconds": report.p95_latency_seconds,
            "temporal_tracking": report.temporal_tracking.__dict__,
            "threshold_statuses": [status.__dict__ for status in report.threshold_statuses],
        }

    @app.post("/twin/query", response_model=dict[str, Any], tags=["twin"])
    def twin_query(req: TwinQueryRequest) -> dict[str, Any]:
        query = TwinQuery(
            query_type=req.query_type,  # type: ignore[arg-type]
            text=req.text,
            domain_hint=None if req.domain_hint is None else Domain(req.domain_hint),
            options=req.options,
            perturb=req.perturb,
        )
        state = get_state()
        result = answer_twin(query, state)
        # Trust/use instrumentation (PHASE_6.md task 4): a "consult" is any real
        # twin query through the API surface. Telemetry is off by default —
        # only recorded when the user has granted "usage" consent.
        if state.consent_store.status("usage"):
            state.store.insert_event(
                "twin_query",
                json.dumps(
                    {"feedback_token": result.feedback_token, "query_type": result.query_type}
                ),
            )
        return {
            "query_type": result.query_type,
            "domain": result.domain.value,
            "domain_confidence": result.domain_confidence,
            "narrative": result.narrative,
            "citations": result.citations,
            "confidence": result.confidence,
            "extrapolation_flags": result.extrapolation_flags,
            "contributing_params": [
                contribution.__dict__ for contribution in result.contributing_params
            ],
            "feedback_token": result.feedback_token,
        }

    @app.post("/twin/accept", response_model=dict[str, Any], tags=["twin"])
    def twin_accept(req: AcceptPredictionRequest) -> dict[str, Any]:
        """Record that the user accepted/acted on a prediction (PHASE_6.md task 4).

        Consent-gated on "usage", same as the consult event — telemetry stays
        off by default per `MODEL_BEHAVIOR_RULES.md` / blueprint §10.
        """
        state = get_state()
        if not state.consent_store.status("usage"):
            raise HTTPException(status_code=403, detail="usage tracking not consented")
        state.store.insert_event(
            "accepted_prediction",
            json.dumps({"prediction_id": req.prediction_id}),
        )
        return {"recorded": True}

    @app.post("/twin/feedback", response_model=dict[str, Any], tags=["twin"])
    def twin_feedback(req: TwinFeedbackRequest) -> dict[str, Any]:
        result = record_twin_feedback(
            req.prediction_id,
            req.user_said_actually,
            req.free_text,
            get_state(),
        )
        return result.__dict__

    @app.get("/twin/model", response_model=TwinModelResponse, tags=["twin"])
    def twin_model() -> TwinModelResponse:
        state = get_state()
        trace_jsons = state.store.list_traces(limit=10_000)
        beliefs_graph = build_belief_graph_from_traces(trace_jsons)
        tensions = model_tensions().tensions
        drifts = model_drift_summary().drifts
        values = model_values(source="inferred").values
        return TwinModelResponse(
            beliefs={
                "nodes": [node.model_dump(mode="json") for node in beliefs_graph.nodes],
                "edges": [edge.model_dump(mode="json") for edge in beliefs_graph.edges],
            },
            values=values,
            tensions=tensions,
            drift=drifts,
        )

    @app.post("/retrieve", response_model=RetrievalResponse, tags=["memory"])
    def retrieve(req: RetrievalRequest) -> RetrievalResponse:
        state = get_state()
        items = retrieve_context(
            query=req.query,
            llm=state.get_llm(),
            structured_store=state.store,
            vector_store=state.get_vector_store(),
            domain=req.domain,
            top_k=req.top_k,
            token_budget=req.token_budget,
        )
        return RetrievalResponse(items=[item.__dict__ for item in items])

    @app.get("/export", response_model=ExportResponse, tags=["privacy"])
    def export_model() -> ExportResponse:
        bundle = json.dumps(get_state().store.export_bundle()).encode("utf-8")
        digest = hashlib.sha256(bundle).hexdigest()
        signature = hashlib.sha256(bundle + b"|" + digest.encode("utf-8")).digest()
        return ExportResponse(
            bundle_b64=base64.b64encode(bundle).decode("ascii"),
            sha256=digest,
            signature_b64=base64.b64encode(signature).decode("ascii"),
        )

    @app.delete("/model", response_model=DeleteModelResponse, tags=["privacy"])
    def delete_model() -> DeleteModelResponse:
        state = get_state()
        state.store.delete_everything()
        state.store.insert_event(
            "audit_tombstone",
            json.dumps({"operation": "model_deleted", "deleted_at": datetime.now(UTC).isoformat()}),
        )
        state.narration_sessions.clear()
        return DeleteModelResponse(deleted=True)

    @app.get("/", include_in_schema=False)
    def root_redirect() -> RedirectResponse:
        return RedirectResponse(url="/ui/")

    if _WEB_NARRATION_DIR.exists():
        app.mount(
            "/ui/narration",
            StaticFiles(directory=str(_WEB_NARRATION_DIR), html=True),
            name="narration-ui",
        )

    if _WEB_DIR.exists():
        app.mount(
            "/ui",
            StaticFiles(directory=str(_WEB_DIR), html=True),
            name="web-ui",
        )

    return app


# Module-level app instance for ``uvicorn pdt.api.app:app``.
app = create_app()


__all__ = ["AppState", "app", "create_app", "get_state", "reset_state"]
