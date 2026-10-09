from __future__ import annotations

import json

import pytest

from pdt.core.schemas import Domain
from pdt.extraction.trace_extractor import build_extraction_event, extract_trace


class StubLLM:
    def __init__(self, text: str, model: str = "stub-model") -> None:
        self._text = text
        self._model = model

    def complete(self, messages, model=None, temperature=0.0, max_tokens=None):  # type: ignore[no-untyped-def]
        class Resp:
            def __init__(self, text: str, model_name: str) -> None:
                self.text = text
                self.model = model_name
                self.provider = "mock"
                self.usage = {}

        return Resp(self._text, model or self._model)

    def embed(self, texts, model=None):  # type: ignore[no-untyped-def]
        return [[0.0] * 16 for _ in texts]


def test_extract_trace_falls_back_to_embedded_json() -> None:
    llm = StubLLM(
        'prefix {"domain":"career","options_detected":["a","b"],"chosen":"a","factors":[{"factor":"learning","weight":"HIGH","direction":"toward_a"}],"inferred_values":["self_direction"]} suffix'
    )
    result = extract_trace("I chose a over b because of learning.", llm)
    assert result.trace.domain == Domain.CAREER
    assert result.trace.chosen_option == "a"


def test_extract_trace_rejects_non_list_options() -> None:
    llm = StubLLM(
        json.dumps(
            {
                "domain": "career",
                "options_detected": "not-a-list",
                "chosen": "a",
                "factors": [{"factor": "learning", "weight": "HIGH", "direction": "toward_a"}],
            }
        )
    )
    with pytest.raises(ValueError, match="options_detected must be a list"):
        extract_trace("I chose a because of learning.", llm)


def test_extract_trace_rejects_non_list_factors() -> None:
    llm = StubLLM(
        json.dumps(
            {
                "domain": "career",
                "options_detected": ["a", "b"],
                "chosen": "a",
                "factors": "not-a-list",
            }
        )
    )
    with pytest.raises(ValueError, match="factors must be a list"):
        extract_trace("I chose a because of learning.", llm)


def test_extract_trace_rejects_invalid_weight() -> None:
    llm = StubLLM(
        json.dumps(
            {
                "domain": "career",
                "options_detected": ["a", "b"],
                "chosen": "a",
                "factors": [{"factor": "learning", "weight": "EXTREME", "direction": "toward_a"}],
            }
        )
    )
    with pytest.raises(ValueError, match="factor weight must be HIGH, MEDIUM, or LOW"):
        extract_trace("I chose a because of learning.", llm)


def test_extract_trace_uses_cross_domain_on_invalid_domain() -> None:
    llm = StubLLM(
        json.dumps(
            {
                "domain": "unknown_domain",
                "options_detected": ["a", "b"],
                "chosen": "a",
                "factors": [{"factor": "learning", "weight": "HIGH", "direction": "toward_a"}],
            }
        )
    )
    result = extract_trace("I chose a because of learning.", llm)
    assert result.trace.domain == Domain.CROSS_DOMAIN


def test_build_extraction_event_contains_raw_text_and_flags() -> None:
    llm = StubLLM(
        json.dumps(
            {
                "domain": "career",
                "options_detected": ["a", "b"],
                "chosen": "a",
                "factors": [{"factor": "missing_factor", "weight": "HIGH", "direction": "toward_a"}],
            }
        )
    )
    narration = "I chose a over b."
    result = extract_trace(narration, llm)
    event = build_extraction_event(result, narration)
    assert event["raw_text"] == narration
    assert event["raw_text_hash"]
    assert event["model_id"] == "stub-model"
    assert "support_flags" in event


def test_extract_trace_rejects_malformed_json_without_object() -> None:
    llm = StubLLM("not json at all")
    with pytest.raises(ValueError, match="malformed JSON"):
        extract_trace("I chose a over b.", llm)
