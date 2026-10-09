"""OpenAI-compatible LLM client.

Works with the official OpenAI API and any OpenAI-compatible endpoint
(via ``base_url`` — e.g., LiteLLM, Ollama, local LLM servers).

This is the only file in the entire codebase that imports ``openai``.
"""

from __future__ import annotations

from openai import OpenAI

from pdt.core.llm.base import LLMResult


class OpenAILLMClient:
    """Concrete LLMClient for OpenAI and compatible APIs."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "",
        default_model: str = "gpt-4o-mini",
        embedding_model: str = "text-embedding-3-small",
    ) -> None:
        if base_url:
            self._client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = OpenAI(api_key=api_key)
        self._default_model = default_model
        self._embedding_model = embedding_model

    def complete(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> LLMResult:
        if max_tokens is not None:
            resp = self._client.chat.completions.create(
                model=model or self._default_model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            resp = self._client.chat.completions.create(
                model=model or self._default_model,
                messages=messages,  # type: ignore[arg-type]
                temperature=temperature,
            )
        choice = resp.choices[0]
        usage: dict[str, int] = {}
        if resp.usage:
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens or 0,
                "completion_tokens": resp.usage.completion_tokens or 0,
            }
        return LLMResult(
            text=choice.message.content or "",
            model=resp.model or self._default_model,
            provider="openai",
            usage=usage,
        )

    def embed(
        self,
        texts: list[str],
        model: str | None = None,
    ) -> list[list[float]]:
        resp = self._client.embeddings.create(
            model=model or self._embedding_model,
            input=texts,
        )
        sorted_data = sorted(resp.data, key=lambda x: x.index)
        return [item.embedding for item in sorted_data]
