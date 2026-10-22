# Mission: Debug, Run, and Validate the Career Intelligence System End-to-End

Act as a senior Python/FastAPI, LangGraph, React/TypeScript engineer and QA engineer. You have access to this local repository and terminal.

Repository:
`D:\IZZATI\Bismillah 2026 Sidang\career-intelligence`

Backend:
`backend/`

Frontend:
`frontend/`

Upload:
`upload/`

## 1. Objective

I want to test the actual application, not merely review code or run isolated unit tests.

My objectives are to:
1. Confirm that the application can start correctly.
2. Upload a real CV through the application's intended workflow.
3. Verify that the system extracts information from the file correctly.
4. Verify that the Profile Agent normalizes the extracted information correctly.
5. Verify that the career recommendation follows the existing knowledge base, deterministic scoring formula, and configured rules.
6. Verify that the Skill Gap Agent follows the existing skill-gap rules and categories.
7. Verify that the Roadmap Agent generates outputs grounded in the detected gaps.
8. Verify that the Verification Agent checks the actual outputs correctly.
9. Observe the actual inputs and outputs at every stage and inspect how data is passed between agents.
10. Identify and document weaknesses, incorrect outputs, hidden assumptions, and failure points before proceeding to project Steps 16.

Do not assume that the application works just because its frontend renders, an API returns HTTP 200, or a JSON response is produced.

## 2. Mandatory project constraints

Before making changes, inspect the repository's current instructions and project state, especially `AGENTS.md`, `PROJECT_STATE.md`, `MASTER_SPEC`, or their actual equivalents if present.

Preserve the existing architecture and frozen decisions:
- Use the existing occupational knowledge base and its existing canonical careers.
- Do not invent careers, skills, occupational requirements, evidence, or provenance.
- Do not change the existing career-fit scoring formula or scoring weights.
- Do not change the frozen skill-gap categories:
  - `matched_evidenced`
  - `matched_claimed_only`
  - `missing`
  - `unmatched_user_claims`
- Do not switch the LLM provider or change the project's database schema/API contract without explicit justification and approval.
- Do not introduce career-transition framing.
- Do not implement Steps 16–20 as part of this task.
- Fix bugs required to make the existing implementation work, but distinguish bug fixes from changes to intended behavior.

Inspect actual code rather than assuming previous assistant reports are accurate.

## 3. Phase A — Repository and environment audit

Inspect:
- Backend dependencies and Python version compatibility.
- `.env` loading and configuration precedence.
- LLM client initialization and selected model.
- Database configuration and connectivity.
- FastAPI routes and dependencies.
- CV extraction, PII redaction, Profile Agent, and skill normalizer.
- Career recommendation agent and `compute_career_fit()`.
- Skill-gap agent, service, and classification rules.
- Roadmap Agent.
- Verification Agent.
- LangGraph state, node transitions, revision handling, and final response.
- Frontend API client, proxy, upload form, loading states, and error handling.
- Existing tests and their use of mocks, fake LLMs, and real databases.

Identify the actual entry points and dependency chain.
Check `.gitignore` for CV upload directories, generated artifacts, environment files, and other sensitive material. Do not print API keys or other secrets. Do not commit CV files or generated private data.
First report the most critical blockers. Then proceed with the necessary fixes unless a destructive or financially consequential action requires my approval.

## 4. Phase B — Make the application runnable

Get the backend and frontend running using the repository's existing configuration.

Verify:
- The backend process starts without import errors or child-process crashes.
- Database connectivity works.
- Required tables and expected data exist.
- The health endpoint works.
- The frontend starts.
- The frontend proxy points to the correct backend address.
- API requests from the frontend reach the intended backend endpoints.

Do not treat a server's initial "running" message as proof that the application imported successfully.

Use the existing virtual environment if available. Do not blindly upgrade every dependency or run destructive database migrations.

If a dependency is missing, determine the correct package and add it to the project's dependency specification if necessary.

If a required database or environment variable is unavailable, report the exact blocker and the smallest action needed. Never expose secret values.

## 5. Phase C — Validate the CV pipeline

Use a synthetic CV fixture first to test extraction, parsing, normalization, and edge cases without consuming LLM quota.
Then, if the environment and API quota permit, run one real CV through the actual upload workflow.
For the real CV, use an existing consented test profile or a synthetic test user. Do not delete or overwrite an existing user's data. If a temporary user is required, use safe cleanup only after verifying its identity and relationships.
Check the following:
### CV extraction
- Does the application read the uploaded file?
- Is the correct text extracted?
- Are important sections omitted, duplicated, or placed in the wrong order?
- Are dates, education, projects, experience, and skills interpreted correctly?
- Does the system handle unsupported formats and empty or malformed files correctly?

### Profile Agent
- What exact sanitized input does the agent receive?
- What structured information does it extract?
- What skills and canonical IDs does it normalize?
- What proficiency and evidence are assigned?
- Which values are directly supported by the CV, inferred, missing, or uncertain?
- What is persisted to the database?
- Does the persisted profile match the agent's returned output?

Do not infer proficiency from a skill mention unless the existing system explicitly defines and implements that inference.
If the model returns malformed or truncated JSON, record the actual failure and fix the underlying issue without silently fabricating missing fields.

## 6. Phase D — Inspect every actual agent execution

I need an inspectable trace of the actual execution, including repeated executions caused by verification and revision routing.
For every stage, capture:
- Execution sequence number.
- Agent or LangGraph node name.
- Attempt/revision number.
- Actual sanitized input.
- Actual output.
- Relevant database and knowledge-base records used.
- Canonical skill IDs, career IDs, and source/provenance IDs where available.
- LLM model and call metadata, without credentials or full sensitive prompts.
- Errors and validation notes.
- Data passed to the next stage.

Observe the existing graph and agent boundaries. Do not create a second pipeline that merely simulates the real workflow.
If a downstream agent reads the user profile from the database instead of receiving the previous agent's output directly, record the actual database snapshot it reads. Do not falsely describe this as direct state propagation.

Clearly distinguish:
1. Agent-produced output.
2. Database records read or written.
3. Knowledge-base retrieval results.
4. Deterministic engine calculations.
5. Verification decisions and final output.

Do not add extra LLM calls solely for inspection.

### Required stages

**Profile Agent**
- Extracted information.
- Normalized profile.
- Skill IDs and evidence.
- Persistence result.

**Career Recommendation Agent**
- Actual profile read by the agent.
- Candidate careers retrieved.
- Required skills and relevant source IDs.
- Actual scoring inputs and per-career score breakdown, where exposed by the existing implementation.
- Ranked recommendations.

**Skill Gap Agent**
- Actual profile and selected career.
- Required and current competencies.
- Skill-by-skill classification.
- Actual deterministic score/breakdown.
- Narrative and its source, if applicable.

**Roadmap Agent**
- Actual gap input.
- Retrieved learning or occupational context.
- Generated roadmap items.
- Mapping between each roadmap item and the skill gap it is intended to address.

**Verification Agent**
- Actual redacted inputs.
- Checks performed.
- `PASS`, `FAIL`, or `REVISE` result.
- Unsupported claims and required revisions.
- Actual routing after the decision.

Do not invent fields that are unavailable. Label them as unavailable and identify what code would be needed to expose them.

## 7. Phase E — Provide a manual inspection artifact

Implement a minimal, temporary diagnostic mode that reuses the existing production workflow.
Prefer existing LangGraph state updates or streaming facilities if compatible with the installed version. Add optional instrumentation only where needed.
Write a sanitized JSON artifact to a location such as:
`backend/artifacts/manual_validation/<run_id>.json`

The artifact must include:
- Run metadata.
- Input file metadata and a content hash, not the raw CV text.
- Actual execution trace.
- Per-agent input/output snapshots.
- Relevant KB/database retrieval references.
- Deterministic scoring breakdowns where available.
- Errors and revision attempts.
- Cross-stage validation results.
- Final workflow output.
- Explicit unavailable fields.

Use an allowlist of safe fields and redact sensitive information. Do not save API keys, tokens, complete prompts, raw CV text, or unnecessary personal data. Ensure generated artifacts and upload directories are excluded from version control.

The inspection mode must not change normal application behavior or silently change the LLM configuration. Clearly label diagnostic runs that use fake/fallback LLM behavior versus full runs using the configured production LLM.

## 8. Phase F — Check correctness, not just successful execution

Create a manual-validation report comparing the actual results with an independent reference derived from the CV and knowledge base.

At minimum, verify:
1. Extracted facts are supported by the original CV.
2. Normalized skill IDs correspond to the intended canonical skills.
3. Persisted profile data matches the expected profile.
4. Career candidates and required skills originate from the existing knowledge base.
5. Career scores match the existing deterministic scoring implementation and its configured weights.
6. Skill-gap categories follow the frozen rules.
7. Gap calculations are consistent with the actual current and required competencies.
8. Roadmap items address the relevant gaps.
9. Verification decisions correspond to the checks actually performed.
10. Data read by downstream agents matches the expected data source and is not silently altered.

Do not validate a calculation by comparing the same function's output against itself. Where practical, independently recompute expected results in a test or manual worksheet using the documented formula.

Label each check `PASS`, `FAIL`, `NOT_APPLICABLE`, or `NEEDS_REVIEW`, and include the reason and source of the expected value.

A valid JSON structure is not proof of semantic correctness.

## 9. Phase G — Test progressively and conserve quota

Use this sequence:

1. Existing unit tests that do not require an LLM.
2. Synthetic CV extraction and normalization tests.
3. FakeLLM integration tests for deterministic pipeline behavior.
4. Database-backed tests using a safe test database.
5. One real LLM call to validate Profile Agent behavior when quota is available.
6. One full real-LLM CV analysis only after earlier stages are stable.
7. Frontend-to-backend end-to-end interaction.

Avoid unnecessary retries and repeated full analyses. Inspect actual call counts before estimating the cost or quota use of a full run.

If Gemini returns `429 RESOURCE_EXHAUSTED`, stop retrying, record the error, and continue with tests that do not require the API. Do not switch providers or models automatically.

Tests using FakeLLM do not establish that real LLM outputs are correct. Report this distinction explicitly.

## 10. Phase H — Fix, verify, and report

For every bug:

- Reproduce it.
- Identify its root cause.
- Make the smallest appropriate fix.
- Add or update a regression test.
- Run the relevant test.
- Report the actual result.

Do not claim tests passed unless they were actually executed and the output confirms success.

Do not perform destructive database operations or modify existing user data.

At completion, provide:

1. Files inspected and changed.
2. Bugs found and root causes.
3. Exact commands used to start the application.
4. Tests actually executed and their results.
5. Any remaining blockers.
6. The exact procedure I should follow to upload a CV manually.
7. The path to the generated JSON artifact.
8. A manual-validation checklist.
9. A clear statement of whether the real end-to-end flow succeeded, partially succeeded, or failed.

### Scope boundary

Do not start project Steps 16–20 as formal implementation work:

16. Implement logging.
17. Implement evaluation framework.
18. Implement baseline/ablation configurations.
19. Run tests as the dedicated project phase.
20. Run end-to-end experiments.

Tests required to fix bugs and verify this diagnostic capability are permitted. Keep this work focused on making the existing system runnable and inspectable before formal evaluation.

Start by inspecting the actual repository and environment. Then work incrementally, verify every fix, and stop at genuine blockers rather than guessing.