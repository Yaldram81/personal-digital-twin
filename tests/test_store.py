"""Tests for the DuckDB structured store: append-only, encrypted round-trips."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pdt.memory.structured import DuckDBStructuredStore


@pytest.fixture
def store(tmp_data_dir: Path, vault) -> DuckDBStructuredStore:
    """A DuckDB store backed by the test vault's key."""
    db_path = tmp_data_dir / "test.duckdb"
    s = DuckDBStructuredStore(db_path, vault.key)
    s.init_schema()
    yield s
    s.close()


def _sample_trace_json(domain: str = "career") -> str:
    return json.dumps(
        {
            "id": "trace-001",
            "domain": domain,
            "context": "evaluating job offer",
            "options": ["startup", "big_tech"],
            "factors_cited": [],
            "chosen_option": "startup",
            "stated_reasons": "learning velocity",
            "inferred_values": ["self_direction", "achievement"],
        }
    )


class TestStoreLifecycle:
    def test_init_schema_creates_tables(self, store: DuckDBStructuredStore) -> None:
        # If schema initialized, trace insert should work (tested below).
        row_id = store.insert_trace(_sample_trace_json())
        assert isinstance(row_id, str)


class TestTraceRoundTrip:
    def test_insert_and_get(self, store: DuckDBStructuredStore) -> None:
        row_id = store.insert_trace(_sample_trace_json())
        retrieved = store.get_trace(row_id)
        assert retrieved is not None
        assert json.loads(retrieved)["chosen_option"] == "startup"

    def test_get_nonexistent_returns_none(self, store: DuckDBStructuredStore) -> None:
        assert store.get_trace("does-not-exist") is None

    def test_list_traces(self, store: DuckDBStructuredStore) -> None:
        store.insert_trace(_sample_trace_json("career"))
        store.insert_trace(_sample_trace_json("financial"))
        all_traces = store.list_traces()
        assert len(all_traces) == 2
        career = store.list_traces(domain="career")
        assert len(career) == 1

    def test_stored_data_is_encrypted_on_disk(
        self, store: DuckDBStructuredStore, tmp_data_dir: Path
    ) -> None:
        """Exit criterion: traces are encrypted at rest — not plaintext on disk."""
        store.insert_trace(_sample_trace_json())
        store.close()
        # Read the raw DuckDB file; the sensitive content must not appear.
        raw = (tmp_data_dir / "test.duckdb").read_bytes()
        assert b"learning velocity" not in raw
        assert b"chosen_option" not in raw


class TestParamAppendOnly:
    """Exit criterion: append-only — INSERTs accumulate, no UPDATE."""

    def test_history_accumulates(self, store: DuckDBStructuredStore) -> None:
        store.insert_param("risk_tolerance", 0.51, 0.1, 5, "self_report")
        store.insert_param("risk_tolerance", 0.61, 0.08, 12, "behavioral")
        store.insert_param("risk_tolerance", 0.68, 0.05, 20, "inferred")

        history = store.param_history("risk_tolerance")
        assert len(history) == 3
        # Ordered ascending by time.
        assert history[0]["value"] == 0.51
        assert history[-1]["value"] == 0.68

    def test_latest_is_most_recent(self, store: DuckDBStructuredStore) -> None:
        store.insert_param("risk_tolerance", 0.51, 0.1, 5, "self_report")
        store.insert_param("risk_tolerance", 0.68, 0.05, 20, "inferred")
        latest = store.get_latest_param("risk_tolerance")
        assert latest is not None
        assert latest["value"] == 0.68
        assert latest["source"] == "inferred"

    def test_domain_specific_params(self, store: DuckDBStructuredStore) -> None:
        store.insert_param("ambiguity_tolerance", 0.6, 0.1, 5, "self_report", domain="career")
        store.insert_param("ambiguity_tolerance", 0.3, 0.1, 5, "self_report", domain="health")
        career = store.get_latest_param("ambiguity_tolerance", domain="career")
        health = store.get_latest_param("ambiguity_tolerance", domain="health")
        assert career["value"] == 0.6
        assert health["value"] == 0.3

    def test_latest_nonexistent_returns_none(self, store: DuckDBStructuredStore) -> None:
        assert store.get_latest_param("nonexistent") is None


class TestBeliefsAndEdges:
    def test_insert_and_list_beliefs(self, store: DuckDBStructuredStore) -> None:
        belief = json.dumps({"id": "b1", "domain": "career", "confidence": 0.8})
        store.insert_belief(belief)
        beliefs = store.list_beliefs()
        assert len(beliefs) == 1

    def test_insert_edge(self, store: DuckDBStructuredStore) -> None:
        store.insert_edge("b1", "b2", "supports", 0.5)
        # Edge is structural data; just verify it doesn't error.

    def test_belief_payload_encrypted(
        self, store: DuckDBStructuredStore, tmp_data_dir: Path
    ) -> None:
        store.insert_belief(json.dumps({"id": "b1", "domain": "career", "secret": "hidden"}))
        store.close()
        raw = (tmp_data_dir / "test.duckdb").read_bytes()
        assert b"hidden" not in raw


class TestDriftLog:
    def test_insert_and_history(self, store: DuckDBStructuredStore) -> None:
        store.insert_drift_entry("risk_tolerance", 0.51, "2024-01-01")
        store.insert_drift_entry("risk_tolerance", 0.68, "2024-09-01")
        history = store.drift_history("risk_tolerance")
        assert len(history) == 2
        assert history[0]["value"] == 0.51
        assert history[1]["value"] == 0.68


class TestEvents:
    def test_insert_event(self, store: DuckDBStructuredStore) -> None:
        row_id = store.insert_event("test_event", json.dumps({"key": "value"}))
        assert isinstance(row_id, str)


class TestDeleteEverything:
    def test_delete_removes_all_data(self, store: DuckDBStructuredStore) -> None:
        store.insert_trace(_sample_trace_json())
        store.insert_param("risk_tolerance", 0.5, 0.1, 1, "self_report")
        store.delete_everything()
        # After delete, history should be empty.
        assert store.param_history("risk_tolerance") == []
        assert store.list_traces() == []
