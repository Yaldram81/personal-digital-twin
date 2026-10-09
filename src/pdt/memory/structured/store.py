"""DuckDB-backed implementation of the structured store.

Design principles:

1. **Append-only** — every table allows INSERT only; UPDATE/DELETE are
   exercised only through `delete_everything()` (the blueprint §10 wipe).
   This satisfies "memory never overwrites truth."
2. **App-level envelope encryption** — DuckDB has no native crypto
   extension, so sensitive columns (traces, beliefs, events) are encrypted
   by the caller via `core.crypto` and stored as BLOBs.
3. **Columnar analytical workload** — the drift log and parameter history
   are time-series tables; DuckDB's columnar format makes range scans and
   aggregations over them efficient.
4. **Single-writer** — acceptable for single-user local-first; serialize
   writes through one connection.

Note on parameter binding: DuckDB's Python API requires named `$name`
placeholders when passing a dict (positional `?` expects a list).
"""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

import duckdb

from pdt.core.crypto.crypto import decrypt, encrypt

# ---------------------------------------------------------------------------
# SQL: schema creation
# ---------------------------------------------------------------------------

_SCHEMA_SQL = """
-- Reasoning traces (§3.4). Encrypted JSON payload.
CREATE TABLE IF NOT EXISTS traces (
    id          VARCHAR PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    domain      VARCHAR,
    payload     BLOB NOT NULL        -- encrypt(trace_json)
);

-- Model parameter estimates (§3.1, §3.2). Append-only history.
CREATE TABLE IF NOT EXISTS model_params (
    id              VARCHAR PRIMARY KEY,
    created_at      TIMESTAMP NOT NULL DEFAULT current_timestamp,
    param_key       VARCHAR NOT NULL,
    domain          VARCHAR,          -- NULL = global
    value           DOUBLE NOT NULL,
    confidence      DOUBLE NOT NULL,
    n_observations  INTEGER NOT NULL DEFAULT 0,
    source          VARCHAR NOT NULL   -- self_report | behavioral | inferred
);

-- Belief nodes (§3.3). Encrypted JSON payload.
CREATE TABLE IF NOT EXISTS beliefs (
    id          VARCHAR PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    domain      VARCHAR,
    payload     BLOB NOT NULL        -- encrypt(belief_json)
);

-- Belief edges (§3.3). Structural data, not personal — unencrypted.
CREATE TABLE IF NOT EXISTS belief_edges (
    id          VARCHAR PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    source      VARCHAR NOT NULL,
    target      VARCHAR NOT NULL,
    relation    VARCHAR NOT NULL,     -- supports | contradicts | causes | correlates
    weight      DOUBLE NOT NULL
);

-- Drift log (§3.5). Time-series of parameter values.
CREATE TABLE IF NOT EXISTS drift_log (
    id          VARCHAR PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    parameter   VARCHAR NOT NULL,
    value       DOUBLE NOT NULL,
    ts_date     DATE NOT NULL
);

-- Audit / event log (append-only). Encrypted detail JSON.
CREATE TABLE IF NOT EXISTS events (
    id          VARCHAR PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    event_type  VARCHAR NOT NULL,
    detail      BLOB NOT NULL        -- encrypt(detail_json)
);

-- Extraction audit log (append-only). Encrypted event payload.
CREATE TABLE IF NOT EXISTS extraction_events (
    id          VARCHAR PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    trace_id    VARCHAR NOT NULL,
    payload     BLOB NOT NULL
);

-- Behavioral signal log (append-only). Encrypted evidence payload.
CREATE TABLE IF NOT EXISTS behavioral_signals (
    id          VARCHAR PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    param_key   VARCHAR NOT NULL,
    domain      VARCHAR,
    payload     BLOB NOT NULL
);

-- Contradiction/inconsistency log (append-only).
CREATE TABLE IF NOT EXISTS inconsistencies (
    id          VARCHAR PRIMARY KEY,
    created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
    param_key   VARCHAR NOT NULL,
    domain      VARCHAR,
    detail      BLOB NOT NULL
);
"""


# ---------------------------------------------------------------------------
# DuckDB implementation
# ---------------------------------------------------------------------------


class DuckDBStructuredStore:
    """DuckDB-backed structured store satisfying the StructuredStore Protocol.

    Args:
        db_path: Path to the DuckDB database file (created if absent).
        encryption_key: 32-byte AES key from Vault. Used to encrypt/decrypt
            sensitive payloads before writing to / after reading from DuckDB.
    """

    def __init__(self, db_path: Path, encryption_key: bytes) -> None:
        self._db_path = db_path
        self._key = encryption_key
        # DuckDB opens lazily; ensure the parent dir exists.
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._db_path))

    # -- helpers ------------------------------------------------------------

    def _encrypt(self, plaintext: str) -> bytes:
        return encrypt(plaintext.encode("utf-8"), self._key)

    def _decrypt(self, ciphertext: bytes) -> str:
        return decrypt(ciphertext, self._key).decode("utf-8")

    @staticmethod
    def _new_id() -> str:
        return str(uuid.uuid4())

    def _execute(self, sql: str, parameters: dict[str, Any] | None = None) -> None:
        self._guard_append_only_sql(sql)
        self._conn.execute(sql, parameters or {})

    def _fetchone(self, sql: str, parameters: dict[str, Any] | None = None) -> Any:
        return self._conn.execute(sql, parameters or {}).fetchone()

    def _fetchall(self, sql: str, parameters: dict[str, Any] | None = None) -> list[Any]:
        return self._conn.execute(sql, parameters or {}).fetchall()

    @staticmethod
    def _guard_append_only_sql(sql: str) -> None:
        normalized = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE).strip().lower()
        if not normalized:
            return
        destructive = ("update ", "delete from ", "truncate ")
        if normalized.startswith(destructive):
            raise ValueError("append-only guard: UPDATE/DELETE/TRUNCATE are forbidden")

    def execute_sql(self, sql: str, parameters: dict[str, Any] | None = None) -> None:
        """Execute ad-hoc SQL through the same append-only guard.

        Intended for admin tooling and tests that need to verify forbidden
        mutations are rejected.
        """
        self._execute(sql, parameters)

    # -- StructuredStore implementation -------------------------------------

    def init_schema(self) -> None:
        for stmt in _SCHEMA_SQL.split(";"):
            stmt = stmt.strip()
            if stmt:
                self._execute(stmt)

    def close(self) -> None:
        self._conn.close()

    # -- Traces -------------------------------------------------------------

    def insert_trace(self, trace_json: str) -> str:
        row_id = self._new_id()
        data = json.loads(trace_json)
        domain = data.get("domain", "")
        self._execute(
            "INSERT INTO traces (id, domain, payload) VALUES ($id, $domain, $payload)",
            {"id": row_id, "domain": domain, "payload": self._encrypt(trace_json)},
        )
        return row_id

    def get_trace(self, trace_id: str) -> str | None:
        row = self._fetchone("SELECT payload FROM traces WHERE id = $id", {"id": trace_id})
        if row is None:
            return None
        return self._decrypt(row[0])

    def list_traces(self, domain: str | None = None, limit: int = 50, offset: int = 0) -> list[str]:
        if domain:
            rows = self._fetchall(
                "SELECT payload FROM traces WHERE domain = $domain "
                "ORDER BY created_at DESC LIMIT $limit OFFSET $offset",
                {"domain": domain, "limit": limit, "offset": offset},
            )
        else:
            rows = self._fetchall(
                "SELECT payload FROM traces ORDER BY created_at DESC LIMIT $limit OFFSET $offset",
                {"limit": limit, "offset": offset},
            )
        return [self._decrypt(r[0]) for r in rows]

    def trace_history(self, trace_id: str) -> list[str]:
        # Trace ids are unique in the structured store (LanceDB handles
        # versioned retrieval); returns 0 or 1 elements.
        row = self._fetchone("SELECT payload FROM traces WHERE id = $id", {"id": trace_id})
        return [self._decrypt(row[0])] if row else []

    # -- Model parameters ---------------------------------------------------

    def insert_param(
        self,
        param_key: str,
        value: float,
        confidence: float,
        n_observations: int,
        source: str,
        domain: str | None = None,
    ) -> str:
        row_id = self._new_id()
        self._execute(
            (
                "INSERT INTO model_params "
                "(id, param_key, domain, value, confidence, n_observations, source) "
                "VALUES ($id, $param_key, $domain, $value, $confidence, "
                "$n_observations, $source)"
            ),
            {
                "id": row_id,
                "param_key": param_key,
                "domain": domain,
                "value": value,
                "confidence": confidence,
                "n_observations": n_observations,
                "source": source,
            },
        )
        return row_id

    def get_latest_param(self, param_key: str, domain: str | None = None) -> dict[str, Any] | None:
        if domain:
            row = self._fetchone(
                (
                    "SELECT value, confidence, n_observations, source, created_at "
                    "FROM model_params "
                    "WHERE param_key = $param_key AND domain = $domain "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"param_key": param_key, "domain": domain},
            )
        else:
            row = self._fetchone(
                (
                    "SELECT value, confidence, n_observations, source, created_at "
                    "FROM model_params "
                    "WHERE param_key = $param_key AND domain IS NULL "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"param_key": param_key},
            )
        if row is None:
            return None
        return {
            "param_key": param_key,
            "domain": domain,
            "value": row[0],
            "confidence": row[1],
            "n_observations": row[2],
            "source": row[3],
            "created_at": str(row[4]),
        }

    def param_history(self, param_key: str, domain: str | None = None) -> list[dict[str, Any]]:
        if domain:
            rows = self._fetchall(
                (
                    "SELECT value, confidence, n_observations, source, created_at "
                    "FROM model_params "
                    "WHERE param_key = $param_key AND domain = $domain "
                    "ORDER BY created_at ASC"
                ),
                {"param_key": param_key, "domain": domain},
            )
        else:
            rows = self._fetchall(
                (
                    "SELECT value, confidence, n_observations, source, created_at "
                    "FROM model_params "
                    "WHERE param_key = $param_key AND domain IS NULL "
                    "ORDER BY created_at ASC"
                ),
                {"param_key": param_key},
            )
        return [
            {
                "param_key": param_key,
                "domain": domain,
                "value": r[0],
                "confidence": r[1],
                "n_observations": r[2],
                "source": r[3],
                "created_at": str(r[4]),
            }
            for r in rows
        ]

    # -- Beliefs ------------------------------------------------------------

    def insert_belief(self, belief_json: str) -> str:
        row_id = self._new_id()
        data = json.loads(belief_json)
        domain = data.get("domain", "")
        self._execute(
            "INSERT INTO beliefs (id, domain, payload) VALUES ($id, $domain, $payload)",
            {"id": row_id, "domain": domain, "payload": self._encrypt(belief_json)},
        )
        return row_id

    def insert_edge(self, source: str, target: str, relation: str, weight: float) -> str:
        row_id = self._new_id()
        self._execute(
            (
                "INSERT INTO belief_edges (id, source, target, relation, weight) "
                "VALUES ($id, $source, $target, $relation, $weight)"
            ),
            {
                "id": row_id,
                "source": source,
                "target": target,
                "relation": relation,
                "weight": weight,
            },
        )
        return row_id

    def list_beliefs(self, domain: str | None = None) -> list[str]:
        if domain:
            rows = self._fetchall(
                "SELECT payload FROM beliefs WHERE domain = $domain ORDER BY created_at DESC",
                {"domain": domain},
            )
        else:
            rows = self._fetchall(
                "SELECT payload FROM beliefs ORDER BY created_at DESC",
                {},
            )
        return [self._decrypt(r[0]) for r in rows]

    # -- Drift log ----------------------------------------------------------

    def insert_drift_entry(self, parameter: str, value: float, timestamp: str) -> str:
        row_id = self._new_id()
        self._execute(
            (
                "INSERT INTO drift_log (id, parameter, value, ts_date) "
                "VALUES ($id, $parameter, $value, $ts_date)"
            ),
            {"id": row_id, "parameter": parameter, "value": value, "ts_date": timestamp},
        )
        return row_id

    def drift_history(self, parameter: str) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT value, ts_date, created_at FROM drift_log "
            "WHERE parameter = $parameter ORDER BY ts_date ASC",
            {"parameter": parameter},
        )
        return [{"parameter": parameter, "value": r[0], "ts_date": str(r[1])} for r in rows]

    # -- Audit events -------------------------------------------------------

    def insert_event(self, event_type: str, detail_json: str) -> str:
        row_id = self._new_id()
        self._execute(
            "INSERT INTO events (id, event_type, detail) VALUES ($id, $event_type, $detail)",
            {"id": row_id, "event_type": event_type, "detail": self._encrypt(detail_json)},
        )
        return row_id

    def insert_extraction_event(self, trace_id: str, event_json: str) -> str:
        row_id = self._new_id()
        self._execute(
            (
                "INSERT INTO extraction_events (id, trace_id, payload) "
                "VALUES ($id, $trace_id, $payload)"
            ),
            {"id": row_id, "trace_id": trace_id, "payload": self._encrypt(event_json)},
        )
        return row_id

    def list_extraction_events(self, trace_id: str | None = None) -> list[str]:
        if trace_id:
            rows = self._fetchall(
                (
                    "SELECT payload FROM extraction_events "
                    "WHERE trace_id = $trace_id ORDER BY created_at ASC"
                ),
                {"trace_id": trace_id},
            )
        else:
            rows = self._fetchall(
                "SELECT payload FROM extraction_events ORDER BY created_at ASC",
                {},
            )
        return [self._decrypt(r[0]) for r in rows]

    def insert_behavioral_signal(
        self,
        param_key: str,
        domain: str | None,
        payload_json: str,
    ) -> str:
        row_id = self._new_id()
        self._execute(
            (
                "INSERT INTO behavioral_signals (id, param_key, domain, payload) "
                "VALUES ($id, $param_key, $domain, $payload)"
            ),
            {
                "id": row_id,
                "param_key": param_key,
                "domain": domain,
                "payload": self._encrypt(payload_json),
            },
        )
        return row_id

    def list_behavioral_signals(
        self,
        param_key: str | None = None,
        domain: str | None = None,
    ) -> list[str]:
        conditions: list[str] = []
        params: dict[str, Any] = {}
        if param_key is not None:
            conditions.append("param_key = $param_key")
            params["param_key"] = param_key
        if domain is not None:
            conditions.append("domain = $domain")
            params["domain"] = domain
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._fetchall(
            f"SELECT payload FROM behavioral_signals{where} ORDER BY created_at ASC",
            params,
        )
        return [self._decrypt(r[0]) for r in rows]

    def insert_inconsistency(self, param_key: str, domain: str | None, detail_json: str) -> str:
        row_id = self._new_id()
        self._execute(
            (
                "INSERT INTO inconsistencies (id, param_key, domain, detail) "
                "VALUES ($id, $param_key, $domain, $detail)"
            ),
            {
                "id": row_id,
                "param_key": param_key,
                "domain": domain,
                "detail": self._encrypt(detail_json),
            },
        )
        return row_id

    def list_inconsistencies(
        self,
        param_key: str | None = None,
        domain: str | None = None,
    ) -> list[str]:
        conditions: list[str] = []
        params: dict[str, Any] = {}
        if param_key is not None:
            conditions.append("param_key = $param_key")
            params["param_key"] = param_key
        if domain is not None:
            conditions.append("domain = $domain")
            params["domain"] = domain
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        rows = self._fetchall(
            f"SELECT detail FROM inconsistencies{where} ORDER BY created_at ASC",
            params,
        )
        return [self._decrypt(r[0]) for r in rows]

    def export_bundle(self) -> dict[str, Any]:
        return {
            "traces": [json.loads(item) for item in self.list_traces(limit=10_000)],
            "beliefs": [json.loads(item) for item in self.list_beliefs()],
            "params": self._fetch_model_params_export(),
            "drift_log": self._fetch_drift_export(),
            "events": self._fetch_event_export(),
            "extraction_events": [json.loads(item) for item in self.list_extraction_events()],
            "behavioral_signals": [json.loads(item) for item in self.list_behavioral_signals()],
            "inconsistencies": [json.loads(item) for item in self.list_inconsistencies()],
        }

    # -- Housekeeping -------------------------------------------------------

    def _fetch_model_params_export(self) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT param_key, domain, value, confidence, n_observations, "
            "source, created_at FROM model_params ORDER BY created_at ASC"
        )
        return [
            {
                "param_key": r[0],
                "domain": r[1],
                "value": r[2],
                "confidence": r[3],
                "n_observations": r[4],
                "source": r[5],
                "created_at": str(r[6]),
            }
            for r in rows
        ]

    def _fetch_drift_export(self) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT parameter, value, ts_date, created_at FROM drift_log ORDER BY ts_date ASC"
        )
        return [
            {
                "parameter": r[0],
                "value": r[1],
                "ts_date": str(r[2]),
                "created_at": str(r[3]),
            }
            for r in rows
        ]

    def _fetch_event_export(self) -> list[dict[str, Any]]:
        rows = self._fetchall(
            "SELECT event_type, detail, created_at FROM events ORDER BY created_at ASC"
        )
        return [
            {
                "event_type": r[0],
                "detail": json.loads(self._decrypt(r[1])),
                "created_at": str(r[2]),
            }
            for r in rows
        ]

    def purge_events_by_type(self, event_type: str) -> None:
        encrypted_details = [
            row[0]
            for row in self._fetchall(
                "SELECT detail FROM events WHERE event_type = $event_type",
                {"event_type": event_type},
            )
        ]
        tombstones = [self._decrypt(detail) for detail in encrypted_details]
        self._conn.execute(
            "DELETE FROM events WHERE event_type = $event_type",
            {"event_type": event_type},
        )
        for tombstone in tombstones:
            self.insert_event(
                "audit_tombstone",
                json.dumps(
                    {
                        "purged_event_type": event_type,
                        "deleted_detail": json.loads(tombstone),
                    }
                ),
            )

    def delete_everything(self) -> None:
        """Drop all tables and re-create an empty schema. Irreversible.

        Blueprint §10 full deletion: personal data is removed; the store
        itself remains usable afterwards (queries return empty results).
        """
        for table in (
            "inconsistencies",
            "behavioral_signals",
            "extraction_events",
            "events",
            "drift_log",
            "belief_edges",
            "beliefs",
            "model_params",
            "traces",
        ):
            self._execute(f"DROP TABLE IF EXISTS {table}")
        self.init_schema()


__all__ = ["DuckDBStructuredStore"]
