"""Focused checks for Phase 0 exit criteria not covered elsewhere."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from pdt.core.crypto import KDFParams, Vault
from pdt.core.llm import PromptRegistry
from pdt.memory.structured import DuckDBStructuredStore
from pdt.memory.vector import LanceVectorStore


def _trace_json() -> str:
    return json.dumps(
        {
            "id": "trace-phase0-001",
            "domain": "career",
            "context": "evaluating job offer",
            "options": ["startup", "big_tech"],
            "factors_cited": [],
            "chosen_option": "startup",
            "stated_reasons": "learning velocity",
        }
    )


def test_structured_store_survives_restart_and_wrong_passphrase_fails(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    params = KDFParams(memory_kib=8192, time_cost=1, parallelism=1)

    vault = Vault.init(data_dir, "correct-passphrase", params)
    store = DuckDBStructuredStore(data_dir / "pdt.duckdb", vault.key)
    store.init_schema()
    row_id = store.insert_trace(_trace_json())
    store.close()

    reopened_vault = Vault.unlock(data_dir, "correct-passphrase", params)
    reopened_store = DuckDBStructuredStore(data_dir / "pdt.duckdb", reopened_vault.key)
    assert json.loads(reopened_store.get_trace(row_id) or "{}")["chosen_option"] == "startup"
    reopened_store.close()

    wrong_vault = Vault.unlock(data_dir, "wrong-passphrase", params)
    wrong_store = DuckDBStructuredStore(data_dir / "pdt.duckdb", wrong_vault.key)
    try:
        wrong_store.get_trace(row_id)
        raise AssertionError("expected authenticated decryption to fail")
    except ValueError as exc:
        assert "decryption failed" in str(exc)
    finally:
        wrong_store.close()


def test_append_only_update_guard(tmp_path: Path) -> None:
    params = KDFParams(memory_kib=8192, time_cost=1, parallelism=1)
    vault = Vault.init(tmp_path / "data-guard", "correct-passphrase", params)
    store = DuckDBStructuredStore(tmp_path / "data-guard" / "pdt.duckdb", vault.key)
    store.init_schema()
    store.insert_param("risk_tolerance", 0.51, 0.1, 5, "self_report")
    with pytest.raises(ValueError, match="append-only guard"):
        store.execute_sql("UPDATE model_params SET value = 0.99")
    store.close()


def test_vector_store_time_travel_history(tmp_path: Path) -> None:
    vstore = LanceVectorStore(tmp_path / "vectors", embedding_model="mock-embed")
    doc_id = vstore.upsert("original text", [1.0, 0.0], {"topic": "career"}, table_name="docs")
    first_version = vstore.current_version("docs")
    first_snapshot = vstore.version_at(doc_id, at=datetime.now(UTC), table_name="docs", version=first_version)
    assert first_snapshot is not None
    assert first_snapshot["text"] == "original text"

    vstore.upsert(
        "updated text",
        [1.0, 0.0],
        {"topic": "career", "_id": doc_id},
        table_name="docs",
    )
    latest = vstore.query([1.0, 0.0], top_k=1, table_name="docs")
    assert latest[0]["text"] == "updated text"

    historical = vstore.version_at(doc_id, at=datetime.now(UTC), table_name="docs", version=first_version)
    assert historical is not None
    assert historical["text"] == "original text"


def test_prompt_manifest_versions_exist() -> None:
    registry = PromptRegistry()
    samples = {
        "reasoning_trace_extraction": {"narration": "x"},
        "conversation_mining": {"conversation": "x"},
        "simulated_reasoning": {
            "value_hierarchy": "x",
            "decision_style": "x",
            "domain_beliefs": "x",
            "historical_traces": "x",
            "domain": "career",
            "characteristic_patterns": "x",
            "options": "x",
        },
        "explanation": {
            "simulation_output": "x",
            "user_vocabulary": "x",
            "trace_citations": "x",
        },
        "blindspot_detection": {
            "domain": "career",
            "typical_factors": "x",
            "user_factors": "x",
        },
    }
    for name, variables in samples.items():
        for version in registry.versions(name):
            assert registry.render(name, version=version, **variables)
