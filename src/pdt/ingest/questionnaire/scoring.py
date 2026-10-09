from __future__ import annotations

from datetime import date

from pdt.core.schemas import EvidenceSource, EvidenceStrength, ScoredScalar
from pdt.ingest.questionnaire.instruments import INSTRUMENTS, QuestionnaireInstrument

PRIOR_CONFIDENCE = 0.25


def _normalize_response(value: int, min_value: int, max_value: int, reverse_scored: bool) -> float:
    if value < min_value or value > max_value:
        raise ValueError(f"response out of range: expected {min_value}-{max_value}, got {value}")
    if max_value == min_value:
        raise ValueError("invalid questionnaire scale")
    normalized = (value - min_value) / (max_value - min_value)
    return 1.0 - normalized if reverse_scored else normalized


def score_instrument(
    instrument_id: str,
    responses: dict[str, int],
    as_of: date | None = None,
) -> dict[str, ScoredScalar]:
    instrument = INSTRUMENTS.get(instrument_id)
    if instrument is None:
        raise ValueError(f"unknown instrument: {instrument_id}")
    return _score(instrument, responses, as_of=as_of)


def _score(
    instrument: QuestionnaireInstrument,
    responses: dict[str, int],
    as_of: date | None = None,
) -> dict[str, ScoredScalar]:
    today = as_of or date.today()
    by_dimension: dict[str, list[float]] = {}
    for item in instrument.items:
        if item.item_id not in responses:
            raise ValueError(f"missing response for item: {item.item_id}")
        score = _normalize_response(
            responses[item.item_id],
            item.min_value,
            item.max_value,
            item.reverse_scored,
        )
        by_dimension.setdefault(item.dimension, []).append(score)

    result: dict[str, ScoredScalar] = {}
    for dimension, values in by_dimension.items():
        avg = sum(values) / len(values)
        result[dimension] = ScoredScalar(
            value=avg,
            confidence=PRIOR_CONFIDENCE,
            n_observations=len(values),
            last_updated=today,
            source=EvidenceSource.SELF_REPORT,
            evidence_strength=EvidenceStrength.WEAK,
        )
    return result


def score_questionnaire_bundle(
    responses_by_instrument: dict[str, dict[str, int]],
    as_of: date | None = None,
) -> dict[str, dict[str, ScoredScalar]]:
    return {
        instrument_id: score_instrument(instrument_id, responses, as_of=as_of)
        for instrument_id, responses in responses_by_instrument.items()
    }
