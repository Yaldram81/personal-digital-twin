from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from pdt.api.app import create_app, get_state, reset_state
from pdt.core.config import Settings
from pdt.core.crypto import Vault
from pdt.core.schemas import EvidenceSource, EvidenceStrength, ScoredScalar
from pdt.extraction.conversation_miner import mine_conversation
from pdt.memory.structured import DuckDBStructuredStore
from pdt.model.confidence import compute_confidence_interval
from pdt.model.contextual_values import learn_contextual_values_from_traces
from pdt.model.fusion import fuse_scored_scalars


class StubConversationLLM:
    def __init__(self, payload: list[dict[str, object]]) -> None:
        self._payload = payload

    def complete(self, messages, model=None, temperature=0.0, max_tokens=None):  # type: ignore[no-untyped-def]
        class Resp:
            def __init__(self, text: str) -> None:
                self.text = text
                self.model = "stub-conversation"
                self.provider = "mock"
                self.usage = {}

        return Resp(json.dumps(self._payload))

    def embed(self, texts, model=None):  # type: ignore[no-untyped-def]
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


def _client_with_phase2_state(tmp_path: Path, payload: list[dict[str, object]]) -> TestClient:
    reset_state()
    data_dir = tmp_path / "data"
    settings = Settings(env="dev", data_dir=data_dir, llm_provider="mock", embedding_model="mock-embed")
    vault = Vault.init(data_dir, "test-passphrase-123", None)
    store = DuckDBStructuredStore(settings.duckdb_path, vault.key)
    store.init_schema()
    app = create_app(settings)
    state = get_state()
    state.attach_store(store)
    state.llm = StubConversationLLM(payload)
    state.narration_sessions = {}
    return TestClient(app)


def test_confidence_shrinks_with_more_consistent_evidence() -> None:
    now = datetime.now(UTC)
    small = compute_confidence_interval([0.6, 0.6], [1.0, 1.0], [now, now])
    large = compute_confidence_interval([0.6, 0.6, 0.6, 0.6], [1.0, 1.0, 1.0, 1.0], [now, now, now, now])
    assert large.half_width < small.half_width


def test_confidence_widens_with_variance_and_staleness() -> None:
    now = datetime.now(UTC)
    low_var = compute_confidence_interval([0.6, 0.6], [1.0, 1.0], [now, now])
    high_var = compute_confidence_interval([0.2, 0.9], [1.0, 1.0], [now, now])
    stale = compute_confidence_interval([0.6, 0.6], [1.0, 1.0], [now - timedelta(days=500), now - timedelta(days=500)], now=now)
    assert high_var.half_width > low_var.half_width
    assert stale.half_width > low_var.half_width


def test_fusion_moves_posterior_without_thrashing() -> None:
    prior = ScoredScalar(value=0.2, confidence=0.3, n_observations=1, last_updated=datetime.now(UTC).date(), source=EvidenceSource.SELF_REPORT, evidence_strength=EvidenceStrength.WEAK)
    behavioral = ScoredScalar(value=0.8, confidence=0.1, n_observations=8, last_updated=datetime.now(UTC).date(), source=EvidenceSource.BEHAVIORAL, evidence_strength=EvidenceStrength.MODERATE)
    fused = fuse_scored_scalars([prior, behavioral])
    assert fused.value > prior.value
    weak_contradiction = ScoredScalar(value=0.1, confidence=0.3, n_observations=1, last_updated=datetime.now(UTC).date(), source=EvidenceSource.BEHAVIORAL, evidence_strength=EvidenceStrength.WEAK)
    fused2 = fuse_scored_scalars([prior, weak_contradiction])
    assert abs(fused2.value - prior.value) < 0.2


def test_conversation_mining_emits_traceable_signals() -> None:
    payload = [
        {
            "category": "risk_language",
            "domain": "career",
            "direction": "increase",
            "magnitude": 0.4,
            "weight": 0.2,
            "lexical_support": "bolder",
        },
        {
            "category": "abstract_framing",
            "domain": "career",
            "direction": "increase",
            "magnitude": 0.3,
            "weight": 0.1,
            "lexical_support": "career",
        },
    ]
    llm = StubConversationLLM(payload)
    messages = [{"role": "user", "content": "I usually prefer the bolder option in career moves."}]
    signals = mine_conversation(messages, llm)
    assert len(signals) >= 2
    assert signals[0].weight <= 0.3
    assert all(signal.evidence_ref for signal in signals)


def test_model_parameters_diff_and_evidence_endpoints(tmp_path: Path) -> None:
    payload = [
        {
            "param": "risk_tolerance",
            "domain": "career",
            "direction": "increase",
            "magnitude": 0.5,
            "weight": 0.2,
            "evidence_ref": "risk_tolerance",
        }
    ]
    with _client_with_phase2_state(tmp_path, payload) as client:
        client.post(
            "/questionnaire/submit",
            json={
                "responses_by_instrument": {
                    "values": {f"v{i}": 3 for i in range(1, 11)},
                    "decision_style": {f"d{i}": 3 for i in range(1, 9)},
                }
            },
        )
        mined = client.post(
            "/conversation/mine",
            json={"messages": [{"role": "user", "content": "My risk_tolerance has grown in career decisions."}]},
        )
        assert mined.status_code == 200
        params = client.get("/model/parameters?domain=career")
        assert params.status_code == 200
        assert params.json()["parameters"]
        diff = client.get("/model/diff")
        assert diff.status_code == 200
        assert any(item["param"] == "risk_tolerance" for item in diff.json()["diffs"])
        evidence = client.get("/evidence/risk_tolerance")
        assert evidence.status_code == 200
        assert evidence.json()["evidence"]


def test_contextual_values_learn_per_domain() -> None:
    traces = [
        json.dumps({"domain": "career", "inferred_values": ["self_direction", "achievement"]}),
        json.dumps({"domain": "health", "inferred_values": ["security"]}),
    ]
    learned = learn_contextual_values_from_traces(traces)
    assert learned
    assert learned[next(iter(learned))]
    assert learned.get(__import__("pdt.core.schemas", fromlist=["Domain"]).Domain.CAREER) is not None
    assert learned.get(__import__("pdt.core.schemas", fromlist=["Domain"]).Domain.HEALTH) is not None


def test_domain_specific_params_and_retrieval_budget(tmp_path: Path) -> None:
    payload = []
    with _client_with_phase2_state(tmp_path, payload) as client:
        state = get_state()
        state.store.insert_param("risk_tolerance", 0.8, 0.1, 4, "behavioral", domain="career")
        state.store.insert_param("risk_tolerance", 0.2, 0.1, 4, "behavioral", domain="health")
        state.store.insert_trace(json.dumps({"id": "t1", "domain": "career", "context": "career decision", "options": ["a", "b"], "factors_cited": [], "chosen_option": "a", "stated_reasons": "career growth and autonomy", "timestamp": "2025-01-01"}))
        vector_store = state.get_vector_store()
        vector_store.upsert("career growth and autonomy", [1.0, 0.0, 0.0, 0.0], {"domain": "career"}, table_name="traces")
        career = client.get("/model/parameters?domain=career").json()["parameters"]
        health = client.get("/model/parameters?domain=health").json()["parameters"]
        assert career != health
        retrieval = client.post("/retrieve", json={"query": "career growth", "domain": "career", "top_k": 5, "token_budget": 3})
        assert retrieval.status_code == 200
        total_tokens = sum(len(item["text"].split()) for item in retrieval.json()["items"])
        assert total_tokens <= 3


def test_retrieval_precision_at_5_fixture(tmp_path: Path) -> None:
    payload = []
    with _client_with_phase2_state(tmp_path, payload) as client:
        state = get_state()
        fixture_path = Path("tests/fixtures/retrieval/retrieval_fixture.json")
        rows = json.loads(fixture_path.read_text(encoding="utf-8"))
        for row in rows:
            state.store.insert_trace(
                json.dumps(
                    {
                        "id": row["id"],
                        "domain": row["domain"],
                        "context": row["text"],
                        "options": ["a", "b"],
                        "factors_cited": [],
                        "chosen_option": "a",
                        "stated_reasons": row["text"],
                        "timestamp": "2025-01-01",
                        "inferred_values": [],
                    }
                )
            )
            state.get_vector_store().upsert(
                row["text"],
                [1.0, 0.0, 0.0, 0.0],
                {"domain": row["domain"], "_id": row["id"]},
                table_name="traces",
            )

        query = "career growth"
        response = client.post(
            "/retrieve",
            json={"query": query, "domain": "career", "top_k": 5, "token_budget": 200},
        )
        assert response.status_code == 200
        items = response.json()["items"]
        relevant = [item for item in items if "career" in item["text"].lower() or "growth" in item["text"].lower()]
        precision_at_5 = len(relevant) / max(1, min(5, len(items)))
        assert precision_at_5 >= 0.6
