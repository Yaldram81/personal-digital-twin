from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal, cast

from pdt.core.llm import PromptRegistry
from pdt.core.llm.base import LLMClient
from pdt.core.schemas import Domain, ReasoningTrace, TraceFactor


@dataclass(frozen=True)
class ExtractionResult:
    trace: ReasoningTrace
    support_flags: list[str]
    prompt_id: str
    prompt_version: str
    raw_text_hash: str
    model_id: str


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_json_object(raw: str) -> dict[str, Any]:
    try:
        return cast(dict[str, Any], json.loads(raw))
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            raise ValueError("LLM returned malformed JSON") from None
        return cast(dict[str, Any], json.loads(match.group(0)))


def _support_flags(narration: str, options: list[str], factors: list[dict[str, Any]]) -> list[str]:
    flags: list[str] = []
    text = narration.lower()
    if len(options) < 2 and "counterfactual" not in text:
        flags.append("insufficient_options")
    for factor in factors:
        factor_text = str(factor.get("factor", "")).strip().lower()
        if factor_text and factor_text not in text:
            flags.append("low_support_factor")
            break
    if not factors:
        flags.append("missing_factors")
    return flags


def extract_trace(
    narration: str,
    llm: LLMClient,
    registry: PromptRegistry | None = None,
    prompt_version: str = "v1",
) -> ExtractionResult:
    if not narration.strip():
        raise ValueError("narration must not be empty")

    prompt_id = "reasoning_trace_extraction"
    reg = registry or PromptRegistry()
    prompt = reg.render(prompt_id, version=prompt_version, narration=narration)
    response = llm.complete(
        [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": prompt},
        ]
    )
    parsed = _parse_json_object(response.text)

    options = parsed.get("options_detected", [])
    if not isinstance(options, list):
        raise ValueError("options_detected must be a list")
    factors = parsed.get("factors", [])
    if not isinstance(factors, list):
        raise ValueError("factors must be a list")

    flags = _support_flags(narration, [str(o) for o in options], factors)
    low_signal = "missing_factors" in flags or (
        len(options) < 2 and "counterfactual" not in narration.lower()
    )
    if not factors:
        raise ValueError("extraction produced no factors")

    domain_value = str(parsed.get("domain", "cross_domain")).lower()
    try:
        domain = Domain(domain_value)
    except ValueError:
        domain = Domain.CROSS_DOMAIN

    normalized_factors: list[TraceFactor] = []
    for item in factors:
        weight = str(item["weight"]).upper()
        if weight not in {"HIGH", "MEDIUM", "LOW"}:
            raise ValueError("factor weight must be HIGH, MEDIUM, or LOW")
        normalized_factors.append(
            TraceFactor(
                factor=str(item["factor"]),
                weight=cast(Literal["HIGH", "MEDIUM", "LOW"], weight),
                direction=str(item.get("direction", "toward_unknown")),
                explicitly_discounted=bool(item.get("explicitly_discounted", False)),
            )
        )

    trace = ReasoningTrace(
        id=_sha256_text(narration)[:16],
        timestamp=date.today(),
        domain=domain,
        context=str(parsed.get("context") or narration[:160]),
        options=[str(o) for o in options],
        factors_cited=normalized_factors,
        chosen_option=str(parsed.get("chosen", "")),
        stated_reasons=narration,
        inferred_values=[str(v) for v in parsed.get("inferred_values", [])],
        low_signal=low_signal,
    )

    return ExtractionResult(
        trace=trace,
        support_flags=flags,
        prompt_id=prompt_id,
        prompt_version=prompt_version,
        raw_text_hash=_sha256_text(narration),
        model_id=response.model,
    )


def build_extraction_event(result: ExtractionResult, raw_text: str) -> dict[str, Any]:
    return {
        "trace_id": result.trace.id,
        "prompt_id": result.prompt_id,
        "prompt_version": result.prompt_version,
        "model_id": result.model_id,
        "raw_text_hash": result.raw_text_hash,
        "raw_text": raw_text,
        "extracted": result.trace.model_dump(mode="json"),
        "support_flags": result.support_flags,
        "created_at": datetime.now(UTC).isoformat(),
    }
