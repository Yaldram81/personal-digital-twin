from __future__ import annotations

import json
from pathlib import Path

from pdt.extraction.trace_extractor import extract_trace


class FixtureLLM:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def complete(self, messages, model=None, temperature=0.0, max_tokens=None):  # type: ignore[no-untyped-def]
        class Resp:
            def __init__(self, text: str) -> None:
                self.text = text
                self.model = "fixture-llm"
                self.provider = "mock"
                self.usage = {}

        return Resp(json.dumps(self._payload))

    def embed(self, texts, model=None):  # type: ignore[no-untyped-def]
        return [[0.0] * 16 for _ in texts]


def test_gold_fixtures_match_expected_chosen_and_top_factors() -> None:
    fixture_dir = Path("tests/fixtures")
    fixture_paths = sorted(fixture_dir.glob("trace_fixture_*.json"))
    assert len(fixture_paths) >= 5

    matches = 0
    for path in fixture_paths:
        fixture = json.loads(path.read_text(encoding="utf-8"))
        result = extract_trace(fixture["narration"], FixtureLLM(fixture["llm_output"]))
        chosen_ok = result.trace.chosen_option == fixture["expected_chosen"]
        factor_names = [factor.factor for factor in result.trace.factors_cited[:2]]
        factors_ok = factor_names == fixture["expected_top_factors"]
        if chosen_ok and factors_ok:
            matches += 1

    assert matches >= 4
