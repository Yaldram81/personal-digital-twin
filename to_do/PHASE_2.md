# Phase 2 — Behavioral Profiling & Confidence Intervals

> The bridge from *self-report priors* to *behavioral inference*. We add the **conversation mining** channel (blueprint §4.2), build the **structured model store** for value/decision-style/belief parameters, compute **confidence intervals** on every parameter (§7.4), and introduce **contextual value weights** by life domain (§7.2). By the end of Phase 2, the system has a real — still simple, but behaviorally-grounded and uncertainty-aware — model of the user.

---

## Goal

Passive conversation signals start updating the model with `source="behavioral"` estimates that **override** the questionnaire priors as evidence accumulates, while **never overwriting** history (append-only per `MEMORY_STRATEGY.md`). Every model parameter now carries a CI computed from sample size, consistency, and recency. Value weights become **per-domain**.

## Dependencies

- **Phase 1**: trace store, extraction pipeline, questionnaire priors.
- (Optional early read of) Phase 4: confidence math shares math utilities with drift; keep `core/stats/` ready.

## Scope

**In scope**
- **Conversation mining** (§4.2): a signal extractor that runs on chat history and emits *weighted evidence* (low weight vs narration) for value/style/belief inferences. Tags each signal with provenance + weight.
- **Structured parameter store**: time-stamped, append-only rows for every estimate of every parameter (enables drift in Phase 4 and contradiction detection in Phase 3).
- **Confidence interval computation** (§7.4): per-parameter CI from n, consistency (variance of evidence), and recency decay.
- **Contextual value weights** (§7.2): a `ValueHierarchy` per life domain `{career, relationships, health, finances, creative}` + a cross-domain tradeoff weight; learned independently from domain-tagged traces.
- **Evidence fusion**: combine `self_report` + `behavioral` + (later) `inferred` evidence into a single posterior estimate per parameter, weighted by source reliability.
- **Hybrid retrieval** for context (ties to `MEMORY_STRATEGY.md` retrieval strategy): query embed → top-K semantic → temporal filter → re-rank by relevance+recency.
- A "model diff" view: show the user how behavioral evidence has shifted their priors.

**Out of scope**
- Belief graph edges and IRL (Phase 3).
- Drift/changepoint detection (Phase 4) — but we *store* the time series it needs.
- The query engine (Phase 5).

## Deliverables

- `extraction/conversation_miner.py`: passive signal extraction over chat logs.
- `model/parameter_store.py`: append-only estimate table + "current value" view = latest fused posterior.
- `model/confidence.py`: CI computation utilities (Wilson/Bayesian beta-binomial or bootstrap — pick one, document why).
- `model/contextual_values.py`: per-domain hierarchies + cross-domain weights.
- `model/fusion.py`: multi-source evidence fusion (Bayesian update or weighted mean with per-source variance).
- `memory/retrieval.py`: hybrid retrieval (semantic + temporal + rerank) backing context construction.
- API: `GET /model/parameters?domain=...`, `GET /model/diff` (priors vs current), `GET /evidence/{param}` (provenance trail).
- Tests: fusion correctness on synthetic evidence; CI shrinks as n grows; retrieval precision@K on a fixture set.

## Tasks

1. **Define the conversation-mining signal schema.** A `BehavioralSignal` = `{param, domain, direction, weight, evidence_text_ref, timestamp, extractor_version}`. *AC: a chat log yields N signals, each traceable to the originating message.*
2. **Build the conversation miner.** An LLM-based extractor (versioned prompt) that scans a conversation and emits signals for: topic initiation vs response, pushback patterns, abstract-vs-concrete framing, "real issue" disambiguation, stated-vs-implied contradictions (§4.2 bullet list). Each signal gets a **low weight** (e.g. 0.1–0.3 of a narration). *AC: on a scripted conversation, ≥80% of expected signals are emitted; no signal invents facts not in the text (anti-hallucination guard, reuse Phase 1 pattern).*
3. **Implement the append-only parameter store.** Schema: `(param_key, domain, value, confidence, n, source, evidence_ids[], timestamp)`. Inserts only; "current value" = a view that fuses rows. *AC: storing two estimates for `risk_tolerance` keeps both; the view returns one fused value with combined n.*
4. **Confidence intervals.** Implement CI as a function of (n, consistency=1−variance, recency_decay). Document the formula in `docs/confidence.md`. *AC: doubling consistent evidence halves the CI half-width (roughly); high-variance evidence yields a wider CI than low-variance at equal n; stale evidence widens CI.*
5. **Evidence fusion.** Posterior = Bayesian update of prior (questionnaire) by likelihood (behavioral signals), with per-source variance. *AC: a strong run of behavioral signals moves the posterior away from a questionnaire prior; a single contradictory signal barely moves it (no thrashing).*
6. **Contextual value weights.** Store a `ValueHierarchy` keyed by domain; learn each from domain-tagged traces only. Cross-domain tradeoff vector learned separately (sparse, needs ≥1 cross-domain decision). *AC: `GET /model/parameters?domain=career` returns career-specific weights that can differ from `domain=health`; a cross-domain decision pulls both.*
7. **Hybrid retrieval.** Implement the 4-step strategy from `MEMORY_STRATEGY.md`. Add a context-budget guard (blueprint risk: context overflow). *AC: precision@5 on a 50-trace fixture ≥0.6; context never exceeds the model's token budget.*
8. **Contradiction *logging* (light).** When a behavioral signal direction conflicts with the current posterior by more than a threshold, log it to an `inconsistencies` table (Phase 3 turns these into surfaced tensions). Do **not** surface to user yet. *AC: a conflicting signal is logged, not silently merged.*

## Data models / schemas

```python
class BehavioralSignal(BaseModel):
    param: str                      # e.g. "risk_tolerance" or "value:self_direction"
    domain: Domain
    direction: Literal["increase","decrease","neutral"]
    magnitude: float                # 0..1
    weight: float                   # signal reliability, < narration weight
    evidence_ref: str               # pointer/hash to source message
    extractor_id: str
    extractor_version: str
    timestamp: datetime

class ParameterEstimate(BaseModel): # append-only row
    param: str
    domain: Domain | None           # None = global/cross-domain
    value: float
    confidence: float
    n: int
    source: Literal["self_report","behavioral","inferred"]
    evidence_ids: list[str]
    timestamp: datetime
```

## Interfaces

- `extraction.mine_conversation(messages) -> list[BehavioralSignal]`.
- `model.fuse(param, domain) -> ScoredScalar` (current posterior).
- `model.confidence.ci(estimates) -> ConfidenceInterval`.
- `memory.retrieve(query, domain, top_k, token_budget) -> list[Trace|Signal]`.

## Blueprint & context references

- Blueprint §4.2 (Conversation Mining), §7.2 (Preference Learning — contextual weights), §7.4 (Uncertainty Estimation).
- `MEMORY_STRATEGY.md` — retrieval strategy (4 steps), "store, don't overwrite."
- `MODEL_BEHAVIOR_RULES.md` — confidence threshold gates personalization; "if confidence < threshold → fallback."
- `EVALUATION_METRICS.md` — precision@K for retrieval; consistency score.
- `FAILURE_MODES.md` — over-reliance on recent data (mitigated by temporal filter + recency-aware CI, not raw recency); embedding drift (record embedding model per vector, Phase 0).

## Exit criteria (definition of done)

- [ ] Conversation mining emits traceable, weighted, low-weight signals; no hallucinated facts.
- [ ] Every parameter has a CI that behaves correctly as a function of n/consistency/recency (unit-tested).
- [ ] Behavioral evidence measurably shifts posteriors away from questionnaire priors on a scripted dataset, without thrashing.
- [ ] Per-domain value hierarchies exist and can differ by domain.
- [ ] Hybrid retrieval hits precision@5 ≥ 0.6 on the fixture set and never exceeds token budget.
- [ ] `GET /model/diff` shows the user how behavior has updated their priors, with provenance.
- [ ] Conflicting evidence is logged, not silently merged.
- [ ] All gates green; `model/` and `extraction/` coverage ≥ 80%.

## Risks & mitigations

| Risk | Source | Mitigation |
|------|--------|------------|
| Over-personalization from noisy signals | `FAILURE_MODES.md` §Model | Low per-signal weights; wide CIs; fusion can't move fast on sparse data. |
| Over-reliance on recent data | `FAILURE_MODES.md` §Memory | Temporal filter + recency *decay*, not recency *dominance*; stable params resist short-term noise (fully enforced in Phase 4). |
| Context overflow | `FAILURE_MODES.md` §System | Token-budget-aware retrieval. |
| Embedding drift | `FAILURE_MODES.md` §System | Pin + record model id; (Phase 6) re-index path. |
| Hallucinated personal facts from mining | `MODEL_BEHAVIOR_RULES.md` | Reuse Phase 1 anti-hallucination guard; provenance required on every signal. |

## Effort estimate

~5–7 weeks. Evidence fusion + CI math is the subtle part; spend time validating on synthetic and scripted data before trusting it on real conversations.
