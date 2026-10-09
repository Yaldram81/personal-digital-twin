# Personal Digital Twin — Implementation Plan

This directory contains the **phased implementation plan** for the Personal Digital Twin (PDT).

The plan is derived from two sources:
- `project_idea/personal-digital-twin.md` — the full research blueprint (the *what* and *why*).
- `project_context/*.md` — engineering constraints: coding standards, memory strategy, model behavior rules, failure modes, evaluation metrics, project intent (the *how*).

The blueprint is research-grade (Maximum Entropy IRL, Bayesian change-point detection, belief graphs, calibrated uncertainty). The context files are pragmatic (single-user, local-first, memory-driven, "simplicity over complexity", encrypted-at-rest, API-first, single LLM abstraction). **This plan honors the blueprint's vision but decomposes it into buildable, incremental engineering phases**, each independently valuable.

---

## Reconciled vision (what we are actually building first)

A **single-user, local-first** system that:

1. Collects the user's decisions and reasoning through structured prompts + passive conversation mining.
2. Builds a computational model of the user: value hierarchy, decision style, belief graph, reasoning traces, and temporal drift — every parameter with a **confidence interval**.
3. Answers **"how would I think about X?"** by simulating the user's reasoning in their own vocabulary, with **calibrated uncertainty** surfaced explicitly.
4. Treats the personal model as **user-owned, encrypted, exportable, and deletable** — the privacy bargain is the product.

Non-goals (per `PROJECT_INTENT.md`): full consciousness replication, general AGI, psychologically accurate emotion simulation.

---

## Phase map

The blueprint defines 4 research phases (Months 0–4, 4–10, 10–18, 18+). We split them into **7 engineering phases**, adding a Phase 0 for the infrastructure the blueprint assumes but doesn't enumerate, and breaking the large middle phases into independently shippable units.

| Phase | Title | Blueprint ref | Core outcome |
|-------|-------|---------------|--------------|
| **0** | Foundation & Infrastructure | §10, coding standards | Repo, env, LLM abstraction, encrypted local store, schemas, CI |
| **1** | Data Collection & Questionnaire Seeding | §3.1, §3.2, §3.4, §4.1, §5.1, §8-P1 | Conversation/narration UI, trace extraction, questionnaire-seeded priors |
| **2** | Behavioral Profiling & Confidence Intervals | §3.3(partial), §4.2, §7.2, §7.4 | Conversation mining, structured model store, confidence intervals, contextual weights |
| **3** | Belief Graph & Value Inference (IRL) | §3.3, §5.2, §7.1, §7.2, §8-P2 | Belief graph, MaxEnt IRL, contradiction detection |
| **4** | Temporal Drift & Uncertainty Propagation | §3.5, §5.3, §5.4, §7.3, §7.4 | BOCPD drift detection, stability tiers, uncertainty propagation |
| **5** | Twin Query Engine & Explanation | §6, §7.5, §8-P3 | Query pipeline, all query types, explanation gen, feedback loop |
| **6** | Evaluation, Privacy Hardening & Generalization | §4.3, §9, §10, §8-P4 | Eval harness, outcome tracking, cross-domain, belief-change sim |

**Dependency order is mostly linear:** 0 → 1 → 2 → 3 → 4 → 5 → 6. Phases 3 and 4 can overlap partially (both depend on 2, neither depends on the other), but doing 3 before 4 is recommended since drift detection is most meaningful on inferred parameters.

---

## Recommended tech stack

The context files do not lock a stack. The recommendations below fit the algorithmic core (numerical optimization, probability, embeddings) and the local-first/encrypted mandate. **Decision rationale:** this is a *single-user, local-first* app (`PROJECT_INTENT`), so we deliberately avoid a database server. DuckDB (columnar analytical SQL) handles the relational + time-series + graph-at-small-scale load, and LanceDB provides embedded vector search with **native versioning** that directly implements the "memory never overwrites truth" append-only rule. Postgres+pgvector+AGE is the documented upgrade path only if the project later moves to multi-user/server deployment.

The selection logic:

| Constraint | What it implies for storage | Choice |
|------------|----------------------------|--------|
| Single-user, local-first | A DB **server** for one person is over-engineering | Embedded engines, no server process |
| Privacy mandate (`blueprint §10`, emphatic) | Smallest attack surface; storage fully under user control | Zero network services; app-level encryption |
| "Simplicity over complexity" | Fewer deploy-time moving parts | One Python process, two in-process engines |
| "Memory never overwrites truth" (`MEMORY_STRATEGY`) | Append-only / versioned history | LanceDB native versioning; DuckDB append-only tables |
| Model-history-as-time-series (drift, §3.5) | Columnar analytical workload | DuckDB columnar engine |

| Concern | Recommendation | Rationale |
|---------|----------------|-----------|
| Language | **Python 3.11+** | Numerical/ML core (numpy, scipy, torch), ecosystem for IRL & changepoint detection. Coding standards mandate `snake_case` for Python. |
| API layer | **FastAPI** | API-first, typed (Pydantic), async; matches "API-first / stateless endpoints where possible". |
| Analytical / relational store | **DuckDB** (embedded, in-process, columnar) | Zero-server, single-user; columnar engine ideal for the time-series drift log and append-only model history. App-level envelope encryption (AES-GCM) for at-rest privacy. Belief graph via recursive CTEs (sufficient at single-user scale). |
| Vector store | **LanceDB** (embedded, columnar, versioned) | In-process, no server; **native versioning/time-travel** maps directly onto the "memory never overwrites truth" append-only requirement. Backs semantic retrieval over traces + beliefs. |
| Encryption | App-level **AES-GCM** envelope over both stores, key derived from user passphrase (Argon2id) | No DB-native crypto dependency; uniform across DuckDB + LanceDB; satisfies §10 at-rest mandate. |
| *(Upgrade path, not now)* | PostgreSQL 16 + pgvector + Apache AGE + pgcrypto | Documented target **only if** the project moves to multi-user/server deployment (a future per `PROJECT_INTENT`). Do not adopt for single-user local-first. |
| LLM access | **Single abstraction layer** (`core/llm/`), provider-agnostic via a `Protocol`, e.g. LiteLLM or custom | CODING_STANDARDS: "All LLM calls must go through a single abstraction layer... No direct API calls inside business logic." |
| Prompt management | **Version-controlled prompt files** (`prompts/`, git-tracked) | CODING_STANDARDS: "All prompts must be version-controlled." |
| Validation | **Pydantic v2** for all schemas | Schema-validated trace extraction (§5.1) and API boundaries. |
| Config/secrets | `.env` + `pydantic-settings`; keys never committed | Privacy mandate. |
| Tests | `pytest`; `ruff` + `mypy` in CI | Modular, testable layers. |
| Deployment | Local app first (CLI + local web UI); single-user | PROJECT_INTENT: single-user initially. |

---

## Global architectural decisions (apply across all phases)

These are non-negotiable design rules, enforced from Phase 0 onward. They come straight from the context files.

1. **Modular layers, never monolithic AI files** (CODING_STANDARDS). Separate `memory/`, `retrieval/`, `reasoning/`, `extraction/` packages. No business logic calls an LLM directly.
2. **Single LLM abstraction layer** (`core/llm/`). Every LLM call — extraction, reasoning, explanation — flows through one interface with versioned prompts. This is what lets us swap providers and run offline evals.
3. **Memory never overwrites truth; conflicting memories are stored, not replaced** (MEMORY_STRATEGY). This is foundational to contradiction detection (Phase 3) and drift detection (Phase 4). Every belief/value update is *appended*, not mutated.
4. **Every parameter carries a confidence interval** (blueprint §3.1, §7.4). From Phase 1, no scalar is stored without an uncertainty estimate. This is the spine of the whole system.
5. **Privacy-by-default**: encrypted at rest, no telemetry without granular consent, full export + deletion (blueprint §10). Built in Phase 0, hardened in Phase 6.
6. **Calibrated uncertainty is the success criterion, not accuracy alone** (blueprint §7.4, §9). Overconfident wrong answers are worse than humble "I don't have enough data" answers.
7. **Append-only model history** (enables drift + audit). The model is a time series, not a current snapshot.

---

## Layered structure (target)

```
src/pdt/
  core/           # shared: llm abstraction, config, crypto, schemas
  ingest/         # Phase 0-1: data intake interfaces
  extraction/     # Phase 1-2: reasoning-trace + signal extraction
  memory/         # Phase 0-4: structured store, vector store, drift log
  model/          # Phase 1-4: value hierarchy, decision style, belief graph
  inference/      # Phase 3-4: IRL, drift detection, uncertainty propagation
  engine/         # Phase 5: query pipeline, explanation generation
  eval/           # Phase 6: evaluation harness
  api/            # Phase 0+: FastAPI app, endpoints
  ui/             # Phase 1+: local web UI / CLI
```

Each phase declares which packages it creates or extends.

---

## How to read these docs

Each phase file follows the same template:

1. **Goal** — one-paragraph outcome.
2. **Dependencies** — what must be done before starting; what this unblocks.
3. **Scope** — explicit *in* / *out* of scope.
4. **Deliverables** — concrete artifacts.
5. **Tasks** — numbered, actionable, each with acceptance criteria.
6. **Data models / schemas** — concrete where relevant.
7. **Interfaces** — modules/APIs this phase exposes and consumes.
8. **Blueprint & context references** — traceability.
9. **Exit criteria** — definition of done (measurable).
10. **Risks & mitigations** — including the relevant `FAILURE_MODES.md` entries.
11. **Effort estimate** — rough, for sequencing.

Start at `PHASE_0.md`. Do not skip it — every later phase depends on its infrastructure.
