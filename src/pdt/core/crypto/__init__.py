"""Crypto: Argon2id key derivation + AES-GCM envelope encryption.

Per blueprint §10: the personal model is encrypted at rest under a key derived
from the user passphrase. The derived key is in-memory only.
"""

from pdt.core.crypto.crypto import (
    KEY_LEN,
    MIN_PASSPHRASE_LEN,
    NONCE_LEN,
    SALT_LEN,
    KDFParams,
    decrypt,
    derive_key,
    encrypt,
    generate_salt,
)
from pdt.core.crypto.vault import Vault

__all__ = [
    "KEY_LEN",
    "KDFParams",
    "MIN_PASSPHRASE_LEN",
    "NONCE_LEN",
    "SALT_LEN",
    "Vault",
    "decrypt",
    "derive_key",
    "encrypt",
    "generate_salt",
]
