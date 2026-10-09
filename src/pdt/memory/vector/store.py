"""LanceDB-backed vector store with native versioning.

LanceDB is embedded (in-process), columnar, and versions every write, so
prior states remain retrievable — this is the "memory never overwrites
truth" property (MEMORY_STRATEGY.md) made structural.

Each row records its ``embedding_model`` (model id) to guard against
embedding drift (FAILURE_MODES.md §System): if the embedding model ever
changes, stored vectors are detectably stale and can be re-indexed.

Schema notes (validated against lancedb 0.33):
- ``_id`` is a top-level column so it can serve as the merge-insert key.
- ``metadata_json`` stores arbitrary string→string metadata as JSON —
  simpler and more portable across lancedb versions than a map column.
- Vector dimension is fixed at table creation (first upsert wins).
"""

from __future__ import annotations

import json
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

_SCHEMA_BASE_FIELDS = [
    pa.field("_id", pa.string()),
    pa.field("text", pa.string()),
    pa.field("metadata_json", pa.string()),
    pa.field("embedding_model", pa.string()),
]


class LanceVectorStore:
    """LanceDB-backed vector store satisfying the VectorStore Protocol.

    Args:
        db_path: Directory where LanceDB stores its data.
        embedding_model: The model id (e.g. ``text-embedding-3-small``)
            recorded on every row so embedding drift is detectable.
    """

    def __init__(self, db_path: Path, embedding_model: str = "unknown") -> None:
        self._db_path = db_path
        self._embedding_model = embedding_model
        db_path.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(db_path))

    def init_schema(self) -> None:
        """LanceDB creates tables lazily on first upsert; no-op here."""
        pass

    def close(self) -> None:
        """Embedded mode has no explicit close; no-op."""
        pass

    # -- helpers ------------------------------------------------------------

    def _table_exists(self, table_name: str) -> bool:
        try:
            self._db.open_table(table_name)
            return True
        except (FileNotFoundError, ValueError):
            return False

    def _get_or_create_table(self, table_name: str, vector_dim: int) -> Any:
        if self._table_exists(table_name):
            return self._db.open_table(table_name)
        schema = pa.schema(
            [pa.field("vector", pa.list_(pa.float32(), vector_dim)), *_SCHEMA_BASE_FIELDS]
        )
        return self._db.create_table(table_name, schema=schema)

    # -- VectorStore implementation ------------------------------------------

    def upsert(
        self,
        text: str,
        vector: list[float],
        metadata: dict[str, str],
        table_name: str = "documents",
    ) -> str:
        doc_id = metadata.get("_id", str(uuid.uuid4()))
        meta = {**metadata, "_id": doc_id}
        table = self._get_or_create_table(table_name, len(vector))
        new_data = pa.table(
            {
                "vector": [vector],
                "_id": [doc_id],
                "text": [text],
                "metadata_json": [json.dumps(meta)],
                "embedding_model": [self._embedding_model],
            }
        )
        (
            table.merge_insert("_id")
            .when_matched_update_all()
            .when_not_matched_insert_all()
            .execute(new_data)
        )
        return doc_id

    def query(
        self,
        vector: list[float],
        top_k: int = 5,
        table_name: str = "documents",
        filter_expr: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self._table_exists(table_name):
            return []
        table = self._db.open_table(table_name)
        query = table.search(vector).limit(top_k)
        if filter_expr:
            query = query.where(filter_expr)
        rows = query.to_list()

        results: list[dict[str, Any]] = []
        for row in rows:
            try:
                meta = json.loads(row.get("metadata_json", "{}"))
            except (TypeError, json.JSONDecodeError):
                meta = {}
            distance = row.get("_distance", 0.0)
            results.append(
                {
                    "text": row.get("text", ""),
                    "metadata": meta,
                    "score": float(distance) if distance is not None else 0.0,
                    "_id": row.get("_id", ""),
                    "embedding_model": row.get("embedding_model", ""),
                }
            )
        return results

    def version_at(
        self,
        doc_id: str,
        at: datetime,
        table_name: str = "documents",
        version: int | None = None,
    ) -> dict[str, Any] | None:
        """Retrieve a document from a specific Lance table version.

        LanceDB time-travel is version-based. The ``at`` parameter is retained to
        match the protocol shape, while callers that need deterministic historic
        reads may also pass an explicit ``version`` obtained from
        :meth:`current_version`.
        """
        del at
        if not self._table_exists(table_name):
            return None
        table = self._db.open_table(table_name)
        if version is not None:
            table.checkout(version)
        rows = table.search().where(f"_id = '{doc_id}'").limit(1).to_list()
        if not rows:
            return None
        row = rows[0]
        try:
            meta = json.loads(row.get("metadata_json", "{}"))
        except (TypeError, json.JSONDecodeError):
            meta = {}
        return {
            "text": row.get("text", ""),
            "metadata": meta,
            "_id": doc_id,
            "embedding_model": row.get("embedding_model", ""),
            "version": version,
        }

    def current_version(self, table_name: str = "documents") -> int:
        if not self._table_exists(table_name):
            raise ValueError(f"table does not exist: {table_name}")
        table = self._db.open_table(table_name)
        return int(table.version)

    def delete_table(self, table_name: str = "documents") -> None:
        with suppress(FileNotFoundError, ValueError):
            self._db.drop_table(table_name)


__all__ = ["LanceVectorStore"]
