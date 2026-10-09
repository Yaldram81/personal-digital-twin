"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from pdt.core.config import Settings
from pdt.core.crypto import KDFParams, Vault


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Isolated data directory per test."""
    d = tmp_path / "data"
    d.mkdir()
    return d


@pytest.fixture
def settings(tmp_data_dir: Path) -> Settings:
    """Settings pointing at a temp data dir with the mock provider."""
    return Settings(
        env="dev",
        data_dir=tmp_data_dir,
        llm_provider="mock",
        llm_api_key="",
        embedding_model="mock-embed",
    )


@pytest.fixture
def vault(tmp_data_dir: Path) -> Vault:
    """An initialized vault with a known test passphrase + fast KDF params."""
    params = KDFParams(memory_kib=8192, time_cost=1, parallelism=1)
    return Vault.init(tmp_data_dir, "test-passphrase-123", params)


@pytest.fixture
def fast_kdf() -> KDFParams:
    """Fast Argon2id params so crypto tests don't take seconds each."""
    return KDFParams(memory_kib=8192, time_cost=1, parallelism=1)


@pytest.fixture
def today() -> date:
    return date(2025, 3, 12)
