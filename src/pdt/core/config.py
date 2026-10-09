"""Application configuration.

All runtime settings flow through `Settings`, loaded from environment variables
(and a local `.env`). No secret material is committed; the key-derivation key is
held only in memory, derived from the user passphrase at runtime.

Per CODING_STANDARDS.md: configuration is centralized; provider keys, DB path,
and encryption params all live here, never hardcoded in business logic.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed settings sourced from the environment.

    A missing required setting raises a clear error on startup. `pdt doctor`
    surfaces the status of each setting for fast diagnosis.
    """

    model_config = SettingsConfigDict(
        env_prefix="PDT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- App -------------------------------------------------------------
    env: str = Field(default="dev", description="Runtime environment: dev | prod.")
    data_dir: Path = Field(default=Path(".data"), description="Encrypted store location.")

    # ---- LLM provider ----------------------------------------------------
    llm_provider: str = Field(default="openai")
    llm_model: str = Field(default="gpt-4o-mini")
    llm_api_key: str = Field(default="", description="Required for cloud providers.")
    llm_base_url: str = Field(default="", description="Optional OpenAI-compatible base URL.")
    embedding_model: str = Field(default="text-embedding-3-small")

    # ---- Encryption (Argon2id KDF parameters) ---------------------------
    kdf_memory_kib: int = Field(default=65536, ge=8192, description="Argon2id memory cost.")
    kdf_time_cost: int = Field(default=3, ge=1, description="Argon2id iterations.")
    kdf_parallelism: int = Field(default=4, ge=1, description="Argon2id parallel lanes.")

    # ---- API server ------------------------------------------------------
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000, ge=1, le=65535)

    @field_validator("data_dir")
    @classmethod
    def _coerce_data_dir(cls, v: Path) -> Path:
        return v.expanduser().resolve() if not v.is_absolute() else v

    @property
    def duckdb_path(self) -> Path:
        return self.data_dir / "pdt.duckdb"

    @property
    def lancedb_path(self) -> Path:
        return self.data_dir / "vectors"

    @property
    def requires_api_key(self) -> bool:
        """True when the configured provider needs a network credential."""
        return self.llm_provider.lower() not in {"mock", ""}


def get_settings() -> Settings:
    """Return a fresh `Settings` instance.

    Constructed per-call rather than cached as a singleton so tests can inject
    overrides via environment variables without global-state leakage.
    """
    return Settings()


__all__ = ["Settings", "get_settings"]
