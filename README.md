# Personal Digital Twin

A computational model of how a specific person thinks — an AI that reconstructs
*your* reasoning, value hierarchy, and decision style from your behavior, then
simulates how you'd think about new problems. Not advice. A simulation of your
own thinking, made legible.

> **Status:** Phase 0 — Foundation & Infrastructure. See [`to_do/`](to_do/) for
> the full phased implementation plan.

---

## Quick start

```bash
# 1. Create a virtual environment and install
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux
pip install -e ".[dev]"

# 2. Configure
cp .env.example .env            # fill in PDT_LLM_API_KEY, etc.

# 3. Create your encrypted vault
pdt init                        # prompts for a passphrase

# 4. Check everything is healthy
pdt doctor

# 5. Run the API server
pdt serve                       # → http://127.0.0.1:8000/health
```

## Architecture

Four layers, strictly separated (enforced by import-linter):

```
src/pdt/
  core/           # config, LLM abstraction, crypto, schemas
    llm/            # ← the ONLY place provider SDKs may be imported
    crypto/         # Argon2id key derivation + AES-GCM envelope encryption
    schemas/        # Pydantic v2 models for blueprint §3
    config.py       # pydantic-settings
  memory/         # structured (DuckDB) + vector (LanceDB) stores
    structured/      # append-only DuckDB; envelope-encrypted columns
    vector/          # LanceDB with native versioning
  api/            # FastAPI app
  ui/cli/         # Typer CLI
  cli.py          # pdt entry point
```

### Storage (no SQLite)

| Engine | Role |
|--------|------|
| **DuckDB** | Analytical/relational store — traces, model params, beliefs, edges, drift log. Append-only. App-level AES-GCM envelope encryption. |
| **LanceDB** | Vector store — semantic retrieval over traces/beliefs. Native versioning = append-only "memory never overwrites truth." |

Both are **embedded, in-process** — no database server. The system is single-user,
local-first, and encrypted at rest under a key derived from your passphrase.

### Key design rules

- **Every parameter carries a confidence interval.** No scalar is stored without
  uncertainty. The schema rejects payloads missing the `confidence` field.
- **Memory never overwrites truth.** All stores are append-only; conflicting
  evidence is recorded, not replaced.
- **Single LLM abstraction layer.** All LLM calls flow through `core.llm`; no
  module outside it may import a provider SDK (enforced in CI).
- **Prompts are version-controlled.** Changing a prompt without bumping its
  version is a CI failure.

## Development

```bash
ruff check src tests          # lint
ruff format --check src tests # format check
mypy                          # type check (strict on core/)
lint-imports                  # architecture boundary rules
pytest                        # tests + coverage (≥80% gate)
```

## Documentation

- [`to_do/README.md`](to_do/README.md) — phased implementation plan
- [`to_do/PHASE_0.md`](to_do/PHASE_0.md) — this phase's spec
- [`project_idea/personal-digital-twin.md`](project_idea/personal-digital-twin.md) — the full blueprint
- [`prompts/README.md`](prompts/README.md) — prompt versioning convention

## License

MIT
