# Phase 1 — Data Collection & Questionnaire Seeding

> Blueprint §8 Phase 1 (Months 0–4). The first user-facing capability: get decisions *into* the system. We can't model a person with no data, so this phase bootstraps the model with **questionnaire priors** (a pragmatic shortcut the blueprint explicitly endorses) and stands up the **explicit decision narration** channel — the highest-quality data source.

---

## Goal

A user can (a) complete a validated psychometric + value questionnaire that seeds the initial model as a *weak, clearly-labeled prior*, and (b) walk the system through a real decision via a structured narration flow that produces **schema-validated reasoning traces** stored in the encrypted DB. By the end of Phase 1, the system has its first real training data and an honest, low-confidence model.

## Dependencies

- **Phase 0** complete: encrypted store, LLM abstraction, versioned prompts, the `ReasoningTrace` schema.

## Scope

**In scope**
- Explicit decision narration UI (CLI first, local web UI second): the 4 structured-reflection prompts from §4.1.
- **Reasoning trace extraction pipeline** (§5.1): LLM + versioned prompt → `ReasoningTrace` (Pydantic-validated) → stored.
- Questionnaire instruments, scored into the §3.1/§3.2 schemas as priors:
  - Schwartz Basic Values Survey (10 dims) → `ValueHierarchy`.
  - Maximization Scale (Schwartz et al.) → `information_seeking`.
  - BIS/BAS (Carver & White) → components of `reasoning_mode`/risk.
  - Cognitive Reflection Test (CRT) → analytical vs intuitive (`reasoning_mode`).
  - Domain-anchoring items for `risk_tolerance`, `time_horizon`, `loss_aversion`, `ambigu_tolerance`, `construal_level`, `social_proof_weight`.
- Confidence/weight tagging: questionnaire-sourced params stored with **low confidence** (wide CI), flagged `source="self_report"`, so later behavioral inference overrides them (Phase 2).
- A "model is weak" disclosure surface: UI shows the user that current estimates are priors, not behaviorally validated.
- Trace input validation: reject degenerate/empty narrations; require ≥2 options or a counterfactual.

**Out of scope**
- Passive conversation mining (Phase 2).
- IRL value inference, belief graph, contradiction detection (Phases 2–3).
- Drift detection (Phase 4).
- The query engine (Phase 5).

## Deliverables

- `ui/cli/narrate.py` and `ui/web/narration`: the narration flow.
- `extraction/trace_extractor.py`: extraction pipeline through the LLM abstraction.
- `prompts/reasoning_trace_extraction/v1.txt` (+ future versions).
- `ingest/questionnaire/`: instrument definitions (items + scoring keys) and a scorer.
- `model/value_hierarchy.py`, `model/decision_style.py`: constructors from questionnaire results (prior mode).
- API endpoints: `POST /narration/start`, `POST /narration/{id}/submit` → extracted trace; `GET /model/summary` (weak-model view).
- Tests: extraction against 5+ gold narration fixtures with expected traces; questionnaire scoring unit tests.

## Tasks

1. **Define the narration flow as a state machine.** States: intake → options → factors → weighting → counterfactual → review → submit. Allow free-text or structured entry. *AC: a user can complete a narration in <5 minutes; flow is resumable.*
2. **Author the extraction prompt (v1).** Following blueprint §5.1 exactly: domain, options_detected, chosen, factors (with weight HIGH/MED/LOW + direction), inferred_values (Schwartz dims), implicit_beliefs. Output must be JSON matching `ReasoningTrace`. *AC: prompt is versioned in `prompts/`; registry loads it; CI fails if changed without version bump.*
3. **Implement `trace_extractor`.** Free-text narration → LLM call (via `core.llm`) → parse → validate with Pydantic → write `ReasoningTrace` to encrypted store; also write raw text + extracted JSON to an append-only `extraction_events` table. *AC: 5 gold fixtures produce traces whose `chosen` and top-2 factors match the expected; malformed LLM output is caught, logged, and the user is asked to rephrase rather than storing garbage.*
4. **Implement questionnaire instruments + scorer.** Encode item banks and reverse-scored items; score into the §3.1/§3.2 schemas. *AC: a fixed fake response set produces deterministic scores; reverse-scored items are handled; every output scalar has `confidence` set to the *prior* width and `source="self_report"`.*
5. **"Weak model" disclosure.** `GET /model/summary` returns the priors with a per-field `evidence_strength` = `weak` and a human note: "These are questionnaire-based starting estimates; they'll be corrected by your behavior." *AC: the summary visibly distinguishes self-report priors from (future) behavioral estimates; satisfies `MODEL_BEHAVIOR_RULES.md` "avoid overfitting personality too early."*
6. **Input validation & degenerate-input handling.** Reject narrations with <2 options and no counterfactual; reject traces where the LLM returns nothing for `factors`. *AC: a narration "I just picked the first one" is accepted but flagged `low_signal=true`, not rejected silently.*
7. **Anti-hallucination guard on extraction.** The extraction prompt must never invent options/factors not supported by the text; add a self-check that compares extracted factors against the source text (a second cheap LLM call or a lexical-overlap heuristic) and flags low-supported extractions for review. *AC: a fabricated factor in a fixture is flagged.*
8. **Privacy surface.** Every stored trace is encrypted (Phase 0 store); add a `GET /export` (full model + traces download) and `DELETE /model` (wipe) stub per §10. *AC: export produces an encrypted+signed bundle; delete removes traces and model params (drift log entry recorded, append-only).*

## Data models / schemas

Reuse Phase 0 `ReasoningTrace`. Extend `ScoredScalar` usage with `source: Literal["self_report","behavioral","inferred"]` and `evidence_strength: Literal["weak","moderate","strong"]`. New:

```python
class TraceExtractionEvent(BaseModel):      # append-only audit
    trace_id: str
    prompt_id: str
    prompt_version: str
    model_id: str
    raw_text_hash: str        # store hash, not plaintext, in the event log
    extracted: ReasoningTrace
    support_flags: list[str]  # e.g. ["low_support_factor"]
    created_at: datetime
```

Questionnaire result schema maps instrument → scored `ScoredScalar`s, each tagged `source="self_report"`.

## Interfaces

- `extraction.extract_trace(narration, llm) -> ReasoningTrace` (+ `support_flags`).
- `ingest.questionnaire.score(instrument_id, responses) -> dict[str, ScoredScalar]`.
- `model.ValueHierarchy.from_questionnaire(scored) -> ValueHierarchy` (prior mode).
- API: `/narration/*`, `/questionnaire/*`, `/model/summary`, `/export`, `/model` (DELETE).

## Blueprint & context references

- Blueprint §4.1 (Explicit Decision Narration), §5.1 (Reasoning Trace Extraction), §8 Phase 1, §3.1/§3.2, §10 (export/delete).
- `MODEL_BEHAVIOR_RULES.md` — anti-hallucination, don't infer sensitive traits (extraction must not invent), overfitting caution.
- `MEMORY_STRATEGY.md` — store, don't overwrite; append-only extraction events.
- `EVALUATION_METRICS.md` — sets up "prediction accuracy" data collection (traces become the held-out set later).

## Exit criteria (definition of done)

- [ ] A user can complete the questionnaire and get a seeded `ValueHierarchy` + `DecisionStyle`, every scalar tagged `source="self_report"`, `evidence_strength="weak"`.
- [ ] A user can narrate a real decision; the pipeline produces a Pydantic-valid `ReasoningTrace`; raw + extracted are stored encrypted.
- [ ] Extraction matches expected `chosen` + top-2 factors on ≥4/5 gold fixtures.
- [ ] Fabricated/unsupported factors are flagged, not silently stored.
- [ ] `/model/summary` clearly communicates the model is weak/prior-based.
- [ ] `/export` and `DELETE /model` work end to end.
- [ ] `ruff`, `mypy`, `pytest` green; extraction has ≥5 fixtures.

## Risks & mitigations

| Risk | Source | Mitigation |
|------|--------|------------|
| Extraction hallucinates factors | `FAILURE_MODES.md` §Model (hallucinated personal facts); `MODEL_BEHAVIOR_RULES.md` | Support-check step; flag-and-review; never auto-trust a single extraction. |
| Over-personalization from questionnaire priors | `FAILURE_MODES.md` §Model (over-personalization); `MODEL_BEHAVIOR_RULES.md` | Wide CIs, `evidence_strength="weak"`, explicit disclosure. |
| Users drop off long narrations | product | Resumable flow; counterfactual optional-but-encouraged; CLI + web parity. |
| Sensitive trait inference | `MODEL_BEHAVIOR_RULES.md` safety | Extraction prompt has a refuse-list; instruments validated/standardized; no free-form inference of protected attributes. |

## Effort estimate

~4–6 weeks. The extraction prompt is the crux — budget real iteration time and gold-fixture building.
