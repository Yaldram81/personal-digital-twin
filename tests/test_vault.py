"""Tests for the Vault: init + unlock lifecycle."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdt.core.crypto import KDFParams, Vault


class TestVault:
    def test_init_creates_salt_file(self, tmp_data_dir: Path, fast_kdf: KDFParams) -> None:
        vault = Vault.init(tmp_data_dir, "strong-passphrase", fast_kdf)
        assert (tmp_data_dir / "vault.salt").exists()
        assert len(vault.key) == 32

    def test_init_idempotent_fails(self, tmp_data_dir: Path, fast_kdf: KDFParams) -> None:
        Vault.init(tmp_data_dir, "strong-passphrase", fast_kdf)
        with pytest.raises(FileExistsError):
            Vault.init(tmp_data_dir, "strong-passphrase", fast_kdf)

    def test_unlock_recreates_same_key(self, tmp_data_dir: Path, fast_kdf: KDFParams) -> None:
        v1 = Vault.init(tmp_data_dir, "strong-passphrase", fast_kdf)
        v2 = Vault.unlock(tmp_data_dir, "strong-passphrase", fast_kdf)
        assert v1.key == v2.key

    def test_wrong_passphrase_different_key(self, tmp_data_dir: Path, fast_kdf: KDFParams) -> None:
        """Wrong passphrase produces a *different* key (no error at unlock —
        by design, to avoid leaking whether the passphrase is correct)."""
        v1 = Vault.init(tmp_data_dir, "strong-passphrase", fast_kdf)
        v2 = Vault.unlock(tmp_data_dir, "wrong-passphrase", fast_kdf)
        assert v1.key != v2.key

    def test_unlock_missing_vault_fails(self, tmp_data_dir: Path, fast_kdf: KDFParams) -> None:
        with pytest.raises(FileNotFoundError):
            Vault.unlock(tmp_data_dir, "strong-passphrase", fast_kdf)

    def test_exists(self, tmp_data_dir: Path, fast_kdf: KDFParams) -> None:
        assert not Vault.exists(tmp_data_dir)
        Vault.init(tmp_data_dir, "strong-passphrase", fast_kdf)
        assert Vault.exists(tmp_data_dir)
