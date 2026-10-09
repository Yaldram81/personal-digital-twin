from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import cast

from pdt.core.crypto.crypto import decrypt, encrypt


@dataclass(frozen=True)
class EncryptedTransportPayload:
    ciphertext_b64: str
    trust_boundary: str


def encrypt_for_llm(context: dict[str, object], key: bytes) -> EncryptedTransportPayload:
    payload = json.dumps(context, sort_keys=True).encode("utf-8")
    ciphertext = encrypt(payload, key)
    return EncryptedTransportPayload(
        ciphertext_b64=base64.b64encode(ciphertext).decode("ascii"),
        trust_boundary="trusted_execution_environment_required_for_remote_decrypt",
    )


def decrypt_from_llm(payload: EncryptedTransportPayload, key: bytes) -> dict[str, object]:
    plaintext = decrypt(base64.b64decode(payload.ciphertext_b64.encode("ascii")), key)
    return cast(dict[str, object], json.loads(plaintext.decode("utf-8")))


__all__ = ["EncryptedTransportPayload", "decrypt_from_llm", "encrypt_for_llm"]
