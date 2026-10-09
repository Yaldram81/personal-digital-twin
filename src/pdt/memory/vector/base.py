"""Abstract protocol for the vector store.

Semantic retrieval over traces, beliefs, and signals. The interface is
implementation-agnostic so LanceDB can be swapped without touching consumers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class VectorStore(Protocol):
    """Embedded vector store with versioning for append-only semantics.

    Per MEMORY_STRATEGY.md: "Memory never overwrites truth." LanceDB's
    native versioning makes prior versions retrievable via time-travel,
    so upserts preserve — not overwrite — history.
    """

    def init_schema(self) -> None:
        """Open the store (idempotent)."""
        ...

    def close(self) -> None:
        """Flush and close."""
        ...

    def upsert(
        self,
        text: str,
        vector: list[float],
        metadata: dict[str, str],
        table_name: str = "documents",
    ) -> str:
        """Insert or update a document. Prior version remains in time-travel history.

        Returns the document id.
        """
        ...

    def query(
        self,
        vector: list[float],
        top_k: int = 5,
        table_name: str = "documents",
        filter_expr: str | None = None,
    ) -> list[dict[str, Any]]:
        """Top-K similarity search. Returns list of {text, metadata, score, _id}."""
        ...

    def version_at(
        self,
        doc_id: str,
        at: datetime,
        table_name: str = "documents",
        version: int | None = None,
    ) -> dict[str, Any] | None:
        """Retrieve the version of a document as it existed at a point in time.

        Returns {text, metadata, score, _id} or None if the doc didn't exist then.
        Implementations may accept an explicit store-version override when the
        backend exposes native version numbers.
        """
        ...

    def current_version(self, table_name: str = "documents") -> int:
        """Return the current backend-native version number for a table."""
        ...

    def delete_table(self, table_name: str = "documents") -> None:
        """Drop a table. Used by the full-delete privacy path."""
        ...


__all__ = ["VectorStore"]
