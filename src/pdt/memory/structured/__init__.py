"""Structured store: append-only DuckDB backend with envelope encryption.

Per MEMORY_STRATEGY.md: "Memory must NEVER overwrite truth."
"""

from pdt.memory.structured.base import StructuredStore
from pdt.memory.structured.store import DuckDBStructuredStore

__all__ = ["DuckDBStructuredStore", "StructuredStore"]
