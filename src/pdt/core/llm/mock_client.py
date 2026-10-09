"""Mock LLM client for testing.

Returns deterministic output without any network call. Embeddings are
zero-initialized vectors of the requested dimension (dummy, but valid for
store round-trip tests).
"""

from __future__ import annotations

import hashlib
import json

from pdt.core.llm.base import LLMResult


class MockLLMClient:
    """Deterministic mock for unit tests and offline development."""

    def __init__(self, default_model: str = "mock") -> None:
        self._default_model = default_model

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResult:
        # Deterministic echo: hash the last user message so tests can assert.
        last_user = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user = msg.get("content", "")
                break
        reply = json.dumps({"echo": last_user, "model": model or self._default_model})
        return LLMResult(
            text=reply,
            model=model or self._default_model,
            provider="mock",
            usage={"prompt_tokens": 10, "completion_tokens": 20},
        )

    def embed(
        self,
        texts: list[str],
        model: str | None = None,  # noqa: ARG002
    ) -> list[list[float]]:
        # Deterministic pseudo-embeddings: first 4 bytes of SHA-256 per text,
        # padded to a 16-dim float vector (good enough for store round-trips).
        dim = 16
        result: list[list[float]] = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()[:dim]
            vec = [float(b) / 255.0 for b in h]
            result.append(vec)
        return result
