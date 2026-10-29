Continue implementing the project based on the latest official audit. For now, work exclusively on **Step 16 — Implement logging**.

## Sources of truth

- `docs/MASTER_SPEC.md` is the authoritative source for workflow definitions and acceptance criteria.
- Follow `AGENTS.md` for architecture constraints, implementation rules, and testing requirements.
- Inspect `PROJECT_STATE.md`, the actual backend implementation, and existing manual-validation artifacts before making changes.
- Do not consider Step 16 complete merely because manual inspection or FakeLLM validation has passed.
- Do not implement Steps 17–20 in this task.

## Objective

Implement logging for every analysis performed through the normal API workflow, satisfying all requirements for Step 16 in `MASTER_SPEC.md` §19.

The previous audit found that the normal `/analysis/cv` and `/analysis/profile` endpoints do not use the manual-validation artifact writer. Therefore, the existing artifact must not be treated as a substitute for logging every analysis.

## Required workflow

1. Re-read the complete Step 16 specification, including every required field, behavior, format, and acceptance criterion in `MASTER_SPEC.md` §19.
2. Inspect the actual API and workflow implementation to identify the correct logging integration points. Avoid duplicate logging and unnecessary architectural changes.
3. Implement per-analysis logging that satisfies the complete §19 specification, including at least:
   - Analysis ID and timestamp.
   - Relevant user/profile ID.
   - Model and model version.
   - Prompt and prompt version.
   - Occupational Knowledge Base version or fingerprint.
   - Executed agents.
   - Privacy-safe agent output records.
   - Verification result.
   - Revision count.
   - Final status and analysis result.

   This list is not a substitute for checking every field required by §19. When metadata is genuinely unavailable, explicitly represent its unavailability as permitted by the specification. Never fabricate values.

4. Ensure logging works for normal analyses through the API, not only through the manual-validation harness. Preserve the existing harness if it remains useful.
5. Follow the project's privacy requirements. Do not persist raw CVs, sensitive prompts, or sensitive responses merely to satisfy logging requirements unless explicitly required by the specification. Use sanitized representations that still support auditing.
6. Preserve existing analysis behavior, API contracts, the frozen architecture, and existing database and knowledge-base data. Do not perform destructive resets, migrations, or experimental-data modifications.
7. Add or update focused tests to verify:
   - Both normal API endpoints produce compliant analysis logs.
   - Required fields are recorded and unavailable metadata is handled explicitly.
   - Agent traces, verification results, revision counts, and final outcomes are recorded consistently.
   - Sensitive information does not leak into logs.
   - Logging failures are handled according to the project's error-handling contract and policies.
8. Run the relevant tests and regression tests required by `AGENTS.md`. Do not claim that tests passed unless they were actually executed.

## Scope restrictions

- Do not implement the evaluation framework, research metrics, or report generator for Step 17.
- Do not implement B0/B2/B3/F configuration paths for Step 18.
- Do not run pilot studies or formal research experiments for Step 20.
- Do not modify `MASTER_SPEC.md` to make the requirements fit the implementation.
- Do not mark Step 16 complete merely because code has been written. Verify every official acceptance criterion in §19 against actual evidence.

## Final report

Provide the following:

1. Each §19 requirement satisfied, with evidence from the implementation.
2. Files created or modified.
3. Any database/schema changes and their justification.
4. Tests actually executed and their results.
5. Any acceptance criteria that remain unmet.
6. Step 16 status: **COMPLETE** only if every official criterion is satisfied; otherwise, **PARTIAL**, with concrete blockers.
7. The impact on `PROJECT_STATE.md` and other status documentation. Update these only when permitted by project rules and supported by verified evidence.

Do not stop at recommendations or a proposed plan. Implement Step 16 according to the specification, verify the results, and report the outcome accurately.