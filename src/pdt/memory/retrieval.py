from __future__ import annotations

import json
from dataclasses import dataclass

from pdt.core.llm.base import LLMClient
from pdt.memory.structured.store import DuckDBStructuredStore
from pdt.memory.vector.store import LanceVectorStore


@dataclass(frozen=True)
class RetrievedItem:
    text: str
    score: float
    recency_rank: int


def retrieve_context(
    query: str,
    llm: LLMClient,
    structured_store: DuckDBStructuredStore,
    vector_store: LanceVectorStore,
    domain: str | None,
    top_k: int,
    token_budget: int,
) -> list[RetrievedItem]:
    query_vector = llm.embed([query])[0]
    semantic = vector_store.query(query_vector, top_k=top_k, table_name="traces")
    traces = structured_store.list_traces(domain=domain, limit=top_k * 10)

    reranked: list[RetrievedItem] = []
    query_terms = set(query.lower().split())
    for index, item in enumerate(semantic):
        text = str(item["text"])
        overlap = len(query_terms.intersection(text.lower().split()))
        reranked.append(
            RetrievedItem(
                text=text,
                score=float(overlap) + max(0.0, 1.0 - float(item["score"])),
                recency_rank=index,
            )
        )
    for index, trace in enumerate(traces):
        parsed = json.loads(trace)
        text = str(parsed.get("stated_reasons", ""))
        overlap = len(query_terms.intersection(text.lower().split()))
        reranked.append(
            RetrievedItem(
                text=text,
                score=float(overlap) + max(0.0, 1.0 - (index * 0.02)),
                recency_rank=index,
            )
        )

    reranked.sort(key=lambda item: (item.score, -item.recency_rank), reverse=True)
    selected: list[RetrievedItem] = []
    tokens_used = 0
    seen_texts: set[str] = set()
    for retrieved_item in reranked:
        if retrieved_item.text in seen_texts:
            continue
        approx_tokens = max(1, len(retrieved_item.text.split()))
        if tokens_used + approx_tokens > token_budget:
            continue
        selected.append(retrieved_item)
        seen_texts.add(retrieved_item.text)
        tokens_used += approx_tokens
        if len(selected) >= top_k:
            break
    return selected
