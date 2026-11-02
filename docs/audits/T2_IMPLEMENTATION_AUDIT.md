# T2 Implementation Audit

**Audit type:** Read-only implementation audit against the approved T1 design freeze  
**Repository revision inspected:** `7020a9f`  
**Audit result:** The repository-level audit is complete. It found substantial implementation gaps; completion of this audit does not mean the system is implementation-ready. The live database schema and current database contents remain unverified and are assigned to the later T4 readiness gate.

## 1. Executive Summary

The existing application has a functioning profile-to-recommendation, skill-gap, roadmap, verification, and workflow path. Several of its deterministic foundations align with T1: `compute_career_fit()` is shared by recommendation and skill-gap calculations; the four required skill-gap categories are preserved; roadmap items are derived from the supplied gap and checked against occupational context; and the general verifier reports findings without mutating its input objects.

The most critical conflict is evidence acceptance. The Profile Agent persists evidence of any declared type, including `self-report`; the repository marks a skill `linked` when any evidence row exists; and career fit treats every `linked` skill as evidenced. The existing profile smoke script explicitly expects a self-report-only skill to become linked. This conflicts with the approved rule that only a PASS Activity–Skill candidate may produce activity-derived evidence and that self-report and other non-activity records are not automatically accepted as `matched_evidenced`.

The approved claim/activity architecture is not present in the inspected application: there is no distinct user TechnologyClaim, CompetencyClaim, ActivitySkillCandidate, or activity-derived CompetencyEvidence lifecycle; no technology alias normalizer; and no Activity–Skill verification rubric. Experience and Project records exist, but the inspected extraction/persistence path does not preserve source spans or connect those records to skill candidates. The current general Verification Agent verifies downstream recommendation, gap, roadmap, and occupational-provenance outputs, not the approved four checks for each candidate.

B0/B2/B3/F are descriptive metadata, not independently runnable configurations. In particular, no implementation supplies B2 with all 10 careers and each complete Career–Skill relationship set. The evaluation metric layer has code and tests, but no experiment runner, validated reference corpus, annotation results, or formal experiment results were found in the inspected repository state.

## 2. Repository and Implementation Areas Inspected

The audit compared source, schemas, tests, and evaluation documentation with `docs/design-freeze.md`, `docs/master_checklist_pra_ablation.md`, `docs/evaluation/DECISIONS.md`, and `docs/evaluation/EXPERIMENT_SPEC.md`. Inspected implementation areas include:

- CV upload, text extraction, PII redaction handoff, Profile Agent extraction and persistence, user schemas/repository, and competency normalization.
- Career recommendation, the shared career-fit service, skill-gap service and schemas.
- Roadmap generation, verification, workflow state/transitions, and representative tests.
- B0/B2/B3/F metadata, evaluation schemas/adapters/metrics, evaluation tests, and dataset/reproducibility documentation.
- Repository file patterns for SQL, migration, and activity/claim/technology-alias implementations.

The working tree was already dirty at inspection (`git status --short`); this report is the only file created for T2. No pre-existing changes were reverted or overwritten. No tests were run. No application, database, import, CV, LLM, or browser workflow was executed. Database findings below are limited to repository code and checked-in files; absence of local DDL does not establish the live database’s tables, constraints, or contents.

The supplied `instruction.md` ends mid-word at “Do not mark T2 complete if substantial implementation areas remain unins…”. The audit therefore does not infer a hidden continuation. It completed inspection of the repository-level implementation areas listed above; live database parity remains explicitly unverified and belongs to T4 per the T1/checklist documents.

Status meanings: **IMPLEMENTED** = direct implementation satisfies the inspected requirement; **PARTIAL** = some relevant behavior exists but does not satisfy the full contract; **MISSING** = no implementation found in inspected repository scope; **CONFLICTING** = observed behavior contradicts an approved decision; **UNVERIFIED** = evidence is insufficient to determine implementation/runtime state.

## 3. Implementation Gap Matrix

| Design requirement | Actual implementation | Evidence (file/function/line) | Status | Gap or risk | Recommended next action |
|---|---|---|---|---|---|
| Separate TechnologyClaim and CompetencyClaim records | User profile has one `UserSkillOut` claim model; the occupational `TechnologyOut` is not a user-claim model. The extraction response has one `skills[]` list and no technology-claim list. | `backend/app/schemas/user.py:65-82`; `backend/app/schemas/retrieval.py:93-119`; `backend/app/agents/profile_agent.py:33-58` | MISSING | A technology mention is not structurally isolated from competency claims. | Define and implement separate claim contracts during T3/T5. |
| Preserve source text/reference and section for claims and Activities | CV extractor returns a single extracted text string and basic document metadata. Profile Agent persists whitelisted Experience/Project fields, not source offsets, sections, or source references. | `backend/app/services/cv_text_extraction_service.py:35-45, 159-219`; `backend/app/api/routes/analysis.py:70-110`; `backend/app/agents/profile_agent.py:86-119` | PARTIAL | Source text reaches extraction after redaction, but the persisted structured records do not retain the approved Activity-to-source trace. | Specify source-reference/span and retention rules in T3. |
| Represent Experience/Project as Activities | Experience and Project output models and persistence methods exist with their own record identifiers. There is no common Activity abstraction/type or lifecycle in the inspected code. | `backend/app/schemas/user.py:29-49`; `backend/app/services/user_service.py:36-48`; `backend/app/agents/profile_agent.py:100-112` | PARTIAL | Existing records could be sources for Activities, but do not implement the approved candidate source contract. | Map source records to stable Activity identities in T3 before candidate generation. |
| Generate canonical ActivitySkillCandidates | No candidate-generation model, service, prompt output, repository path, or workflow node was found. | `backend/app/agents/profile_agent.py:33-58, 86-154`; `backend/app/workflows/career_workflow.py:419-453`; repository search for candidate symbols found only T1 documentation. | MISSING | No path exists to independently relate an activity to a canonical skill. | Implement after T3 data and source-reference contracts are approved. |
| Only PASS candidates create CompetencyEvidence | Profile Agent writes generic evidence rows directly; any row changes user skill status to `linked`. No Activity–Skill candidate gate precedes persistence. | `backend/app/agents/profile_agent.py:121-154`; `backend/app/repositories/user_repository.py:245-269` | CONFLICTING | Self-report, education, certification, or other evidence may be counted as evidenced without approved verification. | Make the PASS candidate outcome the only activity-derived evidence path; preserve other claims as unaccepted. |
| Stable Activity ID + canonical Skill ID evidence deduplication | Generic evidence de-duplication uses user-skill ID, evidence type, normalized description, and URL; it omits `source_table`/`source_id`. User-skill insertion conflicts on exact `(user_id, claimed_skill)`, not canonical skill ID. | `backend/app/repositories/user_repository.py:211-227, 245-262` | PARTIAL | The approved identity key and same-source excerpt protection are not implemented. Physical uniqueness constraints are not established by this code. | Implement the approved identity/dedup rules after T3 contract design and schema review. |
| DB relationships, constraints, indexes, lifecycle fields | Repository SQL expects user/evidence tables; no checked-in SQL or migration files were found. No candidate lifecycle/status/revision persistence is present in the inspected application models. | `backend/app/repositories/user_repository.py:211-273`; checked-in `*.sql`, migration, and `alembic.ini` searches returned no files | UNVERIFIED | Runtime schema, foreign keys, unique indexes, delete behavior, and data inventory were not inspected and must not be inferred from SQL strings or Pydantic models. | Complete read-only schema and integrity verification at T4; do not assume parity. |
| Technology name/alias normalization is exact and collision-checked | No user technology normalizer or alias-resolution implementation was found. `TechnologyOut` exposes technology identity/name/type/source only. | `backend/app/schemas/retrieval.py:93-101`; no alias implementation found in inspected backend | MISSING | NFKC/case-fold/whitespace exact matching, alias collision detection, and catalog fingerprinting are absent. | Implement only against the approved catalog/alias contract; no fuzzy technology-ID assignment. |
| Competency normalization against canonical skills | Exact normalized-name matching, fuzzy matching at `0.88`, then validated LLM-suggested canonical ID; invalid IDs remain unmatched. | `backend/app/agents/skill_normalizer.py:18-50`; called by `backend/app/agents/profile_agent.py:121-136` | PARTIAL | Canonicalization exists, but fuzzy and LLM-assisted outcomes require documented evaluation; this is competency matching, not the prohibited technology-ID fuzzy mapping. | Retain only as an explicitly evaluated competency policy; implement a separate exact-only technology normalizer. |
| Technology mentions cannot silently become competency evidence | The extraction prompt requests `skills[]` but no `technology_claims[]`; evidence is linked to those skills by text key and persisted. There is no type guard that rejects tool-name-only claims/evidence. | `backend/app/agents/profile_agent.py:33-58, 121-154` | PARTIAL | A technology mention may be emitted as a skill/evidence item; the code does not enforce the approved separation. This is a risk, not proof that every technology mention is misclassified. | Add distinct extraction outputs and enforce the evidence boundary with focused tests. |
| Candidate verification uses four approved checks and aggregation | The verifier checks recommendation scores/ranking, gap consistency, roadmap consistency/coverage, provenance, and LLM-generated text. Its `FAIL`-then-`REVISE`-then-`PASS` aggregation is for these general checks, not candidate-level traceability/relevance/inference/sufficiency. | `backend/app/agents/verification_agent.py:159-276, 278-329, 373-420, 426-514, 669-679` | MISSING | Approved Activity–Skill verification rubric and per-dimension findings do not exist. | Add the approved four-check contract to T6; preserve each finding and candidate. |
| REVISE is explicit, bounded, owner-only, and reverified | Workflow has configurable nonnegative `max_revisions` (default 2), selects an owner from findings, routes to that stage, and re-runs dependent stages and verification. Existing agent interfaces have no feedback-taking revision method; prior stage outputs are replaced in state. | `backend/app/workflows/career_workflow.py:116-141, 311-399, 419-453`; tests `backend/tests/test_career_workflow_unit.py:175-266` | PARTIAL | Cap, routing, and re-verification exist for general outputs, but no explicit feedback is passed to the owner and no original-output snapshot is maintained for comparison. No activity-candidate lifecycle is covered. | Add explicit, bounded owner feedback and original/finding preservation in the relevant candidate lifecycle. |
| Verification reports rather than silently mutating received outputs | Verifier computes checks and returns a separate result; a unit test snapshots the inputs before/after. | `backend/app/agents/verification_agent.py:588-679`; `backend/tests/test_verification_agent_unit.py:223-243` | IMPLEMENTED | This guarantee applies to the inputs it currently verifies, not candidate evidence, which is not part of the verifier. | Preserve this invariant when candidate verification is added. |
| Exactly 10 canonical careers are used | Recommendation agent retrieves `rs.get_all_careers()` and scores each returned career. No explicit count/allowlist validation is visible in the agent/workflow. The live catalog was not queried. | `backend/app/agents/career_recommendation_agent.py:122-197`; `backend/app/workflows/career_workflow.py:222-245` | UNVERIFIED | Whether the runtime catalog has exactly the frozen 10 careers is unknown; current code relies on database contents. | Verify actual IDs/count at T4 and enforce canonical scope in runtime configuration. |
| Single career-fit source and exactly four gap categories | Recommendation and skill-gap services use `compute_career_fit()`; skill-gap maps its three required-skill states and separately stores unmatched user claims. | `backend/app/services/career_fit_service.py:141-205`; `backend/app/services/skill_gap_service.py:55-148`; `backend/app/agents/career_recommendation_agent.py:139-197` | IMPLEMENTED | Formula is inspectable and callers are centralized. A repository audit cannot establish that the formula matches every earlier approved historical version. | Preserve the shared function; compare against an explicit frozen formula/baseline if historical non-change must be proven. |
| Only accepted evidence earns `matched_evidenced` | Career fit treats any `evidence_status == "linked"` as full contribution; repository sets `linked` after any evidence row. Profile smoke fixture marks self-report as linked. | `backend/app/services/career_fit_service.py:168-205`; `backend/app/repositories/user_repository.py:265-269`; `backend/tests/test_profile_agent_smoke.py:44-46, 100-112` | CONFLICTING | The approved evidence boundary is violated and can alter career ranking and gap categories. | Resolve before relying on recommendation/gap outputs or evaluation. |
| Claims without accepted evidence and unmatched claims retain meanings | Evidence-free normalized claims map to `matched_claimed_only`; unmatched skill IDs are separately returned as `unmatched_user_claims`, not required-skill `missing`. | `backend/app/services/skill_gap_service.py:55-63, 109-148`; `backend/app/schemas/skill_gap.py` | IMPLEMENTED | Correct classification is conditional on fixing false `linked` evidence described above. | Keep these categories unchanged while repairing the upstream evidence acceptance gate. |
| Roadmap consumes existing gap, preserves grounding, and has safe fallback | Roadmap accepts the gap result, selects missing/claimed-only IDs, verifies canonical context/metadata, embeds the same gap, validates LLM summary, and falls back on invalid output or LLM failure. | `backend/app/agents/learning_roadmap_agent.py:56-110, 126-220`; `backend/app/agents/verification_agent.py:373-420` | IMPLEMENTED | It is a grounded learning-focus list, not a resource-backed course sequence; source evidence still inherits the upstream evidence-status issue. | Preserve the scope; do not add unsupported resources, prerequisites, proficiency, or timeline claims. |
| B0/B2/B3/F are independently executable; B2 receives complete all-10 relations | Configuration objects describe component flags. B2 contains only a generic description/`uses_occupational_kb` flag; manifest validation checks only `config_id`. Tests assert flags, not runnable isolation or payload completeness. | `backend/app/evaluation/configurations.py:1-112`; `backend/tests/test_evaluation_framework.py:333-350` | PARTIAL | No runtime switch/runner or structured B2 payload contract supplies all ten complete relationship sets. | Implement configuration-specific execution and payload validation at T10/T11 after data readiness. |
| Evaluation uses validated labels and reproducible execution | Metric/evaluator/schema/adapter code exists. Documentation states the reference corpus and annotations are absent and the runner/manifests/artifact persistence are not implemented. | `backend/app/evaluation/evaluator.py:1-36, 471`; `docs/evaluation/METRICS_IMPLEMENTATION.md:1-18, 77-89`; `docs/evaluation/DATASET_AND_ANNOTATION.md:1-8` | PARTIAL | Metrics can be computed for supplied cases, but no empirical system performance or formal comparison is established. | Complete T9 dataset/ground truth and T10–T11 runner/configuration gates before formal experiments. |

## 4. Data Model and Database Findings

### Confirmed implementation facts

- `UserSkillOut` models a claimed skill, optional canonical `skill_id`, proficiency, `evidence_status`, and a list of generic evidence rows. It is not a distinct CompetencyClaim with source reference and match status. `UserSkillEvidenceOut` has optional `source_table`/`source_id`, description, and URL (`backend/app/schemas/user.py:56-82, 103-119`).
- Experience and Project records are separately stored and have `experience_id`/`project_id` output fields (`backend/app/schemas/user.py:29-49`). The profile extraction prompt persists their whitelisted fields but does not connect them to candidate skills (`backend/app/agents/profile_agent.py:100-112`).
- The profile extraction path calls `add_skill_evidence()` without setting `source_table` or `source_id` (`backend/app/agents/profile_agent.py:141-153`).
- Evidence matching for idempotent insert/fetch excludes `source_table` and `source_id`, and does not use the approved stable Activity ID + canonical Skill ID key (`backend/app/repositories/user_repository.py:245-262`).
- No user TechnologyClaim, distinct CompetencyClaim, ActivitySkillCandidate, technology alias normalizer, or candidate/evidence verification lifecycle was found in the inspected application. SQL and migration file-pattern searches returned no checked-in files.

### Documentation-only claims

- T1 defines conceptual claim, activity, candidate, evidence, and lifecycle contracts; these documents are the design baseline, not proof that database tables exist.
- The checklist assigns physical contract details to T3 and workbook/database parity/integrity to T4.

### Unverified

No live database connection or schema introspection was performed. Therefore physical tables, foreign keys, unique constraints, indexes, lifecycle columns, actual record counts, catalog contents, and workbook/database parity are **UNVERIFIED**. Repository SQL demonstrates expected table/column names only; it does not prove the live schema satisfies those expectations.

## 5. Pipeline and Agent Findings

### Profile and CV extraction

The CV API reads a bounded upload, extracts text, redacts it, drops the raw extraction reference, then sends redacted text into `CareerWorkflow`; the extractor is described as in-memory and non-persisting. The extractor produces a single `extracted_text` string with document metadata, not section IDs or source spans (`backend/app/api/routes/analysis.py:70-110`; `backend/app/services/cv_text_extraction_service.py:1-5, 35-45, 159-219`). The Profile Agent then extracts skills, generic evidence, education, experience, projects, and certifications. It does not expose separate technology claims or ActivitySkillCandidates (`backend/app/agents/profile_agent.py:33-58, 86-154`).

### Activity-to-skill path

The approved path `Activity → Activity–Skill Candidate → Verification → Competency Evidence` is absent as an end-to-end implementation. The current profile agent stores experience/project rows and generic evidence independently. It does not generate candidates, constrain each candidate to a canonical OKB skill, run four candidate checks, or gate evidence on PASS. Tool-name-only evidence sufficiency is not checked.

### Verification and orchestration

The existing Verification Agent independently recomputes/checks recommendation ranking/scores, skill-gap result, roadmap identity/coverage, source provenance, and generated text. Tests include non-mutation checks. It does not inspect Activity–Skill candidates because those are not present. Its semantic review constructs context for every retrieved career and serializes that context with the outputs into one prompt (`backend/app/agents/verification_agent.py:426-514`); no explicit input-size bound is visible, so context size is a runtime risk, not a measured failure.

Workflow order is profile → recommendation → skill gap → roadmap → verifier. The revision cap, routing, and downstream re-verification are implemented for the current agent outputs. However, the workflow class documents that agents lack feedback-taking revision methods; findings select a target but are not passed as an explicit revision instruction. The stage rerun updates the same state fields, so the final workflow state does not preserve a first-pass output snapshot (`backend/app/workflows/career_workflow.py:116-141, 311-399, 419-453`).

## 6. Career-Fit and Skill-Gap Findings

`compute_career_fit()` is the only inspected career-fit implementation. It weights CORE versus supporting requirements, applies configured KB confidence and claim-only multipliers, optionally applies the existing self-reported-proficiency modifier, normalizes by total weight, and clamps to `[0,1]` (`backend/app/services/career_fit_service.py:141-205`). Recommendation calls it for each returned career; skill-gap calls it and translates the returned statuses rather than recalculating the score (`backend/app/agents/career_recommendation_agent.py:139-197`; `backend/app/services/skill_gap_service.py:71-105`).

The skill-gap result has the required four categories: `matched_evidenced`, `matched_claimed_only`, `missing`, and `unmatched_user_claims`. The first three classify career-required skills; the fourth is assembled separately from user claims with no canonical skill ID. No fifth category or priority tier is added (`backend/app/services/skill_gap_service.py:29-63, 109-148`).

The most serious defect is upstream of the formula: a generic evidence row sets `evidence_status='linked'`, and linked status earns full matched-evidenced contribution. A self-report evidence row is accepted by the current profile path and asserted by its smoke fixture (`backend/app/repositories/user_repository.py:265-269`; `backend/app/services/career_fit_service.py:168-205`; `backend/tests/test_profile_agent_smoke.py:44-46, 100-112`). Thus, the category logic is implemented but the intended meaning of `matched_evidenced` is not preserved. No technology-claim channel currently exists to prove technology claims are excluded from skill scoring.

The independent calculator test checks representative formula outputs and the zero-requirement case (`backend/tests/test_career_fit_independent_verification.py:71-128`). The audited service file was not modified in the worktree at the inspected revision, but repository inspection alone does not establish the approved historical formula baseline; no frozen formula fingerprint was found.

## 7. Roadmap Findings

Roadmap generation consumes `SkillGapResult`/`SkillGapAnalysisOut`, checks that the selected career matches retrieved context, and emits items only for `missing` and `matched_claimed_only` skills in OKB relationship order. It retains skill IDs, category, confidence, and knowledge-base evidence text; it embeds the source gap (`backend/app/agents/learning_roadmap_agent.py:56-110, 180-220`).

The prompt prohibits courses/resources, certifications, prerequisites, technologies, proficiency levels, timelines, ranking, or unsupported facts. The summary validator rejects extra structure, unsupported concepts, non-context names/words, and invalid output; failures use a deterministic fallback and preserve the structured items. The verifier checks canonical identity, metadata, exact gap coverage, duplicates, and unchanged embedded gap (`backend/app/agents/learning_roadmap_agent.py:15-25, 126-178`; `backend/app/agents/verification_agent.py:373-420`).

This is a grounded learning-focus list, not a complete personalized curriculum with verified resources or sequencing. No such sources/contracts are approved. The roadmap also inherits the upstream distinction failure if a non-activity evidence row has been incorrectly marked linked.

## 8. Experiment Configuration Findings

| Arm | Declared behavior | Actual inspected capability |
|---|---|---|
| **B0** | LLM-only, no OKB relationships, deterministic scoring/gap, or verifier. | Metadata flags describe this arm; no executable runtime switch or isolation path was found. |
| **B2** | LLM receives all 10 careers and each complete Career–Skill relationship set; LLM ranks/classifies; no deterministic calculator or verifier. | Metadata says generic occupational relationship data and enables the OKB flag. No payload builder, all-10 completeness validation, or executable B2 path was found. |
| **B3** | OKB and deterministic scoring/gap/roadmap, no verifier or revision. | Metadata flags describe the arm; no executable ablation switch was found. |
| **F** | B3 plus verifier and bounded revision. | Metadata flags describe the arm; the production workflow has a bounded general revision loop, but no evaluation runner isolates and records F runs. |

Evidence: `backend/app/evaluation/configurations.py:1-112`; `backend/tests/test_evaluation_framework.py:333-350`. `validate_configuration_manifest()` validates the configuration ID only; it ignores other manifest fields (`configurations.py:101-112`). Consequently, current tests establish the descriptive flags, not independent execution, shared-input parity, B2’s all-10 complete payload, or absence of unintended shared behavior. The approved B2 scope is settled in T1 documentation; this is an implementation gap, not an unresolved design question.

## 9. Test Coverage and Evaluation Readiness

### Existing tests (static inspection only)

- The independent career-fit tests include hand-calculated comparisons and the empty-requirement case (`backend/tests/test_career_fit_independent_verification.py:71-128`).
- Verification tests cover deterministic score/gap/roadmap failures, unsupported semantic claims, provenance, LLM failure, and input non-mutation (`backend/tests/test_verification_agent_unit.py:223-420`).
- Workflow tests cover graph order, responsible-stage routing, re-verification, revision limits, and non-passing outcomes (`backend/tests/test_career_workflow_unit.py:120-293`).
- Evaluation framework tests assert descriptive arm flags and configuration-ID validation, not arm execution or B2 payload completeness (`backend/tests/test_evaluation_framework.py:333-350`).
- `test_skill_normalizer_unit.py` and `test_learning_roadmap_agent_unit.py` define `main()`-driven assertion scripts rather than pytest `test_*` functions (`backend/tests/test_skill_normalizer_unit.py:18-55`; `backend/tests/test_learning_roadmap_agent_unit.py:100-180`). The profile smoke script also uses a `main()` entry point and contains assertions that self-report evidence becomes linked (`backend/tests/test_profile_agent_smoke.py:44-46, 100-112`).

### Missing coverage and readiness

No tests were found for technology-claim extraction/alias normalization/collision handling; Activity source references and candidate generation; the four candidate checks and PASS-only evidence gate; stable Activity–Skill de-duplication; technology/tool-name isolation; source-span preservation; exact 10-career runtime enforcement; or executable, isolated B0/B2/B3/F arms with B2 payload completeness.

The evaluation package contains schemas, adapters, metrics, and report aggregation. Documentation states that the validated reference corpus/annotations and Step 18 experiment runner/configuration switching/manifest persistence are absent (`docs/evaluation/METRICS_IMPLEMENTATION.md:1-18, 77-89`; `docs/evaluation/DATASET_AND_ANNOTATION.md:1-8`). No real-CV or expert-labeled evaluation result was established. The metric layer is not evidence that the system has been evaluated.

**Execution status:** No tests were executed in this read-only audit, as required by the T2 instruction. No test-pass claim is made.

## 10. Critical Blockers for T3

T3 is the documented **Data Model & Pipeline Alignment** stage. The following items should be resolved in that stage before implementation work that depends on them:

1. Translate the approved claim/activity/candidate/evidence lifecycle into final storage/API contracts, including stable identity, source spans/references, immutability, deduplication, lifecycle/status fields, and the behavior of repeated extraction.
2. Resolve the conflicting evidence semantics: generic evidence rows currently make self-report and other non-activity rows count as `linked`/`matched_evidenced`, contrary to the approved PASS-only activity evidence boundary.
3. Specify how existing Experience/Project records become source Activities and how a candidate retains an auditable source pointer without losing the sanitized source excerpt/section context.
4. Define technology claim extraction, catalog/alias storage and provenance, collision checks, and strict separation from competency claim/evidence.
5. Specify candidate-level four-check findings and owner revision data, including preservation of originals and findings, bounded revision, and re-verification.
6. Define runtime enforcement of the fixed 10 canonical career IDs and the structured B2 all-10 complete relationship payload.

Live DB schema and actual OKB/workbook parity are **not a T3 code fact**; they remain **UNVERIFIED** and are explicit T4 deliverables. Formal experiments must also wait for dataset/ground-truth and experiment-infrastructure gates.

## 11. Items That Can Be Handled Manually by the Researcher

- Update the stage-status/checklist documents after accepting this audit; they were intentionally not edited as part of the single-report deliverable.
- Clarify in evaluation/annotation documentation that annotator evidence labels (including education/certification examples) are reference labels, not authorization for the runtime system to accept those records as `matched_evidenced`.
- Confirm official thesis research-question wording against the approved proposal before making formal evaluation claims; repository evaluation documentation identifies this as outstanding.
- Prepare and approve the human protocol for redacted data collection, blind/dual annotation, adjudication, agreement reporting, and fixed evaluation split. This audit did not collect, inspect, or process CVs.
- Arrange the authorized read-only T4 schema/catalog/workbook-parity verification and provide its report. No database credentials or access were used here.

These are documentation, research-governance, or external-data verification tasks. They do not require changing the application code.

## 12. Recommended Order of Work for T3 Onward

1. **T3 — Align contracts:** finalize API/storage/source-span details for separate claims, Activities, ActivitySkillCandidates, and CompetencyEvidence; settle stable IDs, deduplication, immutable originals, revision findings, technology aliases, and the PASS-only evidence boundary.
2. **T4 — Verify occupational data:** perform approved read-only schema and data-integrity checks; establish the actual 10-career catalog, Career–Skill completeness, workbook/database parity, provenance, and a reproducible snapshot/hash report. Do not infer this from repository schemas.
3. **T5 — Implement core profile pipelines:** separate technology and competency extraction; normalize each by its approved rules; preserve sanitized source references; construct Activities and canonical-skill candidates without accepting evidence yet.
4. **T6 — Implement verification/evidence integration:** apply the four candidate checks and approved aggregation; preserve originals/findings; implement explicit, bounded, owner-only revision/re-verification; create evidence only from PASS; ensure career fit and gaps consume the accepted status without changing their formula/categories.
5. **T7 — Functional and integration tests:** add focused tests for the T3–T6 contracts and run the project's appropriate suites; record outcomes and defects.
6. **T8 — Application/interface validation:** validate the CV-to-profile path and exposed schemas only after the backend contracts and tests are stable.
7. **T9 — Dataset and ground truth:** complete redaction, annotations, adjudication, agreement, split, and immutable manifests; do not use model outputs as independent ground truth.
8. **T10–T11 — Reproducibility and configurations:** build the runner and manifests, enforce B0/B2/B3/F isolation, validate B2's structured all-10 relationship payload, then produce a configuration-validation and execution plan.
9. **Formal experiments:** begin only after all documented quality gates pass; no experiment result is reported by this audit.

**Audit limitations:** static repository inspection only; no tests or runtime paths were executed; no database or workbook parity was checked; no CVs or other candidate data were read; no LLM or browser was invoked. These are explicit limits, not negative findings about the live environment.
