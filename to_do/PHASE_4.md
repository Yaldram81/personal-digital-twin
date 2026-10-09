# Phase 4 — Temporal Drift Detection & Uncertainty Propagation

> Blueprint §5.3, §5.4, §7.3. The system gains a *sense of time*. Every parameter is now a time series, and we answer two questions: **has this part of you genuinely changed?** (Bayesian change-point detection) and **how sure is the whole prediction, given the uncertainty of its inputs?** (uncertainty propagation). This is what stops the twin from confidently claiming you've "changed" based on a noisy week — or confidently simulating you in a domain where it's guessing.

---

## Goal

(1) **Temporal drift detection** via BOCPD (Adams & MacKay, 2007) on every parameter's estimate history, classifying parameters into stability tiers and flagging genuine inflection points vs noise. (2) **Uncertainty propagation** through the prediction logic, so any downstream output (Phase 5) carries a calibrated uncertainty score derived from its inputs' CIs. (3) **Stability-tier-aware smoothing** so core values resist short-term noise while surface attitudes update quickly.

## Dependencies

- **Phase 2**: append-only parameter store (the time series source), CI math.
- **Phase 3** (recommended, can run parallel): IRL-inferred values + belief stability tiers feed drift detection.
- Provides calibrated uncertainty inputs to **Phase 5**.

## Scope

**In scope**
- **Drift log** as a first-class artifact (§3.5): per-parameter time series with detected inflection points, trend, rate of change.
- **BOCPD** implementation (§5.3): run on each parameter; emit changepoint posterior + most-likely run-length.
- **Stability tier classification** (§5.3): core values / situational preferences / surface attitudes; tiers drive smoothing aggressiveness and update rates.
- **Major life event detection** (§7.3): infer periods of likely fundamental change from conversation topic/emotional-valence/domain shifts; upweight recent observations during such windows.
- **Uncertainty propagation** (§5.4): compose CIs across model components into a single prediction-uncertainty score (analytic where possible, Monte Carlo/bootstrap otherwise).
- **Calibration tracking**: maintain a calibration curve per output type (when the system says "80% confident", is it right ~80% of the time?).

**Out of scope**
- The query engine that *consumes* uncertainty (Phase 5) — but the propagation API is defined here and stub-tested.
- Outcome-based re-calibration of the whole model (Phase 6 closes that loop).

## Deliverables

- `inference/drift.py`: BOCPD runner, stability-tier classifier, smoothing policy.
- `inference/changepoint.py`: the BOCPD core (or a vetted library wrapper) with a configurable hazard function and likelihood model.
- `inference/uncertainty.py`: propagate `list[ScoredScalar]` + composition fn → `ConfidenceInterval`; Monte Carlo fallback for non-linear compositions.
- `inference/calibration.py`: calibration curve tracking + reliability diagram output.
- `memory/drift_log.py`: §3.5 `DriftLog` read views + inflection annotation.
- API: `GET /model/drift/{param}`, `GET /model/drift` (summary), `GET /model/calibration`.
- Tests: BOCPD recovers an injected changepoint on synthetic series; smoothing suppresses noise on a core value; uncertainty propagation matches analytic expectation on linear compositions.

## Tasks

1. **Drift log views.** Read the Phase 2 append-only store as a per-parameter time series; materialize §3.5 `DriftLog` records (history, trend, rate_of_change). *AC: `/model/drift/risk_tolerance` returns the documented structure.*
2. **Implement BOCPD.** Gaussian likelihood + constant hazard (geometric run-length prior) as the baseline; allow a Student-t likelihood for robustness to outliers. *AC: on a synthetic series with a known mean-shift at t=50, the run-length posterior collapses near t=50 and the most-probable changepoint is within ±5 steps; pure-noise series does NOT flag a changepoint (false-positive rate controlled).*
3. **Stability tier classifier.** Map parameters to tiers using a config (core: Schwartz core values + deep moral intuitions; situational: domain preferences; surface: stated attitudes). Tiers set smoothing strength and the rate at which new evidence moves the estimate. *AC: a core value with 3 anomalous traces barely moves; a surface attitude with the same moves noticeably.*
4. **Smoothing policy.** Exponentially-weighted / Kalman-style update per tier; core = strong smoothing + high inertia, surface = responsive. *AC: noise-injection test shows core values drift less than surface attitudes under identical perturbation.*
5. **Major life event windows.** Heuristic detector over conversation signals (domain-shift burst, emotional-valence shift, new decision domains appearing) → marks a time window where recent evidence is upweighted. *AC: a synthetic "event" (sudden domain shift) widens the upweight window; outside it, normal weighting resumes.*
6. **Uncertainty propagation.** For a composition f(x1..xn) with each xi a `ScoredScalar`: linear case → analytic CI; non-linear → Monte Carlo sampling of xi within their CIs, propagate through f, report output distribution. *AC: on f=x1+x2 (linear), propagated CI matches analytic; on f=x1*x2, Monte Carlo CI is wider and matches a brute-force grid.*
7. **Calibration tracking.** Record (predicted_confidence, was_correct) for each verifiable output (starts in Phase 5, but the recorder + reliability diagram exists now on synthetic verdicts). *AC: on synthetic perfectly-calibrated data the reliability curve is diagonal; intentionally-overconfident data bends it down.*
8. **Wire uncertainty into the (future) prediction contract.** Define `Prediction` = `{result, confidence, contributing_params: list[(param, weight, ci)], extrapolation_flags}`. Phase 5 fills `result`; Phase 4 owns the rest. *AC: a stub prediction with 2 high-CI inputs yields a wider output CI than one with low-CI inputs.*

## Data models / schemas

Reuse Phase 0 `DriftLog`, `DriftLogEntry`. Add:

```python
class ChangePointResult(BaseModel):
    param: str
    most_likely_t: datetime | None
    posterior: list[float]        # P(changepoint at t) over the series
    run_length_dist: list[float]
    detected: bool
    confidence: float

class Prediction(BaseModel):
    result: Any                   # filled by Phase 5
    confidence: float
    contributing_params: list[Contribution]
    extrapolation_flags: list[str]  # e.g. "data_sparse_domain"

class Contribution(BaseModel):
    param: str
    weight: float
    ci: ConfidenceInterval
```

## Interfaces

- `inference.drift.analyze(param) -> ChangePointResult`.
- `inference.drift.tier(param) -> StabilityTier`.
- `inference.uncertainty.propagate(contributions) -> ConfidenceInterval`.
- `inference.calibration.record(prediction_id, confidence, correct)`; `.reliability_diagram()`.

## Blueprint & context references

- Blueprint §3.5 (Temporal Drift Log), §5.3 (Temporal Drift Detection), §5.4 (Uncertainty Propagation), §7.3 (Temporal Personality Drift — 3 mechanisms), §7.4 (Uncertainty Estimation), §9 (calibration curve).
- `MODEL_BEHAVIOR_RULES.md` — "If confidence < threshold → fallback" now has *real* propagated confidence behind it.
- `FAILURE_MODES.md` — "over-reliance on recent data" (smoothing + tiers mitigate); overconfidence (calibration + propagation mitigate).

## Exit criteria (definition of done)

- [ ] BOCPD recovers injected changepoints on synthetic series with controlled false-positive rate on pure noise.
- [ ] Stability tiers demonstrably change smoothing behavior (core resists noise, surface responds).
- [ ] Major life-event windows upweight recent evidence and then decay.
- [ ] Uncertainty propagation matches analytic CIs on linear compositions and is sensibly wider on non-linear ones (Monte Carlo).
- [ ] Calibration recorder + reliability diagram work on synthetic data.
- [ ] `/model/drift/{param}` returns the full §3.5 structure with detected inflections.
- [ ] All gates green; BOCPD + propagation have unit tests on synthetic + edge cases.

## Risks & mitigations

| Risk | Source | Mitigation |
|------|--------|------------|
| Overclaiming personality change from noise | blueprint §7.3 | Tiers + smoothing + changepoint detection; require sustained shift, not a spike. |
| BOCPD false positives | — | Conservative hazard; require posterior threshold; tier-dependent sensitivity. |
| Uncertainty propagation is wrong → over/underconfidence | blueprint §7.4 | Monte Carlo cross-check on analytic paths; calibration curve as the ground-truth check (fully exploited in Phase 6). |
| Computational cost of per-parameter BOCPD | — | Run lazily/nightly, cache run-length posteriors, incremental updates. |
| Stale calibration | — | Calibration is a moving target; recompute on a rolling window (Phase 6 operationalizes). |

## Effort estimate

~5–7 weeks. BOCPD correctness + calibration discipline are subtle; the synthetic-test gate ("recovers known changepoints, ignores pure noise") is non-negotiable before trusting it on a real person's model.
