from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from pdt.core.llm import PromptRegistry
from pdt.core.llm.base import LLMClient
from pdt.core.schemas import Domain


@dataclass(frozen=True)
class BehavioralSignal:
    param: str
    domain: Domain
    direction: Literal["increase", "decrease", "neutral"]
    magnitude: float
    weight: float
    evidence_ref: str
    extractor_id: str
    extractor_version: str
    timestamp: datetime


def _message_ref(message: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(message, sort_keys=True).encode("utf-8")).hexdigest()[:16]


CATEGORY_PARAM_MAP: dict[str, str] = {
    "topic_initiation": "information_seeking",
    "pushback": "reasoning_mode",
    "abstract_framing": "construal_level",
    "real_issue_disambiguation": "information_seeking",
    "contradiction": "ambiguity_tolerance",
    "risk_language": "risk_tolerance",
}


def _coerce_domain(value: str) -> Domain:
    try:
        return Domain(value)
    except ValueError:
        return Domain.CROSS_DOMAIN


def mine_conversation(
    messages: list[dict[str, str]],
    llm: LLMClient,
    registry: PromptRegistry | None = None,
    prompt_version: str = "v1",
) -> list[BehavioralSignal]:
    if not messages:
        return []
    reg = registry or PromptRegistry()
    conversation = "\n".join(f"{m.get('role', 'user')}: {m.get('content', '')}" for m in messages)
    prompt = reg.render("conversation_mining", version=prompt_version, conversation=conversation)
    response = llm.complete(
        [
            {"role": "system", "content": "Return only valid JSON."},
            {"role": "user", "content": prompt},
        ]
    )
    data = cast(list[dict[str, Any]], json.loads(response.text))
    refs = [_message_ref(message) for message in messages]
    message_text = conversation.lower()
    signals: list[BehavioralSignal] = []
    for index, item in enumerate(data):
        category = str(item.get("category", ""))
        param = str(item.get("param") or CATEGORY_PARAM_MAP.get(category, ""))
        if not param:
            continue
        evidence_ref = str(item.get("evidence_ref") or refs[min(index, len(refs) - 1)])
        direction = str(item.get("direction", "neutral"))
        if direction not in {"increase", "decrease", "neutral"}:
            direction = "neutral"
        signal = BehavioralSignal(
            param=param,
            domain=_coerce_domain(str(item.get("domain", "cross_domain"))),
            direction=cast(Literal["increase", "decrease", "neutral"], direction),
            magnitude=max(0.0, min(1.0, float(item.get("magnitude", 0.0)))),
            weight=max(0.1, min(0.3, float(item.get("weight", 0.1)))),
            evidence_ref=evidence_ref,
            extractor_id="conversation_mining",
            extractor_version=prompt_version,
            timestamp=datetime.now(UTC),
        )
        param_tokens = set(param.lower().split("_"))
        if signal.evidence_ref in refs or any(token in message_text for token in param_tokens):
            signals.append(signal)
            continue
        lexical_support = str(item.get("lexical_support", "")).lower()
        if lexical_support and lexical_support in message_text:
            signals.append(signal)
    return signals
