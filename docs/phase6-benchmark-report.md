# Phase 6 Benchmark Report

This report operationalizes the threshold clause from `project_context/EVALUATION_METRICS.md` and `to_do/PHASE_6.md`.

## Thresholds

- Memory recall accuracy > 75%
- Response consistency score > 80%
- Latency < 2s for standard queries

## How the repo now measures them

- **Memory recall accuracy**: `src/pdt/eval/harness.py` leave-one-out recall
- **Response consistency**: `src/pdt/eval/benchmark.py` exact-repeat stability on deterministic twin queries
- **Latency**: `src/pdt/eval/benchmark.py` in-process p95 over standard queries
- **Recognition score**: `src/pdt/eval/explanation_study.py` blind A/B scaffold

## Current honest status

The codebase now contains:

- a runnable benchmark report builder
- an API endpoint at `/eval/benchmark`
- automated tests asserting the benchmark surface exists and reports threshold statuses

What this does **not** yet prove is that the thresholds are met on a real longitudinal user dataset. The current fixtures are small synthetic/dev fixtures intended to verify behavior, not establish product-grade empirical performance.

## Gap and plan

Until a real dataset is collected, the threshold clause from Phase 6 should be treated as:

- **implemented and measurable** in code
- **not yet empirically certified** on production-like data

Plan to close the gap:

1. collect a larger longitudinal trace set from real use
2. run `/eval/benchmark` or the underlying benchmark module on that dataset
3. snapshot the observed values into this report
4. promote threshold failures into CI policy once the dataset is stable

## Why this is still Phase 6-complete

`to_do/PHASE_6.md` allows either:

- thresholds met on a real dataset, **or**
- a documented gap with a plan

This repository now satisfies the second path explicitly and honestly.
