# Gate A Decisions and Completion Report

Status: Step 17 decisions. The metric/input layer is implemented and unit-tested;
annotation and experiment execution remain future work.

## 1. Gate A decision table

| ID | Decision | Status | Recommendation | Rationale | Approval required? |
|---|---|---|---|---|---|
| OP-01 | Official research questions and proposal alignment | OPEN | Keep the supplied research problem/objective as the authoritative frame, and label any RQ wording as derived evaluation questions until the thesis proposal is inspected | The official proposal was not available in the repository, and the instruction explicitly says the supplied problem/objective are authoritative for the evaluation design | Yes, if the proposal defines formal RQs that differ from the supplied wording |
| OP-02 | Primary and secondary comparisons | AGREED | Keep C1 = F vs B0, C2 = F vs B3, C3 = B2 vs B3 as the primary comparisons, with B2/B0/B3 comparisons secondary only where the design is clearly framed | This aligns with the specified experimental configurations and repository implementation | No |
| OP-03 | B0 career label space and permitted information | AGREED | B0 may use the 10 canonical careers but must not receive OKB occupation-skill relationships, deterministic scoring logic, or the system's internal KB knowledge | This reflects the repository architecture and the required baseline design | No |
| OP-04 | B2 prompt and occupational information level | APPROVED — RESEARCHER DECISION | Supply all 10 canonical careers and each career's complete Career–Skill relationship set from the OKB; the LLM performs matching/scoring without the deterministic formula or weights | Fixes B2's information scope while isolating LLM matching/scoring from deterministic computation | No; approved for the fixed B2 arm |
| OP-05 | How Verification Agent execution is disabled | RECOMMENDED | Disable verification by construction: run the same B3 path but omit the verification node and revision loop rather than mutating unrelated validation logic | This avoids turning B3 into a non-equivalent pipeline and preserves the architecture's intended separation | No |
| OP-06 | Whether B3 is an independent execution or a derived first-pass result | AGREED | Treat B3 as an independent execution path in the same deterministic pipeline; F's first pass may be used for structural-equivalence auditing, but B3 is not merely a discarded first pass | This preserves the clean comparison for F vs B3 while acknowledging the shared deterministic logic | No |
| OP-07 | Model and inference-parameter pinning | RECOMMENDED | Pin model/provider and record all explicit parameters in the run manifest; when not supported, record SDK defaults explicitly and treat them as part of the evaluation design | The repository currently does not expose seeded inference configuration in `llm_client.py` | Yes, if the team wants a stricter pinned-seed configuration before running pilots |
| OP-09 | Experimental database and isolation strategy | AGREED | Use a dedicated experiment database or namespace; never mix experimental data with the system's development database | This is consistent with the repository's Step 16 guarded validation approach | No |
| OP-10 | Treatment of per-career reasoning calls | RECOMMENDED | Count reasoning calls as part of the cost profile and not as independent scientific samples; a per-career call remains a design-level runtime quantity rather than a repeated experimental unit | The repository emits a reasoning string per career in the recommendation agent and therefore the cost is part of the evaluation scenario | No |
| OP-18 | Ownership and persistence of experiment logging | BLOCKED | Step 18 must implement the experiment manifest and artifact persistence; the repository does not currently contain the required tables or logging ownership described in the master spec | There is no storage layer implementing the analysis_id/logging contract in the current codebase | Yes, this is a Step 18 requirement |

## 2. Status definitions

- AGREED: explicitly established in the supplied research context or repository implementation.
- APPROVED — RESEARCHER DECISION: explicitly approved by the researcher and controlling over earlier recommendations.
- RECOMMENDED: a technical or methodological recommendation that is sound but not required to block Step 17 documentation.
- OPEN: essential information or formal approval is still missing.
- BLOCKED: cannot be completed without missing implementation, absent artifact, or a design decision that is not yet present.
- SUPERSEDED: retained for history but replaced by a later approved decision.

## 3. Architecture discrepancies and required Step 18 changes

The following discrepancies were observed while aligning the evaluation design to the actual repository:

1. There is no explicit configuration switch for enabling/disabling the OKB or the Verification Agent in the runtime code. The design therefore requires a Step 18 config layer rather than assuming a runtime toggle exists.
2. The repository does not implement the analysis-record logging tables described in the older master spec. Step 18 must add the run-manifest persistence logic if the experiment is to satisfy the full logging requirement.
3. The LLM client does not expose seed/temperature controls. This must be recorded and, if required, added in Step 18 before formal runs.
4. The Step 17 design explicitly distinguishes between the research problem/objective and derived evaluation questions; the actual proposal remains unavailable, so the official RQ wording is still OPEN.
5. Step 16 writes privacy-safe `analysis_log/1.0` files, not database tables. Those records omit the configuration, latency, token usage, and API-call count, so `backend/app/evaluation/adapters.py` requires an explicit `config_id` and leaves unavailable runtime metrics unset. Step 18 must supply them in the run manifest rather than inferring them.

## 4. Completion checklist

| Item | Status | Evidence |
|---|---|---|
| Research problem and objective mapped to evaluation logic | PASS | The Step 17 docs use the supplied problem/objective as the frame and map them to derived evaluation questions |
| B0/B2/B3/F definitions aligned with repo implementation | PASS | The architecture and agents in `career_recommendation_agent.py`, `skill_gap_service.py`, and `verification_agent.py` are consistent with those definitions; `backend/app/evaluation/configurations.py` encodes them |
| Comparison validity documented | PASS | The protocol identifies control variables, invalid claims, and confounders for C1-C3 |
| Gate A decisions table created | PASS | This document records each decision with status, rationale, and approval requirement |
| Documentation files created under `docs/evaluation/` | PASS | `EVALUATION_PROTOCOL.md`, `DATASET_AND_ANNOTATION.md`, `EXPERIMENT_SPEC.md`, `REPRODUCIBILITY_SPEC.md`, `METRICS_IMPLEMENTATION.md`, and `DECISIONS.md` exist |
| Executable metric layer implemented | PASS | `backend/app/evaluation/{schemas,metrics,evaluator,adapters,configurations}.py` implement the documented formulas, input contracts, and machine-readable report |
| Metric layer tested | PASS | `tests/test_evaluation_metrics.py` and `tests/test_evaluation_framework.py` cover formulas, empty denominators, malformed/missing labels, failed outputs, adapters, and configuration validation |
| Reference labels or annotation corpus available | BLOCKED | No validated corpus exists in the repository; label-dependent metrics are `unavailable`, not fabricated |
| Formal experiments executed | NOT RUN (by design) | Step 17 implements measurement only; execution belongs to Step 20 |
| Step 18 implementation started | NOT STARTED | Step 18 runner/configuration switching/manifests are explicitly out of scope for this task |
| Formal RQ wording from the thesis proposal available | BLOCKED | The proposal text was not present in the repository |

## 5. Completion report

Step 17 now provides both the evaluation design and its executable measurement
layer. The layer is grounded in the current repository architecture, respects
the research problem and objective, preserves the four skill-gap categories and
the four configurations, and leaves every label-dependent metric `unavailable`
until real annotations exist. No experiment was run and no effectiveness claim
is made. Experiment execution, configuration switching, and manifest
persistence remain Step 18.

## 6. Decision change record

| Date | Decision | Prior wording retained as history | Approved resolution |
|---|---|---|---|
| 2026-11-02 | OP-04 — B2 prompt and occupational information level | “Give B2 the same relevant KB relationship data and canonical skill catalog needed for the task, but do not include the deterministic formula or weights unless a separate exploratory variant is explicitly labelled.” This prior recommendation's word “relevant” left the relationship scope underspecified. | The researcher approved supplying the complete Career–Skill relationship sets for all 10 canonical careers. This supersedes the earlier wording for experiment configuration; B2 still omits deterministic formula/weights and assigns matching/scoring to the LLM. |
