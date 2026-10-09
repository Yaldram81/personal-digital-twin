"""High-level vault: binds a passphrase to a persisted salt and yields a key.

The salt is stored on disk (unencrypted — it is not secret) alongside the
encrypted stores. The derived key lives only in memory for the process
lifetime. On `init`, a fresh salt is generated; on `unlock`, the existing
salt is loaded and the key is re-derived.
"""

from __future__ import annotations

from pathlib import Path

from pdt.core.crypto.crypto import (
    KEY_LEN,
    SALT_LEN,
    KDFParams,
    derive_key,
    generate_salt,
)


class Vault:
    """A user passphrase bound to a persisted salt file.

    Usage::

        vault = Vault.init(data_dir, passphrase, params)
        key = vault.key            # 32 raw bytes, in-memory only

        # later, new process:
        vault = Vault.unlock(data_dir, passphrase, params)
    """

    _SALT_FILENAME = "vault.salt"

    def __init__(self, key: bytes) -> None:
        # Key length is validated at derivation time; assert once more at the
        # boundary since callers could construct this directly.
        if len(key) != KEY_LEN:
            raise ValueError(f"key must be {KEY_LEN} bytes, got {len(key)}")
        self._key = key

    @property
    def key(self) -> bytes:
        return self._key

    @classmethod
    def init(cls, data_dir: Path, passphrase: str, params: KDFParams | None = None) -> Vault:
        """Create a new vault: generate and persist a fresh salt, derive the key."""
        data_dir.mkdir(parents=True, exist_ok=True)
        salt_path = data_dir / cls._SALT_FILENAME
        if salt_path.exists():
            raise FileExistsError(
                f"vault already exists at {salt_path}; use Vault.unlock() instead"
            )
        salt = generate_salt()
        salt_path.write_bytes(salt)
        key = derive_key(passphrase, salt, params)
        return cls(key)

    @classmethod
    def unlock(cls, data_dir: Path, passphrase: str, params: KDFParams | None = None) -> Vault:
        """Open an existing vault: load salt, re-derive the key.

        A wrong passphrase produces a *valid* key (Argon2id always succeeds);
        the failure surfaces later as a decrypt error. This is intentional —
        it leaks no information about whether the passphrase is right.
        """
        salt_path = data_dir / cls._SALT_FILENAME
        if not salt_path.exists():
            raise FileNotFoundError(f"no vault at {salt_path}; run `pdt init` first")
        salt = salt_path.read_bytes()
        if len(salt) != SALT_LEN:
            raise ValueError(f"corrupt salt file: expected {SALT_LEN} bytes")
        key = derive_key(passphrase, salt, params)
        return cls(key)

    @classmethod
    def exists(cls, data_dir: Path) -> bool:
        return (data_dir / cls._SALT_FILENAME).exists()


__all__ = ["Vault"]
