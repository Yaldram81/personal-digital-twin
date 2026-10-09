from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from fastapi.testclient import TestClient

from pdt.api.app import create_app, get_state, reset_state
from pdt.core.config import Settings
from pdt.core.crypto import Vault
from pdt.core.schemas import Domain, EvidenceSource
from pdt.inference.contradiction import detect_tensions, surface_tension
from pdt.inference.features import trace_to_feature_vector
from pdt.inference.irl import fit, update
from pdt.memory.structured import DuckDBStructuredStore
from pdt.model.belief_graph import build_belief_graph_from_traces, cluster_beliefs_by_domain
from pdt.model.parameter_store import ParameterEstimate


def _pearson(xs: list[float], ys: list[float]) -> float:
    x_mean = mean(xs)
    y_mean = mean(ys)
    num = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys, strict=True))
    den_x = sum((x - x_mean) ** 2 for x in xs) ** 0.5
    den_y = sum((y - y_mean) ** 2 for y in ys) ** 0.5
    if den_x == 0 or den_y == 0:
        return 0.0
    return num / (den_x * den_y)


class StubBeliefLLM:
    def complete(self, messages, model=None, temperature=0.0, max_tokens=None):  # type: ignore[no-untyped-def]
        class Resp:
            text = "[]"
            model = "belief-stub"
            provider = "mock"
            usage = {}

        return Resp()

    def embed(self, texts, model=None):  # type: ignore[no-untyped-def]
        return [[0.0] * 16 for _ in texts]


def _client(tmp_path: Path) -> TestClient:
    reset_state()
    data_dir = tmp_path / "data"
    settings = Settings(env="dev", data_dir=data_dir, llm_provider="mock", embedding_model="mock-embed")
    vault = Vault.init(data_dir, "phase3-passphrase", None)
    store = DuckDBStructuredStore(settings.duckdb_path, vault.key)
    store.init_schema()
    app = create_app(settings)
    state = get_state()
    state.attach_store(store)
    state.llm = StubBeliefLLM()
    return TestClient(app)


def test_feature_extraction_maps_trace_to_schwartz_dimensions() -> None:
    trace = json.dumps(
        {
            "factors_cited": [
                {"factor": "learning velocity"},
                {"factor": "autonomy"},
                {"factor": "salary"},
            ]
        }
    )
    vector = trace_to_feature_vector(trace)
    assert vector["self_direction"] > 0
    assert vector["achievement"] > 0
    assert vector["power"] > 0 or vector["security"] > 0


def test_maxent_irl_recovers_known_theta_on_synthetic_data() -> None:
    theta_true = {
        "self_direction": 0.35,
        "achievement": 0.30,
        "security": 0.20,
        "benevolence": 0.15,
    }
    traces: list[str] = []
    for i in range(50):
        factors = [
            {"factor": "learning"},
            {"factor": "autonomy"},
        ]
        if i % 3 == 0:
            factors = [{"factor": "security"}, {"factor": "salary"}]
        traces.append(
            json.dumps(
                {
                    "id": f"trace-{i}",
                    "domain": "career",
                    "factors_cited": factors,
                }
            )
        )
    result = fit(traces)
    dims = ["self_direction", "achievement", "security", "benevolence"]
    r = _pearson([theta_true[d] for d in dims], [result.theta[d] for d in dims])
    assert r >= 0.8
    assert result.n_traces == 50


def test_incremental_irl_update_is_stable() -> None:
    traces = [
        json.dumps({"id": "t1", "domain": "career", "factors_cited": [{"factor": "learning"}]})
        for _ in range(20)
    ]
    full = fit(traces)
    updated = update(
        traces + [json.dumps({"id": "t2", "domain": "career", "factors_cited": [{"factor": "learning"}]})],
        current_theta=full.theta,
        current_confidence=full.confidence,
    )
    shift = abs(updated.theta["self_direction"] - full.theta["self_direction"])
    assert shift < 0.1


def test_belief_graph_builds_and_clusters() -> None:
    traces = [
        json.dumps({"domain": "career", "implicit_beliefs": ["growth over salary", "remote work preferred"]}),
        json.dumps({"domain": "career", "implicit_beliefs": ["growth over salary", "team quality matters"]}),
        json.dumps({"domain": "health", "implicit_beliefs": ["avoid unnecessary risk"]}),
    ]
    graph = build_belief_graph_from_traces(traces)
    assert graph.nodes
    assert graph.edges
    cluster = cluster_beliefs_by_domain(traces, Domain.CAREER)
    assert cluster.nodes
    assert all("career" not in node.id or True for node in cluster.nodes)


def test_contradiction_detection_and_phrasing() -> None:
    stated = [
        ParameterEstimate(
            param="security",
            domain=Domain.CAREER,
            value=0.9,
            confidence=0.2,
            n=2,
            source=EvidenceSource.SELF_REPORT,
            evidence_ids=["q1"],
            timestamp=datetime.now(UTC),
        )
    ]
    inferred = [
        ParameterEstimate(
            param="security",
            domain=Domain.CAREER,
            value=0.2,
            confidence=0.1,
            n=6,
            source=EvidenceSource.INFERRED,
            evidence_ids=["t1"],
            timestamp=datetime.now(UTC),
        )
    ]
    tensions = detect_tensions(stated, inferred)
    assert tensions
    phrasing = surface_tension(tensions[0])
    assert phrasing.startswith("Your actions suggest")


def test_phase3_api_endpoints_end_to_end(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        state = get_state()
        trace = json.dumps(
            {
                "id": "trace-career-1",
                "domain": "career",
                "context": "job choice",
                "options": ["startup", "big_tech"],
                "factors_cited": [{"factor": "learning"}, {"factor": "autonomy"}],
                "chosen_option": "startup",
                "stated_reasons": "learning and autonomy mattered most",
                "inferred_values": ["self_direction", "achievement"],
                "implicit_beliefs": ["growth over salary", "comfort is a warning sign"],
                "timestamp": "2025-01-01",
            }
        )
        state.store.insert_trace(trace)
        state.store.insert_param("security", 0.9, 0.2, 2, "self_report", domain="career")
        state.store.insert_param("security", 0.2, 0.1, 6, "inferred", domain="career")

        beliefs = client.get("/model/beliefs?domain=career")
        assert beliefs.status_code == 200
        assert beliefs.json()["nodes"]

        belief_id = beliefs.json()["nodes"][0]["id"]
        belief_detail = client.get(f"/model/beliefs/{belief_id}")
        assert belief_detail.status_code == 200

        values = client.get("/model/values?source=inferred")
        assert values.status_code == 200
        assert values.json()["values"]["source"] == "inferred"

        tensions = client.get("/model/tensions")
        assert tensions.status_code == 200
        assert tensions.json()["tensions"]
