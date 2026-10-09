# Phase 0 — Foundation & Infrastructure

> Build the skeleton every later phase stands on. Zero user-facing AI behavior yet — this phase is about making the architecture rules from `CODING_STANDARDS.md` real in code, and locking in the privacy mandate from blueprint §10 before any personal data exists.

---

## Goal

A runnable, tested, local-first application skeleton with: the single LLM abstraction layer, an encrypted local store, vector store, version-controlled prompts, Pydantic schemas for all five model components, CI, and config/secrets management. By the end of Phase 0, a developer can `pdt init`, write a value to the encrypted store, call the LLM abstraction with a versioned prompt, and retrieve it back.

## Dependencies

- None. This is the start of the line. (Tech stack is locked in `README.md`: Python 3.11+, FastAPI, **DuckDB + LanceDB (embedded, no DB server)**, app-level AES-GCM encryption.)

## Scope

**In scope**
- Repo scaffolding, package layout, virtualenv/dependency management.
- Single LLM abstraction layer (`core/llm/`) with one provider implemented.
- Encrypted analytical/relational store: **DuckDB** (embedded, in-process) with app-level AES-GCM envelope encryption over sensitive columns/files. Append-only tables for traces, model params, beliefs, edges, drift log, events.
- Embedded **vector store**: LanceDB (in-process), with **native versioning enabled** so semantic search over traces/beliefs inherits the append-only "never overwrite truth" property. Embeddings behind the LLM abstraction.
- Prompt registry: prompts live as version-controlled files, loaded by `prompt_id@version`.
- Pydantic v2 schemas for all blueprint §3 components (value hierarchy, decision style, belief graph, reasoning trace, drift log) — *data classes only*, no inference logic yet.
- Crypto module: key derivation from user credential, encrypt/decrypt at field and file granularity.
- Config + secrets: `pydantic-settings`, `.env`, no secrets committed; key derivation key never persisted in plaintext.
- A minimal FastAPI app with a `/health` endpoint and one round-trip storage endpoint.
- Linting (`ruff`), typing (`mypy`), tests (`pytest`), and CI (GitHub Actions or equivalent).
- A `pdt` CLI entry point with `init`, `doctor` (env/config check).

**Out of scope**
- Any inference, extraction, or reasoning logic (Phases 1+).
- The conversation/narration UI (Phase 1).
- IRL, belief graph construction, drift detection (Phases 3–4).
- Cloud sync / multi-user.

## Deliverables

- `src/pdt/` package with the layered structure from `README.md`.
- `core/llm/`: `LLMClient` Protocol + one concrete client + a prompt registry.
- `core/crypto/`: key derivation, encrypt-at-rest, encrypt-before-transmit helpers.
- `core/schemas/`: the five Pydantic models.
- `memory/structured/` (DuckDB backend) and `memory/vector/` (LanceDB backend): storage behind Protocols.
- `api/`: FastAPI app skeleton.
- `tests/`: unit tests for crypto, store round-trip, prompt registry, LLM abstraction (mocked).
- `prompts/`: versioned prompt files in git; a README documenting the convention.
- `pyproject.toml`, `.env.example`, `Makefile` or task runner, CI config.
- `docs/architecture.md`: the reconciled layered diagram.

## Tasks

1. **Scaffold the repo.** Create the `src/pdt/` package layout exactly as in `README.md`. Add `pyproject.toml` (Python 3.11+), `.gitignore`, `.env.example`. *AC: `pip install -e .` succeeds; `python -c "import pdt"` works.*
2. **Define Pydantic schemas for blueprint §3.** Implement `ValueHierarchy`, `DecisionStyle`, `BeliefNode`, `BeliefEdge`, `BeliefGraph`, `ReasoningTrace`, `DriftLogEntry`, `DriftLog`. Every scalar carries `value: float` **and** `confidence: float` (CI half-width) **and** `n_observations: int`. *AC: all schemas importable; round-trip serialize/deserialize tests pass; a missing confidence field fails validation.*
3. **Build the crypto module.** Key derivation from a user passphrase via Argon2id → encryption key; AES-GCM encrypt/decrypt at byte level; field-level and file-level helpers. *AC: a round-trip test encrypts and decrypts a payload; the derived key is never written to disk; tampering a ciphertext fails authenticated decryption.*
4. **Implement the encrypted DuckDB store.** DuckDB (embedded) with app-level AES-GCM envelope encryption over sensitive columns/values (DuckDB has no native crypto extension, so encrypt at the app layer before write; store ciphertext as `BLOB`). Tables (all append-only — no in-place updates, ever): `traces`, `model_params`, `drift_log`, `beliefs`, `edges`, `events` (audit). Belief graph queried via recursive CTEs. *AC: store a trace, restart the process, reload with correct passphrase, retrieve it. Wrong passphrase fails closed. An attempted UPDATE on an append-only table is rejected by a guard/check.*
5. **Wire the LanceDB vector store with versioning.** Enable LanceDB's native versioning (time-travel) on the traces + beliefs tables; embed and upsert a small doc; run a top-K similarity query. Keep the embedding model behind the LLM abstraction (it's an "AI call"). Record `embedding_model` (id+version) on every row to guard against embedding drift. *AC: 5 docs inserted, top-1 query returns the expected nearest doc; an upsert preserves the prior version retrievable via time-travel (the "store, don't overwrite" guarantee).*
6. **Build the LLM abstraction layer.** Define `LLMClient` Protocol (`complete`, `embed`) and one concrete client (e.g. OpenAI-compatible). **No other module may import a provider SDK directly** — enforce with an import linter rule. Prompt loading: `registry.render("reasoning_trace_extraction", version="v1", **vars)`. *AC: a test mocks the client; another test loads a real prompt file by id+version and asserts the rendered template.*
7. **Version-control prompts.** `prompts/<name>/vN.txt` with a manifest mapping logical id → file. Add a README documenting: one prompt per file, versioned, variables templated, change requires a version bump. *AC: changing a prompt without bumping the version fails CI.*
8. **Config & secrets.** `pydantic-settings` `Settings` class; provider keys, DB path, encryption params from `.env`. *AC: missing required setting raises a clear error on startup; `pdt doctor` reports config status.*
9. **FastAPI skeleton + one round-trip endpoint.** `/health` and e.g. `POST /debug/store` + `GET /debug/store/{id}` over the encrypted store (dev-only, gated by a flag). *AC: API starts, health returns 200, round-trip works end to end.*
10. **Quality gates & CI.** `ruff`, `mypy --strict` on `core/`, `pytest` with coverage gate (target ≥80% on `core/`). CI runs all three on push. *AC: CI is green on the main branch; a deliberately failing type check is caught.*

## Data models / schemas

Full §3 models in Pydantic. Key rule to encode now: **no scalar without uncertainty**.

```python
class ScoredScalar(BaseModel):
    value: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)   # CI half-width or 1−stderr
    n_observations: int = Field(0, ge=0)
    last_updated: date
    model_config = ConfigDict(frozen=True)            # append-only updates; never mutate
```

`ValueHierarchy` = map of 10 Schwartz dims → `ScoredScalar` + `stability_score`.
`DecisionStyle` = the 8 cognitive-style dims → `ScoredScalar`.
`ReasoningTrace`, `BeliefNode/Edge/Graph`, `DriftLog(Entry)` per blueprint §3.3–3.5.

## Interfaces

This phase *creates* (consumers come later):
- `core.llm.LLMClient` (Protocol), `core.llm.get_client()`, `core.llm.registry`.
- `core.crypto.derive_key()`, `encrypt()`, `decrypt()`.
- `memory.structured.StructuredStore` (Protocol) + DuckDB impl; **append-only** `insert` + `get_latest` / `history` over trace/model_param/belief/edge/drift. No `UPDATE`/in-place mutation (enforced by a guard).
- `memory.vector.VectorStore` (Protocol) + LanceDB impl; `upsert`, `query(top_k)`, plus `version_at(timestamp)` (time-travel) to satisfy the append-only "store, don't overwrite" rule.

## Blueprint & context references

- Blueprint §10 (Privacy Architecture) — drives the crypto + store design.
- Blueprint §3 (all subsections) — drives the schema set.
- `CODING_STANDARDS.md` — modular layers, single LLM abstraction, versioned prompts, snake_case.
- `MEMORY_STRATEGY.md` — "Memory must NEVER overwrite truth... Conflicting memories are stored, not replaced." → design the store as append-only / versioned.
- `MODEL_BEHAVIOR_RULES.md` — confidence thresholds exist from day one (schema enforces the field).

## Exit criteria (definition of done)

- [ ] Fresh clone → `pip install -e .` → `pdt init` → set passphrase → `pdt doctor` passes.
- [ ] Encrypted round-trip: store a value in DuckDB, kill process, reload, retrieve. Wrong passphrase fails.
- [ ] Append-only guarantee verified: re-inserting a param keeps both rows; an attempted UPDATE is rejected; `history()` returns the full series.
- [ ] LanceDB time-travel: an upsert preserves the prior version, retrievable via `version_at()`.
- [ ] A test that calls the LLM abstraction with a versioned prompt and a mocked provider passes.
- [ ] Import-linter rule proves no module outside `core/llm/` imports a provider SDK.
- [ ] Vector store top-K query returns sensible nearest docs on a 5-doc fixture; every row records its `embedding_model`.
- [ ] All five §3 schemas validate, serialize, and reject a payload missing a confidence field.
- [ ] CI green: `ruff`, `mypy --strict` on `core/`, `pytest` ≥80% on `core/`.
- [ ] No secret material in git; `.env.example` documents every variable.

## Risks & mitigations

| Risk | From `FAILURE_MODES.md` / blueprint | Mitigation |
|------|--------------------------------------|------------|
| DuckDB single-writer concurrency (it's in-process, one writer at a time) | — (infra) | Acceptable for single-user. Serialize writes through one writer task/coroutine in the app; reads are concurrent. Don't pretend it's a multi-writer server. |
| LanceDB versioning storage growth | — (infra) | Append-only is the *point*, but set a retention/compaction policy for vector history; keep model-param/trace history indefinitely (it's the drift substrate). |
| Embedding drift over time | `FAILURE_MODES.md` §System | Pin the embedding model id+version in `Settings`; record `embedding_model` on every vector row. Re-index path documented (Phase 6 operationalizes). |
| Secrets committed | Privacy mandate | Pre-commit secret scan; `.env` gitignored; CI checks. |
| Monolithic AI logic creeping in | `CODING_STANDARDS.md` | Import-linter boundary rule + code review. |
| Context overflow later | `FAILURE_MODES.md` §System | (Fwd) Retrieval layer (Phase 2) will budget context; note here, build there. |
| Lock-in / future multi-user | `PROJECT_INTENT` (multi-user is "future") | Both interfaces are Protocols; a Postgres+pgvector+AGE backend can be added later behind the same `StructuredStore`/`VectorStore` contracts. |

## Effort estimate

~2–3 weeks for one engineer. This is the highest-leverage time in the whole project — every shortcut here is paid back with interest.
