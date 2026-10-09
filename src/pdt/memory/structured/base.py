"""Abstract protocol for the structured store.

All data access goes through this Protocol so the implementation is swappable
(DuckDB today; Postgres if/when multi-user).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StructuredStore(Protocol):
    """Append-only structured storage for model parameters, traces, beliefs, and drift.

    Key invariant: **no UPDATE or in-place mutation.** All mutations are
    INSERT-only. "Memory never overwrites truth" (MEMORY_STRATEGY.md).
    """

    # -- Lifecycle ---------------------------------------------------------

    def init_schema(self) -> None:
        """Create tables if they don't exist (idempotent)."""
        ...

    def close(self) -> None:
        """Flush and close the underlying connection."""
        ...

    # -- Traces (§3.4) -----------------------------------------------------

    def insert_trace(self, trace_json: str) -> str:
        """Insert a reasoning trace (encrypted JSON blob). Returns the row id."""
        ...

    def get_trace(self, trace_id: str) -> str | None:
        """Retrieve a trace by id. Returns decrypted JSON or None."""
        ...

    def list_traces(
        self,
        domain: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Sequence[str]:
        """Return traces (decrypted JSON), optionally filtered by domain."""
        ...

    def trace_history(self, trace_id: str) -> Sequence[str]:
        """Return all versions of a trace_id (append-only history)."""
        ...

    # -- Model Parameters (§3.1, §3.2) --------------------------------------

    def insert_param(
        self,
        param_key: str,
        value: float,
        confidence: float,
        n_observations: int,
        source: str,
        domain: str | None = None,
    ) -> str:
        """Insert a parameter estimate row. Returns row id."""
        ...

    def get_latest_param(
        self,
        param_key: str,
        domain: str | None = None,
    ) -> dict[str, Any] | None:
        """Return the most recent estimate for a parameter, or None."""
        ...

    def param_history(
        self,
        param_key: str,
        domain: str | None = None,
    ) -> Sequence[dict[str, Any]]:
        """Return the full append-only history for a parameter."""
        ...

    # -- Beliefs (§3.3) -----------------------------------------------------

    def insert_belief(self, belief_json: str) -> str:
        """Insert a belief node (encrypted JSON). Returns row id."""
        ...

    def insert_edge(self, source: str, target: str, relation: str, weight: float) -> str:
        """Insert a belief edge (unencrypted — structural, not personal)."""
        ...

    def list_beliefs(self, domain: str | None = None) -> Sequence[str]:
        """Return beliefs, optionally filtered by domain."""
        ...

    # -- Drift Log (§3.5) ---------------------------------------------------

    def insert_drift_entry(self, parameter: str, value: float, timestamp: str) -> str:
        """Append a drift log entry. Returns row id."""
        ...

    def drift_history(self, parameter: str) -> Sequence[dict[str, Any]]:
        """Return the full drift series for a parameter."""
        ...

    # -- Audit (append-only events) -----------------------------------------

    def insert_event(self, event_type: str, detail_json: str) -> str:
        """Append an audit event (encrypted detail). Returns row id."""
        ...

    # -- Housekeeping --------------------------------------------------------

    def delete_everything(self) -> None:
        """Wipe all tables. Used by `pdt model delete` (blueprint §10)."""
        ...


__all__ = ["StructuredStore"]
