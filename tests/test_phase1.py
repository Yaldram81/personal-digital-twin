from __future__ import annotations

import base64
import json
from hashlib import sha256

from fastapi.testclient import TestClient

from pdt.api.app import create_app, get_state, reset_state
from pdt.core.config import Settings
from pdt.core.crypto import Vault
from pdt.memory.structured import DuckDBStructuredStore


class StubTraceLLM:
    def __init__(self, text: str) -> None:
        self._text = text

    def complete(self, messages, model=None, temperature=0.0, max_tokens=None):  # type: ignore[no-untyped-def]
        class Resp:
            def __init__(self, text: str, model_name: str) -> None:
                self.text = text
                self.model = model_name
                self.provider = "mock"
                self.usage = {}

        return Resp(self._text, model or "stub-trace")

    def embed(self, texts, model=None):  # type: ignore[no-untyped-def]
        return [[0.0] * 16 for _ in texts]


def _client_with_store(tmp_path, llm_text: str) -> TestClient:  # type: ignore[no-untyped-def]
    reset_state()
    data_dir = tmp_path / "data"
    settings = Settings(env="dev", data_dir=data_dir, llm_provider="mock")
    vault = Vault.init(data_dir, "test-passphrase-123", None)
    store = DuckDBStructuredStore(settings.duckdb_path, vault.key)
    store.init_schema()
    app = create_app(settings)
    state = get_state()
    state.attach_store(store)
    state.llm = StubTraceLLM(llm_text)
    state.narration_sessions = {}
    return TestClient(app)


def test_questionnaire_submit_and_model_summary(tmp_path) -> None:  # type: ignore[no-untyped-def]
    llm_payload = json.dumps(
        {
            "domain": "career",
            "options_detected": ["startup", "big_tech"],
            "chosen": "startup",
            "factors": [{"factor": "learning", "weight": "HIGH", "direction": "toward_startup"}],
            "inferred_values": ["self_direction", "achievement"],
        }
    )
    with _client_with_store(tmp_path, llm_payload) as client:
        resp = client.post(
            "/questionnaire/submit",
            json={
                "responses_by_instrument": {
                    "values": {f"v{i}": 4 for i in range(1, 11)},
                    "decision_style": {f"d{i}": 4 for i in range(1, 9)},
                }
            },
        )
        assert resp.status_code == 200

        summary = client.get("/model/summary")
        assert summary.status_code == 200
        data = summary.json()
        assert data["note"].startswith("These are questionnaire-based")
        assert data["value_hierarchy"]["values"]["self_direction"]["source"] == "self_report"
        assert data["decision_style"]["dimensions"]["information_seeking"]["evidence_strength"] == "weak"


def test_questionnaire_submit_fuses_all_named_instruments(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Every blueprint-named instrument in `ingest/questionnaire/instruments.py`
    (not just "values"/"decision_style") must actually seed the model, with
    same-dimension scores across instruments fused rather than dropped.
    """
    llm_payload = json.dumps(
        {
            "domain": "career",
            "options_detected": ["startup", "big_tech"],
            "chosen": "startup",
            "factors": [{"factor": "learning", "weight": "HIGH", "direction": "toward_startup"}],
            "inferred_values": ["self_direction"],
        }
    )
    with _client_with_store(tmp_path, llm_payload) as client:
        resp = client.post(
            "/questionnaire/submit",
            json={
                "responses_by_instrument": {
                    "values": {f"v{i}": 4 for i in range(1, 11)},
                    "decision_style": {f"d{i}": 4 for i in range(1, 9)},
                    "maximization_scale": {"ms1": 5, "ms2": 5, "ms3": 5, "ms4": 1},
                    "bisbas": {"bb1": 4, "bb2": 4, "bb3": 2, "bb4": 2, "bb5": 4},
                    "crt": {"crt1": 1, "crt2": 1, "crt3": 0},
                    "domain_anchors": {f"da{i}": 4 for i in range(1, 7)},
                }
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        # decision_style dims now receive evidence from decision_style +
        # maximization_scale/bisbas/crt/domain_anchors -- still 8 dims total,
        # not double-counted as separate entries.
        assert body["decision_dimensions"] == 8

        params = client.get("/model/parameters").json()["parameters"]
        # risk_tolerance is scored by decision_style, bisbas, AND domain_anchors --
        # fusing three self-report sources should yield more observations than
        # the single-instrument case (n_observations reflects fused evidence).
        assert params["risk_tolerance:global"]["n_observations"] >= 3


def test_narration_submit_stores_trace_and_extraction_event(tmp_path) -> None:  # type: ignore[no-untyped-def]
    llm_payload = json.dumps(
        {
            "domain": "career",
            "options_detected": ["startup", "big_tech"],
            "chosen": "startup",
            "factors": [
                {"factor": "learning", "weight": "HIGH", "direction": "toward_startup"},
                {"factor": "autonomy", "weight": "MEDIUM", "direction": "toward_startup"},
            ],
            "inferred_values": ["self_direction", "achievement"],
        }
    )
    with _client_with_store(tmp_path, llm_payload) as client:
        start = client.post("/narration/start")
        assert start.status_code == 200
        session_id = start.json()["id"]

        submit = client.post(
            f"/narration/{session_id}/submit",
            json={
                "narration": "I had to choose between startup and big_tech. I picked startup for learning and autonomy.",
            },
        )
        assert submit.status_code == 200
        body = submit.json()
        assert body["trace"]["chosen_option"] == "startup"
        assert body["support_flags"] == []

        exported = client.get("/export")
        assert exported.status_code == 200
        export_body = exported.json()
        decoded = json.loads(base64.b64decode(export_body["bundle_b64"]).decode("utf-8"))
        assert len(decoded["traces"]) == 1
        assert len(decoded["extraction_events"]) == 1
        assert decoded["extraction_events"][0]["raw_text"].startswith("I had to choose")
        assert export_body["sha256"] == sha256(base64.b64decode(export_body["bundle_b64"])).hexdigest()
        assert export_body["signature_b64"]


def test_low_support_factor_is_flagged(tmp_path) -> None:  # type: ignore[no-untyped-def]
    llm_payload = json.dumps(
        {
            "domain": "career",
            "options_detected": ["startup", "big_tech"],
            "chosen": "startup",
            "factors": [{"factor": "salary", "weight": "HIGH", "direction": "toward_big_tech"}],
            "inferred_values": ["achievement"],
        }
    )
    with _client_with_store(tmp_path, llm_payload) as client:
        session_id = client.post("/narration/start").json()["id"]
        submit = client.post(
            f"/narration/{session_id}/submit",
            json={"narration": "I chose startup because of learning and autonomy over the long run."},
        )
        assert submit.status_code == 200
        assert "low_support_factor" in submit.json()["support_flags"]


def test_narration_session_is_resumable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    llm_payload = json.dumps(
        {
            "domain": "career",
            "options_detected": ["startup", "big_tech"],
            "chosen": "startup",
            "factors": [{"factor": "learning", "weight": "HIGH", "direction": "toward_startup"}],
            "inferred_values": ["self_direction"],
        }
    )
    with _client_with_store(tmp_path, llm_payload) as client:
        start = client.post("/narration/start").json()
        session_id = start["id"]
        advanced = client.post(
            f"/narration/{session_id}/advance",
            json={"field_name": "options", "value": "startup vs big_tech"},
        )
        assert advanced.status_code == 200
        fetched = client.get(f"/narration/{session_id}")
        assert fetched.status_code == 200
        assert fetched.json()["responses"]["options"] == "startup vs big_tech"


def test_low_signal_single_option_is_accepted_and_flagged(tmp_path) -> None:  # type: ignore[no-untyped-def]
    llm_payload = json.dumps(
        {
            "domain": "career",
            "options_detected": ["first_option"],
            "chosen": "first_option",
            "factors": [{"factor": "picked the first one", "weight": "LOW", "direction": "toward_first_option"}],
            "inferred_values": [],
        }
    )
    with _client_with_store(tmp_path, llm_payload) as client:
        session_id = client.post("/narration/start").json()["id"]
        submit = client.post(
            f"/narration/{session_id}/submit",
            json={"narration": "I just picked the first one."},
        )
        assert submit.status_code == 200
        assert submit.json()["trace"]["low_signal"] is True


def test_delete_model_wipes_exported_data(tmp_path) -> None:  # type: ignore[no-untyped-def]
    llm_payload = json.dumps(
        {
            "domain": "career",
            "options_detected": ["startup", "big_tech"],
            "chosen": "startup",
            "factors": [{"factor": "learning", "weight": "HIGH", "direction": "toward_startup"}],
            "inferred_values": ["self_direction"],
        }
    )
    with _client_with_store(tmp_path, llm_payload) as client:
        client.post(
            "/questionnaire/submit",
            json={
                "responses_by_instrument": {
                    "values": {f"v{i}": 3 for i in range(1, 11)},
                    "decision_style": {f"d{i}": 3 for i in range(1, 9)},
                }
            },
        )
        session_id = client.post("/narration/start").json()["id"]
        client.post(
            f"/narration/{session_id}/submit",
            json={"narration": "I picked startup over big_tech for learning."},
        )
        deleted = client.delete("/model")
        assert deleted.status_code == 200
        exported = client.get("/export").json()
        decoded = json.loads(base64.b64decode(exported["bundle_b64"]).decode("utf-8"))
        assert decoded["traces"] == []
        assert decoded["params"] == []
