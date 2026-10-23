# Step 16 — Inspection, Reproducibility, and Career-Fit Verification

## Purpose

Complete the narrowly scoped Step 16 inspection/reproducibility work for the career-intelligence project. The goal is to produce a reliable, privacy-conscious record of what the actual multi-agent workflow receives, produces, and forwards, while making it possible to independently verify the system's career-fit percentage using the formula that is already implemented.

**Do not redesign the scoring formula or refactor the system just to simplify verification. First establish the actual implementation from code.**

## 1. Inspect before changing anything

Read and compare the current local versions of:

- `docs/MASTER_SPEC.md`
- `docs/PROJECT_STATE.md`
- The actual manual-validation runner
- `Recorder` and the inspection package
- `artifact.build_artifact()` and its schema
- `CareerWorkflow.run()` and the compiled graph/node execution
- `GeminiClient`, provider/model resolution, SDK/version handling, and generation configuration
- Agent prompt definitions and per-agent token limits
- Career-fit scoring implementation, especially `compute_career_fit()`
- Step 9 skill-gap implementation
- Relevant unit, inspection, scoring, and manual-validation tests

Inspect the current local worktree and preserve every pre-existing modified or untracked file. Do not assume prior audit reports are still accurate without checking the current code.

Before editing, provide a brief internal plan in your execution summary or final report identifying the files and interfaces that need to change. Do not modify `docs/PROJECT_STATE.md` until the implementation and tests have been reviewed.

## 2. Objective A — One coherent manual-validation artifact path

Connect manual validation to the existing artifact builder so that one coherent artifact-generation path is used. Avoid duplicated or competing artifact schemas.

Use synthetic inputs and FakeLLM for automated tests. Do not implement normal API per-analysis persistence in this task.

The artifact must be based on the actual workflow execution and runtime configuration—not merely fields that happen to exist in a schema.

### Required run-level metadata

Record the following where available:

- Run ID and timestamp
- Git revision/commit, when safely available
- Knowledge-base version; if it cannot be determined, record an explicit `unavailable`/`unknown` value and explain why
- Provider and resolved model actually used by the run
- SDK/package name and version
- Generation settings: distinguish explicitly configured values from SDK defaults; record effective values only when they can actually be established
- Prompt identifiers/version labels and hashes, preferably hashes rather than full prompt text
- Per-agent/per-call token limits
- Effective workflow revision cap
- Executed nodes/agents and their execution order
- Verification outcomes, revisions, and final analysis status
- Sanitized error-stage metadata, where applicable

Do not infer a production model/provider from FakeLLM tests. Clearly label test doubles as test doubles.

### Runtime truth and unavailable values

Populate metadata from the real configuration/runtime objects used by the run. Do not hardcode guessed values merely to fill fields. Distinguish:

- explicitly configured settings;
- SDK defaults that are known;
- settings whose effective value cannot be resolved from the available interfaces.

For unknown values, use an explicit `unavailable` or `unknown` marker, with a reason when useful. Do not present unknown/default values as pinned configuration.

### Artifact privacy and security

Never include the following in saved artifacts or normal diagnostic logs:

- Raw CV or profile contents
- Extracted CV text or personal information
- Secrets, API keys, database credentials, or environment-variable values
- Full prompts that contain CV/profile information
- Raw exception messages that may contain sensitive content
- Unnecessary personal data

Prefer structured metadata, sanitized stage information, prompt hashes/IDs, safe source references, and explicit status fields. Inspect the artifact serialization path to ensure nested fields cannot accidentally leak sensitive content.

## 3. Objective B — Observe actual agent-to-agent processing

The reporting goal is to understand, for each actual agent/node in a workflow run:

1. What input it actually received
2. What output it actually produced
3. What data was forwarded to the next agent/node
4. Which outputs or fields were accepted, rejected, transformed, or omitted
5. Which knowledge-base records/sources supported the result, when available
6. What the Verification Agent checked and its outcome
7. Whether a revision occurred, why it occurred at a safe, structured level, and which output changed
8. What final structured result was returned to the next stage/user

Implement observability using actual graph/node execution events and data already available at the appropriate boundaries. Do not invent events or reconstruct payloads from assumptions.

### Trace requirements

- Associate trace events with one `run_id` and stable stage/node identifiers.
- Record stage start/completion or outcome where the workflow can reliably expose it.
- Capture safe structured inputs/outputs and forwarded-field summaries sufficient to audit data flow.
- Where full payload capture could contain personal data, record a sanitized representation, field names, types, counts, IDs, hashes, or redacted values instead.
- Make it possible to distinguish the agent's generated output from the validated/normalized output actually forwarded downstream.
- Record verification decisions and revision transitions as structured events.
- Include error-stage/status metadata without raw sensitive exception text.
- Keep observer/instrumentation failures from breaking normal analysis unless existing project requirements explicitly state otherwise.
- Preserve ordinary API workflow behavior. Do not add a second business-logic execution path solely for observability.
- Do not store or expose hidden chain-of-thought. The requirement is to log observable inputs, structured outputs, transformations, evidence references, verification decisions, scoring operations, and forwarded data—not private internal reasoning.

If the current workflow does not expose enough information to establish a value, mark it as unavailable rather than guessing. Clearly document the limits of what can be observed.

## 4. Objective C — Establish the existing career-fit formula (read and verify; do not redesign)

Before implementing a manual numerical check, reconstruct the exact career-fit formula from the current code, especially `compute_career_fit()`, its callers, related configuration, and tests.

Report clearly:

1. The exact formula currently implemented, written mathematically and explained in plain language
2. Every input variable and its source
3. Every active coefficient, multiplier, normalization denominator, missing/unmatched-skill rule, and rounding rule
4. Whether CORE/SUPPORTING, knowledge-base confidence, claim-only evidence, or proficiency currently affects career-fit calculation; distinguish active calculation factors from metadata
5. Whether Step 9 skill-gap logic still uses importance weights, ranking, priority, or severity, based on actual code and tests
6. Whether implementation, tests, documentation, and the previously agreed design disagree
7. Exact source paths, function names, and test names supporting the findings

The previous design discussion included removing skill-importance ranking/priority/severity from Step 9 while retaining CORE/SUPPORTING/confidence as metadata there. Do not assume this means the career-fit formula in Step 8 was removed. Verify both separately in the current code.

Do not create a new formula, alter the formula, or refactor scoring for this task. Do not copy an earlier proposed/example formula unless the current implementation confirms it.

If the formula cannot be reconstructed unambiguously, report the unresolved parts and stop short of claiming it is verified.

## 5. Objective D — Independently verify numerical career-fit results

After the existing formula has been established from code, add an independent numerical verification using a small synthetic fixture.

Requirements:

- Use fixed, documented synthetic inputs.
- Show every intermediate calculation: skill matches/values, active factors, numerator, denominator, normalization, and rounding, as applicable to the actual formula.
- Compute the expected result independently of the production scoring function. Do not call the same scoring function to generate the “manual expected” value.
- Compare the independently calculated result with the system result.
- Report absolute difference and the justified tolerance, including how rounding affects the comparison.
- Verify multiple candidates if the scoring API supports it; do not verify only the top-ranked candidate.
- Add regression tests for the verified formula and important edge cases found in the implementation, without changing the formula.
- Keep the manual calculator/test helper separate from production scoring code so it can catch implementation errors.

The example and tests must follow the actual formula found in the repository. Do not assume a weighted formula or any particular coefficient until code inspection confirms it.

Explain the scope of the evidence: matching independent calculations demonstrate implementation consistency for the tested cases, not by themselves the real-world validity of career recommendations.

## 6. Test input: existing `cv2.pdf` fixture

The user reports an existing `cv2.pdf` file in the repository-root `upload/` directory, alongside `backend/`. Verify the exact local path and accessibility; do not assume it exists.

- If present and readable, use it only as an optional local PDF parsing/extraction fixture if that test is useful.
- Do not print its contents, extracted text, or personal information in terminal output, test failure messages, reports, traces, or artifacts.
- Do not upload it to an external service, call a live LLM, or send it through a workflow that mutates a real database.
- Do not use production credentials or perform external requests.
- Do not modify, move, or delete `cv2.pdf`.
- Keep synthetic-data tests. `cv2.pdf` is a real sample CV, not guaranteed synthetic data.
- If missing or inaccessible, state that fact and continue with synthetic fixtures. Do not search unrelated directories for another CV.
- Report separately which tests used the PDF fixture and which used synthetic data.
- Avoid asserting that the PDF test is privacy-safe solely because the artifact passed; test for leakage using synthetic sentinel strings and inspect the resulting artifact structure.

## 7. Scope boundaries

Do not:

- Implement API-wide per-analysis persistence in this task
- Implement baseline/ablation switches or begin Step 17
- Redesign the frontend or implement new frontend pages
- Change the career-fit formula or redesign Step 9 scoring
- Delete, disable, or weaken failing tests merely to get a passing result
- Revert, overwrite, or clean up unrelated user changes
- Modify `docs/PROJECT_STATE.md` before implementation and test results are reviewed
- Run live LLM requests, external API calls, real CV uploads, or production database mutations

Preserve existing workflow behavior. Optional instrumentation should use the existing workflow execution path.

## 8. Validation requirements

Run:

1. Focused artifact, recorder/inspection, manual-validation, workflow, and career-fit scoring tests
2. Relevant broader offline backend regression suites
3. Syntax/compile checks for changed Python files
4. `git diff --check`
5. Artifact privacy checks using synthetic sentinel values that should never appear in serialized output

Use the repository's existing environment and conventions. Do not install dependencies unless necessary and explicitly justified. If a command fails, report the exact command, failure, and whether it was environmental or a code/test failure. Do not omit failures from the report.

Do not execute the manual-validation runner against a real database. Exercise its artifact-generation path through isolated tests and fakes.

## 9. Final report required

Provide a concise but evidence-based report with these sections:

### A. Changes
- Every changed file and its purpose
- Confirm unrelated pre-existing modified/untracked files were preserved

### B. Actual workflow trace
- Which nodes/agents were observed
- What input/output/forwarded-data details are captured at each stage
- Which fields are redacted, hashed, summarized, or unavailable
- How verification and revision events are represented
- What cannot be observed from the current workflow

### C. Artifact schema and data provenance
For every required metadata field, state:
- Field name
- Actual runtime/code source
- Whether populated, defaulted, or unavailable
- Privacy handling

### D. Career-fit formula and independent verification
- Exact formula from current implementation
- Explanation of active factors versus metadata
- Separate conclusion about Step 9 priority/weighting behavior
- One worked synthetic example with all intermediate calculations
- System score, independent manual score, absolute difference, and tolerance
- Tests covering the calculation and edge cases

### E. Test results
- Exact commands run
- Pass/fail/skipped counts
- Which tests used synthetic data
- Which tests, if any, used `upload/cv2.pdf`
- Syntax check and `git diff --check` results
- Any tests not run and why

### F. Remaining gaps and Step 16 decision
- Explicit unresolved reproducibility or traceability gaps
- What remains unverified without a live run
- Whether Step 16 can be considered complete, partially complete, or incomplete, with evidence
- Recommended next task

Be precise. Schema fields existing is not evidence that values are populated. Passing unit tests is not evidence of a live end-to-end run. Do not claim completion beyond what the code and tests establish.
