"""Reserved package for cross-cutting numerical primitives.

`to_do/README.md` anticipated a shared `core/stats/` math layer for
confidence-interval and evidence-weighting utilities. In practice, that math
ended up living next to the domain code that owns it instead:

- `pdt.model.confidence` — confidence-interval computation (Phase 2).
- `pdt.inference.uncertainty` — CI propagation, Monte Carlo composition (Phase 4).
- `pdt.inference.changepoint` — BOCPD core (Phase 4).

`core/` is the innermost layer (per the import-linter layered-architecture
contract in `.importlinter`): nothing in `core/` may depend on `model/` or
`inference/`, so this package intentionally does **not** re-export those
modules — doing so would invert the dependency direction. It stays a
documented, empty placeholder rather than a shortcut that violates the
layering rule. If a genuinely core-level (dependency-free) numerical
primitive emerges that both `model/` and `inference/` need, it belongs here.
"""

from __future__ import annotations

__all__: list[str] = []
