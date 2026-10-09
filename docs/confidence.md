# Confidence intervals

Phase 2 models confidence as a CI half-width derived from three factors:

- `n`: more evidence shrinks uncertainty.
- `consistency`: higher variance across evidence widens uncertainty.
- `recency_decay`: stale evidence widens uncertainty.

## Formula

For a set of parameter estimates with values in `[0, 1]`:

- `mean = weighted_mean(values)`
- `variance = weighted_variance(values)`
- `consistency = max(0, 1 - variance)`
- `effective_n = sum(weights)`
- `base_half_width = 0.5 / sqrt(max(effective_n, 1))`
- `consistency_penalty = 1 + (1 - consistency)`
- `recency_penalty = 1 + recency_decay`
- `ci_half_width = clamp(base_half_width * consistency_penalty * recency_penalty, 0, 1)`

This is intentionally simple and monotonic:
- more consistent evidence narrows the interval
- more evidence narrows the interval
- older evidence widens the interval

The implementation uses this deterministic heuristic instead of a heavier Bayesian package so it remains explainable and easy to validate in tests.
