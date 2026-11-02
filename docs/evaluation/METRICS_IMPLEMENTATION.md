# Metrics Implementation (Step 17)

Status: implemented and unit-tested. This document describes the executable
measurement layer in `backend/app/evaluation/`. It does **not** report any
experimental result: no reference corpus exists in the repository yet, so every
label-dependent metric is `unavailable` until labels are supplied.

## 1. Scope and step boundary

| Layer | Owner | Status |
|---|---|---|
| Metric formulas and input contracts | Step 17 (`backend/app/evaluation/`) | Implemented |
| Configuration definitions B0/B2/B3/F | Step 17 (`configurations.py`) | Implemented (descriptive only) |
| Adapters from `analysis_log/1.0` and agent outputs | Step 17 (`adapters.py`) | Implemented |
| Experiment runner, configuration switching, manifests, artifact persistence | Step 18 | **Not implemented** |
| Infrastructure validation matrix | Step 19 | **Not implemented** |
| Pilot and formal experiments | Step 20 | **Not implemented** |

Step 17 never runs the workflow, never calls an LLM, never writes to the
database, and never creates reference labels. It consumes a case that a Step 18
runner (or a test) supplies.

## 2. Evaluation unit

* One `EvaluationCase` = one `profile_id` under one configuration.
* `ProfileEvaluation` holds the metrics for that case.
* `EvaluationReport` aggregates **within a profile first**, then across
  profiles. Repeating a profile for stability does not over-weight it.
  `case_count` counts cases; `profile_count` counts distinct profiles;
  `MetricResult.n` is the number of profiles that contributed a value, and
  `MetricResult.skipped` is the number of profiles where the metric applied but
  could not be computed.

A report must contain cases from exactly one configuration. Mixed
configurations and an empty batch raise `ValueError`. In addition to the
profile-level metrics, the report computes `career.stability_at_3` from
repeated runs of the same profile when at least two runs are present.

## 3. Input contracts

All models are in `app/evaluation/schemas.py` and reject corrupted input
(duplicate IDs, negative relevance, fault IDs outside the audited pool,
mismatched profile IDs) with a Pydantic `ValidationError`.

### 3.1 Prediction side

| Model | Fields used |
|---|---|
| `RecommendationPrediction` | `ranking` (rank 1 first), `fit_scores`, `referenced_skill_ids`, `evidenced_skill_ids`, `evidence_reference_counts` |
| `SkillGapPrediction` | `career_id`, `required_skill_status`, `unmatched_user_claim_keys` |
| `RoadmapPrediction` | `items[]` with `skill_id`, `gap_status`, `learning_action`, `knowledge_base_basis` |
| `VerificationPrediction` | `status`, `checks[]`, `reported_claim_ids`, `first_pass_status`, `revision_count` |
| `OperationalMetadata` | `latency_ms`, `token_usage`, `api_call_count`, `retry_count`, `revision_count` |

Predictions are optional. A failed or unavailable output is represented by
`None` (or `run_status="failed"`), not by an empty fabricated result.

### 3.2 Reference side

| Model | Purpose |
|---|---|
| `RecommendationReference` | `career_id -> relevance` labels for one profile |
| `SkillGapReference` | `required_skill_status` for one career plus `unmatched_user_claim_keys` |
| `VerificationReference` | `injected_fault_ids` and, optionally, `audited_claim_ids` |
| `KbReference` | canonical career IDs, canonical required-skill IDs per career, known skill IDs |

`unmatched_user_claim_keys` is a claim-level identifier set. It is **never**
converted into a required-skill status and never counted as a missing skill.
The reference skill status remains the three required-skill categories only.

### 3.3 Adapters

`adapters.py` projects real output without modifying it:

* `recommendation_prediction_from_outputs` preserves the system's existing
  ranking order. `matched_skills` becomes the evidenced set (one evidence
  reference per matched skill); `claimed_only_skills` and
  `missing_skills_preview` are referenced but not evidenced.
* `skill_gap_prediction_from_outputs` keeps the three required-skill categories
  in `required_skill_status` and stores `unmatched_user_claims` under
  `user_skill_id:<n>` keys.
* `roadmap_prediction_from_outputs` accepts only the two canonical gap statuses
  and the two canonical learning actions.
* `verification_prediction_from_outputs` keys reported claims as
  `"<component>::<claim>"`. A Step 18 harness may inject a different key
  function if it owns the fault labels.
* `case_from_analysis_record` reads a Step 16 `analysis_log/1.0` record. The
  record does not store the configuration, so `config_id` is mandatory. Runtime
  metrics stay `None` instead of being inferred.

## 4. Metric definitions

`P@k` below is the set of the first `k` ranked careers. `rel(c)` is the supplied
relevance label. A career is relevant when `rel(c) >= 1`.

### 4.1 Career ranking

| Metric | Formula | Undefined when |
|---|---|---|
| `career.hit_at_1` | `1` if any `c in P@1` is relevant, else `0` | no relevant career is labeled |
| `career.hit_at_3` | `1` if any `c in P@3` is relevant, else `0` | no relevant career is labeled |
| `career.ndcg_at_3` | `DCG@3 / IDCG@3`, `DCG = sum((2^rel - 1) / log2(rank + 1))` | IDCG is zero |
| `career.mrr` | `1 / rank` of the first relevant career, else `0` | no relevant career is labeled |
| `career.tie_at_3` | `1` if equal fit scores cross the top-3 boundary, else `0` | fewer than 4 ranked careers carry a fit score |
| `career.stability_at_3` | mean pairwise Jaccard overlap of the top-3 sets across repeated runs of a profile | no profile has at least two usable runs |
| `top_k_overlap` (helper) | Jaccard overlap of two top-k sets | both sets empty |
| `mean_pairwise_top_k_stability` (helper) | mean pairwise top-k overlap over repeated runs | fewer than two usable runs |

Ties are reported separately instead of being hidden inside Hit@k. The
deterministic engine breaks ties by `career_id`; the tie indicator makes that
arbitrary ordering visible. `career.stability_at_3` is produced by the report
only when a profile has at least two runs; a single-run design reports it as
`unavailable`. Step 18 owns the repeated-run schedule that supplies those runs.

### 4.2 Skill-gap classification

Reference statuses are exactly `matched_evidenced`, `matched_claimed_only`, and
`missing`. The fourth canonical category, `unmatched_user_claims`, is measured
separately as a claim-level set (`skill_gap.unmatched_claim_recall`) because it
labels user claims rather than required skills; forcing it into the per-skill
status macro-F1 would misrepresent it as a missing career requirement.

For each status:

* `precision = TP / (TP + FP)`
* `recall = TP / (TP + FN)`
* `f1 = 2 * precision * recall / (precision + recall)`

A skill present in the reference but absent from the prediction counts as a
false negative. A supported status with no predicted member has precision `0`
by convention, so macro-F1 remains defined for every status that has reference
support. `status_macro_f1` is the unweighted mean over statuses with non-zero
reference support; `status_accuracy` is `correct / reference_skills`.

Exposed names:

* `skill_gap.status_macro_f1`, `skill_gap.status_accuracy`
* `skill_gap.<status>.{precision,recall,f1}` for the three statuses
* `skill_gap.<status>_set.{precision,recall,f1}` for `missing` and
  `matched_claimed_only`
* `skill_gap.over_credit_rate` — reference-`missing` skills predicted as
  `matched_evidenced` or `matched_claimed_only`, divided by reference-`missing`
  skills
* `skill_gap.unmatched_claim_recall` — claim-set recall for unmatched user
  claims

Empty denominators produce `None` / `unavailable`, never a fabricated zero.

### 4.3 Verification

Using controlled fault-injection labels:

* `verification.detection_recall = TP / injected`
* `verification.detection_precision = TP / reported`
* `verification.false_positive_rate = reported non-injected audited claims / audited clean claims`
* `verification.outcome_pass = 1` when final status is `PASS`
* `verification.revision_triggered = 1` when `revision_count > 0`
* `verification.revision_count` — recorded integer
* `verification.resolution` — `1` if a non-`PASS` first pass ends in `PASS`;
  undefined when the first pass already passed

`false_positive_rate` stays unavailable when `audited_claim_ids` is omitted; the
framework does not assume unreported claims were clean.

### 4.4 Traceability and roadmap

Traceability levels for each ranked career:

* **L1** — the career ID exists in the canonical KB and has requirements.
* **L2** — every referenced skill is a canonical requirement of that career and
  exists in the known skill set.
* **L3** — every evidenced skill additionally carries at least one evidence
  reference. A career with no evidenced skill caps at L2.

Rates are `traceability.recommendation_l{1,2,3}_rate`, plus
`traceability.evidence_lineage_rate` and `traceability.gap_item_lineage_rate`.
An empty item set is undefined, not a failure.

Roadmap metrics compare the roadmap against the authoritative gap status
(reference labels when available, otherwise the deterministic system result):

* `roadmap.coverage` — expected gap skills covered / expected gap skills
* `roadmap.unsupported_item_rate` — items outside the expected gap set / items
* `roadmap.grounding_rate` — items with non-empty `knowledge_base_basis` / items
* `roadmap.status_consistency` — actionable items whose `gap_status` equals the
  gap result
* `roadmap.action_consistency` — actionable items whose `learning_action`
  matches `develop_skill` for `missing` and `add_linked_evidence` for
  `matched_claimed_only`

### 4.5 Operational and failure metrics

`operational.failure` is `1` when `run_status == "failed"`, else `0`. Latency,
token usage, API-call count, retry count, and revision count are emitted only
when the case supplies them; the Step 16 record does not, so they remain
unavailable rather than being guessed.

## 5. Missing, malformed, and unavailable handling

| Situation | Behaviour |
|---|---|
| No reference labels | Label-dependent metrics are omitted and a warning is recorded |
| Empty reference labels | Metrics present with `status="unavailable"` and a reason |
| Failed run / missing prediction | Labels are kept; affected metrics are `unavailable` |
| Gap prediction refers to a different career | Gap metrics are `unavailable` |
| Denominator is empty | Value is `None` / `unavailable` |
| Malformed labels (duplicates, negative relevance, bad status) | Input validation fails loudly |
| Mixed configurations in one report | `ValueError` |
| Empty case batch | `ValueError` |

`MetricResult.status` distinguishes a real `0.0` from an undefined measurement.
Every unavailable metric carries a human-readable `reason`.

## 6. Output format

`EvaluationReport` serializes to JSON with `report.to_dict()`:

```json
{
  "schema_version": "evaluation/1.0",
  "generated_at": "2026-10-30T00:00:00Z",
  "config_id": "F",
  "case_count": 1,
  "profile_count": 1,
  "failed_case_count": 0,
  "metrics": {
    "career.hit_at_1": {
      "name": "career.hit_at_1",
      "status": "computed",
      "value": 1.0,
      "unit": "ratio",
      "n": 1,
      "skipped": 0,
      "reason": null
    }
  },
  "profiles": [],
  "warnings": []
}
```

The report is deterministic apart from `generated_at`. `profiles` retains the
per-profile values so aggregation can be audited.

## 7. Configuration compliance

`configurations.py` defines exactly B0, B2, B3, and F with the flags documented
in `EVALUATION_PROTOCOL.md` and `EXPERIMENT_SPEC.md`. `get_configuration` and
`validate_configuration_manifest` reject any other ID. These are declarations;
no runtime switching is implemented in Step 17.

## 8. Known limitations

* No reference dataset or annotation exists in the repository, so no metric here
  has been computed on real data and no effectiveness claim is possible.
* The Step 16 `analysis_log/1.0` record does not store configuration, latency,
  token usage, or API-call count. Those fields must come from the Step 18
  manifest/runner.
* Stability is computed when the report receives repeated runs of a profile;
  Step 17 does not create the repetition schedule (Step 18 does).
* Roadmap `knowledge_base_basis` is treated as a non-empty citation string; it
  is not re-validated against the KB records in this layer.
* The verification claim-key function is a harness convention, not an official
  identity scheme. Step 18 must keep the key function fixed for a run.
* E8 weight sensitivity and E9 KB validity are specified in
  `EXPERIMENT_SPEC.md` but are not implemented as Step 17 metrics.

## 9. Verification

Executed in `backend/`:

```text
.\.venv\Scripts\python.exe -m pytest tests\test_evaluation_metrics.py tests\test_evaluation_framework.py -q
```

Result at the time of this record: **66 passed**. The suite covers formula
hand-computation, empty denominators, missing/malformed labels, failed runs,
career mismatch, claim-set separation, traceability levels, roadmap grounding,
tie detection, repeated-run stability, configuration validation, Step 16
adapters, an end-to-end analysis-record-to-report path, repeat-within-profile
aggregation, JSON serialization, and the stability/tie helpers.
