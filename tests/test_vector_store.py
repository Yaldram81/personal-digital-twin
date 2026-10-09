"""Tests for the LanceDB vector store: upsert, query, versioning."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdt.memory.vector import LanceVectorStore


@pytest.fixture
def vstore(tmp_data_dir: Path) -> LanceVectorStore:
    store = LanceVectorStore(tmp_data_dir / "vectors", embedding_model="mock-embed")
    store.init_schema()
    yield store
    store.close()


def _near(a: list[float], b: list[float], tol: float = 0.01) -> bool:
    return all(abs(x - y) < tol for x, y in zip(a, b, strict=True))


class TestVectorStore:
    def test_upsert_and_query_returns_nearest(self, vstore: LanceVectorStore) -> None:
        """Exit criterion: top-1 query returns the expected nearest doc."""
        docs = [
            ("apples are sweet", [1.0, 0.0, 0.0, 0.0]),
            ("oranges are citrus", [0.0, 1.0, 0.0, 0.0]),
            ("bananas are yellow", [0.0, 0.0, 1.0, 0.0]),
            ("grapes make wine", [0.0, 0.0, 0.0, 1.0]),
            ("kiwis are fuzzy", [0.9, 0.1, 0.0, 0.0]),
        ]
        for text, vec in docs:
            vstore.upsert(text, vec, {"type": "fruit"}, table_name="fruits")

        # Query closest to apples → should return apples (and kiwis).
        results = vstore.query([1.0, 0.0, 0.0, 0.0], top_k=1, table_name="fruits")
        assert len(results) == 1
        assert "apples" in results[0]["text"]

    def test_query_empty_table_returns_empty(self, vstore: LanceVectorStore) -> None:
        results = vstore.query([1.0, 0.0], top_k=5, table_name="nonexistent")
        assert results == []

    def test_upsert_returns_id(self, vstore: LanceVectorStore) -> None:
        doc_id = vstore.upsert("test text", [1.0, 0.0], {"k": "v"})
        assert isinstance(doc_id, str)
        assert len(doc_id) > 0

    def test_records_embedding_model(self, vstore: LanceVectorStore) -> None:
        """Exit criterion: every row records its embedding model (drift guard)."""
        vstore.upsert("text", [1.0, 0.0], {"k": "v"}, table_name="t1")
        results = vstore.query([1.0, 0.0], top_k=1, table_name="t1")
        assert results[0]["embedding_model"] == "mock-embed"

    def test_multiple_tables(self, vstore: LanceVectorStore) -> None:
        vstore.upsert("trace A", [1.0, 0.0], {}, table_name="traces")
        vstore.upsert("belief B", [0.0, 1.0], {}, table_name="beliefs")
        trace_results = vstore.query([1.0, 0.0], top_k=1, table_name="traces")
        belief_results = vstore.query([1.0, 0.0], top_k=1, table_name="beliefs")
        assert "trace A" in trace_results[0]["text"]
        assert "belief B" in belief_results[0]["text"]

    def test_delete_table(self, vstore: LanceVectorStore) -> None:
        vstore.upsert("text", [1.0, 0.0], {}, table_name="to_delete")
        vstore.delete_table("to_delete")
        assert vstore.query([1.0, 0.0], top_k=1, table_name="to_delete") == []
