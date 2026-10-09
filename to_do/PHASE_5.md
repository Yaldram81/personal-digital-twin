# Phase 5 — Twin Query Engine & Explanation Generation

> Blueprint §8 Phase 3 (Months 10–18). This is the user-facing capability — the whole point. "How would *I* think about X?" The engine assembles the user's model, simulates their reasoning *as that model* (not as generic advice), propagates uncertainty (from Phase 4) into an explicit confidence flag, and explains the result in the user's own vocabulary with citations to their actual past reasoning. It also closes the training loop with a feedback mechanism.

---

## Goal

A query pipeline handling all six query types (§6.2), producing outputs that (a) read like the user's own reasoning, (b) carry calibrated uncertainty with explicit "I'm extrapolating here" flags, and (c) cite the user's real traces. Plus a feedback channel that records when the twin was wrong — closing the loop for Phase 6 evaluation.

## Dependencies

- **Phase 2**: hybrid retrieval, contextual value weights, fusion.
- **Phase 3**: belief graph clusters, IRL-inferred values, tensions.
- **Phase 4**: uncertainty propagation, drift data, calibration recorder, the `Prediction` contract.

## Scope

**In scope**
- **Query processing pipeline** (§6.1): domain classification → model retrieval → simulated reasoning → uncertainty flagging → explanation generation.
- **All six query types** (§6.2): prediction, priority elicitation, reaction simulation, counterfactual, drift, blind-spot.
- **Simulated-reasoning prompt** (§6.1 Step 3): encodes value hierarchy + decision style + domain belief cluster + historical trace patterns; instructs the LLM to reason *as* that person, show the process, and say when uncertain.
- **Uncertainty flagging** (§6.1 Step 4, §5.4): annotate which parts of the answer rest on high-CI params or data-sparse domains.
- **Explanation generation** (§6.1 Step 5, §7.5): user's vocabulary, their characteristic framing, citations to real traces ("Similar to how you weighed the 2024 startup decision...").
- **Model exploration UI**: "here is what the system currently believes about your value hierarchy", tensions, drift views.
- **Feedback mechanism**: "this prediction was wrong — here's what I actually thought" → stored as outcome signal for Phase 6.

**Out of scope**
- Cross-domain reasoning, belief-change simulation, collaborative two-person mode, proactive calendar/doc integration (Phase 6).
- Re-training IRL/drift from feedback automatically (Phase 6 closes that loop systematically).

## Deliverables

- `engine/pipeline.py`: the 5-step orchestrator.
- `engine/domain_classifier.py`, `engine/model_retrieval.py`, `engine/simulator.py`, `engine/explainer.py`.
- Query-type handlers in `engine/queries/`: `prediction.py`, `priority.py`, `reaction.py`, `counterfactual.py`, `drift.py`, `blindspot.py`.
- Versioned prompts: `simulated_reasoning/v1.txt`, `explanation/v1.txt`, `blindspot/v1.txt`, etc.
- API: `POST /twin/query` (typed by query type), `POST /twin/feedback`, `GET /twin/model` (explorable view).
- Tests: golden answers on a fixture persona; uncertainty flags fire when a fixture model is data-sparse; explanation cites real trace ids; blind-spot surfaces an absent-but-typical factor.

## Tasks

1. **Domain classifier.** Map a query to `{career, financial, relational, creative, ethical}` (and a confidence). Drives which belief cluster + contextual weights are active. *AC: 5 fixture queries classified correctly; ambiguous queries get a lower domain-confidence that propagates.*
2. **Model retrieval assembler.** Pull: value hierarchy (domain-contextual), decision style, domain belief cluster (Phase 3), relevant traces (Phase 2 retrieval). Respect token budget; prefer high-evidence items. *AC: assembled context is bounded, traceable, and includes provenance.*
3. **Simulated-reasoning prompt (v1).** Implement exactly the blueprint §6.1 Step 3 structure: system persona = the user's model; characteristic reasoning steps derived from their traces; instruction to show reasoning and admit uncertainty. *AC: on a fixture persona, the output reasons through options in the persona's characteristic order and weights; does NOT give generic best-practice advice.*
4. **Uncertainty flagging.** After generation, map cited factors back to contributing params (Phase 4 `Contribution`s); if any relied on wide-CI or data-sparse params, append an explicit flag in the user's terms. *AC: a query in a domain with few traces produces "I'm extrapolating here — you've rarely decided in this area" rather than a confident verdict.*
5. **Explanation generator.** Rewrite/annotate the simulation in the user's vocabulary (mined from their traces) and with trace citations. *AC: output contains ≥1 citation to a real trace id when relevant; phrasing uses the user's terms, not generic frameworks.*
6. **Six query handlers.** Implement each per §6.2: prediction (simulate + confidence), priority (rank active value cluster), reaction (belief graph + personality), counterfactual (hold context, perturb one param, re-simulate), drift (surface Phase 4 drift log), blind-spot (typical-for-domain factors absent from the user's history). *AC: each handler type-checks inputs/outputs and passes its golden fixture.*
7. **Counterfactual correctness.** For counterfactuals, the only thing that changes is the named parameter; everything else is held constant. *AC: a counterfactual re-run with the same perturbation is deterministic; differing only the perturbed param changes the output predictably.*
8. **Blind-spot detector.** Maintain a per-domain "factors typically important" set (seeded from general knowledge, editable); compare against the user's historical factors; surface the gap. *AC: if the user never cites "commute" in career traces but it's typical, it's surfaced as a possible blind spot.*
9. **Model exploration UI.** A view of current beliefs/values/style + tensions (Phase 3) + drift (Phase 4), all with confidence and provenance. *AC: a user can see "what the system believes about me" with evidence trails.*
10. **Feedback channel.** `POST /twin/feedback` records `{prediction_id, user_said_actually, free_text}` → stored as an outcome signal + fed to calibration recorder (Phase 4). *AC: a wrong-prediction report is stored and reduces the recorded calibration for that domain.*

## Data models / schemas

```python
class TwinQuery(BaseModel):
    query_type: Literal["prediction","priority","reaction","counterfactual","drift","blindspot"]
    text: str
    domain_hint: Domain | None
    options: list[str] | None       # for prediction/counterfactual
    perturb: dict[str, float] | None# for counterfactual

class TwinAnswer(BaseModel):
    query_type: str
    domain: Domain
    domain_confidence: float
    narrative: str                  # the simulated reasoning, user-voiced
    citations: list[str]            # trace ids
    confidence: float               # propagated
    extrapolation_flags: list[str]
    contributing_params: list[Contribution]
    feedback_token: str             # for POST /twin/feedback
```

## Interfaces

- `engine.answer(query: TwinQuery) -> TwinAnswer`.
- `engine.feedback(prediction_id, correction) -> FeedbackRecord`.
- API as above.

## Blueprint & context references

- Blueprint §6 (entire), §7.5 (Explanation Generation), §8 Phase 3.
- `MODEL_BEHAVIOR_RULES.md` — confidence < threshold → neutral/uncertain fallback; match tone only with sufficient data; don't fabricate history.
- `FAILURE_MODES.md` — generic responses from weak retrieval (mitigated by retrieval + simulation-as-persona); hallucinated personal facts (citations required; no claim without a trace or explicit extrapolation flag).
- `EVALUATION_METRICS.md` — latency < 2s (budget the pipeline; cache retrieval); consistency score.

## Exit criteria (definition of done)

- [ ] All six query types return valid `TwinAnswer` on their golden fixtures.
- [ ] Simulated reasoning reasons *as the user's model*, not as generic advice (human-judged on fixtures; ideally a blind A/B vs a generic LLM answer).
- [ ] Uncertainty flags fire correctly: data-sparse domains and wide-CI params produce explicit "extrapolating" caveats, not confident fiction.
- [ ] Explanations cite real trace ids and use the user's vocabulary.
- [ ] Counterfactuals are deterministic and perturb only the named param.
- [ ] Blind-spot query surfaces a genuinely-absent typical factor.
- [ ] Feedback records a correction and feeds calibration.
- [ ] p95 query latency < 2s for standard queries (`EVALUATION_METRICS.md`).
- [ ] All gates green.

## Risks & mitigations

| Risk | Source | Mitigation |
|------|--------|------------|
| Confident fiction in data-sparse domains | blueprint §7.4 (the #1 failure mode) | Hard uncertainty flagging; refuse to assert without evidence; explicit extrapolation language; calibration feedback loop. |
| Output reads like generic advice, not the user | blueprint §7.5 | Persona-conditioned prompt; vocabulary mining; citation requirement; blind A/B eval. |
| Hallucinated personal facts/citations | `FAILURE_MODES.md` §Model | Citations must resolve to real trace ids; unverifiable claims blocked; extrapolation flag mandatory. |
| Over-personalization / uncanny valley | blueprint §12 (research Q) | Confidence-gated personalization; let the user inspect/dismiss; don't over-assert. |
| Latency blowup | `EVALUATION_METRICS.md` | Cache retrieval; bound context; profile p95. |
| Counterfactual non-determinism | — | Temperature control; deterministic seed; re-run parity test. |

## Effort estimate

~8–12 weeks. This is the phase where everything has to work together and the product either feels like a mirror or a stranger. Budget heavy iteration with real users and the blind A/B comparison (generic vs twin) — that comparison is the core success signal from `EVALUATION_METRICS.md` (consistency > 80%).
