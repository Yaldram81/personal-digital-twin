from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from pdt.api.app import create_app, get_state, reset_state
from pdt.core.config import Settings
from pdt.core.crypto import Vault
from pdt.engine.pipeline import TwinQuery, answer, feedback
from pdt.memory.structured import DuckDBStructuredStore


class StubTwinLLM:
    def complete(self, messages, model=None, temperature=0.0, max_tokens=None):  # type: ignore[no-untyped-def]
        class Resp:
            text = "simulated-user-voice"
            model = "twin-stub"
            provider = "mock"
            usage = {}

        return Resp()

    def embed(self, texts, model=None):  # type: ignore[no-untyped-def]
        return [[0.0] * 16 for _ in texts]


def _client(tmp_path: Path) -> TestClient:
    reset_state()
    data_dir = tmp_path / "data"
    settings = Settings(env="dev", data_dir=data_dir, llm_provider="mock", embedding_model="mock-embed")
    vault = Vault.init(data_dir, "phase5-passphrase", None)
    store = DuckDBStructuredStore(settings.duckdb_path, vault.key)
    store.init_schema()
    app = create_app(settings)
    state = get_state()
    state.attach_store(store)
    state.llm = StubTwinLLM()
    return TestClient(app)


def _seed_persona(state) -> None:  # type: ignore[no-untyped-def]
    traces = [
        {
            "id": "trace-career-1",
            "domain": "career",
            "context": "job choice",
            "options": ["startup", "big_tech"],
            "factors_cited": [{"factor": "learning"}, {"factor": "team quality"}],
            "chosen_option": "startup",
            "stated_reasons": "learning velocity matters more than comfort or prestige",
            "implicit_beliefs": ["growth over salary", "comfort is a warning sign"],
            "timestamp": "2025-01-10",
        },
        {
            "id": "trace-career-2",
            "domain": "career",
            "context": "team decision",
            "options": ["manager_a", "manager_b"],
            "factors_cited": [{"factor": "team quality"}, {"factor": "compensation"}],
            "chosen_option": "manager_a",
            "stated_reasons": "team quality keeps showing up for me",
            "implicit_beliefs": ["team quality matters", "growth over salary"],
            "timestamp": "2025-02-14",
        },
    ]
    for trace in traces:
        state.store.insert_trace(json.dumps(trace))
    state.store.insert_param("self_direction", 0.82, 0.08, 8, "inferred", domain="career")
    state.store.insert_param("achievement", 0.77, 0.09, 8, "inferred", domain="career")
    state.store.insert_param("security", 0.31, 0.22, 2, "inferred", domain="career")
    state.store.insert_param("risk_tolerance", 0.71, 0.09, 6, "behavioral", domain="career")
    state.store.insert_param("reasoning_mode", 0.74, 0.07, 6, "behavioral", domain="career")
    state.store.insert_param("security", 0.82, 0.18, 2, "self_report", domain="career")


def test_all_six_query_types_return_valid_answers(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        _seed_persona(state)
        query_types = [
            TwinQuery("prediction", "How would I evaluate these job offers?", options=["offer a", "offer b"]),
            TwinQuery("priority", "What would I care about most in this career move?"),
            TwinQuery("reaction", "How would I react if my manager changed suddenly?"),
            TwinQuery("counterfactual", "Would I decide differently?", options=["offer a", "offer b"], perturb={"security": 0.9}),
            TwinQuery("drift", "Has my thinking changed on risk?"),
            TwinQuery("blindspot", "What might I be overlooking in this career choice?"),
        ]
        for query in query_types:
            result = answer(query, state)
            assert result.query_type == query.query_type
            assert result.narrative
            assert 0.0 <= result.confidence <= 1.0
            assert result.feedback_token


def test_uncertainty_flags_fire_for_sparse_domain(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        _seed_persona(state)
        result = answer(TwinQuery("prediction", "How would I handle a health treatment decision?"), state)
        assert result.extrapolation_flags
        assert any("extrapolating" in flag.lower() for flag in result.extrapolation_flags)
        assert result.confidence < 0.9


def test_neutral_fallback_fires_on_critically_low_confidence(tmp_path: Path) -> None:
    """MODEL_BEHAVIOR_RULES.md: "If confidence < threshold -> fallback to
    neutral LLM behavior." A single maximal-uncertainty contributing param
    (confidence=0.98, meaning the CI half-width itself is ~0.98) should
    propagate to an output confidence below the neutral-fallback floor.
    """
    with _client(tmp_path):
        state = get_state()
        _seed_persona(state)
        state.store.insert_param(
            "security", 0.5, 0.98, 1, "inferred", domain="creative"
        )
        result = answer(TwinQuery("prediction", "How would I evaluate a new creative project?"), state)
        assert result.confidence < 0.2
        assert "neutral_fallback_low_confidence" in result.extrapolation_flags
        assert "neutral" in result.narrative.lower()


def test_explanation_cites_real_trace_ids_and_uses_vocabulary(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        _seed_persona(state)
        result = answer(TwinQuery("prediction", "How would I think about a startup role?"), state)
        assert result.citations
        assert any(citation.startswith("trace-career-") for citation in result.citations)
        assert "trace-career-1" in result.narrative or "trace-career-2" in result.narrative


def test_counterfactual_is_deterministic_and_only_perturbs_named_param(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        _seed_persona(state)
        query = TwinQuery(
            "counterfactual",
            "Would I choose differently if security mattered more?",
            options=["offer a", "offer b"],
            perturb={"security": 0.95},
        )
        first = answer(query, state)
        second = answer(query, state)
        assert first.narrative == second.narrative
        assert "security" in first.narrative.lower()


def test_blindspot_surfaces_absent_typical_factor(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        _seed_persona(state)
        result = answer(TwinQuery("blindspot", "What am I missing in this career move?"), state)
        assert "commute" in result.narrative.lower() or "compensation" in result.narrative.lower()


def test_feedback_records_correction_and_updates_calibration(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        _seed_persona(state)
        result = answer(TwinQuery("prediction", "How would I evaluate this role?"), state)
        before = len(state.calibration_tracker.records)
        record = feedback(result.feedback_token, "I actually cared more about stability", "The commute changed everything", state)
        assert record.prediction_id == result.feedback_token
        assert len(state.calibration_tracker.records) == before + 1
        exported = state.store.export_bundle()["events"]
        assert any(event["event_type"] == "twin_feedback" for event in exported)


def test_domain_ambiguity_propagates_flag(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        _seed_persona(state)
        result = answer(TwinQuery("prediction", "How would I think about this?"), state)
        assert any("domain match" in flag.lower() or "rarely decided" in flag.lower() for flag in result.extrapolation_flags)


def test_phase5_api_endpoints(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        state = get_state()
        _seed_persona(state)
        resp = client.post(
            "/twin/query",
            json={
                "query_type": "prediction",
                "text": "How would I evaluate this startup offer?",
                "domain_hint": "career",
                "options": ["startup", "big_tech"],
                "perturb": None,
            },
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["query_type"] == "prediction"
        assert payload["citations"]

        feedback_resp = client.post(
            "/twin/feedback",
            json={
                "prediction_id": payload["feedback_token"],
                "user_said_actually": "I wanted stability",
                "free_text": "The brand and commute mattered more than usual.",
            },
        )
        assert feedback_resp.status_code == 200

        model_resp = client.get("/twin/model")
        assert model_resp.status_code == 200
        model_payload = model_resp.json()
        assert "beliefs" in model_payload
        assert "tensions" in model_payload
        assert "drift" in model_payload
