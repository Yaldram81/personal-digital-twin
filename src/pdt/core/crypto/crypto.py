"""Cryptographic primitives for the Personal Digital Twin.

This module is the sole place encryption happens. Per the blueprint §10 privacy
mandate, all model parameters and traces are encrypted at rest using a key
derived from the user's passphrase. The derived key is held only in memory and
is **never** written to disk.

Two responsibilities:

1. **Key derivation** — Argon2id turns a user passphrase (+ random per-vault
   salt) into a 256-bit symmetric key. Argon2id is memory-hard, which matters
   because the attacker's likely advantage here is offline brute force on a
   stolen vault file.
2. **Envelope encryption** — AES-GCM provides authenticated encryption: a
   tampered ciphertext is rejected on decrypt (integrity + confidentiality).
   Each ciphertext carries its own random 96-bit nonce, so the same plaintext
   encrypts differently each time.
"""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Key length in bytes. AES-256 → 32 bytes.
KEY_LEN = 32

#: AES-GCM nonce length in bytes (96 bits is the recommended GCM nonce size).
NONCE_LEN = 12

#: Salt length in bytes. 128-bit salt makes precomputed rainbow tables infeasible.
SALT_LEN = 16

#: Magic prefix so we can detect/validate our envelope format on decrypt.
_ENVELOPE_MAGIC = b"PDT1"

#: Minimum passphrase length. Short passphrases are the realistic attack vector.
MIN_PASSPHRASE_LEN = 8


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KDFParams:
    """Argon2id parameters, sourced from Settings.

    Kept as a dataclass (not Settings) so crypto stays decoupled from config
    and is unit-testable in isolation.
    """

    memory_kib: int = 65536  # 64 MiB
    time_cost: int = 3
    parallelism: int = 4


def generate_salt() -> bytes:
    """Return a fresh cryptographically-random salt."""
    return secrets.token_bytes(SALT_LEN)


def derive_key(passphrase: str, salt: bytes, params: KDFParams | None = None) -> bytes:
    """Derive a 256-bit key from a passphrase using Argon2id.

    The key is returned to the caller and is not stored anywhere by this
    function. Callers must keep it in memory only.
    """
    if not passphrase:
        raise ValueError("passphrase must not be empty")
    if len(passphrase) < MIN_PASSPHRASE_LEN:
        raise ValueError(
            f"passphrase too short: need >= {MIN_PASSPHRASE_LEN} chars, got {len(passphrase)}"
        )
    if len(salt) != SALT_LEN:
        raise ValueError(f"salt must be {SALT_LEN} bytes, got {len(salt)}")

    p = params or KDFParams()
    return hash_secret_raw(
        secret=passphrase.encode("utf-8"),
        salt=salt,
        hash_len=KEY_LEN,
        type=Type.ID,  # Argon2id (hybrid data-dependent + data-independent)
        time_cost=p.time_cost,
        memory_cost=p.memory_kib,
        parallelism=p.parallelism,
    )


# ---------------------------------------------------------------------------
# Envelope encryption (AES-GCM)
# ---------------------------------------------------------------------------


def encrypt(plaintext: bytes, key: bytes) -> bytes:
    """Encrypt `plaintext` with AES-GCM under `key`.

    Returns an envelope: ``magic || nonce || ciphertext+tag``. The nonce is
    fresh and random on every call, so identical plaintexts produce different
    ciphertexts.
    """
    _require_key(key)
    nonce = os.urandom(NONCE_LEN)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return _ENVELOPE_MAGIC + nonce + ciphertext


def decrypt(envelope: bytes, key: bytes) -> bytes:
    """Decrypt an envelope produced by :func:`encrypt`.

    Raises :class:`ValueError` if the envelope is malformed or has been
    tampered with — AES-GCM authenticates, so any modification is detected.
    """
    _require_key(key)
    magic_len = len(_ENVELOPE_MAGIC)
    if len(envelope) < magic_len + NONCE_LEN:
        raise ValueError("ciphertext too short to be a valid envelope")
    if envelope[:magic_len] != _ENVELOPE_MAGIC:
        raise ValueError("bad envelope magic — not a PDT ciphertext")
    nonce = envelope[magic_len : magic_len + NONCE_LEN]
    ciphertext = envelope[magic_len + NONCE_LEN :]
    aesgcm = AESGCM(key)
    # InvalidTag surfaces as a generic Exception from cryptography; normalize.
    try:
        return aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as exc:  # noqa: BLE001 — cryptography raises InvalidTag
        raise ValueError("decryption failed: wrong key or tampered ciphertext") from exc


def _require_key(key: bytes) -> None:
    if len(key) != KEY_LEN:
        raise ValueError(f"key must be {KEY_LEN} bytes, got {len(key)}")


__all__ = [
    "KEY_LEN",
    "KDFParams",
    "MIN_PASSPHRASE_LEN",
    "NONCE_LEN",
    "SALT_LEN",
    "decrypt",
    "derive_key",
    "encrypt",
    "generate_salt",
]
