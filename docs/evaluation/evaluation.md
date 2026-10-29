# EVALUATION PROTOCOL (Step 17)

Status: **ARCHIVED DRAFT — retained for historical context.**
The canonical Step 17 documentation now lives in:

- `EVALUATION_PROTOCOL.md`
- `DATASET_AND_ANNOTATION.md`
- `EXPERIMENT_SPEC.md`
- `REPRODUCIBILITY_SPEC.md`
- `DECISIONS.md`

This file remains as an earlier draft and should be read as a historical working note rather than as the final source of truth.

Evidence tags used in all five files:

| Tag | Meaning |
|---|---|
| `[DOC]` | Stated in a project document (`AGENTS.md`, `PROJECT_STATE.md`, `MASTER_SPEC.md`, `manual_validation.md`) |
| `[CODE-READ]` | Seen in source or test files by reading only. **Nothing was executed in Step 17.** |
| `[AGREED]` | Approved by the researcher in the Step 17 continuation message |
| `[PROV]` | Provisional recommendation. It is the default unless the researcher objects. See `DECISIONS.md` (PR-xx) |
| `[OPEN]` | Unresolved. Needs approval. See `DECISIONS.md` (OP-xx) |

---

## 1. Purpose, scope, step boundaries

Step 17 produces an evaluation *design*. It implements no configuration, changes no production code, mutates no database, runs no experiment, and makes no paid LLM call.

| Step | Role `[DOC]` | Relation to Step 17 |
|---|---|---|
| 16 | Inspection, career-fit verification, guarded isolated-DB validation (complete). Used FakeLLM. | Functional evidence only. Supplies the Recorder, artifact and contract infrastructure that Step 18 can reuse. |
| **17** | Evaluation framework and protocol | This document set. |
| 18 | Baseline and ablation configurations (`MASTER_SPEC §23`) | Implements what `EXPERIMENT_SPEC.md §12` requires. |
| 19 | Tests | Functional tests: metric-code tests, parity tests, FK inventory. These are not scientific evidence. |
| 20 | End-to-end experiments | Executes this protocol: pilot, then formal runs. |

Numbering drift `[DOC]`: `MASTER_SPEC §23` labels Step 16 as "logging". `PROJECT_STATE.md` redefined Step 16 as inspection and validation. The `MASTER_SPEC §19` logging deliverable (analysis_id, timestamp, model version, prompt version, KB version) is therefore **unassigned** (OP-18). Nothing in `backend/app` writes the MASTER_SPEC analysis tables `[CODE-READ]`.

## 2. Source audit

Inspected (read only): `MASTER_SPEC.md` and the master prompt, `AGENTS.md`, `PROJECT_STATE.md`, `manual_validation.md`, backend agents, services, repositories, schemas, workflow, API, inspection module, runner scripts, tests, config, and the frontend source.

**Not available, therefore not verified:**
- The thesis proposal (RQs, objectives, hypotheses, scope). The official RQ wording is unverified (OP-01).
- `docs/evaluation/*` (none existed before this step).
- The KB workbook, its README or data dictionary, and database DDL or FK inventory.
- The Step 16 artifact JSON `619d709…` (only its audit text in `PROJECT_STATE.md` was seen).

## 3. Agreed experimental design `[AGREED]`

| ID | Configuration | Objective |
|---|---|---|
| B0 | LLM-only, no OKB, no Verification Agent | LLM-only baseline |
| B2 | LLM receives OKB occupation–skill relationships; the LLM does matching and scoring | Contribution of structured occupational information |
| B3 | OKB + system-based matching and scoring, no Verification Agent | System matching and scoring without verification |
| F | OKB + system-based matching and scoring + Verification Agent | Complete proposed system |

Primary comparisons: **C1 = F vs B0**, **C2 = F vs B3**, **C3 = B2 vs B3**.

Superseded design elements `[DOC]` vs `[AGREED]`:
- `MASTER_SPEC §21` configs A–D map as follows: A → B0, B → B3, D → F. Config C ("KB off, verification on") is incoherent for the implemented verifier. Every verifier check compares output against the KB or against the deterministic engines `[CODE-READ]`. It is not used.
- B2 has no counterpart in `MASTER_SPEC`.
- The "LLM + semantic matching" baseline and `use_semantic_matching` are not part of the agreed design. No embedding or pgvector code was found `[CODE-READ]`.

## 4. Research questions and objectives — **PROVISIONAL MAPPING**

The thesis proposal was not available. The wording below comes from `MASTER_SPEC §25`, which is a planning document and **not** the official RQ list. It must not be quoted as the thesis RQs. Objectives mapping: **UNAVAILABLE** (OP-01).

| Provisional question (MASTER_SPEC §25) | Comparisons | Experiments | Primary metric | Secondary metrics | Evidence to report | Cannot show |
|---|---|---|---|---|---|---|
| P-RQ1 Grounding → career recommendation | C1; C3; secondary B2 vs B0 | E2 | M2 nDCG@3 | M1 Hit@1/3, tie-aware variants, M13 | Paired differences with CIs | That occupational *sources* cause the gain. OKB content, determinism and pipeline are fused in C1. |
| P-RQ2 Grounding → skill-gap | C3; F/B3/B2 vs B0 (secondary, KB-favouring) | E3, E9 | M5 status macro-F1 (oracle target) | M6 gap-set P/R/F1, M4 over-credit | As above, conditional on E9 | That OKB requirements are valid (needs E9). B0-vs-OKB gap results favour OKB configs by construction. |
| P-RQ3 Verifier → correctness and consistency | C2; E4a | E4a, E4b | M8 unsupported-claim rate (F vs B3) | M7 detection recall and FPR, resolution rate, M10 | Detection by fault class; resolution of first-pass defects | That the verifier *corrects* anything by itself (RISK-06). Structured outputs are expected identical in F and B3. |
| P-RQ4 MAS vs LLM-only benefit | C1 | E2, E3, E4b, E7 | M2 | M5, M6, M8 | As above | That *multi-agent structure* helps. C1 does not isolate any component. |
| P-RQ5 Traceability | none (descriptive) | E5b | M9 traceability L1–L3 | — | Rates per level, F and B3 | Validity or sufficiency of the evidence. B0 is zero by construction. |

Diagnostic experiments that answer no RQ directly but condition all of them: E1 (extraction and normalization), E5a (stability), E7 (operational), E8 (weight sensitivity), E9 (OKB expert audit), E6 (roadmap coverage).

## 5. Comparison matrix and valid claims

| Comparison | Status | Valid claim | Invalid claims |
|---|---|---|---|
| **C1 F vs B0** | Primary `[AGREED]` | Overall difference between the complete approach and an LLM-only baseline | Any single component's effect. Differs in OKB access, determinism, profile representation (catalog-assisted vs free text), pipeline, guards and verifier. |
| **C2 F vs B3** | Primary `[AGREED]` | The effect of verification **detection plus gated resampling** on returned outputs, if C2-VALID holds | "Verification improves correctness of structured outputs". Those outputs are deterministic and identical by design (§6.2). "Verifier corrects text". The revision loop resamples without feedback `[CODE-READ]`. |
| **C3 B2 vs B3** | Primary `[AGREED]` | LLM-driven vs system-based matching, scoring and gap classification, given equal OKB relationships and equal profile bundle, if C3-VALID holds | The value of OKB content (both have it). Which scoring *formula* is correct. The formula is validated only against human labels (E2/E3). |
| B2 vs B0 | Secondary `[PROV]`, OP-02 | Effect of giving the LLM OKB relations and the skill catalog | Effect of relations alone. B0 lacks the catalog, so the output vocabulary differs. |
| F vs B2 | Secondary `[PROV]`, OP-02 | End-to-end system vs LLM-with-OKB | Component attribution |
| B3 vs B0 | Secondary `[PROV]`, OP-02 | Effect of the system-based pipeline without verification | As F vs B0 |

### 5.1 Conditions that invalidate each primary comparison

**C2-VALID.** All must hold, otherwise C2 is reported as "not isolated":
1. Identical profile bundle (`profile_bundle_sha256` equal) and the same `user_id` for F and B3.
2. Identical KB fingerprint, `scoring_weights`, `max_tokens`, model identifier and inference settings.
3. Identical prompt-file hashes for every non-verifier call.
4. The only code difference is the absence of the verification node and the revision loop. Checked by a graph diff in Step 19.
5. Identical retry, timeout and failure-classification policy.
6. The first-pass outputs of F and B3 are shown to be equivalent. For structured outputs this is equality. For text it is distributional, and a sensitivity analysis uses F's stored first pass as the B3 sample (`EXPERIMENT_SPEC §7 E4b`).

**C3-VALID.** All must hold:
1. Information parity: B2 receives every field that `compute_career_fit` consumes (per requirement: `skill_id`, `evidence_class`, `confidence`; per user skill: `skill_id`, `evidence_status`, `proficiency`), the same profile bundle, and the same requirement set (hashes equal to B3's).
2. B2 receives no information B3 lacks (for example `evidence_source_text`), and B3 uses none that B2 lacks.
3. B2's prompt does not contain the numeric weights or formula, unless the run is labelled as the exploratory "formula-given" arm (OP-04). Otherwise the construct changes from "LLM judgement" to "LLM arithmetic".
4. B2 outputs are validated against the same schema and ID rules as B3. Invalid IDs are failures, not silently repaired.
5. No truncation at the token limit (truncation is a failure and is reported).
6. The B2 code path demonstrably calls none of the system's matching or scoring functions (tests T1–T2, `EXPERIMENT_SPEC §5`).

**C1.** No validity conditions can isolate a component. It is always interpreted as a whole-approach comparison. Additional caveat: B0 gap results are scored against an OKB-derived requirement set and are therefore structurally favourable to OKB configurations (RISK-01).

### 5.2 Confounds common to the comparisons

| Confound | Affects | Mitigation | Residual |
|---|---|---|---|
| Profile representation (B0 free text vs shared persisted bundle) | C1 | Report E1 separately; identical redacted CV text | Cannot be removed. It is part of "the approach". |
| In-agent guards (narrative validator, roadmap summary validator, normalizer ID check) exist in B3 and F `[CODE-READ]` | C2 | Record `validation_notes` and narrative-source labels | They attenuate any verifier effect on text. Reported as a limitation. |
| Unpinned temperature and seed `[CODE-READ]` | All | Repeats, interleaved order, record SDK defaults | Variance is part of the results (OP-07). |
| F receives up to `1 + max_revisions` samples of the owning agent | C2 | Analyse resolution rate and first-pass snapshots | Gain may reflect resampling plus a detector, not feedback. |
| Provider drift over time | All | Interleave configs within blocks; record timestamps and resolved model | Mutable aliases may hide drift. |
| Prompt-tuning effort | C1, C3 | Equal dev budget, freeze before test | Subjective. Document the effort. |
| LLM pretraining may contain ESCO or O*NET text | C1 | Disclose | Favours B0, i.e. conservative for F. |

## 6. Valid interpretation rules

### 6.1 Functional validation is not scientific evaluation
Step 16 results (X1–X11, H1–H9, contract) `[DOC]` show that the pipeline runs and is internally consistent *on a FakeLLM test double*. Their references are fresh reads of the same KB and recomputations with the same functions. They do not show accuracy, effectiveness, real-LLM behaviour, or occupational validity. A scientific claim needs a reference independent of the system and KB, or a comparison between configurations.

### 6.2 Structural invariance in F vs B3
Given an identical profile bundle and KB, the recommendation scores, ranking, gap categories and roadmap items are deterministic functions in both configs `[CODE-READ]`. They are expected to be identical. This is reported as an **equality audit** (count of differing outputs), not as a statistical test. Differences in returned text arise only from LLM sampling and from the revision loop.

## 7. Validity and reliability risks

| ID | Risk | Mitigation | Residual |
|---|---|---|---|
| RISK-01 | Ground-truth independence and circularity. The requirement set used in E3 is the OKB's own. | E1/E2 labels come from the CV and annotators blind to `career_skills`. E3 is declared *conditional on OKB validity* and is bounded by E9. B0 gap results are labelled KB-favouring. | E3 cannot be stronger than E9. |
| RISK-02 | OKB correctness and coverage. Curation method not visible; 24/87 skills lack structured `skill_source_evidence` rows `[DOC]`; the skill catalog has no language-level entries (Python is intentionally unmatched) `[CODE-READ]`. | E9 audit; coverage statistics reported (rows with evidence level L1/L2/L3). | Entry-level validity is only as good as E9. |
| RISK-03 | Expert validation. No qualified expert confirmed. | If no expert: narrow claims to agreement with annotated relevance, state "occupational validity unassessed". Never fabricate expert validation. | OP-12. |
| RISK-04 | LLM variability and reproducibility. | Repeats, ITT, record everything (`REPRODUCIBILITY_SPEC`). | No bitwise reproducibility is claimed for LLM stages. |
| RISK-05 | Bias in extraction, normalization and evidence attribution. Fuzzy threshold 0.88; an LLM-suggested ID is accepted if it exists in the catalog; Python-style hyponyms unmatched; Indonesian vs English wording. | E1 with dual-level labels (A1), language strata, false-match rate. | Annotator language skill. |
| RISK-06 | The verifier detects without correcting. The loop reruns the agent without feedback. | Report detection (E4a), resolution rate and persistence (E4b). Frame the verifier as detective. | OP-19. |
| RISK-07 | Self-report equals project/work evidence. The system sets `evidence_status='linked'` when any evidence row exists, **including** `self-report` `[CODE-READ]`. `MASTER_SPEC §18(7)` forbids treating unsupported claims as verified. | Dual reference policies S and E; over-credit rate M4; strata by evidence level. | OP-15. The definition is frozen, so no behaviour change is proposed. |
| RISK-08 | Ties. Tie-break is `career_id` (arbitrary). All-zero profiles produce a tied ranking. | Tie-aware sensitivity metrics; report the share of profiles with a tie crossing rank 3. | No abstention exists. |
| RISK-09 | Incomplete or empty profiles. | A low-evidence stratum is reported separately. | None. |
| RISK-10 | Failed runs. | ITT scoring plus a per-protocol secondary analysis. | Quota limits may reduce n. |
| RISK-11 | Leakage between OKB, prompts and labels. | Annotator material excludes `career_skills`. Synthetic profiles are authored from external sources. Baseline prompts tuned on dev only. | Pretraining leakage (conservative for F). |
| RISK-12 | Synthetic overclaiming. | Every result labelled with dataset type; S-M excluded from scientific claims. | Real-CV n may be small. |
| RISK-13 | Shared-extraction design hides extraction variance from B2/B3/F comparisons. | E5a reports both downstream-only and end-to-end stability. | C1 includes extraction differences. |
| RISK-14 | Schema/FK validity vs runtime cleanup. H9 shows zero remaining rows in nine written tables only `[DOC]`. | Read-only `information_schema` inventory in Step 19. | **Not verified today.** |

## 8. Statistical analysis plan `[PROV]` (PR-08)

- Unit of analysis: the profile. Repeats are averaged within profile first.
- Confirmatory family (Holm-corrected, two-sided):
  - H1: F vs B0 on nDCG@3.
  - H2: F vs B3 on unsupported-claim rate (M8).
  - H3: B2 vs B3 on nDCG@3.
  - H4: B2 vs B3 on status macro-F1 under the primary reference policy (M5).
- Everything else is exploratory and labelled so.
- Continuous endpoints: paired bootstrap (resample profiles) for the mean difference with a 95% CI. Wilcoxon signed-rank is secondary.
- Binary Hit@k: exact McNemar.
- H2 (sentence-level): cluster bootstrap by profile, so sentences are not treated as independent.
- Detection counts (E4a): exact Clopper–Pearson intervals.
- Report effect sizes and CIs first. State practical-significance thresholds before the pilot (OP-14). Do not claim "no difference" when the CI is wide.
- No power or sample size is stated. The method is pilot-estimated variance (σ_d) followed by n ≈ (z·σ_d/d)² for a target half-width d (OP-13).
- Structural-invariance audits (F vs B3 structured outputs) are counts, not tests.

## 9. Reporting rules

1. Report all four configurations on every metric where defined, including failure rates.
2. Label each result with dataset type (R, S-H), split, and ITT or per-protocol.
3. Never present S-M or Step 16 results as accuracy evidence.
4. Never describe the roadmap as pedagogically effective. Only coverage and groundedness are measured.
5. Never describe the verifier as "improving correctness" of deterministic outputs.
6. Report negative and null results with CIs.
7. State which claims depend on OKB validity (E9) and whether E9 was performed.

## 10. Step 17 completion criteria

See `DECISIONS.md` for open approvals and the completion report in the Step 17 handoff. Step 17 is not complete until: official RQs verified (OP-01), documents placed in the repository, and gate-A decisions closed.