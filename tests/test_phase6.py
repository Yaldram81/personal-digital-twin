from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from pdt.api.app import create_app, get_state, reset_state
from pdt.core.config import Settings
from pdt.core.consent import ConsentStore
from pdt.core.crypto import Vault
from pdt.core.crypto.transport import decrypt_from_llm, encrypt_for_llm
from pdt.engine.domain_classifier import classify_domain
from pdt.engine.model_retrieval import assemble_model_context
from pdt.engine.queries.belief_change import handle_belief_change
from pdt.engine.queries.collaborative import handle_collaborative
from pdt.engine.queries.crossdomain import handle_crossdomain
from pdt.engine.queries.longhorizon import handle_longhorizon
from pdt.eval.harness import run_holdout, trust_use_metrics
from pdt.ingest.outcome_tracker import Outcome, record_outcome
from pdt.integration.proactive import maybe_surface
from pdt.memory.structured import DuckDBStructuredStore


class StubPhase6LLM:
    def complete(self, messages, model=None, temperature=0.0, max_tokens=None):  # type: ignore[no-untyped-def]
        class Resp:
            text = "phase6-llm"
            model = "phase6"
            provider = "mock"
            usage = {}

        return Resp()

    def embed(self, texts, model=None):  # type: ignore[no-untyped-def]
        return [[0.0] * 16 for _ in texts]


def _client(tmp_path: Path) -> TestClient:
    reset_state()
    data_dir = tmp_path / "data"
    settings = Settings(env="dev", data_dir=data_dir, llm_provider="mock", embedding_model="mock-embed")
    vault = Vault.init(data_dir, "phase6-passphrase", None)
    store = DuckDBStructuredStore(settings.duckdb_path, vault.key)
    store.init_schema()
    app = create_app(settings)
    state = get_state()
    state.attach_store(store)
    state.llm = StubPhase6LLM()
    state.consent_store = ConsentStore()
    return TestClient(app)


def _seed_state(state) -> None:  # type: ignore[no-untyped-def]
    traces = [
        {
            "id": "trace-1",
            "domain": "career",
            "context": "job move",
            "options": ["stay", "move"],
            "chosen_option": "move",
            "factors_cited": [{"factor": "learning"}, {"factor": "team quality"}],
            "stated_reasons": "learning and team quality dominated",
            "implicit_beliefs": ["growth over salary", "team quality matters"],
            "timestamp": "2025-01-10",
        },
        {
            "id": "trace-2",
            "domain": "financial",
            "context": "city move budget",
            "options": ["move", "stay"],
            "chosen_option": "move",
            "factors_cited": [{"factor": "cash flow"}, {"factor": "risk"}],
            "stated_reasons": "cash flow and upside both mattered",
            "implicit_beliefs": ["upside can justify discomfort"],
            "timestamp": "2025-02-01",
        },
    ]
    for trace in traces:
        state.store.insert_trace(json.dumps(trace))
    state.store.insert_param("self_direction", 0.82, 0.08, 8, "inferred", domain="career")
    state.store.insert_param("risk_tolerance", 0.71, 0.09, 6, "behavioral", domain="career")
    state.store.insert_param("security", 0.42, 0.15, 4, "inferred", domain="financial")
    state.store.insert_event("accepted_prediction", json.dumps({"id": "accept-1"}))


def test_eval_harness_reports_core_metrics(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        _seed_state(state)
        report = run_holdout(state)
        assert 0.0 <= report.accuracy <= 1.0
        assert 0.0 <= report.precision <= 1.0
        assert 0.0 <= report.recall <= 1.0
        assert 0.0 <= report.ece <= 1.0
        assert report.recognition_score is not None


def test_outcome_tracking_requires_consent_and_regret_updates_model(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        _seed_state(state)
        outcome = Outcome(
            prediction_id="pred-1",
            trace_id="trace-1",
            actual_choice="stay",
            retrospective="regret",
            free_text="I underestimated stability.",
            timestamp=datetime.now(UTC),
        )
        try:
            record_outcome(outcome, state)
            raise AssertionError("expected consent failure")
        except PermissionError:
            pass
        state.consent_store.grant("outcomes")
        before = len(state.store.export_bundle()["params"])
        record_outcome(outcome, state)
        after_bundle = state.store.export_bundle()
        assert len(after_bundle["params"]) > before
        assert any(event["event_type"] == "outcome" for event in after_bundle["events"])


def test_encrypt_before_transmit_round_trip(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        payload = {"model": "sensitive", "trace_ids": ["trace-1"]}
        encrypted = encrypt_for_llm(payload, state.store._key)  # type: ignore[attr-defined]
        assert "sensitive" not in encrypted.ciphertext_b64
        decrypted = decrypt_from_llm(encrypted, state.store._key)  # type: ignore[attr-defined]
        assert decrypted == payload


def test_consent_granular_gating_and_export(tmp_path: Path) -> None:
    with _client(tmp_path):
        store = ConsentStore()
        assert store.status("outcomes") is False
        store.grant("outcomes")
        assert store.status("outcomes") is True
        store.revoke("outcomes")
        assert store.status("outcomes") is False
        exported = store.export()
        assert "outcomes" in exported


def test_crossdomain_reasoning_widens_scope(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        _seed_state(state)
        career = assemble_model_context("job move", classify_domain("job move"), state)
        financial = assemble_model_context("budget and rent", classify_domain("budget and rent"), state)
        result = handle_crossdomain("Should I move cities for this job?", [career, financial])
        assert "career" in result["narrative"].lower()
        assert "financial" in result["narrative"].lower()


def test_belief_change_collaborative_longhorizon_and_proactive_exist(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        _seed_state(state)
        primary = assemble_model_context("job move", classify_domain("job move"), state)
        secondary = assemble_model_context("budget and rent", classify_domain("budget and rent"), state)
        belief_change = handle_belief_change("What if I changed my view on growth?", primary, "growth_over_salary")
        collaborative = handle_collaborative(primary, secondary, "How would we decide together?")
        longhorizon = handle_longhorizon("How might my thinking change?", primary)
        proactive = maybe_surface("Decision review meeting", consented=True)
        assert "hypothetically" in belief_change["narrative"].lower()
        assert "jointly" in collaborative["narrative"].lower()
        assert "speculative" in longhorizon["narrative"].lower()
        assert proactive is not None


def test_trust_use_metrics_and_phase6_api(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        _seed_state(state)
        metrics = trust_use_metrics(state.store.export_bundle()["events"])
        assert "consult_rate" in metrics
        assert "accept_rate" in metrics


def test_revoking_outcome_consent_purges_existing_outcomes(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        state = get_state()
        _seed_state(state)
        state.consent_store.grant("outcomes")
        outcome = {
            "prediction_id": "pred-2",
            "trace_id": "trace-1",
            "actual_choice": "stay",
            "retrospective": "neutral",
            "free_text": "post-hoc reflection",
        }
        response = client.post("/outcomes", json=outcome)
        assert response.status_code == 200
        exported = state.store.export_bundle()["events"]
        assert any(event["event_type"] == "outcome" for event in exported)

        revoke = client.post("/consent", json={"data_type": "outcomes", "granted": False})
        assert revoke.status_code == 200
        after = state.store.export_bundle()["events"]
        assert not any(event["event_type"] == "outcome" for event in after)
        assert any(event["event_type"] == "audit_tombstone" for event in after)


def test_regret_update_targets_the_regretted_trace_domain(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        _seed_state(state)
        state.consent_store.grant("outcomes")
        outcome = Outcome(
            prediction_id="pred-fin",
            trace_id="trace-2",
            actual_choice="stay",
            retrospective="regret",
            free_text="I underweighted the financial risk.",
            timestamp=datetime.now(UTC),
        )
        before = {
            (item["param_key"], item["domain"]): item["confidence"]
            for item in state.store.export_bundle()["params"]
        }
        record_outcome(outcome, state)
        after = state.store.export_bundle()["params"]
        financial_rows = [item for item in after if item["domain"] == "financial"]
        assert len(financial_rows) > 1
        widened = max(financial_rows, key=lambda item: item["confidence"])
        assert widened["confidence"] > before[(widened["param_key"], widened["domain"])]


def test_twin_query_consult_and_accept_are_consent_gated(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        state = get_state()
        _seed_state(state)
        query_body = {
            "query_type": "prediction",
            "text": "How would I evaluate this career move?",
            "domain_hint": "career",
            "options": ["stay", "move"],
            "perturb": None,
        }

        no_consent_resp = client.post("/twin/query", json=query_body)
        assert no_consent_resp.status_code == 200
        events_before = state.store.export_bundle()["events"]
        assert not any(event["event_type"] == "twin_query" for event in events_before)

        accept_denied = client.post(
            "/twin/accept", json={"prediction_id": no_consent_resp.json()["feedback_token"]}
        )
        assert accept_denied.status_code == 403

        consent_resp = client.post("/consent", json={"data_type": "usage", "granted": True})
        assert consent_resp.status_code == 200

        query_resp = client.post("/twin/query", json=query_body)
        assert query_resp.status_code == 200
        feedback_token = query_resp.json()["feedback_token"]

        accept_resp = client.post("/twin/accept", json={"prediction_id": feedback_token})
        assert accept_resp.status_code == 200

        events_after = state.store.export_bundle()["events"]
        assert any(event["event_type"] == "twin_query" for event in events_after)
        assert any(event["event_type"] == "accepted_prediction" for event in events_after)

        metrics = trust_use_metrics(events_after)
        assert metrics["consult_count"] >= 1.0
        assert metrics["accept_count"] >= 1.0


def test_export_and_delete_leave_only_audit_tombstone(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        state = get_state()
        _seed_state(state)
        export_response = client.get("/export")
        assert export_response.status_code == 200
        exported = export_response.json()
        bundle = json.loads(base64.b64decode(exported["bundle_b64"]).decode("utf-8"))
        assert bundle["traces"]
        assert bundle["params"]
        assert bundle["events"]

        delete_response = client.delete("/model")
        assert delete_response.status_code == 200
        post_delete = state.store.export_bundle()
        assert post_delete["traces"] == []
        assert post_delete["beliefs"] == []
        assert post_delete["params"] == []
        assert post_delete["behavioral_signals"] == []
        assert post_delete["inconsistencies"] == []
        assert len(post_delete["events"]) == 1
        assert post_delete["events"][0]["event_type"] == "audit_tombstone"
