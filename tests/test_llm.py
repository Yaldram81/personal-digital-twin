"""Tests for the LLM abstraction layer + prompt registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from pdt.core.llm import MockLLMClient, PromptRegistry, create_client
from pdt.core.llm.base import LLMClient


class TestLLMAbstraction:
    """Exit criterion: the abstraction works with a mocked provider."""

    def test_create_mock_client(self) -> None:
        client = create_client("mock")
        assert isinstance(client, MockLLMClient)

    def test_create_unsupported_provider(self) -> None:
        with pytest.raises(ValueError, match="unsupported"):
            create_client("bogus")

    def test_mock_client_satisfies_protocol(self) -> None:
        """The mock is usable wherever the LLMClient Protocol is expected."""
        client: LLMClient = create_client("mock")
        result = client.complete([{"role": "user", "content": "hello"}])
        assert isinstance(result.text, str)
        assert result.provider == "mock"

    def test_mock_complete_is_deterministic(self) -> None:
        client = create_client("mock")
        r = client.complete([{"role": "user", "content": "test input"}])
        assert "test input" in r.text

    def test_mock_embed_returns_vectors(self) -> None:
        client = create_client("mock")
        vecs = client.embed(["hello", "world"])
        assert len(vecs) == 2
        assert all(len(v) == 16 for v in vecs)

    def test_mock_embed_is_deterministic(self) -> None:
        """Same text → same vector (important for retrieval tests)."""
        client = create_client("mock")
        v1 = client.embed(["deterministic"])
        v2 = client.embed(["deterministic"])
        assert v1 == v2


class TestPromptRegistry:
    """Exit criterion: prompts load by id+version and render correctly."""

    def test_default_registry_loads_real_prompt(self) -> None:
        """The shipped manifest should resolve reasoning_trace_extraction."""
        registry = PromptRegistry()
        text = registry.render("reasoning_trace_extraction", version="v1", narration="test")
        assert "reasoning-trace extraction" in text.lower()
        assert "test" in text  # variable substituted

    def test_latest_version_used_when_omitted(self) -> None:
        registry = PromptRegistry()
        text = registry.render("reasoning_trace_extraction", narration="hello")
        assert "hello" in text

    def test_list_prompts(self) -> None:
        registry = PromptRegistry()
        names = registry.list_prompts()
        assert "reasoning_trace_extraction" in names
        assert "simulated_reasoning" in names

    def test_versions(self) -> None:
        registry = PromptRegistry()
        versions = registry.versions("reasoning_trace_extraction")
        assert "v1" in versions

    def test_unknown_prompt_raises(self) -> None:
        registry = PromptRegistry()
        with pytest.raises(ValueError, match="unknown prompt"):
            registry.render("does_not_exist")

    def test_missing_version_file_raises(self, tmp_path: Path) -> None:
        registry = PromptRegistry(prompts_dir=tmp_path)
        # Empty manifest → unknown prompt.
        with pytest.raises((ValueError, FileNotFoundError)):
            registry.render("anything", version="v1")
