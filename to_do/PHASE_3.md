# Phase 3 — Belief Graph & Value Inference (IRL)

> Blueprint §8 Phase 2 (Months 4–10). The model becomes genuinely *computational*. We build the **belief graph** (§3.3), implement **Maximum Entropy Inverse Reinforcement Learning** to recover value weights from observed choices (§5.2), add **contradiction detection** (§7.1), and refine **contextual value weights** with inferred (not just self-report/behavioral) evidence. By the end of Phase 3, the value hierarchy is inferred from *what the user actually chose*, not what they said.

---

## Goal

Replace questionnaire/behavioral priors for the value hierarchy with **behavior-derived estimates via IRL**, structured as a belief graph that encodes co-activation between beliefs. Stated-vs-inferred contradictions are detected, logged, and (optionally) surfaced to the user as tensions rather than silently resolved.

## Dependencies

- **Phase 2**: parameter store (append-only), fusion, confidence math, contextual weights, contradiction *logging* (this phase promotes it to detection + surfacing).
- Reads reasoning traces from Phase 1.

## Scope

**In scope**
- **Belief graph** (§3.3): nodes (beliefs with confidence + stability tier + evidence), edges (relations: supports/contradicts/causes/correlates, weighted), plus co-activation clustering for decision-domain activation.
- **Maximum Entropy IRL** (§5.2): recover Schwartz value-weight vector θ maximizing trajectory entropy subject to feature-matching constraints, run incrementally on each new trace.
- **Contradiction detection** (§7.1): stated-vs-inferred conflict → logged tension; behavioral inference weighted above self-report when they disagree; tension surfaced to user with phrasing from blueprint ("Your actions suggest...").
- **Inferred-evidence source**: IRL outputs feed back into the fusion layer (Phase 2) as `source="inferred"`.
- **Belief-cluster retrieval**: given a decision domain, return the active belief cluster (the subgraph that co-activates).
- Incremental IRL update (not full retrain) with shift magnitude gated by current confidence.

**Out of scope**
- Drift / changepoint detection on parameters (Phase 4) — but every inferred estimate is timestamped so Phase 4 can consume it.
- The query engine that *uses* all this (Phase 5).
- Belief-change *simulation* (Phase 6).

## Deliverables

- `model/belief_graph.py`: `BeliefGraph` CRUD, cluster extraction, edge maintenance.
- `inference/irl.py`: MaxEnt IRL optimizer (gradient-based), incremental update API, feature extraction from traces.
- `inference/features.py`: trace → feature vector (Schwartz-dim scoring of options/factors).
- `inference/contradiction.py`: stated-vs-inferred detector + tension surfacing.
- `prompts/belief_extraction/v1.txt`, `prompts/contradiction_phrasing/v1.txt` (versioned).
- API: `GET /model/beliefs?domain=...`, `GET /model/beliefs/{id}`, `GET /model/tensions`, `GET /model/values?source=inferred`.
- Notebooks/tests: IRL recovers known θ on a synthetic trace set with N traces; belief graph builds from a fixture corpus.

## Tasks

1. **Belief node extraction.** LLM (versioned prompt) extracts candidate beliefs from traces + signals (distinct from value dims — these are personal credences, §3.3). Deduplicate via embedding similarity; assign `stability` tier (stable/medium/volatile) heuristically now (refined Phase 4). *AC: a corpus of 20 traces yields a dedup'd belief set; near-duplicates merge with an evidence union.*
2. **Edge construction.** Detect relations between beliefs: `supports`/`contradicts` (semantic + co-occurrence), `causes`/`correlates` (from trace factor structure). Weight edges by co-occurrence frequency and semantic similarity. *AC: a trace citing beliefs A,B,C increments co-occurrence among them; the graph reflects it.*
3. **Cluster extraction by domain.** Given a domain, return the subgraph of co-activating beliefs (community detection or thresholded co-occurrence). This is what the query engine (Phase 5) will feed into simulated reasoning. *AC: `GET /model/beliefs?domain=career` returns a connected, domain-relevant cluster.*
4. **Feature extraction from traces.** Map each option + its factors onto the 10 Schwartz dimensions → a feature vector per trace. *AC: a synthetic trace set with known dim倾向ations yields feature vectors matching the design.*
5. **MaxEnt IRL core.** Implement the optimizer (§5.2): maximize H(π_θ) s.t. E_π_θ[features] ≈ E_observed[features]. Use gradient ascent with soft-max (Boltzmann) policy. Validate on **synthetic traces generated from a known θ** → recovered θ should be within tolerance as N grows. *AC: with N=50 synthetic traces from a known θ, recovered θ has Pearson r ≥ 0.8 with ground truth; CI is wider at low N.*
6. **Incremental updates.** On each new trace, run a few gradient steps from current θ (warm start), with step size scaled to current confidence (high confidence → small steps). *AC: adding 1 trace is O(seconds), not a full retrain; the estimate moves a little, not a lot, when confidence is already high.*
7. **Feed IRL into fusion.** IRL θ becomes `source="inferred"` evidence in the Phase 2 fusion layer. *AC: `/model/values` can return the inferred hierarchy alongside self-report/behavioral; fusion prefers inferred as N grows.*
8. **Contradiction detection & surfacing.** Compare stated beliefs/values vs inferred; when |stated − inferred| > threshold AND inferred has sufficient n, log a `Tension` and (user-opt-in) surface it using §7.1 phrasing. *AC: a fixture where a user says "I value security" but chose risk repeatedly → a tension is logged and phrased non-judgmentally.*
9. **Calibration of IRL confidence.** IRL-derived value weights get CIs from the Hessian / bootstrap over traces; small N → wide CI (satisfies §7.4). *AC: a low-N inferred value has a visibly wider CI than a high-N one.*

## Data models / schemas

Reuse Phase 0 `BeliefNode`, `BeliefEdge`, `BeliefGraph`. Add:

```python
class Tension(BaseModel):
    stated: ParameterEstimate       # source="self_report" or explicit belief
    inferred: ParameterEstimate     # source="inferred" or "behavioral"
    magnitude: float                # |stated.value - inferred.value|
    domain: Domain | None
    surfaced: bool
    phrasing_version: str
    created_at: datetime

class IRLResult(BaseModel):
    theta: dict[str, float]         # Schwartz dim -> weight
    confidence: dict[str, float]
    n_traces: int
    last_trace_id: str
    converged: bool
```

## Interfaces

- `inference.irl.update(traces) -> IRLResult` (incremental) and `inference.irl.fit(traces) -> IRLResult` (full).
- `model.belief_graph.cluster(domain) -> BeliefGraph`.
- `inference.contradiction.detect() -> list[Tension]`.

## Blueprint & context references

- Blueprint §3.3 (Belief Graph), §5.2 (MaxEnt IRL), §7.1 (Belief Modeling — bottom-up from behavior), §7.2 (contextual weights), §7.4 (uncertainty), §8 Phase 2.
- `MEMORY_STRATEGY.md` — store don't overwrite (tensions stored alongside beliefs, not replacing).
- `MODEL_BEHAVIOR_RULES.md` — don't infer sensitive traits (IRL operates on validated value dims, not protected attributes; add guardrails).
- `EVALUATION_METRICS.md` — prediction accuracy (IRL outputs are the thing later evaluated).

## Exit criteria (definition of done)

- [ ] MaxEnt IRL recovers a known θ on synthetic data (Pearson r ≥ 0.8 at N≥50).
- [ ] Belief graph builds from a real fixture corpus; nodes dedup'd; edges weighted; domain clusters extractable.
- [ ] IRL θ flows into fusion as `source="inferred"` and narrows value CIs as traces accrue.
- [ ] Stated-vs-inferred contradictions are detected, logged as `Tension`, and surfaceable with §7.1 phrasing.
- [ ] Incremental update is cheap (O(seconds)) and stable (no thrashing on a single new trace).
- [ ] No sensitive-trait inference; value inference confined to validated Schwartz dims.
- [ ] All gates green; IRL has synthetic-recovery + incremental-stability tests.

## Risks & mitigations

| Risk | Source | Mitigation |
|------|--------|------------|
| IRL overfits / is unstable at low N | blueprint §7.4 (overconfidence) | MaxEnt regularization (entropy), wide CIs, warm-start incremental updates, withhold strong claims until n threshold. |
| Inferring sensitive/protected traits | `MODEL_BEHAVIOR_RULES.md` safety | Restrict θ space to the 10 validated Schwartz dims; refuse-list in belief extraction; review beliefs before persistence. |
| Hallucinated beliefs | `FAILURE_MODES.md` §Model | Belief extraction needs textual support (reuse Phase 1 guard); unsupported beliefs flagged, not stored silently. |
| Belief graph becomes a hairball | — | Edge weight thresholding + domain scoping; prune low-evidence nodes. |
| Contradictions feel accusatory | blueprint §7.1 ("surface the tension") | Phrasing prompt is non-judgmental, opt-in surfacing, user can dismiss. |

## Effort estimate

~7–10 weeks. IRL correctness is the long pole — the synthetic-recovery test is the gate that says "the math is right" before trusting it on a real person.
