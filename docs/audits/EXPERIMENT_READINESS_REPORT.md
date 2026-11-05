# Experiment Readiness Report

**Date:** 2026-11-04  
**Scope:** B0, B2, B3, and F readiness only; no experiment arms executed.

## Readiness matrix

| Component | Current status | Missing requirement | Next action |
|---|---|---|---|
| B0 | **PARTIAL** | Configuration definition exists, but no Step 18 execution runner or approved annotation corpus | Implement the runner and prepare real annotations |
| B2 | **PARTIAL** | Configuration definition exists; KB target import and runner are incomplete | Resolve target schema/import, then implement runner wiring |
| B3 | **PARTIAL** | Deterministic matching/scoring exists; target approved KB is not imported and no runner exists | Resolve import and add isolated execution/manifest path |
| F | **PARTIAL/BLOCKED** | Verification/revision components and config exist; no Step 18 runner, approved corpus, or completed target import | Complete B3 prerequisites, then wire bounded verification/revision runs |

## Evidence

- `backend/app/evaluation/configurations.py` defines B0/B2/B3/F.
- `backend/app/evaluation/metrics.py` and `evaluator.py` implement metric calculations.
- No Step 18 baseline/ablation runner or repeated-run manifest workflow was found.
- The repository contains schemas and tests for annotation-shaped inputs, but no verified ground-truth annotation corpus was found in the inspected artifact paths.

## Metrics

The metric implementations exist, including career nDCG@3 and skill-gap Macro-F1. Label-dependent results are **BLOCKED** until real annotations and expert validation are available. No metric value was fabricated. Traceability and latency/token metrics are also dependent on execution instrumentation and run manifests.

## Shortest next implementation step

1. Obtain approval for the target-only varchar widening required by the approved Kominfo source value.
2. Re-run the target import and all FK/provenance/count validations.
3. Implement the Step 18 runner with isolated configuration switching and machine-readable run manifests.
4. Prepare and validate the annotation corpus before formal B0/B2/B3/F runs.

No experiment was started in this stage.
