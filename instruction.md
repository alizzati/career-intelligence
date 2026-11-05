# READ-ONLY AUDIT: B0/B2/B3/F EXPERIMENT CONFIGURATIONS AND EVALUATION ADAPTER CONTRACTS

## Context

We are preparing the formal evaluation design for an undergraduate thesis:

**Hybrid Verification Multi-Agent System for CV-Based Hard-Skill Analysis, Career Recommendation, Skill-Gap Analysis, and Learning Roadmap for Fresh IT Graduates.**

A previous repository audit established the following:

1. The evaluation framework has been implemented.
2. `backend/app/evaluation/metrics.py`, `evaluator.py`, `adapters.py`, `configurations.py`, and `schemas.py` exist.
3. B0, B2, B3, and F are currently documented as experiment configurations.
4. No formal baseline comparison or ablation experiment has been executed.
5. The repository does not yet contain a confirmed, independently annotated CV evaluation dataset.
6. The intended experiment design is:
   - B0: LLM-only baseline.
   - B2: Semantic matching baseline.
   - B3: Full system without Verification Agent.
   - F: Full Hybrid Verification Multi-Agent System.
7. Baseline comparisons: F vs B0 and F vs B2.
8. Ablation comparison: F vs B3.
9. The four existing skill-gap categories, OKB taxonomy, ten career IDs, existing career requirements, scoring weights, and agent responsibilities are frozen unless explicitly approved.

## Objective

Conduct a focused, evidence-based, READ-ONLY audit to determine whether the repository's current implementation can support the proposed experiments.

Do not implement or modify anything.

The audit must establish the actual execution behavior and data contracts, not merely infer behavior from configuration names or documentation.

---

# 1. Repository and Implementation Discovery

Inspect the relevant implementation and trace the actual runtime call paths.

At minimum, inspect:

- `backend/app/evaluation/configurations.py`
- `backend/app/evaluation/schemas.py`
- `backend/app/evaluation/metrics.py`
- `backend/app/evaluation/evaluator.py`
- `backend/app/evaluation/adapters.py`
- `backend/app/evaluation/`
- The production workflow and LangGraph orchestration.
- Profile Agent and skill extraction/normalization.
- Career Recommendation Agent and career-fit calculation.
- Skill-Gap Engine and Skill-Gap Agent.
- Learning Roadmap Agent.
- Verification Agent and revision mechanism.
- Relevant API routes and service functions.
- Relevant evaluation tests and fixtures.
- Relevant evaluation documentation.

Search the repository for all references to:

- `B0`, `B2`, `B3`, `F`
- `experiment_config`
- `evaluation_config`
- `adapter`
- `evaluate`
- `verification`
- `semantic_matching`
- `ablation`
- `baseline`

Trace each configuration from its declaration to its actual execution entry point.

Do not assume a configuration is executable merely because it exists in a dictionary, schema, documentation file, or test fixture.

# 2. Audit Each Experiment Configuration

For each configuration B0, B2, B3, and F, produce a detailed implementation audit.

Use this table:

| Audit dimension | Required finding |
|---|---|
| Configuration definition | Exact file, symbol, and relevant lines |
| Runtime entry point | Actual function/class that executes it, if any |
| Execution path | Actual sequence of components called |
| LLM usage | Whether an LLM is called and where |
| OKB usage | Whether OKB retrieval/grounding is used |
| Skill normalization | Exact normalization behavior |
| Career matching | Exact matching/scoring mechanism |
| Skill-gap calculation | Whether the same deterministic engine is used |
| Roadmap generation | Whether it is executed and how |
| Verification | Whether Verification Agent runs |
| Revision | Whether verification-triggered revision is enabled |
| Output contract | Actual output schema and fields |
| Evaluation compatibility | Whether current adapters can process the output |
| Execution status | Runnable, partially runnable, metadata-only, or not implemented |

For every finding, cite the exact source file and line range.

## 2.1 B0 — LLM-only baseline

Determine precisely what B0 means in the current repository.

Questions:

- Does B0 have an executable runtime path?
- Does it use LLM for skill extraction, career recommendation, skill-gap analysis, or all of them?
- Does it bypass OKB retrieval?
- Does it bypass deterministic career scoring?
- Does it bypass skill normalization?
- Does it generate roadmap output?
- Does it use any hidden deterministic logic that would make it not genuinely LLM-only?
- Can its output be converted into the same evaluation schema as F?

Do not invent a definition if the implementation does not establish one.

If B0 is only descriptive metadata, state that clearly.

## 2.2 B2 — Semantic matching baseline

Determine precisely what B2 means in the current repository.

Questions:

- Is there an actual semantic matching implementation?
- Which embedding model or semantic similarity mechanism is used?
- What text fields are compared?
- Does it compare CV claims against canonical skill names, descriptions, or both?
- Is there a threshold?
- How are matched skills converted into career-fit scores?
- Does it use OKB data?
- Does it use the same skill-gap engine as F?
- Is it executable independently?
- Does it have an output contract compatible with the evaluation adapters?

Do not confuse ordinary LLM-assisted normalization, fuzzy string matching, or retrieval with a dedicated semantic matching baseline.

If B2 is only metadata, identify what is missing.

## 2.3 B3 — Full system without Verification Agent

Determine whether B3 can execute the full system while excluding only the Verification Agent and its revision mechanism.

Questions:

- Is there a runtime switch to disable Verification Agent?
- Can the workflow execute all other components unchanged?
- Does disabling verification also disable revision?
- Are any verification checks still performed inside other agents or services?
- Are prompts, scoring, OKB access, and other settings identical to F?
- Is there a way to prove that B3 differs from F only by the verification mechanism?

If this cannot be guaranteed, explain why the current implementation does not yet constitute a controlled ablation.

## 2.4 F — Full system

Determine the exact production workflow used by F.

Document:

- Actual graph nodes.
- Actual graph edges and conditional transitions.
- Agent execution order.
- Deterministic service calls.
- LLM calls.
- OKB retrieval points.
- Verification checks.
- Revision loops and maximum revision count.
- Final output structure.

Distinguish the actual implementation from architectural descriptions in documentation.

---

# 3. Audit Evaluation Adapter Contracts

This is a critical part of the audit.

Inspect every adapter in `backend/app/evaluation/adapters.py` and trace its input and output schemas.

For each adapter, provide:

| Adapter | Accepted input | Required fields | Output schema | Metrics consuming output | Failure behavior |
|---|---|---|---|---|---|

Determine whether adapters accept:

1. Production F output directly.
2. B3 output without verification metadata.
3. B0 output with potentially different structures.
4. B2 output with semantic matching results.

Identify any assumptions that make an adapter dependent on F-specific fields.

Specifically investigate:

- Missing fields.
- Optional versus required fields.
- Default values that could conceal missing information.
- Status/category mapping.
- Evidence and provenance mapping.
- Career ranking mapping.
- Skill-gap category mapping.
- Roadmap item mapping.
- Verification finding mapping.
- Error and incomplete-run handling.

Do not silently map missing values to positive or negative labels.

Determine whether an unavailable field is:
- legitimately not applicable,
- missing due to an implementation defect,
- or unsupported by the configuration.

These cases must remain distinguishable.

# 4. Audit Metric Compatibility and Fairness

Inspect `metrics.py`, `evaluator.py`, schemas, adapters, and tests.

For every metric, document:

- Exact formula or implementation behavior.
- Required reference labels.
- Required system output fields.
- Whether the metric can be calculated for B0, B2, B3, and F.
- Whether the metric is meaningful for all configurations.
- Whether any metric currently relies on system-generated labels rather than independent ground truth.

At minimum, audit:

### Skill extraction and normalization
- Precision
- Recall
- F1

### Career recommendation
- Hit@1
- Hit@3
- nDCG@3
- MRR
- Repeated-run stability, if implemented

### Skill-gap
- Accuracy
- Per-class Precision/Recall/F1
- Macro-F1
- Over-credit rate
- Missing-skill and unmatched-claim metrics

Preserve the existing four skill-gap categories:
- `matched_evidenced`
- `matched_claimed_only`
- `missing`
- `unmatched_user_claims`

Do not change their definitions.

### Learning roadmap
- Coverage
- Unsupported-item rate
- Grounding
- Status consistency
- Action consistency

### Verification
- Fault detection precision
- Fault detection recall
- False-positive rate
- Revision/outcome/resolution metrics

### Traceability
- Evidence lineage rate
- Gap-item lineage rate

For each metric, explicitly state whether it can be calculated for a configuration that does not implement verification.

Do not treat "not applicable" as zero.

Identify any metric whose current implementation measures internal consistency rather than independent correctness.

# 5. Audit Experimental Fairness and Confounding

Assess whether the proposed comparisons are methodologically valid.

## 5.1 F vs B0

Determine which mechanisms differ between F and B0.

List all simultaneous changes, such as:
- LLM usage.
- OKB grounding.
- Skill normalization.
- Deterministic scoring.
- Multi-agent orchestration.
- Verification and revision.

State clearly whether this is a whole-approach baseline comparison rather than a single-component ablation.

## 5.2 F vs B2

Determine whether B2 can isolate semantic matching as a baseline.

Identify differences in:
- Skill extraction.
- Normalization.
- Matching.
- Career scoring.
- OKB access.
- Skill-gap generation.

Explain whether these differences make the comparison confounded.

## 5.3 F vs B3

Determine whether F and B3 differ only in Verification Agent and its revision mechanism.

Identify any additional differences.

## 5.4 Paired evaluation

Determine whether the current evaluator supports evaluating the same CV against multiple configurations and comparing paired results.

If not, identify the missing functionality.

Do not implement statistical tests. Only report whether the current data structures support paired comparison and what would be needed.

# 6. Inspect Existing Tests and Fixtures

Inspect evaluation-related tests and fixtures.

Classify each as:

- Unit test of metric formula.
- Adapter contract test.
- Configuration test.
- Workflow integration test.
- Experiment runner test.
- Empirical evaluation.

Report which configuration paths are actually exercised by tests.

Do not describe synthetic fixtures as real CV evaluation data.

Do not execute Gemini or other external LLM calls.

Do not run CV analyses.

Do not run database writes or migrations.

Do not modify test fixtures.

# 7. Identify Exact Implementation Gaps

Create a prioritized gap table:

| Priority | Gap | Evidence | Why it matters | Required change | Risk |
|---|---|---|---|---|---|

Group gaps into:

A. Configuration/runtime execution gaps.

B. Output schema and adapter gaps.

C. Metric/reference data gaps.

D. Experiment runner and paired comparison gaps.

E. Reproducibility and manifest gaps.

F. Ground-truth and annotation gaps.

Separate code changes from data preparation and research-methodology decisions.

# 8. Recommend a Minimal Implementation Design

Based strictly on the actual repository, propose the smallest implementation plan that enables:

1. B0 vs F baseline comparison.
2. B2 vs F baseline comparison.
3. B3 vs F Verification Agent ablation.
4. Reuse of the existing evaluation framework.
5. Consistent output evaluation.
6. Reproducible experiment records.

The plan must preserve:

- The existing OKB taxonomy.
- The ten career IDs.
- Existing career requirements.
- Existing scoring weights.
- The four skill-gap categories.
- Existing agent responsibilities.
- Existing production workflow behavior unless explicitly approved.

Do not implement this plan.

For every proposed code change, name the likely files/functions affected and explain why.

Do not create new skills, aliases, technology mappings, or taxonomy entries.

# 9. Required Final Report Structure

Return the audit in this exact structure:

1. Executive Summary
2. Actual Runtime Architecture
3. Configuration Audit: B0, B2, B3, F
4. Evaluation Adapter Contract Audit
5. Metric Compatibility Matrix
6. Experimental Fairness and Confounding Analysis
7. Existing Test and Fixture Coverage
8. Implementation Gap Register
9. Minimal Implementation Plan
10. Decisions Requiring Researcher Approval
11. Final Readiness Verdict

The final readiness verdict must classify each experiment:

- B0: Ready / Partially Ready / Not Ready
- B2: Ready / Partially Ready / Not Ready
- B3: Ready / Partially Ready / Not Ready
- F: Ready / Partially Ready / Not Ready
- Evaluation adapters: Ready / Partially Ready / Not Ready
- Formal experiment execution: Ready / Not Ready

Use evidence from actual code and line references throughout.

Clearly distinguish:
- Implemented and executable.
- Implemented but not integrated.
- Descriptive metadata only.
- Documented but not implemented.
- Proposed future work.

## STRICT CONSTRAINTS

This is a READ-ONLY AUDIT.

- Do not edit source code.
- Do not create files.
- Do not modify documentation.
- Do not change database schemas or records.
- Do not run migrations or import scripts.
- Do not call Gemini or any external LLM.
- Do not execute CV analyses.
- Do not run formal experiments.
- Do not change scoring formulas or weights.
- Do not modify the four skill-gap categories.
- Do not add new skills, aliases, mappings, or taxonomy entries.
- Do not modify the ten career IDs or career requirements.
- Do not claim that an experiment has been executed unless there is actual execution evidence.

If an item cannot be verified from the repository, state "Not verified" and explain what evidence is missing.

Stop after presenting the audit report. Do not implement anything.