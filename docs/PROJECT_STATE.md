# Project State

## Project

Hybrid Verified Multi-Agent Career Intelligence System for IT Graduates.

## Confirmed Completed Steps

* Steps 1–4: Knowledge Base inspection, PostgreSQL schema, data import, and semantic validation.
* Step 5: Deterministic retrieval.
* Step 6: User profile representation.
* Step 7: Profile Agent.
* Step 8: Career Recommendation Agent.
* Step 9: Deterministic Skill-Gap Engine.
* Step 10: Skill-Gap Agent.
* Step 11: Learning Roadmap Agent.
* Step 12: Verification Agent.
* Step 13: LangGraph multi-agent orchestration.
* Step 13.1: Best-effort PII redaction and Profile Agent privacy boundary.
* Step 13.2: In-memory PDF, DOCX, and TXT text extraction.
* Step 14: FastAPI integration and Step 14.1 security/configuration hardening.
* Step 14.2: Runtime integration tests against the local database and FastAPI app.
* Step 14.3: Existing-profile privacy hardening for persisted user text.
* Step 14.4: Insert-only user skill ingestion.
* Step 15: React/Vite frontend over the existing API.

Step 16: Inspection, career-fit verification, artifact contract, and guarded
isolated-database validation (see its record below).

* Step 16 (`MASTER_SPEC` §19): privacy-safe per-analysis logging for both normal
  analysis endpoints (see its record below).

Steps 5–11 regression tests were run locally during Step 12 implementation and passed.
Step 12 deterministic checks and mocked semantic-review tests passed; a local-KB
integration smoke run returned PASS for 41 checks without a live LLM call.
Step 13's focused tests and local workflow integration run passed.

## Current Checkpoint

As of 2026-10-27, Steps 1–16 are complete. The HEAD commit is `1921d30`
("update project state"); the Step 16 code, tests, and documentation were
committed in `ebf83fd` and `1921d30`. The guarded manual-validation run produced
`619d709...` after the X2 fix with 11/11 cross-stage checks PASS, H1–H9 PASS,
and zero contract violations. Step 17 has not started.

Verified during this reconciliation:

* Frontend: `npm run typecheck` passed; `npm test` passed with **2 files, 10
  tests** (see the Step 15 record).
* Step 16 focused offline suites after the preflight fixes: **126 passed, 1
  warning**; the same files gave 117 passed before those tests were added (see
  the Step 16 record).
* `python -m py_compile` on the changed inspection/runner/test files passed;
  `git diff --check` passed (one pre-existing LF/CRLF notice for
  `backend/scripts/import_kb.py`).
* The post-fix manual-validation artifact `619d709...` (2026-10-27) records
  11/11 cross-stage PASS (including X2) and H1–H9 PASS, and passes
  `scripts/check_artifact.py` with zero violations. See the final acceptance
  audit in the Step 16 record.

The database-backed runtime tests and live LLM behavior were not run during
this reconciliation. Earlier results for those remain prior evidence, not
freshly verified facts.

## Local Full-Stack Runtime Check (2026-10-18)

* Added direct backend runtime dependencies missing from
  `backend/requirements.txt`: Pydantic, SQLAlchemy, the PostgreSQL psycopg2
  driver, python-dotenv, and Google Gen AI SDK. Added `requirements-dev.txt`
  for pytest and a secret-free `.env.example` describing local DB, LLM, and
  development-only API acknowledgement settings.
* Python 3.13.0 successfully installed the declared dependencies; `app.main`
  imports, and `pip check` reports no broken requirements. No Python-version
  switch was required.
* The existing React/Vite API client already uses `/api` and the Vite proxy
  targets `127.0.0.1:8000`, matching FastAPI paths and the loopback policy.
  No API-path or port changes were needed.
* Tests run:
  * From `backend`: `$env:CAREER_RUN_RUNTIME_DB_TESTS='1'; .\.venv\Scripts\python.exe -m pytest -q`
    — **160 passed, 1 LangChain pending-deprecation warning**. This includes
    opt-in local PostgreSQL/Knowledge Base runtime tests using synthetic users
    and fake LLM clients.
  * From `frontend`: `npm run typecheck` — passed; `npm test` — **1 file,
    7 tests passed**; `npm run build` — passed. (Historical 2026-10-18 result.
    The current frontend suite is 2 files / 10 tests; see the Step 15 record.)
* Live HTTP checks: Uvicorn started on `127.0.0.1:8000`; `GET /health`
  returned HTTP 200 with `{"status":"ok"}`. `GET /openapi.json` showed
  `/health` GET and `/analysis/users`, `/analysis/profile`, `/analysis/cv`
  POST routes. Vite served `/` with HTTP 200 and `GET
  http://localhost:5173/api/health` returned HTTP 200 through the configured
  proxy. A synthetic user was created through the running API (HTTP 201),
  confirmed persisted, then deleted by its exact returned ID and synthetic
  email.
* Analysis was exercised against the local DB/Knowledge Base using the real
  workflow and fake LLM clients in the runtime suite. No live/paid Gemini
  request was made; a live model-backed analysis therefore remains unverified.
  API routes fail closed unless `CAREER_API_ACKNOWLEDGE_NO_AUTH=true`; keep the
  service bound to loopback because this is not authentication.

## Frozen Constraints

* 10 canonical careers.
* Existing Knowledge Base and canonical IDs are authoritative.
* Deterministic career-fit and skill-gap results must not be recalculated by LLM agents.
* Preserve the four established skill-gap categories.
* No skill-gap priority scoring or proficiency-gap calculations.
* Reuse the existing LLM client.
* No paid live API tests unless explicitly approved.
* Verification reports findings only; it does not mutate agent outputs.
* Semantic review is only needed for LLM-generated text. Missing/failed semantic
  review is reported as REVISE rather than treated as a pass.
* Orchestration defaults to an already-persisted profile. Raw profile extraction
  is optional and only runs when raw profile text is supplied.
* Submitted profile text is redacted before Profile Agent/LLM use. Raw text is
  not retained in the returned workflow state. The Profile Agent only persists
  its existing whitelisted structured extraction fields, after redacting PII
  from their string values; raw CV text is never persisted by that agent.
  Only redacted free-form profile text plus the existing canonical skill
  catalog is sent to the Profile Agent LLM. Persistable CV-derived fields are
  limited to education (institution, degree, field, dates, description),
  experience (company, role, employment type, dates, description), projects
  (title, description, URL, role), certifications (name, issuer, dates,
  credential URL), claimed skills (claim, normalized ID/name, proficiency),
  and evidence (type, description, URL); every string value is redacted first.
* For existing-profile analysis, persisted user claim/proficiency strings are
  redacted in the Skill-Gap LLM prompt. Sanitized copies are supplied to
  verification and API response serialization; canonical IDs, deterministic
  categories/scores, and the original Step 9 result remain unchanged.
* PII redaction is best-effort pattern matching, not a guarantee that all
  personal information is detected. CV file extraction is implemented as a
  standalone in-memory service. Its output must pass through the existing PII
  redactor before any Profile Agent/LLM call. The implemented CV API enforces
  this order; Step 14.2 exercises it using synthetic input and a fake LLM.
* Orchestration revision limit is configurable; a workflow is only marked
  VERIFIED when the overall verification and every check pass without unresolved
  unsupported claims or required revisions.

## Pending Work

1. Step 16 is complete; no further E2E run is required. Optional only if the
   researcher rejects the recorded dirty-tree overlay: one guarded rerun from a
   literally clean HEAD (the overlay was non-code task notes, not system code).
2. Implement the Step 17 evaluation framework (not started).
3. Implement and evaluate Step 18 baseline and ablation configurations.
4. Step 19 full test matrix and Step 20 end-to-end experiments remain pending.
5. Review live LLM-backed analysis only when explicitly approved; current
   database-backed analysis regression tests use fake LLM clients.

## Step 12 Verification Record

* Added `backend/app/agents/verification_agent.py` and
  `backend/app/schemas/verification.py`; added focused tests in
  `backend/tests/test_verification_agent_unit.py`.
* Verification checks canonical recommendation IDs/metadata/ranking, recomputes
  scores only through the shared `compute_career_fit()`, compares Step 9 output
  through the existing deterministic classifier, validates Step 10 narrative
  IDs against Step 9 categories, and validates Step 11 item identity/evidence,
  gap coverage, and embedded Step 9 output.
* Provenance is accepted only from records resolved by retrieval. Missing or
  ambiguous source mappings are reported as unavailable, not filled in.
  LLM-generated prose is checked only when present, using the existing
  `LLMClient`; the LLM cannot change structured agent outputs.
* Tests run:
  * `python -m pytest tests\test_verification_agent_unit.py -q` — 11 passed.
  * `python -m py_compile app\agents\verification_agent.py app\schemas\verification.py tests\test_verification_agent_unit.py` — passed.
  * Existing Steps 5–11 unit and smoke scripts all passed locally, including
    retrieval, user/profile services, career recommendation, skill-gap engine
    and agent, skill normalization, and roadmap tests. The optional live LLM
    portion of the Step 10 smoke test was skipped; mocked paths were exercised.
  * A deterministic local-KB integration run verified 10 recommendations and
    returned PASS across 41 checks; its temporary user was deleted.
* No live/paid API call was made. The workspace has no Git metadata, so a Git
  status/diff could not be recorded. Some existing smoke scripts intentionally
  leave their test users in the local database, as reported by those scripts.

## Step 13 Orchestration Record

* Added `backend/app/workflows/career_workflow.py` as a compiled, typed
  `StateGraph`, its package initializer, focused fake-agent tests in
  `backend/tests/test_career_workflow_unit.py`, and
  `backend/requirements.txt` declaring `langgraph>=0.6,<1`.
* The graph loads an existing profile by `user_id` without re-parsing it;
  optional raw profile text invokes the existing Profile Agent. It then runs
  career recommendations, selects the explicit canonical target or the
  top-ranked recommendation, runs the existing Skill-Gap Agent and Roadmap
  Agent, and passes those exact results to the Verification Agent.
* PASS ends as `VERIFIED`. Non-passing findings are routed to a responsible
  recommendation, skill-gap, or roadmap stage when an existing verifier check
  identifies one. Downstream stages are rerun after upstream regeneration.
  Findings without a responsible supported agent end `VERIFICATION_FAILED`.
  `max_revisions` (default 2) bounds retries; exhaustion ends as
  `REVISION_LIMIT_REACHED`. Agent/runtime errors and invalid inputs end as
  `ERROR` with structured stage/type/message details. No terminal path converts
  a non-passing or internally inconsistent verification result into success.
* Existing agent methods do not accept verifier feedback as a revision prompt;
  the graph reruns the owning stage using its current public interface instead
  of changing completed Steps 5–12. Profile extraction is skipped unless raw
  text is explicitly supplied. No DB schema, API, or provider changes were made.
* LangGraph 0.6.2 was already installed but had no dependency manifest in the
  workspace; the new backend requirements file declares only the added
  orchestration dependency. Existing application dependencies remain
  undocumented in a manifest.
* Tests run:
  * `python -m pytest tests\test_career_workflow_unit.py -q` — 23 passed;
    LangGraph emitted 20 `config_type` deprecation warnings from the installed
    0.6.2 package.
  * `python -m py_compile app\workflows\career_workflow.py app\workflows\__init__.py tests\test_career_workflow_unit.py` — passed.
  * `python -c "from langgraph.graph import StateGraph, START, END; import langgraph; print('LangGraph StateGraph import OK')"` — passed.
  * Step 8 `test_career_fit_service_unit.py` and
    `test_career_recommendation_agent_smoke.py` — passed.
  * Step 9 `test_skill_gap_service_unit.py` and
    `test_skill_gap_service_smoke.py` — passed.
  * Step 10 `test_skill_gap_agent_unit.py` and
    `test_skill_gap_agent_smoke.py` — passed; optional live LLM portion skipped.
  * Step 11 `test_learning_roadmap_agent_unit.py` and
    `test_learning_roadmap_agent_smoke.py` — passed.
  * Step 12 `python -m pytest tests\test_verification_agent_unit.py -q` — 11 passed.
  * Full local workflow with existing DB/KB and no live LLM call — `VERIFIED`,
    41 verification checks; temporary integration user deleted.
* No live Gemini call was made. The pending next stage is Step 14, API
  integration; it was not started.

## Step 13.1 PII Redaction Record

* Added `backend/app/services/pii_redaction_service.py` with reusable text and
  structured-value redaction. It replaces labeled names, email addresses,
  common phone formats, labeled addresses and street-address lines, labeled
  NIK/KTP/NPWP/passport identifiers, and standalone 16-digit identifiers with
  typed placeholders. Detection metadata contains only entity types/counts;
  matched values are not returned.
* `ProfileAgent.run()` redacts input before prompt construction and recursively
  redacts every string in the LLM extraction before exposing it or persisting
  the existing allowlisted education, experience, project, certification,
  skill, and evidence fields. Unrecognized extraction fields are not written
  through those existing persistence calls.
* `CareerWorkflow` keeps only redacted profile text transiently inside graph
  execution and removes it from the returned state. Errors from profile,
  downstream stages, or graph execution use generic messages whenever a
  profile was submitted, so exceptions cannot echo submitted profile content.
  No logging statements, LLM interface, provider configuration, database
  schema, file parser, or API endpoint was added or changed.
* Tests added: `backend/tests/test_pii_redaction_service.py` and
  `backend/tests/test_profile_privacy_boundary.py`.
* Tests run:
  * `python -m pytest tests\test_pii_redaction_service.py tests\test_profile_privacy_boundary.py tests\test_career_workflow_unit.py -q`
    — 34 passed; 23 LangGraph `config_type` deprecation warnings.
  * `python -m py_compile app\services\pii_redaction_service.py app\agents\profile_agent.py app\workflows\career_workflow.py tests\test_pii_redaction_service.py tests\test_profile_privacy_boundary.py`
    — passed.
  * `python tests\test_profile_agent_smoke.py` — passed; the existing smoke
    script created test users 70 and 71 and reports that they remain in the
    local database.
* No live/paid LLM call or dependency installation was performed. Redaction
  can miss unlabeled names/addresses, unusual phone formats, obfuscated
  identifiers, and PII embedded in unstructured text; long numeric strings
  beginning with `0` or `+` can be false positives. Existing account
  `email`/`full_name` fields are unchanged. CV parsing and Step 14 API
  integration remain pending.

## Step 13.2 CV Text Extraction Record

* Added `backend/app/services/cv_text_extraction_service.py`. Its reusable
  `CVTextExtractor.extract(file_bytes, filename)` interface validates extension
  and file signature/container, then returns extracted text and safe metadata
  (format, byte size, page count when applicable, and character count). It
  operates in memory only; no upload file or extracted text is persisted,
  logged, or sent to an LLM.
* Supports selectable-text PDF, DOCX text in body paragraphs/tables and
  headers/footers, and TXT decoded as UTF-8 (including BOM) or BOM-marked
  UTF-16. PDFs without meaningful selectable text produce an actionable
  scanned/image-only unsupported error; OCR is not implemented. Password-
  protected PDFs and macro-enabled Word files are rejected.
* Default limits are 10 MiB per input, 20 PDF pages, and 50 MiB expanded DOCX
  contents. File size, PDF page count, and DOCX expanded-content limits can be
  configured in `CVTextExtractor`. Safe errors do not include document content
  or the supplied filename.
* `backend/requirements.txt` now declares `PyMuPDF>=1.24,<2` and
  `python-docx>=1.1,<2`. PyMuPDF 1.26.7 and python-docx 1.2.0 were already
  installed in the environment, so no package installation was performed.
  TXT decoding and DOCX container checks also use the Python standard library.
* Added synthetic tests in `backend/tests/test_cv_text_extraction_service.py`.
  Tests run:
  * `python -m pytest tests\test_cv_text_extraction_service.py tests\test_pii_redaction_service.py tests\test_profile_privacy_boundary.py tests\test_career_workflow_unit.py -q`
    — 54 passed; 23 LangGraph `config_type` deprecation warnings.
  * `python -m py_compile app\services\cv_text_extraction_service.py tests\test_cv_text_extraction_service.py`
    — passed.
  * `python tests\test_profile_agent_smoke.py` — passed; the existing smoke
    script created test users 73 and 74 and reports that they remain in the
    local database.
* Extraction returns raw document text as required, but keeps it only in its
  return value. The future caller must invoke the existing `redact_pii()` on
  that text before passing it to `ProfileAgent` or `CareerWorkflow`. That
  upload-to-workflow connection is intentionally not implemented in this
  step. Redaction remains best-effort; text embedded in images, unusual
  encodings, PDF structures unsupported by PyMuPDF, and malicious resource-
  intensive documents remain limitations. OCR and Step 14 API integration
  are pending.

## Step 14 FastAPI Integration Record
* Added `app/main.py`, `app/api/{errors,uploads,responses,dependencies}.py`, `app/api/routes/{health,analysis}.py`, `app/core/config.py`, `app/schemas/api.py`, `tests/test_api_analysis.py`. `requirements.txt` += fastapi, python-multipart, uvicorn, httpx.
* Endpoints: `GET /health`; `POST /analysis/cv` (multipart `user_id`, `file`, optional `target_career_id`); `POST /analysis/profile` (JSON). Order for CV: bounded read → `CVTextExtractor` → `redact_pii` → `CareerWorkflow` (Profile Agent receives only redacted text).
* Verification failure is HTTP 200 with `verified: false` and `final_status` `VERIFICATION_FAILED` or `REVISION_LIMIT_REACHED`; only `ERROR` returns HTTP 500. Responses omit `llm_error` detail and workflow exception messages.
* No schema, agent, or LLM-provider changes.
* Tests run: `python -m pytest tests\test_api_analysis.py -q` — 22 passed (23 LangGraph and 1 httpx deprecation warnings). Regression scripts for Steps 7–11 passed (Profile Agent smoke left test users 77 and 78).
* Limitations at initial API implementation: **no authentication, authorization, or ownership checks** (any caller can analyze or write to any `user_id`); no rate limiting or CORS; Starlette spools the multipart body before the size check, so a proxy-level limit is required; repeated-upload persistence had not yet been tested; synchronous, slow requests; no live Gemini integration test; three DB smoke tests not rerun; the scoring-weight filename mismatch and database credential risks were reported at that checkpoint.

## Step 14.1 Security and Configuration Hardening Record
* **DB config:** `core/db.py` kini membangun koneksi hanya dari `CAREER_DB_URL` atau `CAREER_DB_PASSWORD` (+ opsional `CAREER_DB_HOST/PORT/NAME/USER`), dengan engine lazy. Konfigurasi hilang → `DatabaseConfigurationError` (API: 503 `database_not_configured`). `scripts/import_kb.py` memakai `get_engine()`. Ditambahkan `backend/.env.example`.
* **Bobot skor:** `config/scoring_weight.yaml` diganti nama menjadi `scoring_weights.yaml` agar dimuat `load_scoring_weights()`. `PyYAML` dideklarasikan.
* **Batas request:** `app/api/boundary.py` (ASGI murni) menghitung byte body aktual; `/analysis/cv` dibatasi file limit + overhead, JSON dibatasi kecil. `Content-Length` bukan sumber kepercayaan.
* **Idempotensi profil:** penulisan pendidikan, pengalaman, proyek, sertifikasi, dan evidence berupa insert-if-absent pada kunci alami ternormalisasi, diserialisasi per user dengan advisory lock. Tanpa perubahan skema; best-effort.
* **Akses:** `/analysis/*` fail-closed kecuali `CAREER_API_ACKNOWLEDGE_NO_AUTH=true`, dan hanya untuk klien loopback kecuali `CAREER_API_ALLOW_REMOTE_CLIENTS=true`. **Ini bukan autentikasi.**
* **Status HTTP:** verifikasi FAIL/REVISE tetap HTTP 200 dengan `verified:false`; input salah 4xx; kegagalan internal 5xx (dikunci oleh tes).
* **Tes (dijalankan lokal oleh peneliti):**
* `test_db_config`, `test_scoring_weights_config`, `test_api_boundary`, `test_api_analysis`, `test_profile_idempotency` → **72 passed**.
  * Regresi: CV extraction, PII, privacy boundary, workflow, verification → **65 passed**.
  * Regresi skrip: career fit, skill gap (unit, smoke, agent), roadmap, user service smoke, profile agent smoke → lulus.
* **Risiko terbuka:** tanpa autentikasi/otorisasi/kepemilikan (IDOR), tanpa rate limiting; Starlette tetap men-spool body di bawah batas; idempotensi tidak menjamin unik (dua stint dengan perusahaan+jabatan sama bergabung; deskripsi evidence berbeda antar-eksekusi LLM bisa menambah baris); upsert `create_user_skill` bisa menimpa `proficiency`/`skill_id` saat upload ulang; `ProfileAgentResult.evidence_persisted` kini berarti "diproses"; loader bobot masih jatuh diam-diam ke default jika YAML rusak; `import_kb.py` tidak idempoten; manifest dependensi belum lengkap.


## Step 14.2 Runtime Integration Test Record

* Added `backend/tests/test_api_runtime_integration.py`. The suite is explicitly
  enabled with `CAREER_RUN_RUNTIME_DB_TESTS=1`, refuses non-loopback database
  hosts and requires the local `career_intelligence` database with all 10
  canonical careers. No separate test database or shared transaction fixture
  exists; each test creates a uniquely named synthetic user and deletes only
  that exact user ID. Existing foreign keys cascade its dependent rows.
* Using the actual FastAPI app/TestClient, real workflow/agents/services, local
  PostgreSQL and the local Knowledge Base, it exercises successful
  `/analysis/profile` and `/analysis/cv` requests; persisted-claim PII
  redaction; fake-LLM prompt privacy; malformed/oversized upload rejection;
  `/health`; missing user/career handling on both analysis routes; verification
  failure and revision exhaustion; and repeated CV requests. Repeat submission
  retained one row per expected category and preserved existing
  education/experience/project fields when fake extraction returned changed
  descriptions.
* Database configuration and connectivity failures are tested with injected
  exceptions rather than by taking the local database offline. These cases
  verify sanitized HTTP errors and logs. CV text, persisted claims, API
  responses, fake LLM prompts, and captured logs use only synthetic test
  values; no live LLM calls occur.
* Tests run from `backend`:
  * `$env:CAREER_RUN_RUNTIME_DB_TESTS='1'; python -m pytest tests\test_api_runtime_integration.py tests\test_profile_idempotency.py -q`
    — **18 passed, 10 warnings** (one Starlette/httpx deprecation and nine
    LangGraph `config_type` deprecations). The integration routes and
    idempotency checks exercised local PostgreSQL; the database-failure cases
    used mocks.
  * `$env:CAREER_RUN_RUNTIME_DB_TESTS='1'; python -m pytest tests\test_api_runtime_integration.py tests\test_api_analysis.py tests\test_profile_idempotency.py tests\test_skill_gap_privacy.py tests\test_career_workflow_unit.py tests\test_profile_privacy_boundary.py tests\test_verification_agent_unit.py -q`
    — **86 passed, 64 warnings** (one Starlette/httpx deprecation and 63
    LangGraph `config_type` deprecations).
  * `python -m py_compile tests\test_api_runtime_integration.py` — passed.
  * `git diff --check` — passed.
* Post-test cleanup check queried counts only: **zero** users in the synthetic
  integration namespace and **zero** related profile rows remained. The local
  database and KB connection were available; no credentials or connection
  details were printed.
* Scope limitation: TestClient exercised the ASGI application in-process, not a
  separately running Uvicorn server. Live Gemini/provider behavior was not
  tested. Repeat-upload tests verified unchanged education, experience, and
  project fields; `create_user_skill` still updates proficiency/normalization
  fields for a duplicate claim if later extraction returns different values,
  so that remains a profile-update risk.

## Step 14.3 Existing-Profile Privacy Hardening Record

* Added `backend/app/services/profile_privacy_service.py` to create
  privacy-safe copies of user-derived skill-gap claims, proficiency strings,
  narratives, recommendation reasoning, roadmap summaries, and verification
  findings. Canonical occupational fields, IDs, categories, evidence metadata,
  scores, and the source Step 9 result are preserved.
* Files changed: `backend/app/services/profile_privacy_service.py`,
  `backend/app/agents/skill_gap_agent.py`,
  `backend/app/agents/verification_agent.py`,
  `backend/app/workflows/career_workflow.py`, `backend/app/api/responses.py`,
  `backend/tests/test_skill_gap_privacy.py`,
  `backend/tests/test_api_analysis.py`,
  `backend/tests/test_verification_agent_unit.py`, and this state record.
* `SkillGapAgent` now redacts persisted claim/proficiency text before prompt
  construction and redacts narrative/error text before returning it. Its
  embedded `SkillGapResult` remains the original unchanged Step 9 object.
* `CareerWorkflow` passes sanitized copies to the Verification Agent.
  Verification compares user-claim text only after applying the same PII
  redactor to the expected deterministic result; deterministic IDs,
  classifications, evidence fields, and scores are still compared. The
  semantic-review prompt also sanitizes narrative text if the Verification
  Agent is called directly.
* API response construction sanitizes user-derived claim/proficiency fields and
  narrative/error text without mutating workflow outputs. No database schema,
  provider, API contract, or Step 9 calculation was changed.
* Synthetic regression coverage verifies Skill-Gap and semantic-verification
  LLM prompts, verifier inputs, API responses, captured logs, and preservation
  of Step 9 classifications/source data.
* Tests run:
  * `python -m pytest tests\test_skill_gap_privacy.py tests\test_api_analysis.py tests\test_career_workflow_unit.py tests\test_profile_privacy_boundary.py tests\test_verification_agent_unit.py -q`
    — **68 passed**, 55 existing framework deprecation warnings.
  * `python -m py_compile app\services\profile_privacy_service.py app\agents\skill_gap_agent.py app\agents\verification_agent.py app\workflows\career_workflow.py app\api\responses.py tests\test_skill_gap_privacy.py tests\test_api_analysis.py tests\test_verification_agent_unit.py`
    — passed.
  * `python tests\test_skill_gap_agent_unit.py` — passed.
* No live/paid LLM calls or real personal data were used. The redactor remains
  best-effort and can miss PII outside its supported patterns. Raw persisted
  profile values and the authoritative Step 9 object remain unchanged in
  storage/workflow state; other unreviewed consumers of that data must apply
  the same privacy boundary.

## Step 14.4 Insert-Only Skill Ingestion

* `user_repository.create_user_skill()` now uses `ON CONFLICT
  (user_id, claimed_skill) DO NOTHING`, then fetches and returns the existing
  row when a claim is already present. Repeated ingestion preserves the
  original row ID, `skill_id`, `normalized_skill`, and `proficiency`, including
  when a later extraction proposes different values or `NULL`. New claims are
  inserted normally. The service/agent return contract and database schema are
  unchanged.
* Added synthetic database regressions for identical claims, changed
  proficiency, changed canonical mapping/normalized value, incoming NULLs, and
  insertion of new claims. Strengthened the runtime CV repeat-submission test
  to assert that changed extracted proficiency does not overwrite the stored
  value.
* Files changed: `backend/app/repositories/user_repository.py`,
  `backend/tests/test_profile_idempotency.py`,
  `backend/tests/test_api_runtime_integration.py`, and this state record.
* Tests run from `backend` with the opt-in loopback PostgreSQL integration
  suite and local Knowledge Base:
  * `$env:CAREER_RUN_RUNTIME_DB_TESTS='1'; python -m pytest tests\test_profile_idempotency.py tests\test_api_runtime_integration.py -q`
    — **23 passed, 10 warnings** (one Starlette/httpx deprecation and nine
    LangGraph `config_type` deprecations).
  * `$env:CAREER_RUN_RUNTIME_DB_TESTS='1'; python -m pytest tests\test_api_runtime_integration.py tests\test_api_analysis.py tests\test_profile_idempotency.py tests\test_skill_gap_privacy.py tests\test_career_workflow_unit.py tests\test_profile_privacy_boundary.py tests\test_verification_agent_unit.py -q`
    — **91 passed, 64 warnings** (one Starlette/httpx deprecation and 63
    LangGraph `config_type` deprecations).
  * `python -m tests.test_career_fit_service_unit` — passed.
  * `python -m tests.test_skill_gap_service_unit` — passed.
  * `python -m tests.test_skill_gap_agent_unit` — passed.
* Database-backed tests used uniquely created synthetic users with cleanup of
  only those exact IDs; no schema or existing user data was changed. No live or
  paid LLM calls were made.
* Explicit user-directed skill editing remains future work. Until such a path
  is implemented, re-ingesting a claim is insert-only and cannot update the
  stored proficiency or canonical mapping. Canonicalization differences in
  `claimed_skill` text can still produce distinct claims because the existing
  unique key is intentionally unchanged.

## Step 15 Frontend Record

* Implemented a React 18 / Vite / TypeScript frontend under `frontend/` on top
  of the existing FastAPI API. Files: `src/App.tsx`, `src/pages.tsx`,
  `src/components.tsx`, `src/services/api.ts`, `src/types/api.ts`,
  `src/main.tsx`, `src/styles.css`, plus `src/services/api.test.ts` and
  `src/components.test.tsx`.
* Eight views: Home, User Profile, Skills & Evidence, Career Recommendations,
  Skill Gap, Learning Roadmap, Evidence / Sources, and Analysis Details. Home
  supports a backend health check, user creation/selection, stored-profile
  analysis, an optional canonical target career ID, and CV upload
  (PDF/DOCX/TXT). Analysis results are held in browser memory only; no
  frontend persistence was added.
* The API client uses the `/api` prefix; the Vite dev proxy rewrites it to
  `http://127.0.0.1:8000`, preserving the backend loopback boundary. Network
  failures and HTTP error bodies are exposed as distinct `ApiRequestError`
  kinds; quota and invalid-model errors are mapped to readable messages while
  raw stage identifiers are not shown to the user.
* The UI renders fields returned by the API. It explicitly marks unavailable
  data (stored profile details, evidence descriptions/URLs, provenance
  records, analysis ID/history/timestamps/model version) instead of inventing
  values. It displays deterministic recommendations, all four skill-gap
  categories, roadmap items, verification checks, and scoring weights.
* Tests run from `frontend` on 2026-10-26:
  * `npm run typecheck` — passed.
  * `npm test` — **2 files, 10 tests passed** (`api.test.ts` 8,
    `components.test.tsx` 2).
* Current coverage is API-contract and component-rendering only. No browser or
  end-to-end test ran against a live backend, no live LLM was used, and
  `npm run build` was not re-run during this reconciliation. The historical
  2026-10-18 record (1 file, 7 tests, build passed) predates the current
  2-file suite.
* Commits: `32f82da` (initial frontend) and `3d563c6` (Step 15 implementation).

## Step 16 Inspection and Career-Fit Verification Record

Status: **COMPLETE** (2026-10-27). The guarded isolated-database run produced
`619d709...` after the X2 fix; all 11 cross-stage checks (including X2) and
H1–H9 pass, the artifact contract reports zero violations, and the work is
committed.

### One artifact path and runtime metadata

* Connected the synthetic manual-validation runner to the existing `Recorder`,
  actual agent proxies, LangGraph node-update observer, and `build_artifact()`
  path. It now persists one inspection schema rather than the runner's prior
  competing trace schema. The original Step 16 implementation did not execute
  the runner; a later manual run produced the artifact described below.
* Artifacts record actual runtime client/model identity, installed SDK package
  version, per-call prompt identifiers and hashes, per-call token limits, Git
  revision, effective workflow revision cap/count, node and agent execution
  order, verification checks, revision targets and safe changed output fields,
  scoring weights, and final status. KB version is explicitly unavailable
  because no KB version is exposed. FakeLLM runs are labeled as test doubles;
  Gemini temperature and other unpinned settings are identified as SDK defaults
  with effective values unavailable.
* Trace privacy was tightened: exception messages, prompt/response text,
  extracted profile strings, user claims, narratives, and verifier free text
  are not serialized. Text-derived values use hashes/lengths; DB writes record
  field names/types only; workflow errors retain only safe stage/type and
  numeric or allowlisted status metadata. Agent start/duration is recorded;
  graph-only node start times are unavailable because LangGraph's observer
  exposes completed updates.
* Added an independent two-candidate career-fit numerical test. The current
  formula uses per-requirement weight `base_class_weight × KB_confidence` and
  contribution based on linked/claim-only/missing status, with a capped
  modifier for any reported proficiency; the score is clamped weighted
  contribution divided by total requirement weight, or zero for an empty
  denominator. Recommendations and Step 9 expose the score rounded to four
  decimals. Step 9 keeps no priority/rank/severity logic; its fit score still
  uses the shared Step 8 calculator. In the synthetic fixture, independent
  scores are `CAREER_A=1.7/2.625=0.647619...` (reported `0.6476`) and
  `CAREER_B=1.2/1.7=0.705882...` (reported `0.7059`); observed differences are
  bounded by `0.00005`, the four-decimal rounding tolerance. Additional edge
  tests cover linked/claimed-only proficiency, non-informative proficiency,
  case-insensitive CORE labels, duplicate requirements, unknown evidence
  status, and non-default weights.
* Committed inspection/Step 16-related files (some landed in `3d563c6`, others
  in `e9f09ee`): `backend/app/inspection/recorder.py`,
  `backend/app/inspection/artifact.py`, `backend/scripts/manual_validation.py`,
  `backend/tests/test_inspection_core.py`,
  `backend/tests/test_inspection_serialization.py`,
  `backend/tests/test_inspection_integration.py`,
  `backend/tests/test_manual_validation_workflow.py`,
  `backend/tests/test_career_fit_independent_verification.py`,
  `backend/tests/test_career_fit_edge_cases.py`, and this state record.
  Follow-up files are listed under X2 hardening below.

### X2 profile-view hardening (committed in ebf83fd)

* X2 previously compared every `get_user_full_profile` read. A read taken
  before the Profile Agent persisted the CV (for example the API's
  pre-workflow user check) could observe an empty profile and produce a false
  FAIL.
* `c_profile_views()` now derives a persistence cutoff from the latest Profile
  Agent run's own DB writes (or that run's sequence if it wrote nothing),
  excludes reads at or before the cutoff, and reports them under
  `compared.ignored_pre_persistence_reads`.
* X2 now requires at least two distinct workflow agents among the comparable
  reads. Repeated reads by the same agent do not satisfy the threshold; the
  post-run DB snapshot is a reference only and never counts as an agent read.
  Insufficient evidence returns `UNAVAILABLE`, not PASS or FAIL.
* Changed files in the working tree: `backend/app/inspection/artifact.py`,
  `backend/tests/test_inspection_profile_views.py` (new), and
  `backend/tests/test_inspection_integration.py` (real-Recorder precheck
  regression). The workflow's actual profile reads are in
  `career_recommendation_agent.py`, `skill_gap_service.py`, and
  `verification_agent.py`; the API pre-check is recorded under `workflow`.
* The existing-profile path (no Profile Agent run) keeps all reads comparable,
  but the `workflow` stage still does not count toward the two-agent threshold.

### Artifact evidence inspected (metadata only)

* Five files exist under `backend/artifacts/manual_validation/`. Four legacy
  311102-byte artifacts (2026-10-20/22) use the pre-0.3/legacy trace layout,
  record `database_name: career_intelligence`, and report all 11 cross-stage
  checks PASS with `VERIFIED`. They predate the coherent
  `manual_validation/0.3` schema and are not evidence for the current path.
* `facb7088776846358de47142954f589a.json` (266543 bytes,
  `schema_version: manual_validation/0.3`, started 2026-10-25T11:03:38Z, Git
  `e9f09ee`, FakeLLM test double, `google-genai` 2.31.0, 14 calls, 0 failures)
  is the latest artifact. The workflow final status was `VERIFIED`, but the
  harness cross-stage summary was **10 PASS / 1 FAIL**: X2 failed with
  "profile signature differs between reads"; reads were recorded for
  `workflow` 1, `career_recommendation` 1, `skill_gap` 1, `verification` 1,
  and `post_run` 1. This is the failure pattern the X2 cutoff fix addresses.
* The latest artifact predates the X2 fix and the runner safety guard. It does
  not record the database name; the runner at its recorded commit `e9f09ee`
  required `current_database() == "career_intelligence"`, so it did not
  exercise the current `career_intelligence_e2e_test` guard.
* Re-validated on 2026-10-27 with `scripts/check_artifact.py`: the latest
  artifact now returns **6 violations**, because the contract has since added
  the isolated-database and provenance fields. They are the three missing
  `run_metadata` fields (`database`, `git_dirty`, `git_diff_sha256`), the
  matching type checks (`database` must be an object; `git_dirty` must be
  boolean/`unavailable`), and "a cross-stage check reported FAIL" (X2). The
  artifact therefore fails the current contract for evidence-format reasons as
  well as for the X2 result; it is not a post-fix artifact.
* No artifact has been generated after the X2 fix, and no artifact records use
  of the guarded isolated database. The artifact was not regenerated during
  this reconciliation.

### Preflight audit for the isolated run (2026-10-26)

Static audit only: the runner was not executed, no database was contacted, and
no tests were re-run for this audit.

* The guard and the workflow services share the single cached engine from
  `app.core.db.get_engine()` (the `_LazyEngine` proxy), and no other
  `create_engine` call exists. The database checked by
  `_validate_isolated_db_safety()` is therefore the database the workflow uses.
* Guard order is fail-closed before mutation: explicit opt-in, `engine.url.host`,
  `engine.url.database`, then `SELECT current_database()`. The name check runs
  before the guard opens a connection, and every check runs before the
  synthetic user is created.
* `backend/.env` currently names the production database
  (`CAREER_DB_NAME=career_intelligence`) while the e2e opt-in is already set. A
  bare invocation therefore stops at the `engine.url.database` check without
  connecting to or modifying either database. The run must explicitly override
  `CAREER_DB_NAME` and must not set `CAREER_DB_URL`.
* The guard does not check the port. Both local databases are reached at
  `localhost:5433`, so the database-name check, not the port, is the
  distinguishing safety boundary. The effective port is now recorded but not
  used as a guard.
* Isolated-database readiness (schema plus exactly ten careers) cannot be
  verified offline. The runner checks `career_count == 10` before any mutation,
  so an unprepared database fails safely instead of producing evidence.

### Preflight fixes implemented (2026-10-26)

* **Database identity in the artifact.** `_validate_isolated_db_safety()` now
  returns, and the runner records, `name`, `host`, `port`, and the
  server-confirmed `server_current_database` under `run_metadata.database`.
  No user name, password, or connection URL is stored. `validate_artifact()`
  requires the exact e2e name, a loopback host, a valid port, matching
  URL/server-confirmed names, and rejects credential-like extra fields.
* **Truthful provenance.** `_git_provenance()` records the base `git_commit`,
  `git_dirty`, and `git_diff_sha256` (SHA-256 over the binary diff against HEAD
  plus each untracked, non-ignored file's path and content digest). The
  contract requires a 64-char digest when the tree is dirty and forbids one
  when clean. Only digests are stored, never file contents or paths.
* **Contract in the verdict.** The runner calls
  `app.inspection.contract.validate_artifact()` through `_final_verdict()`;
  contract violations, cross-stage FAIL/ERROR, failed independent checks, or a
  harness error now all force a nonzero exit. Violation messages contain paths
  and rules only.
* **Full synthetic-user cleanup.** `_cleanup_synthetic_user()` deletes
  `user_skill_evidence` first, then `user_skills`, `user_preferences`,
  `user_education`, `user_experience`, `user_projects`,
  `user_certifications`, `user_profiles`, and finally `users`, all by the
  exact user id and in one transaction. It then re-counts every table and
  fails H9 unless all remainders are zero; per-table deleted/remaining counts
  are recorded in H9. Cleanup no longer depends on undocumented cascade
  behaviour. The actual e2e schema and cascade have not been exercised.
* The fail-closed guard is unchanged in order and remains the only database
  gate. No production database was contacted and no runner or DB-backed test
  was executed.
* Older `manual_validation/0.3` artifacts lack `database`, `git_dirty`, and
  `git_diff_sha256`; `validate_artifact()` now rejects them. The schema version
  was not bumped because the fields are additive and no post-fix artifact
  exists yet.
* Offline focused suite: **126 passed, 1 warning** (10 files; command under
  Tests and checks). `py_compile` passed; `git diff --check` passed except the
  pre-existing LF/CRLF notice for `scripts/import_kb.py`.
* At the time of this audit: no post-fix artifact from the guarded isolated
  database existed; cleanup SQL and table names were validated only with mocks;
  isolated-DB readiness and actual FK behaviour were unverified; and the
  changes were uncommitted, so a run would have recorded a dirty digest. These
  were resolved on 2026-10-27 (see the final acceptance audit).
* Step 16 remained PARTIAL at the time of this audit.

### Final readiness audit (2026-10-26)

Static/offline audit only: the runner was not executed, no database was
contacted, and no DB-backed test, KB import, or live LLM/API call was made.

* **Schema/FK coverage is not verifiable offline.** The repository tracks no
  DDL, migrations, ORM models, or `CREATE TABLE` statements. `user_repository.py`
  is the only user-domain write path: it writes `users`, `user_profiles`,
  `user_education`, `user_experience`, `user_projects`,
  `user_certifications`, `user_skills`, and `user_skill_evidence`;
  `user_preferences` is read-only. `_cleanup_synthetic_user()` covers all nine
  user tables and deletes evidence before skills before the user row. The
  analysis tables named in MASTER_SPEC are not written anywhere in
  `backend/app`. The real FK graph, cascade rules, triggers, and any additional
  table referencing `users` remain **unverified** until the read-only
  `information_schema` inventory is approved and run.
* **X2 scope and completion gate.** `c_profile_views()` compares only the
  skill-level signature (skill id, evidence status, proficiency, evidence
  count), not education/experience/projects/certifications. The artifact
  contract and `_final_verdict()` treat `UNAVAILABLE` as non-failing, so
  Step 16 completion must require X2 = `PASS`, not merely the absence of FAIL.
* **Provenance gate.** A dirty tree with a valid reproducible digest satisfies
  the artifact contract, but Step 16 evidence should come from a committed
  Step 16 tree with `git_dirty = false` so `git_commit` identifies exactly what
  produced the artifact.
* Re-ran the 10-file offline suite during this audit: **126 passed, 1 warning**.
* Step 16 remained PARTIAL at the time of that audit; it was closed on
  2026-10-27 (see the final acceptance audit below).

### Tests and checks

* Preflight-fix re-run on 2026-10-26 from `backend` (offline files only; no
  database, runner, KB import, or live model):
  * `.\.venv\Scripts\python.exe -m pytest tests\test_manual_validation_gate.py tests\test_artifact_contract.py tests\test_inspection_integration.py tests\test_inspection_core.py tests\test_inspection_profile_views.py tests\test_inspection_serialization.py tests\test_manual_validation_workflow.py tests\test_career_fit_independent_verification.py tests\test_career_fit_edge_cases.py tests\test_career_workflow_unit.py -q -p no:cacheprovider`
    — **126 passed, 1 warning** (LangChain pending-deprecation).
  * `.\.venv\Scripts\python.exe -m py_compile app\inspection\artifact.py app\inspection\contract.py scripts\manual_validation.py tests\test_manual_validation_gate.py tests\test_artifact_contract.py tests\test_inspection_integration.py`
    — passed.
  * `git diff --check` — passed (pre-existing LF/CRLF notice for
    `backend/scripts/import_kb.py`).
* Prior reconciliation run on 2026-10-26: the same 10 files gave **117 passed,
  1 warning** before the preflight fixes and tests were added.
* `upload/cv2.pdf` exists at the repository root (217740 bytes) but was not
  read, parsed, or used; the executed tests use synthetic fixtures.
* Previously recorded but **not re-executed during this reconciliation**:
  focused inspection/workflow/scoring tests (51 passed), broader offline
  regressions (187 passed, 10 deselected, 1 warning), and the career-fit,
  skill-gap, and skill-gap-agent unit scripts. Treat those as prior evidence.
* The in-memory integration/contract tests exercise real agents, the real
  workflow, the real recorder/artifact builder, and a scripted LLM, but replace
  PostgreSQL and the KB with in-memory stand-ins. They do not establish a real
  database run or live-model behavior.

### Final acceptance audit (2026-10-27)

Read-only audit of the guarded run's artifact. No database connection, SQL,
KB import, live LLM call, or rerun was made; the artifact was validated with
`scripts/check_artifact.py`.

* Latest artifact: `backend/artifacts/manual_validation/619d7091a5674dbe92311630a93dc112.json`
  (267630 bytes, SHA-256 `F25992...F5B0`), schema `manual_validation/0.3`,
  started 2026-10-27T05:04:02Z, duration 3634.7 ms, FakeLLM test double,
  14 calls / 0 failures.
* Contract: `check_artifact.py` → **`CONTRACT OK`**, exit 0, zero violations.
* Cross-stage: **11/11 PASS**, including **X2 PASS** with
  `persistence_cutoff_seq = 11`, `ignored_pre_persistence_reads =
  [{seq: 1, stage: "workflow"}]`, and compared reads for
  career_recommendation, skill_gap, verification, and post_run.
* Independent: **H1–H9 PASS**. H9 records deleted rows (evidence 1, skills 3,
  education 1, projects 1, users 1; others 0) and **remaining = 0 in all nine
  user tables**.
* Workflow: `final_status = VERIFIED`, `verified = true`, revision_count 0,
  `errors = []`, `instrumentation_warnings = []`, `harness_error = []`.
* Isolated DB: `{name: career_intelligence_e2e_test, host: localhost,
  port: 5433, server_current_database: career_intelligence_e2e_test}`.
* KB: before = after = 10 careers / 87 skills / 155 career_skills /
  8 occupations; `kb_unchanged = true`. `kb_version` is still explicitly
  unavailable.
* Provenance: `git_commit = 1921d30` (still HEAD), `git_dirty = true`,
  `git_diff_sha256 = df01dc...`. The run began at 13:04 +08:00; `1921d30` was
  created at 13:02:51 and `ebf83fd` (all Step 16 code) at 12:53:15.
  `git diff ebf83fd..HEAD -- backend` is empty and no Step 16 file has a
  post-run modification time, so the code under test is the committed HEAD.
  The dirty overlay was non-code files (`.gitignore` ignore-rule edit at 12:51
  plus task-note markdowns). The recorded digest cannot be recomputed today
  because `opencode_instruction.md` was edited at 13:10, after the run.
* The artifact does not persist the runner's literal exit code. Recomputing
  `_final_verdict()` from its inputs (empty harness error, H1–H9 PASS, no
  cross-stage FAIL/ERROR, zero contract violations) yields PASS.
* No static FK/DDL inventory exists in the repository. H9 proves runtime
  cleanup for the nine tables the user domain writes; tables never written are
  not exercised.

### Remaining limitations and decision

* The isolated-DB guard, DB identity recording, child-row cleanup, and
  contract are now proven against `career_intelligence_e2e_test` for the
  synthetic path, not only by mocks.
* The artifact's provenance is dirty (`git_dirty = true`) even though the code
  under test is committed at the recorded HEAD; see the final acceptance audit
  for the non-code overlay and the non-reproducible digest.
* The schema/FK graph and triggers are still not inventoried from files or a DB
  query. H9 proves zero remaining rows in the nine written user tables; it does
  not prove the absence of unrelated tables that reference `users` but were
  never written.
* No live LLM/provider call was made. FakeLLM establishes path and privacy
  behavior only; provider/model settings, SDK defaults, retry behavior, and
  real-model quality remain unverified. KB version is explicitly unavailable.
* **Decision: Step 16 is COMPLETE.** The formal criteria — post-fix artifact
  from the guarded isolated-DB path, 11/11 cross-stage PASS including X2,
  H1–H9 PASS, zero contract violations, and committed changes — are met. A
  literally clean-tree artifact would require one guarded rerun from clean
  HEAD; it is optional and not needed for functional or contract acceptance.

Do not mark pending work complete without inspecting the code and running the relevant tests.

## Step 16 MASTER_SPEC §19 Analysis Logging Record (2026-10-29)

### Existing implementation and gap found

The existing Step 16 inspection harness (`app/inspection/recorder.py` and
`scripts/manual_validation.py`) writes a manual-validation artifact, but it is
explicitly not used by normal API runs. Neither `/analysis/cv` nor
`/analysis/profile` wrote a `MASTER_SPEC` §19 record. No analysis-log table or
migration infrastructure exists, so this stage uses privacy-safe file
persistence instead of an unapproved schema change.

### Implemented behavior

* Both normal analysis endpoints write exactly one JSON record after the
  workflow returns, including workflow `ERROR` outcomes. Requests rejected
  before the workflow (validation, 404, unsupported/oversized upload, LLM
  unavailable) do not create an analysis log.
* Each record contains every §19 field: `analysis_id`, `timestamp`,
  `user_profile_id`, `model`, `model_version`, `prompt_version_identifier`,
  `kb_version`, `agents_executed`, `agent_outputs`, `verification_result`,
  `revision_count`, and `final_result`.
* `agents_executed` comes from the workflow node observer and counts revision
  attempts. The existing-profile path reuses persisted data, so the Profile
  Agent is correctly recorded as not executed there.
* `agent_outputs` stores the sanitized final structured outputs. The Profile
  Agent output is reduced to persistence counts and claim hashes; extracted
  profile fields and raw CV text are never stored.
* `workflow_trace.nodes` records the observed node order (including revision
  loops), so the trace, revision count, verification status, and final status
  can be cross-checked.
* `model_version` and `kb_version` are explicitly recorded as unavailable rather
  than invented. Prompt identifiers are SHA-256 hashes of the existing system
  prompt constants for the agents that executed.
* Records default to `backend/artifacts/analysis_logs/<analysis_id>.json`
  (`backend/artifacts` is already git-ignored) and can be redirected with
  `CAREER_ANALYSIS_LOG_DIR`. Writes are atomic.
* All strings pass the existing best-effort PII/secret redactor and length cap;
  workflow exception messages are omitted entirely. A logging failure is
  reported as a type-only warning and cannot change the analysis response.

### Files created or modified

* Created `backend/app/services/analysis_log_service.py`.
* Modified `backend/app/api/routes/analysis.py`.
* Modified `backend/tests/test_api_analysis.py` and
  `backend/tests/test_api_runtime_integration.py` to isolate logs in `tmp_path`.
* Created `backend/tests/test_analysis_logging.py`.
* Modified `backend/.env.example` to document `CAREER_ANALYSIS_LOG_DIR`.
* No database, schema, migration, Knowledge Base, or API response-contract
  changes were made.

### Tests executed (actual results)

* From `backend`:
  `.\.venv\Scripts\python.exe -m pytest tests\test_analysis_logging.py -q`
  → **7 passed, 1 warning**.
* Focused regressions:
  `.\.venv\Scripts\python.exe -m pytest tests\test_api_analysis.py tests\test_career_workflow_unit.py tests\test_artifact_contract.py tests\test_inspection_core.py tests\test_inspection_integration.py tests\test_inspection_profile_views.py tests\test_inspection_serialization.py tests\test_manual_validation_workflow.py tests\test_api_boundary.py -q`
  → **151 passed, 1 warning**.
* Full offline suite:
  `.\.venv\Scripts\python.exe -m pytest -q`
  → **279 passed, 9 skipped, 1 failed, 1 warning**. The single failure is
  `tests/test_api_users.py::test_creates_user_and_returns_only_user_id`, caused
  by pre-existing uncommitted work in `backend/app/api/routes/users.py` that now
  reads `user.email`/`user.full_name` while that test still mocks only
  `user_id`. This task did not modify that route or test.
* The default `backend/artifacts/analysis_logs` directory was not created by
  the test runs; isolation worked.
* Database-backed runtime tests were not run because
  `CAREER_RUN_RUNTIME_DB_TESTS=1` was not set. No live/paid LLM call was made.

### Remaining limitations

* `model_version` is unavailable because the active `GeminiClient` exposes only
  the model identifier. `kb_version` is unavailable because the Knowledge Base
  has no exposed version identifier.
* The file log is the current persistence layer; it does not add the
  `analysis_id`/logging tables mentioned in `MASTER_SPEC` §22/§23.
* The full-suite failure above is unrelated to this task but remains in the
  working tree until the frontend/user API work is completed.

**Status: COMPLETE for `MASTER_SPEC` §19 normal-API logging.** No further Step
16 logging work is required; Step 17 has not started.

## Update Rule

Update this file after each completed development stage. Record actual test results, changed files, unresolved issues, and the next stage. Do not rely solely on conversation history.
