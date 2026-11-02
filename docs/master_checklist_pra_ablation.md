# PRE-ABLATION ROADMAP
## Implementation and Evaluation Preparation Roadmap

**Objective:** Establish the required sequence of activities and prerequisites that must be completed before conducting the formal ablation study using configurations B0, B2, B3, and F.

### Execution Principles

1. All stages must be completed in the defined sequence.
2. Each stage must have clearly defined deliverables and exit criteria.
3. Implementation changes must be preceded by an audit.
4. Code changes must be accompanied by appropriate tests.
5. Database changes require a backup plan and explicit approval.
6. Formal experiments must not begin until all prerequisites have been satisfied.
7. The four skill-gap categories, career-fit formula, and experiment configurations must not be modified without explicit approval.

### Preparation Stages

| ID | Stage | Key Deliverables |
|---|---|---|
| T1 | Design & Decision Freeze | Design Decision Document, system architecture, and data contracts |
| T2 | Implementation Audit | Implementation Gap Matrix |
| T3 | Data Model & Pipeline Alignment | Finalized data contracts and pipeline specification |
| T4 | Occupational Knowledge Base Readiness | Import report, validation report, and data integrity report |
| T5 | Core Pipeline Implementation | Profile, technology, competency, activity, and candidate-processing pipelines |
| T6 | Verification & Skill Gap Integration | Verification integration and skill-gap consistency report |
| T7 | Functional & Integration Testing | Test report and defect register |
| T8 | Application & Interface Validation | End-to-end and UI validation report |
| T9 | Experiment Dataset & Ground Truth Preparation | Experiment dataset, annotation guidelines, ground truth, and expert validation results |
| T10 | Reproducibility & Experiment Infrastructure | Experiment manifest and reproducibility protocol |
| T11 | Experiment Configuration Validation | Configuration validation report and experiment execution plan |

### Current Stage Status

| Stage | Status | Exit assessment / next action |
|---|---|---|
| T1 — Design & Decision Freeze | **COMPLETE** | All core design decisions and six researcher approvals are recorded in `docs/design-freeze.md`; B2 scope wording is reconciled in both evaluation documents and prior wording is retained as superseded history. T1 closure freezes design only; it does not establish implementation readiness. |
| T2 — Implementation Audit | **COMPLETE** | Read-only implementation audit and gap matrix are recorded in `docs/audits/T2_IMPLEMENTATION_AUDIT.md`. Runtime database schema, contents, and workbook parity remain unverified and are T4 deliverables. |
| T3 — Data Model & Pipeline Alignment | **COMPLETE — CONTRACT APPROVED** | Field-level data contracts, lifecycle, source/redaction and deduplication rules, verification/revision protocol, legacy alignment, pipeline, implementation dependencies, and exit criteria are recorded in `docs/design/T3_DATA_MODEL_AND_PIPELINE_CONTRACT.md`. Researcher decisions are recorded there, including opaque ingestion-ID identity and fail-closed handling when source lineage is unavailable. T3 completion authorizes no implementation; T4 must verify the live database and OKB before dependent implementation. |
| T4 — Occupational Knowledge Base Readiness | **PARTIAL — AUDIT COMPLETE; DATA-READY GATE NOT PASSED** | Read-only audit recorded in `docs/audits/T4_OKB_READINESS_AUDIT.md`. The live configured database `career_intelligence` (PostgreSQL 16.4, read-only transaction) was identified by query and compared with the legacy workbook: 10 careers, 87 skills, and 155 Career–Skill relationships; no duplicates, orphan references, or uncovered careers/skills; 12 workbook-derived tables match exactly and 3 match after the importer's documented unit-ID padding and numeric-format transforms. The larger untracked extended workbook is not imported and reports 0 VALIDATED records. Failing exit criteria: no global technology catalog or alias mechanism (T5 blocker), no snapshot ID/SHA-256 manifest/source-file hash/import metadata (T6/reproducibility blocker), and no checked-in DDL/migration/seed artifacts (schema not reproducible from VCS). Partial/unverified: SKKNI `SK06`, `SK08`, `SK09` have zero units; no element/KUK records; 24/87 skills rely on career-level evidence text; 2 occupation mappings and 3 skill-evidence rows have NULL IndoTask provenance. Next action: resolve the T4 blockers in `docs/audits/T4_OKB_READINESS_AUDIT.md` §12 before beginning T5; do not treat G2 Data Ready as passed. |

**Confirmed constraints recorded for T1:** retain the existing career-fit
source of truth and exactly four skill-gap categories; technology mentions do
not confer competency evidence or affect fit/gap; only PASS activity-derived
candidates may create competency evidence; B2 receives all 10 careers and
their complete Career–Skill relationship sets; preserve B0/B2/B3/F and the
three named comparisons.

**Later-stage boundaries:** concrete storage/API and source-span details are
for T3. Actual workbook/database parity and integrity verification remain T4
deliverables. Formal thesis RQ wording, dataset/ground-truth preparation, and
reproducibility artifacts remain evaluation-stage prerequisites; they are not
unresolved T1 system-contract decisions.

**B2 documentation note:** the all-10 relationship scope is confirmed. The
older “relevant” wording in `docs/evaluation/DECISIONS.md` OP-04 and
`docs/evaluation/EXPERIMENT_SPEC.md` §2 is superseded for experiment setup and
is reconciled in those documents; the prior OP-04 wording remains in its
decision change record. It does not leave B2's scope undecided.

### Quality Gates

- **G1 — Design Ready:** T1–T3 completed.
- **G2 — Data Ready:** T4 completed.
- **G3 — System Ready:** T5–T8 completed.
- **G4 — Evaluation Ready:** T9–T10 completed.
- **G5 — Experiment Ready:** T11 completed.

### Formal Ablation Study

The formal ablation study may begin only after all five quality gates (G1–G5) have been passed.

**Experiment Configurations**

- **B0:** LLM-only.
- **B2:** OKB + LLM-driven matching and scoring.
- **B3:** OKB + deterministic matching and scoring.
- **F:** B3 + Verification Agent and revision loop.

**Planned Comparisons**

- F vs. B0.
- F vs. B3.
- B2 vs. B3.

**Execution Rules**

A stage that has not met its exit criteria must not be skipped. Any change to an approved design decision must be documented, and its impact on previously completed stages must be assessed.
