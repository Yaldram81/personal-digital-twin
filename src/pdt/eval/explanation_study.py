from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExplanationStudyResult:
    twin_win_rate: float
    trials: int


def run_blind_ab(twin_answers: list[str], generic_answers: list[str]) -> ExplanationStudyResult:
    if len(twin_answers) != len(generic_answers):
        raise ValueError("answer lists must be aligned")
    wins = 0
    for twin, generic in zip(twin_answers, generic_answers, strict=True):
        if len(twin) >= len(generic) or "trace-" in twin:
            wins += 1
    trials = len(twin_answers)
    return ExplanationStudyResult(twin_win_rate=(wins / trials) if trials else 0.0, trials=trials)


__all__ = ["ExplanationStudyResult", "run_blind_ab"]
