"""Tests for CLI happy paths and error handling."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from pdt.cli import app

runner = CliRunner()


def test_doctor_reports_missing_init_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PDT_ENV", "dev")
    monkeypatch.setenv("PDT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PDT_LLM_PROVIDER", "mock")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "Some checks need attention" in result.stdout


def test_doctor_passes_after_vault_and_store_init(monkeypatch, tmp_path: Path) -> None:
    from pdt.core.crypto import KDFParams, Vault
    from pdt.memory.structured import DuckDBStructuredStore

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    vault = Vault.init(data_dir, "strong-passphrase", KDFParams(memory_kib=8192, time_cost=1, parallelism=1))
    store = DuckDBStructuredStore(data_dir / "pdt.duckdb", vault.key)
    store.init_schema()
    store.close()
    (data_dir / "vectors").mkdir(exist_ok=True)

    monkeypatch.setenv("PDT_ENV", "dev")
    monkeypatch.setenv("PDT_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PDT_LLM_PROVIDER", "mock")
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "All checks passed" in result.stdout


def test_doctor_fails_without_required_api_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PDT_ENV", "dev")
    monkeypatch.setenv("PDT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PDT_LLM_PROVIDER", "openai")
    monkeypatch.delenv("PDT_LLM_API_KEY", raising=False)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "missing key" in result.stdout


def test_init_rejects_mismatched_passphrases(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PDT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("getpass.getpass", lambda prompt: "first" if "Choose" in prompt else "second")
    result = runner.invoke(app, ["init"])
    assert result.exit_code == 1
    assert "Passphrases do not match" in result.stdout


def test_serve_requires_existing_vault(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PDT_DATA_DIR", str(tmp_path / "data"))
    result = runner.invoke(app, ["serve", "--host", "127.0.0.1", "--port", "8000"])
    assert result.exit_code == 1
    assert "Run `pdt init` first" in result.stdout


def test_narrate_requires_existing_vault(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PDT_DATA_DIR", str(tmp_path / "data"))
    result = runner.invoke(app, ["narrate"])
    assert result.exit_code == 1
    assert "Run `pdt init` first" in result.stdout


def test_narrate_creates_a_trace_end_to_end(monkeypatch, tmp_path: Path) -> None:
    from pdt.core.crypto import KDFParams, Vault
    from pdt.memory.structured import DuckDBStructuredStore

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    weak_params = KDFParams(memory_kib=8192, time_cost=1, parallelism=1)
    vault = Vault.init(data_dir, "narrate-passphrase", weak_params)
    store = DuckDBStructuredStore(data_dir / "pdt.duckdb", vault.key)
    store.init_schema()
    store.close()

    monkeypatch.setenv("PDT_DATA_DIR", str(data_dir))
    monkeypatch.setenv("PDT_LLM_PROVIDER", "mock")
    # Keep the CLI's own KDF derivation consistent with the weak params used
    # to init the vault above, so the CLI-derived key matches `vault.key`.
    monkeypatch.setenv("PDT_KDF_MEMORY_KIB", "8192")
    monkeypatch.setenv("PDT_KDF_TIME_COST", "1")
    monkeypatch.setenv("PDT_KDF_PARALLELISM", "1")
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "narrate-passphrase")

    class _StubExtractionLLM:
        def complete(self, messages, model=None, temperature=0.0, max_tokens=None):  # type: ignore[no-untyped-def]
            import json as _json

            from pdt.core.llm.base import LLMResult

            payload = _json.dumps(
                {
                    "domain": "career",
                    "options_detected": ["startup", "big_tech"],
                    "chosen": "startup",
                    "factors": [
                        {"factor": "learning", "weight": "HIGH", "direction": "toward_startup"}
                    ],
                    "inferred_values": ["self_direction"],
                }
            )
            return LLMResult(text=payload, model="stub", provider="stub")

        def embed(self, texts, model=None):  # type: ignore[no-untyped-def]
            return [[0.0] * 16 for _ in texts]

    monkeypatch.setattr(
        "pdt.core.llm.base.create_client", lambda **kwargs: _StubExtractionLLM()  # noqa: ARG005
    )

    narration_lines = [
        "I chose the startup over big tech.",
        "startup, big_tech",
        "learning velocity mattered most",
        "learning outweighed comfort",
        "",
        "",
    ]
    result = runner.invoke(app, ["narrate"], input="\n".join(narration_lines) + "\n")
    assert result.exit_code == 0, result.stdout
    assert "Trace stored" in result.stdout
    assert "Domain: career" in result.stdout

    verify_store = DuckDBStructuredStore(data_dir / "pdt.duckdb", vault.key)
    traces = verify_store.list_traces(limit=10)
    assert len(traces) == 1
    verify_store.close()
