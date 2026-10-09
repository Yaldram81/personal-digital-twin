"""LLM abstraction layer.

Per CODING_STANDARDS.md: "All LLM calls must go through a single abstraction
layer. No direct API calls inside business logic."

This module defines:

1. ``LLMClient`` Protocol — the interface every provider must implement.
2. ``create_client`` factory — selects the concrete client by provider name
   from Settings, so business logic never imports a provider SDK.
3. ``LLMResult`` — the uniform return type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class LLMResult:
    """Uniform return from any LLM provider."""

    text: str
    model: str = ""
    provider: str = ""
    usage: dict[str, int] = field(default_factory=dict)  # e.g. prompt_tokens, completion_tokens


@runtime_checkable
class LLMClient(Protocol):
    """The interface every LLM provider implements.

    Chat completion and embedding are the two operations the system needs.
    """

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResult:
        """Chat completion. Returns the assistant message text."""
        ...

    def embed(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> list[list[float]]:
        """Embed one or more texts into vectors."""
        ...


def create_client(
    provider: str,
    api_key: str = "",
    base_url: str = "",
    default_model: str = "",
    embedding_model: str = "",
) -> LLMClient:
    """Factory: returns a concrete ``LLMClient`` based on provider name.

    Per the import-linter rule, no module outside ``core.llm`` may import a
    provider SDK directly — all access flows through the returned Protocol.
    """
    if provider.lower() == "openai":
        from pdt.core.llm.openai_client import OpenAILLMClient

        return OpenAILLMClient(
            api_key=api_key,
            base_url=base_url,
            default_model=default_model,
            embedding_model=embedding_model,
        )
    if provider.lower() == "mock":
        from pdt.core.llm.mock_client import MockLLMClient

        return MockLLMClient(default_model=default_model or "mock")

    raise ValueError(f"unsupported LLM provider: {provider}")


__all__ = ["LLMClient", "LLMResult", "create_client"]
