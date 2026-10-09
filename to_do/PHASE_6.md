# Phase 6 — Evaluation, Privacy Hardening & Generalization

> Blueprint §8 Phase 4 (Months 18+) and §4.3, §9, §10. The system becomes *trustworthy and proven* — not just functional. We build the **evaluation harness** (the four metrics from §9), close the **outcome-tracking loop** (§4.3), harden **privacy** to production grade (§10), and push the **generalization edges** (cross-domain reasoning, belief-change simulation, long-horizon prediction). This phase is partly open research (blueprint §12) — treat the generalization deliverables as experiments, not certainties.

---

## Goal

(1) An **evaluation framework** that quantitatively measures prediction accuracy + calibration, explanation quality (via user studies / blind A/B), temporal tracking, and real-world trust/use. (2) **Outcome tracking** that closes the training loop from real decision results. (3) **Privacy hardening** to the full §10 spec (encrypted-before-transmit, trusted execution option, granular consent, export/delete verified). (4) **Generalization** experiments: cross-domain reasoning, belief-change simulation, collaborative two-person mode, long-horizon prediction, proactive integration.

## Dependencies

- All prior phases, especially **Phase 5** (predictions to evaluate + feedback channel) and **Phase 4** (calibration recorder to operationalize).

## Scope

**In scope**
- **Evaluation harness** (§9): held-out trace prediction accuracy, calibration curves, explanation-recognition (blind A/B), temporal-tracking, trust/use behavioral metrics.
- **Outcome tracking** (§4.3): users report decision outcomes + retrospective assessment; feeds back as reward/correction signal into IRL & fusion.
- **Privacy hardening** (§10): encrypt-before-transmit to cloud LLM, TEE option, per-data-type granular consent, verified export + complete deletion, no-shared-model guarantee tested.
- **Cross-domain reasoning** (§8-P4): decisions spanning career+relationships+finances; combine contextual weights + cross-domain tradeoffs.
- **Belief-change simulation** (§8-P4): "if you changed this core belief, how would your decisions shift?" — counterfactual over the belief graph.
- **Collaborative twin mode** (§8-P4): model how two people's reasoning interact for joint decisions.
- **Long-horizon prediction** (§8-P4): "how is your thinking on X likely to evolve?" — extrapolate drift trajectories (explicitly uncertain).
- **Proactive integration** (§8-P4): surface relevant predictions from calendar/documents context (opt-in, privacy-sensitive).

**Out of scope / research**
- Settling the open questions in blueprint §12 (stability models, behavioral-vs-self-report conditions, sample-efficiency curve) — these are investigated *via* the eval harness, not "completed."
- Full multi-tenant architecture (PROJECT_INTENT defers this; single-user first).

## Deliverables

- `eval/harness.py`: run all §9 metrics; produce a report (accuracy, precision/recall, calibration curve, recognition score).
- `eval/holdout.py`: train/test split over traces; leave-one-out for small N.
- `eval/explanation_study.py`: blind A/B scaffolding (twin answer vs generic LLM answer, user picks "which sounds more like me").
- `ingest/outcome_tracker.py`: outcome reports → reward/correction signal into IRL (Phase 3) + fusion (Phase 2).
- `core/crypto/transport.py`: encrypt-before-transmit; TEE integration path (or documented stub if no TEE available locally).
- `core/consent.py`: per-data-type consent store; gate telemetry/export.
- `engine/queries/crossdomain.py`, `belief_change.py`, `collaborative.py`, `longhorizon.py`.
- `integration/proactive.py`: opt-in calendar/doc context surface.
- Reports/dashboards for each §9 metric.

## Tasks

1. **Hold-out evaluation.** Given the trace library, hold out K traces, train the model on the rest, predict the held-out `chosen`, measure precision/recall + **calibration** (reliability diagram from Phase 4). *AC: report runs end-to-end; accuracy and Expected Calibration Error (ECE) are reported; misses correlate with wide-CI/data-sparse params (blueprint §9 expects this).*
2. **Explanation recognition study.** Blind A/B: for a sample of queries, show the user the twin's answer and a generic-LLM answer, ask "which sounds more like how you'd reason?" *AC: study scaffold exists; twin wins at a rate above chance; recognition score reported (blueprint §9 target).*
3. **Temporal tracking metric.** Compare twin predictions made at the start vs end of a window; accuracy should improve as data accrues. *AC: metric computed over a longitudinal fixture or real rolling data; improvement is demonstrable.*
4. **Trust & use behavioral metric.** Instrument (consented) whether users consult the twin for real decisions and whether they accept its predictions. *AC: dashboard shows consult-rate and accept-rate; consent-gated per `MODEL_BEHAVIOR_RULES`/§10.*
5. **Outcome tracking loop.** User reports "I took the startup job; 6 months in I feel X." → stored as outcome; X feeds IRL as reward and fusion as correction; if regret, the model learns it under-weighted something (§4.3). *AC: a regretted decision widens the CI on the relevant params and shifts inferred weights on a re-fit.*
6. **Encrypt-before-transmit.** Personal-model context is encrypted before sending to a cloud LLM; document the TEE decryption path; if no TEE, document the residual trust assumption honestly. *AC: a network capture shows the personal context is not plaintext on the wire; decryption happens only in the documented trust boundary.*
7. **Granular consent + telemetry gating.** Per-data-type consent (traces, beliefs, values, outcomes, usage); telemetry off by default; export/delete verified to remove each consented category. *AC: revoking consent for "outcomes" stops their collection and purges existing; deletion removes all categories and leaves only an append-only audit tombstone.*
8. **Export/delete verification.** Automated test that export is complete+decryptable and that delete leaves no recoverable personal data (only audit tombstones). *AC: test passes; this is the §10 guarantee proven, not promised.*
9. **Cross-domain reasoning.** Combine contextual weights across domains + the cross-domain tradeoff vector (Phase 2) for multi-domain decisions. *AC: a "should I move cities for this job?" query (career+relationships+finances) pulls all three and reasons across them; uncertainty is wider (composition of domains).*
10. **Belief-change simulation.** Counterfactual over the belief graph: perturb one core belief, re-simulate decisions, show the downstream shift. *AC: output is clearly hypothetical, cites the perturbed belief, and is honestly uncertain (it's extrapolation).*
11. **Collaborative two-person mode.** Load two models, simulate interaction/joint decision. *AC: two fixture personas produce a joint-decision simulation; dominance/tradeoff dynamics are visible.*
12. **Long-horizon prediction.** Extrapolate drift trajectories (Phase 4) forward; heavily caveated. *AC: output is framed as speculative, with widening CIs over the horizon.*
13. **Proactive integration (opt-in).** From calendar/doc context, surface a relevant twin prediction (e.g., ahead of a decision-bearing meeting). *AC: opt-in only; surfaces are privacy-gated; user can dismiss.*

## Data models / schemas

```python
class Outcome(BaseModel):
    prediction_id: str | None
    trace_id: str
    actual_choice: str | None
    retrospective: Literal["satisfied","neutral","regret"] | None
    free_text: str | None
    timestamp: datetime

class EvalReport(BaseModel):
    accuracy: float
    precision: float
    recall: float
    ece: float                       # expected calibration error
    recognition_score: float | None  # blind A/B win rate
    misses_vs_ci: float              # correlation of misses with wide-CI params
```

## Interfaces

- `eval.run_holdout(k) -> EvalReport`.
- `ingest.outcome_tracker.record(outcome)`.
- `engine.queries.crossdomain.answer(...)`, `.belief_change`, `.collaborative`, `.longhorizon`.
- `core.consent.{grant,revoke,status}(data_type)`.
- `core.crypto.transport.encrypt_for_llm(context)`.

## Blueprint & context references

- Blueprint §4.3 (Outcome Tracking), §9 (Evaluation Framework — all four metrics), §10 (Privacy Architecture — full spec), §8 Phase 4 (generalization deliverables), §12 (open research questions investigated via the harness).
- `PROJECT_INTENT.md` — success definition (retrieve accurately, match style, predict, improve over time) is *measured* here.
- `EVALUATION_METRICS.md` — the thresholds (recall >75%, consistency >80%, latency <2s, precision@K) become CI gates.
- `MODEL_BEHAVIOR_RULES.md` / `FAILURE_MODES.md` — every failure mode now has a metric watching for it.

## Exit criteria (definition of done)

- [ ] Eval harness reports accuracy, precision/recall, **calibration (ECE)**, recognition score; misses correlate with wide-CI params.
- [ ] `EVALUATION_METRICS.md` thresholds met on a real dataset (recall >75%, consistency >80%, p95 latency <2s) OR a documented gap with a plan.
- [ ] Outcome tracking closes the loop: a regretted decision measurably updates the model.
- [ ] Privacy §10 guarantees **verified by test**, not promised: encrypt-before-transmit, granular consent, complete export, verified deletion.
- [ ] Cross-domain reasoning produces sensibly-wider-uncertainty multi-domain answers.
- [ ] Belief-change simulation is clearly hypothetical and uncertainty-honest.
- [ ] Collaborative mode and long-horizon prediction exist as documented experiments (success not guaranteed — blueprint §12).
- [ ] All gates green; privacy tests are non-blocking CI (privacy regressions fail the build).

## Risks & mitigations

| Risk | Source | Mitigation |
|------|--------|------------|
| Overconfident/under-calibrated predictions slip through | blueprint §7.4, §9 | ECE as a first-class metric; calibration feedback loop from Phase 4/5; recalibration on a rolling window. |
| Privacy regression (plaintext on wire, incomplete delete) | blueprint §10 | Automated privacy tests in CI; network-capture test; deletion-completeness test. |
| Generalization overclaims (belief-change, long-horizon) | blueprint §12 (open research) | Frame as experiments; widening CIs; never present extrapolation as prediction. |
| Outcome data is sparse / self-selected | blueprint §4.3 | Low-friction capture; don't over-weight sparse outcomes; wide CIs. |
| User studies are slow/expensive | §9 | Start small (n-of-1 author + a few users); the blind A/B is the cheapest strong signal. |
| Trust not earned | §9 | Track accept/consult rate; if low, the model isn't good enough yet — don't ship harder, improve calibration/explanation. |

## Effort estimate

Ongoing. The evaluation harness + outcome loop + privacy hardening is ~6–8 weeks to a solid v1. The generalization deliverables are research — budget them as separate experimental tracks that may or may not graduate into the product, exactly as blueprint §12 frames them. The honest measure of "done" for this phase is: **the system is right when it says it's right, says when it's not, keeps the user's data as the user's, and earns trust through accuracy rather than asserting it.**
