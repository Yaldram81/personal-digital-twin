"""Tests for Settings-derived config behavior."""

from __future__ import annotations

from pathlib import Path

from pdt.core.config import Settings


def test_settings_derives_store_paths(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, llm_provider="mock")
    assert settings.duckdb_path == tmp_path / "pdt.duckdb"
    assert settings.lancedb_path == tmp_path / "vectors"


def test_requires_api_key_for_openai(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, llm_provider="openai")
    assert settings.requires_api_key is True


def test_does_not_require_api_key_for_mock(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, llm_provider="mock")
    assert settings.requires_api_key is False


def test_relative_data_dir_is_resolved() -> None:
    settings = Settings(data_dir=Path(".data-test"), llm_provider="mock")
    assert settings.data_dir.is_absolute()
