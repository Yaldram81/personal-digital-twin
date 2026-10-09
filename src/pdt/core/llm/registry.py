"""Version-controlled prompt registry.

Per CODING_STANDARDS.md: "All prompts must be version-controlled."

Prompts live as files under ``prompts/<name>/vN.txt``. The manifest
(``prompts/_manifest.json``) maps logical ``<name>`` to the latest version
file and records all known versions. Changing a prompt without bumping the
version is a CI failure.

Usage::

    registry.render("reasoning_trace_extraction", version="v1", **vars)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, cast


def _resolve_prompts_dir() -> Path:
    """Locate the prompts directory.

    Resolution order:
    1. ``PDT_PROMPTS_DIR`` env var (explicit override).
    2. ``./prompts`` relative to the current working directory.
    3. Package-relative: ``<repo-root>/prompts`` (this file lives at
       ``<repo-root>/src/pdt/core/llm/registry.py``).
    """
    env = os.environ.get("PDT_PROMPTS_DIR")
    if env:
        return Path(env).expanduser().resolve()

    cwd_candidate = Path.cwd() / "prompts"
    if (cwd_candidate / "_manifest.json").exists():
        return cwd_candidate

    pkg_candidate = Path(__file__).resolve().parents[4] / "prompts"
    if (pkg_candidate / "_manifest.json").exists():
        return pkg_candidate

    # Last resort: the package-relative path even if missing (callers get a
    # clear FileNotFoundError naming the location).
    return pkg_candidate


_PROMPTS_DIR: Path = _resolve_prompts_dir()
_MANIFEST_FILE = _PROMPTS_DIR / "_manifest.json"


def _load_manifest() -> dict[str, Any]:
    if not _MANIFEST_FILE.exists():
        return {}
    return cast(dict[str, Any], json.loads(_MANIFEST_FILE.read_text(encoding="utf-8")))


class PromptRegistry:
    """Load and render versioned prompts from the ``prompts/`` directory."""

    def __init__(self, prompts_dir: Path | None = None) -> None:
        self._dir = prompts_dir or _PROMPTS_DIR
        manifest_file = self._dir / "_manifest.json"
        if manifest_file.exists():
            self._manifest = cast(
                dict[str, Any],
                json.loads(manifest_file.read_text(encoding="utf-8")),
            )
        else:
            self._manifest = {}

    def render(self, name: str, version: str | None = None, **variables: str) -> str:
        """Load a prompt template and substitute variables.

        Args:
            name: Logical prompt id (e.g. ``reasoning_trace_extraction``).
            version: Explicit version (e.g. ``v1``). If ``None``, uses the
                latest version recorded in the manifest.
            **variables: Key-value pairs to substitute into the template
                via ``str.format_map``.

        Returns:
            The rendered prompt text.

        Raises:
            FileNotFoundError: If the prompt file doesn't exist.
            KeyError: If a required variable is missing.
        """
        version = version or self._latest_version(name)
        path = self._dir / name / f"{version}.txt"
        if not path.exists():
            raise FileNotFoundError(f"prompt not found: {path}")

        template = path.read_text(encoding="utf-8")
        return str(template.format_map(variables))

    def list_prompts(self) -> list[str]:
        """Return all known prompt names."""
        return list(self._manifest.keys())

    def versions(self, name: str) -> list[str]:
        """Return all registered versions for a prompt."""
        entry = self._manifest.get(name, {})
        return list(entry.get("versions", []))

    def _latest_version(self, name: str) -> str:
        entry = self._manifest.get(name)
        if not entry:
            raise ValueError(f"unknown prompt: {name}")
        return cast(str, entry["latest"])

    def __repr__(self) -> str:
        return f"PromptRegistry(dir={self._dir}, prompts={len(self._manifest)})"


# Module-level singleton for convenience.
default_registry = PromptRegistry()

render = default_registry.render
list_prompts = default_registry.list_prompts

__all__ = ["PromptRegistry", "default_registry", "render", "list_prompts"]
