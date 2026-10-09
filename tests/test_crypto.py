"""Tests for the crypto module: key derivation + AES-GCM envelope encryption."""

from __future__ import annotations

import pytest

from pdt.core.crypto import (
    KEY_LEN,
    SALT_LEN,
    KDFParams,
    decrypt,
    derive_key,
    encrypt,
    generate_salt,
)


class TestKeyDerivation:
    def test_derive_key_produces_correct_length(self, fast_kdf: KDFParams) -> None:
        key = derive_key("strong-passphrase", generate_salt(), fast_kdf)
        assert len(key) == KEY_LEN

    def test_same_passphrase_same_salt_same_key(self, fast_kdf: KDFParams) -> None:
        salt = generate_salt()
        k1 = derive_key("strong-passphrase", salt, fast_kdf)
        k2 = derive_key("strong-passphrase", salt, fast_kdf)
        assert k1 == k2

    def test_different_salt_different_key(self, fast_kdf: KDFParams) -> None:
        k1 = derive_key("strong-passphrase", generate_salt(), fast_kdf)
        k2 = derive_key("strong-passphrase", generate_salt(), fast_kdf)
        assert k1 != k2

    def test_different_passphrase_different_key(self, fast_kdf: KDFParams) -> None:
        salt = generate_salt()
        k1 = derive_key("strong-passphrase", salt, fast_kdf)
        k2 = derive_key("other-passphrase", salt, fast_kdf)
        assert k1 != k2

    def test_empty_passphrase_rejected(self, fast_kdf: KDFParams) -> None:
        with pytest.raises(ValueError, match="empty"):
            derive_key("", generate_salt(), fast_kdf)

    def test_short_passphrase_rejected(self, fast_kdf: KDFParams) -> None:
        with pytest.raises(ValueError, match="too short"):
            derive_key("short", generate_salt(), fast_kdf)

    def test_wrong_salt_length_rejected(self, fast_kdf: KDFParams) -> None:
        with pytest.raises(ValueError, match="salt"):
            derive_key("strong-passphrase", b"too_short", fast_kdf)

    def test_salt_is_correct_length(self) -> None:
        assert len(generate_salt()) == SALT_LEN


class TestEnvelopeEncryption:
    def test_roundtrip(self, fast_kdf: KDFParams) -> None:
        key = derive_key("strong-passphrase", generate_salt(), fast_kdf)
        plaintext = b"the user values autonomy over security"
        ct = encrypt(plaintext, key)
        pt = decrypt(ct, key)
        assert pt == plaintext

    def test_ciphertext_differs_from_plaintext(self, fast_kdf: KDFParams) -> None:
        key = derive_key("strong-passphrase", generate_salt(), fast_kdf)
        plaintext = b"some secret trace data"
        ct = encrypt(plaintext, key)
        assert ct != plaintext
        assert plaintext not in ct

    def test_same_plaintext_different_ciphertext(self, fast_kdf: KDFParams) -> None:
        """Random nonce means identical plaintexts encrypt differently."""
        key = derive_key("strong-passphrase", generate_salt(), fast_kdf)
        plaintext = b"identical"
        ct1 = encrypt(plaintext, key)
        ct2 = encrypt(plaintext, key)
        assert ct1 != ct2

    def test_wrong_key_fails_decryption(self, fast_kdf: KDFParams) -> None:
        salt = generate_salt()
        key1 = derive_key("strong-passphrase", salt, fast_kdf)
        key2 = derive_key("different-pass", salt, fast_kdf)
        ct = encrypt(b"secret", key1)
        with pytest.raises(ValueError, match="decryption failed"):
            decrypt(ct, key2)

    def test_tampered_ciphertext_rejected(self, fast_kdf: KDFParams) -> None:
        """AES-GCM authenticates — any tampering is detected on decrypt."""
        key = derive_key("strong-passphrase", generate_salt(), fast_kdf)
        ct = bytearray(encrypt(b"original secret", key))
        # Flip a byte in the ciphertext portion (past magic + nonce).
        ct[-1] ^= 0xFF
        with pytest.raises(ValueError, match="decryption failed"):
            decrypt(bytes(ct), key)

    def test_malformed_envelope_rejected(self, fast_kdf: KDFParams) -> None:
        key = derive_key("strong-passphrase", generate_salt(), fast_kdf)
        with pytest.raises(ValueError, match="too short"):
            decrypt(b"short", key)
        with pytest.raises(ValueError, match="magic"):
            decrypt(b"XXXX" + b"\x00" * 20, key)

    def test_wrong_key_length_rejected(self) -> None:
        with pytest.raises(ValueError, match="key"):
            encrypt(b"data", b"too_short")
