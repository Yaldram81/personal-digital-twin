# Prompts

Version-controlled prompt templates for the Personal Digital Twin.

## Convention

- One prompt per directory: `prompts/<name>/`
- Each version is a file: `v1.txt`, `v2.txt`, etc.
- The **manifest** (`_manifest.json`) maps logical names to latest versions
  and tracks all known versions.
- **Changing a prompt without bumping the version fails CI.** The manifest
  is the source of truth for what version the system uses.

## Loading

Prompts are loaded via `pdt.core.llm.registry`:

```python
from pdt.core.llm import render

prompt = render("reasoning_trace_extraction", version="v1", narration=user_text)
```

If `version` is omitted, the latest version from the manifest is used.

## Adding a new prompt

1. Create the directory: `prompts/<name>/`
2. Create the version file: `prompts/<name>/v1.txt`
3. Add the entry to `_manifest.json` with `"latest": "v1"` and `"versions": ["v1"]`

## Bumping a version

1. Copy `v1.txt` → `v2.txt` (or create fresh)
2. Update `_manifest.json`: add `"v2"` to `versions` and set `"latest": "v2"`
3. Commit both files together
