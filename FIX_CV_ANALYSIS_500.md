# Task: Fix HTTP 500 Error in CV Analysis Workflow

Act as a senior Python backend engineer specializing in FastAPI, SQLAlchemy, PostgreSQL, data validation, and AI-powered CV parsing.

## 1. Project Context

The project is `career-intelligence`. The backend uses FastAPI, SQLAlchemy, and PostgreSQL. The CV analysis workflow includes a `ProfileAgent` that extracts structured information from an uploaded CV using an LLM and persists the extracted profile data to the database.

The relevant files identified so far are:

- `backend/app/agents/profile_agent.py`
- `backend/app/services/user_service.py`
- `backend/app/repositories/user_repository.py`
- `backend/app/schemas/user.py`
- `backend/app/workflows/career_workflow.py`

Inspect the actual local codebase before making changes. These paths are starting points, not an exhaustive list.

## 2. Confirmed Root Cause

Uploading a CV triggers:

`POST /api/analysis/cv` → HTTP 500 Internal Server Error.

The API response is:

```json
{
  "error": {
    "code": "workflow_error",
    "message": "The analysis could not be completed (stage: profile_analysis).",
    "stage": "profile_analysis",
    "error_type": "DataError"
  }
}
```

The backend log confirms:

```text
Education database error: sintaks masukan tidak valid untuk tipe date : « Aug 2023 »
LINE 2: ...Bachelor of Computer Science', 'Computer Science', 'Aug 2023'...
```

The execution path is:

`profile_agent.py:run()` → `user_service.add_education()` → `user_repository.create_education()` → PostgreSQL INSERT.

The `user_education` table has the following relevant columns:

- `start_date`: PostgreSQL `date`, nullable
- `end_date`: PostgreSQL `date`, nullable

The LLM extracted a date value of `"Aug 2023"`, but the application passed it directly to PostgreSQL, which rejected the value.

This is a confirmed date-normalization/validation defect. Do not waste time investigating the LLM provider, API credentials, database connectivity, or unrelated infrastructure as the primary cause of this specific failure.

## 3. Main Objective

Fix the CV analysis HTTP 500 error by implementing robust normalization and validation of extracted date values before database persistence.

The fix must address the underlying data-processing problem, not merely suppress the exception or hide the HTTP 500 response.

## 4. Required Investigation

Before editing:

1. Inspect the current implementations of `ProfileAgent.run()`, all profile persistence loops, the user service and repository methods, relevant Pydantic schemas, and the database models or migrations if present.
2. Identify every extracted date field that is persisted to PostgreSQL, including education dates, work-experience dates, and certification dates.
3. Determine which other fields use PostgreSQL `date` columns and check whether they can receive the same non-ISO date formats.
4. Inspect existing tests, validation utilities, project conventions, and dependencies. Reuse existing utilities where appropriate instead of creating redundant implementations.
5. Trace how the extracted values flow from the LLM response to database insertion.

Do not assume that the education fields are the only possible source of this class of error.

## 5. Required Implementation

### A. Create or reuse a centralized date-normalization utility

Normalize extracted date values before they reach database persistence.

The utility must handle at least:

- `Aug 2023` → `2023-08-01`
- `August 2023` → `2023-08-01`
- `2023-08` → `2023-08-01`
- `2023` → `2023-01-01`
- `2023-08-15` → `2023-08-15`
- Valid Python `date` or `datetime` values → a compatible date value
- `None`, empty strings, or whitespace-only strings → `None`
- `Present`, `Current`, `Ongoing`, or equivalent explicit indicators for an ongoing position → `None` for an end-date field
- Invalid or ambiguous values → handle safely according to the validation policy below

For month-and-year values, using the first day of the month is a storage convention only. Do not present it as the actual day on which the education or job started.

Use deterministic parsing. Prefer Python's standard library or an existing project dependency. Do not introduce a new dependency without a clear need.

### B. Distinguish start dates from end dates

Use field-aware normalization.

- Missing or unknown dates should not cause the entire CV analysis to fail.
- Explicit ongoing indicators should map to `None` for end dates.
- Do not automatically convert arbitrary invalid strings to `None` without recording a useful validation warning or applying an explicit documented policy.
- Do not silently fabricate dates.
- If a value is ambiguous or invalid, preserve the relevant extracted information where possible and follow the project's existing validation/error-handling conventions.

### C. Apply normalization consistently

Normalize date fields for all applicable profile entities before persistence, including:

- Education: `start_date`, `end_date`
- Work experience: `start_date`, `end_date`
- Certifications: `issue_date`, `expiry_date`
- Any other extracted profile field mapped to a PostgreSQL `date` column

Inspect the actual schema and repository implementation to confirm field names and storage types.

Avoid scattering slightly different date-parsing logic throughout multiple agents or repositories. Prefer one reusable utility at an appropriate layer.

### D. Validate data before database insertion

Ensure date strings are normalized or rejected according to the explicit policy before SQL execution.

Keep the existing SQL parameterization, deduplication behavior, transaction boundaries, and repository conventions intact.

Do not change PostgreSQL column types just to accommodate unnormalized strings.

### E. Preserve profile information and downstream behavior

The purpose of this fix is to make profile extraction and persistence robust, not to remove education or other profile features.

- Preserve the extracted institution, degree, field of study, company, role, certification name, descriptions, and other existing fields.
- Do not delete education persistence or skip all education records to bypass the error.
- Do not modify career recommendation scoring, skill-gap calculations, occupational knowledge-base mapping, agent responsibilities, or learning-roadmap logic unless investigation demonstrates a direct necessity.
- Keep existing API response contracts and successful workflow behavior compatible.
- Do not expose raw CV text, personal information, database credentials, or sensitive extracted values in logs.

### F. Handle failures appropriately

Do not simply catch `DataError` and continue as if persistence succeeded.

If invalid input remains after normalization, use the project's established validation and error-handling mechanisms. Log only the minimum safe diagnostic information needed to identify the affected field and the validation failure.

Do not leave temporary verbose diagnostic logging in production code.

## 6. Required Tests

Add or update automated tests using the project's existing test framework and conventions.

At minimum, test:

1. Month/year parsing: `Aug 2023`.
2. Full month-name parsing: `August 2023`.
3. ISO year-month parsing: `2023-08`.
4. Year-only parsing: `2023`.
5. Full ISO date parsing: `2023-08-15`.
6. Missing, empty, and whitespace-only dates.
7. Ongoing indicators for end-date fields.
8. Invalid date values and the documented error-handling policy.
9. Normalization of education, experience, and certification date fields.
10. Regression coverage proving that a CV containing `Aug 2023` no longer fails during education persistence.
11. Preservation of existing non-date profile fields.
12. Existing profile-analysis and downstream workflow tests, where available.

Prefer unit tests that do not require a live LLM or external API. Use the project's existing database-testing strategy for persistence integration tests. Do not modify production data to run tests.

## 7. Verification and Acceptance Criteria

The task is complete only when:

- The date-normalization utility is implemented and tested.
- All relevant extracted date fields are normalized before persistence.
- The regression test for `Aug 2023` passes.
- Existing relevant tests pass.
- The CV analysis workflow can persist a profile containing month/year dates without triggering the same PostgreSQL `DataError`.
- The workflow still returns meaningful errors for genuinely unrecoverable failures.
- No database schema change is made unless independently justified by the existing schema and requirements.
- No unrelated recommendation, skill-gap, or roadmap behavior is changed.

Run the relevant tests and report the actual results. Do not claim that a live CV upload has been verified unless you actually ran it successfully in the available environment.

## 8. Implementation Rules

- Work directly in the existing local repository.
- Inspect before editing; avoid assumptions about code not yet examined.
- Keep the change minimal, maintainable, and consistent with the project's architecture.
- Do not rewrite entire files when a targeted change is sufficient.
- Do not overwrite unrelated user modifications or revert uncommitted changes.
- Do not change environment variables, credentials, or `.env` files.
- Do not weaken validation or suppress exceptions merely to make the endpoint return HTTP 200.
- Do not make unrelated refactors.

## 9. Final Report

After implementation, provide:

1. The confirmed root cause.
2. The files changed and the purpose of each change.
3. The normalization and invalid-date handling policy implemented.
4. Tests executed and their actual pass/fail results.
5. Any remaining limitations or unverified behavior.
6. Exact commands to run the relevant tests and restart the backend locally.

Start by inspecting the repository and tracing the current date-handling path. Then implement the fix, add regression tests, run the tests, and report the results.
