"""Guardrails for version-controlled prompts."""

from __future__ import annotations

import json
from pathlib import Path


def test_manifest_matches_prompt_files() -> None:
    prompts_dir = Path("prompts")
    manifest = json.loads((prompts_dir / "_manifest.json").read_text(encoding="utf-8"))

    for name, entry in manifest.items():
        versions = entry["versions"]
        assert entry["latest"] in versions
        for version in versions:
            assert (prompts_dir / name / f"{version}.txt").exists()

    for prompt_dir in prompts_dir.iterdir():
        if not prompt_dir.is_dir():
            continue
        declared = set(manifest[prompt_dir.name]["versions"])
        actual = {path.stem for path in prompt_dir.glob("v*.txt")}
        assert declared == actual
