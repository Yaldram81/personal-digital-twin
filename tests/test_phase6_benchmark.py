from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from pdt.api.app import create_app, get_state, reset_state
from pdt.core.config import Settings
from pdt.core.crypto import Vault
from pdt.engine.pipeline import TwinQuery
from pdt.eval.benchmark import build_phase6_benchmark_report
from pdt.eval.temporal import temporal_tracking_report
from pdt.memory.structured import DuckDBStructuredStore


class StubBenchmarkLLM:
    def complete(self, messages, model=None, temperature=0.0, max_tokens=None):  # type: ignore[no-untyped-def]
        class Resp:
            text = "benchmark-llm"
            model = "benchmark"
            provider = "mock"
            usage = {}

        return Resp()

    def embed(self, texts, model=None):  # type: ignore[no-untyped-def]
        return [[0.0] * 16 for _ in texts]


def _client(tmp_path: Path) -> TestClient:
    reset_state()
    data_dir = tmp_path / "data"
    settings = Settings(env="dev", data_dir=data_dir, llm_provider="mock", embedding_model="mock-embed")
    vault = Vault.init(data_dir, "benchmark-passphrase", None)
    store = DuckDBStructuredStore(settings.duckdb_path, vault.key)
    store.init_schema()
    app = create_app(settings)
    state = get_state()
    state.attach_store(store)
    state.llm = StubBenchmarkLLM()
    return TestClient(app)


def _seed_state(state) -> None:  # type: ignore[no-untyped-def]
    traces = [
        {
            "id": "trace-bench-1",
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
            "id": "trace-bench-2",
            "domain": "career",
            "context": "manager decision",
            "options": ["manager_a", "manager_b"],
            "chosen_option": "manager_a",
            "factors_cited": [{"factor": "team quality"}],
            "stated_reasons": "team quality mattered most",
            "implicit_beliefs": ["team quality matters"],
            "timestamp": "2025-02-10",
        },
    ]
    for trace in traces:
        state.store.insert_trace(json.dumps(trace))
    state.store.insert_param("self_direction", 0.81, 0.08, 8, "inferred", domain="career")
    state.store.insert_param("risk_tolerance", 0.70, 0.09, 6, "behavioral", domain="career")


def test_phase6_benchmark_report_exposes_threshold_statuses(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        _seed_state(state)
        queries = [
            TwinQuery("prediction", "How would I evaluate this career move?"),
            TwinQuery("priority", "What would I care about most?"),
            TwinQuery("reaction", "How would I react if leadership changed?"),
        ]
        report = build_phase6_benchmark_report(state, queries)
        assert report.consistency_score is not None
        assert report.p95_latency_seconds is not None
        assert len(report.threshold_statuses) >= 4
        metrics = {status.metric: status for status in report.threshold_statuses}
        assert "memory_recall_accuracy" in metrics
        assert "response_consistency_score" in metrics
        assert "p95_latency_seconds" in metrics
        assert "recognition_score" in metrics


def test_eval_benchmark_endpoint_returns_gap_or_pass_report(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        state = get_state()
        _seed_state(state)
        response = client.get("/eval/benchmark")
        assert response.status_code == 200
        payload = response.json()
        assert "holdout" in payload
        assert "consistency_score" in payload
        assert "p95_latency_seconds" in payload
        assert "temporal_tracking" in payload
        assert "threshold_statuses" in payload
        assert payload["threshold_statuses"]
        metrics = {status["metric"] for status in payload["threshold_statuses"]}
        assert "temporal_tracking_improves" in metrics


def test_temporal_tracking_report_runs_over_longitudinal_fixture(tmp_path: Path) -> None:
    with _client(tmp_path):
        state = get_state()
        _seed_state(state)
        # Add two more chronologically later traces so the early/late split
        # (PHASE_6.md task 3) has a genuine held-out late window to evaluate.
        later_traces = [
            {
                "id": "trace-bench-3",
                "domain": "career",
                "context": "promotion timing",
                "options": ["wait", "ask now"],
                "chosen_option": "ask now",
                "factors_cited": [{"factor": "team quality"}],
                "stated_reasons": "team quality mattered most",
                "implicit_beliefs": ["team quality matters"],
                "timestamp": "2025-03-10",
            },
            {
                "id": "trace-bench-4",
                "domain": "career",
                "context": "relocation",
                "options": ["move", "stay"],
                "chosen_option": "move",
                "factors_cited": [{"factor": "learning"}],
                "stated_reasons": "learning and team quality dominated",
                "implicit_beliefs": ["growth over salary"],
                "timestamp": "2025-04-10",
            },
        ]
        for trace in later_traces:
            state.store.insert_trace(json.dumps(trace))

        report = temporal_tracking_report(state)
        assert report.late_n > 0
        assert 0.0 <= report.early_accuracy <= 1.0
        assert 0.0 <= report.late_accuracy <= 1.0
