from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import mean, variance


@dataclass(frozen=True)
class BOCPDResult:
    posterior: list[float]
    run_length_dist: list[float]
    most_likely_index: int | None
    detected: bool
    confidence: float
    effect_size: float
    hazard: float


@dataclass(frozen=True)
class NormalGammaState:
    mean: float
    kappa: float
    alpha: float
    beta: float


def _student_t_log_pdf(x: float, state: NormalGammaState) -> float:
    dof = max(2.0 * state.alpha, 1e-6)
    scale_sq = state.beta * (state.kappa + 1.0) / max(state.alpha * state.kappa, 1e-6)
    scale_sq = max(scale_sq, 1e-6)
    centered = (x - state.mean) ** 2 / (dof * scale_sq)
    return (
        math.lgamma((dof + 1.0) / 2.0)
        - math.lgamma(dof / 2.0)
        - 0.5 * math.log(dof * math.pi * scale_sq)
        - ((dof + 1.0) / 2.0) * math.log1p(centered)
    )


def _gaussian_log_pdf(x: float, state: NormalGammaState) -> float:
    variance_est = state.beta / max(state.alpha - 1.0, 1e-6)
    predictive_var = max(variance_est * (1.0 + 1.0 / max(state.kappa, 1e-6)), 1e-6)
    return -0.5 * (
        math.log(2.0 * math.pi * predictive_var) + ((x - state.mean) ** 2) / predictive_var
    )


def _predictive_log_prob(x: float, state: NormalGammaState, likelihood: str) -> float:
    if likelihood == "student_t":
        return _student_t_log_pdf(x, state)
    return _gaussian_log_pdf(x, state)


def _update_state(state: NormalGammaState, x: float) -> NormalGammaState:
    new_kappa = state.kappa + 1.0
    mean_delta = x - state.mean
    new_mean = ((state.kappa * state.mean) + x) / new_kappa
    new_alpha = state.alpha + 0.5
    new_beta = state.beta + ((state.kappa * mean_delta * mean_delta) / (2.0 * new_kappa))
    return NormalGammaState(new_mean, new_kappa, new_alpha, new_beta)


def _logsumexp(values: list[float]) -> float:
    finite = [value for value in values if value != float("-inf")]
    if not finite:
        return float("-inf")
    anchor = max(finite)
    return anchor + math.log(sum(math.exp(value - anchor) for value in finite))


def _default_prior(series: list[float]) -> NormalGammaState:
    center = mean(series) if series else 0.5
    spread = variance(series) if len(series) > 1 else 0.05
    return NormalGammaState(mean=center, kappa=1.0, alpha=2.0, beta=max(spread, 1e-3))


def run_bocpd(
    series: list[float],
    hazard: float = 0.03,
    likelihood: str = "gaussian",
    min_segment: int = 5,
) -> BOCPDResult:
    if not series:
        return BOCPDResult([], [], None, False, 0.0, 0.0, hazard)

    prior = _default_prior(series)
    max_run = len(series)
    run_log_probs = [float("-inf")] * (max_run + 1)
    run_log_probs[0] = 0.0
    state_by_run = [prior]

    changepoint_posterior = [0.0] * len(series)
    final_run_dist = [0.0] * len(series)

    for time_index, observation in enumerate(series):
        next_log_probs = [float("-inf")] * (max_run + 1)
        predictive_logs = [
            _predictive_log_prob(observation, state, likelihood)
            for state in state_by_run
        ]

        cp_terms: list[float] = []
        for run_length, (log_prob, pred_log) in enumerate(
            zip(run_log_probs[: len(state_by_run)], predictive_logs, strict=True)
        ):
            if log_prob == float("-inf"):
                continue
            growth_log = log_prob + math.log(max(1.0 - hazard, 1e-9)) + pred_log
            next_log_probs[run_length + 1] = growth_log
            cp_terms.append(log_prob + math.log(max(hazard, 1e-9)) + pred_log)

        next_log_probs[0] = _logsumexp(cp_terms)
        normalizer = _logsumexp(next_log_probs[: time_index + 2])
        if normalizer == float("-inf"):
            continue

        normalized = [value - normalizer for value in next_log_probs[: time_index + 2]]
        run_log_probs = normalized + [float("-inf")] * (max_run - time_index - 1)
        changepoint_posterior[time_index] = math.exp(run_log_probs[0])

        next_states = [_update_state(prior, observation)]
        next_states.extend(_update_state(state, observation) for state in state_by_run)
        state_by_run = next_states[: time_index + 2]

        if time_index == len(series) - 1:
            final_run_dist = [math.exp(value) for value in run_log_probs[: len(series)]]
            total = sum(final_run_dist) or 1.0
            final_run_dist = [value / total for value in final_run_dist]

    candidate_indices = list(range(min_segment - 1, len(series) - min_segment))
    if not candidate_indices:
        return BOCPDResult(changepoint_posterior, final_run_dist, None, False, 0.0, 0.0, hazard)

    posterior_scores = changepoint_posterior[:]
    overall_std = math.sqrt(variance(series)) if len(series) > 1 else 0.0
    for idx in candidate_indices:
        left = series[: idx + 1]
        right = series[idx + 1 :]
        if not left or not right:
            continue
        mean_gap = abs(mean(right) - mean(left))
        effect_size = mean_gap / max(overall_std, 0.05)
        posterior_scores[idx] *= 1.0 + min(effect_size, 5.0)

    best_index = max(candidate_indices, key=posterior_scores.__getitem__)
    confidence = min(1.0, posterior_scores[best_index])

    left = series[: best_index + 1]
    right = series[best_index + 1 :]
    mean_gap = abs(mean(right) - mean(left)) if left and right else 0.0
    effect_size = mean_gap / max(overall_std, 0.05)
    detected = confidence >= 0.08 and effect_size >= 1.0

    return BOCPDResult(
        posterior=posterior_scores,
        run_length_dist=final_run_dist,
        most_likely_index=best_index + 1 if detected else None,
        detected=detected,
        confidence=confidence,
        effect_size=effect_size,
        hazard=hazard,
    )


__all__ = [
    "BOCPDResult",
    "NormalGammaState",
    "run_bocpd",
]
