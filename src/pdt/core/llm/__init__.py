"""LLM abstraction layer.

Per CODING_STANDARDS.md: all LLM calls go through this single layer.
No module outside ``core.llm`` may import a provider SDK directly.
"""

from pdt.core.llm.base import LLMClient, LLMResult, create_client
from pdt.core.llm.mock_client import MockLLMClient
from pdt.core.llm.openai_client import OpenAILLMClient
from pdt.core.llm.registry import PromptRegistry, default_registry, render

__all__ = [
    "LLMClient",
    "LLMResult",
    "MockLLMClient",
    "OpenAILLMClient",
    "PromptRegistry",
    "create_client",
    "default_registry",
    "render",
]
