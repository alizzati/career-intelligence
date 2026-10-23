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

Steps 5–11 regression tests were run locally during Step 12 implementation and passed.
Step 12 deterministic checks and mocked semantic-review tests passed; a local-KB
integration smoke run returned PASS for 41 checks without a live LLM call.
Step 13's focused tests and local workflow integration run passed.

## Current Checkpoint

Steps 14.2 and 14.3 are complete. The database-backed runtime tests use the
local `career_intelligence` database through FastAPI's TestClient and fake
LLMs; they do not establish live Gemini integration. Local Uvicorn liveness,
Vite proxy health, and synthetic API user creation were separately checked
over HTTP.

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
    7 tests passed**; `npm run build` — passed.
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

1. Finish Step 16 by running the shared manual-validation artifact path against
   an explicitly safe local test database and checking the resulting artifact;
   current status is partial (see Step 16 record below).
2. Implement and evaluate baseline and ablation configurations.
3. Review live LLM-backed analysis only when explicitly approved; current
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

## Step 16 Inspection and Career-Fit Verification Record

* Connected the synthetic manual-validation runner to the existing
  `Recorder`, actual agent proxies, LangGraph node-update observer, and
  `build_artifact()` path. It now persists one inspection schema rather than
  the runner's prior competing trace schema. The runner itself was not
  executed because it creates a database user and persists profile data.
* Artifacts record actual runtime client/model identity, installed SDK package
  version, per-call prompt identifiers and hashes, per-call token limits,
  Git revision, effective workflow revision cap/count, node and agent
  execution order, verification checks, revision targets and safe changed
  output fields, scoring weights, and final status. KB version is explicitly
  unavailable because no KB version is exposed. FakeLLM runs are labeled as
  test doubles; Gemini temperature and other unpinned settings are identified
  as SDK defaults with effective values unavailable.
* Trace privacy was tightened: exception messages, prompt/response text,
  extracted profile strings, user claims, narratives, and verifier free text
  are not serialized. Text-derived values use hashes/lengths; DB writes record
  field names/types only; workflow errors retain only safe stage/type and
  numeric or allowlisted status metadata. Agent start/duration is recorded;
  graph-only node start times are unavailable because LangGraph's observer
  exposes completed updates.
* Added an independent two-candidate career-fit numerical test. The current
  formula uses per-requirement weight `base_class_weight × KB_confidence`
  and contribution based on linked/claim-only/missing status, with a capped
  modifier for any reported proficiency; the score is clamped weighted
  contribution divided by total requirement weight, or zero for an empty
  denominator. Recommendations and Step 9 expose the score rounded to four
  decimals. Step 9 keeps no priority/rank/severity logic; its fit score still
  uses the shared Step 8 calculator. In the synthetic fixture, independent
  scores are `CAREER_A=1.7/2.625=0.647619...` (reported `0.6476`) and
  `CAREER_B=1.2/1.7=0.705882...` (reported `0.7059`); observed differences
  are bounded by `0.00005`, the four-decimal rounding tolerance.
* Changed files for this task: `backend/app/inspection/recorder.py`,
  `backend/app/inspection/artifact.py`, `backend/scripts/manual_validation.py`,
  `backend/tests/test_inspection_core.py`,
  `backend/tests/test_manual_validation_workflow.py`,
  `backend/tests/test_career_fit_independent_verification.py` (new), and this
  state record. Existing unrelated modifications and untracked files were
  preserved.
* Tests/checks run from `backend`:
  * Focused inspection/workflow/scoring tests — **51 passed, 1 warning**.
  * Broader offline backend regressions — **187 passed, 10 deselected, 1
    warning**. DB-mutating idempotency cases were deselected; no database or
    live LLM calls were made.
  * `python -m tests.test_career_fit_service_unit`,
    `python -m tests.test_skill_gap_service_unit`, and
    `python -m tests.test_skill_gap_agent_unit` — passed.
  * `python -m py_compile` on the changed Python implementation/test files —
    passed; `git diff --check` — passed.
* Environment evidence: Google Gen AI SDK version **2.31.0** is installed.
  `upload/cv2.pdf` exists and is readable, but its contents were not accessed
  or used. No manual-validation artifact was generated in this task; builder
  metadata/privacy were exercised by isolated synthetic tests. No real Gemini
  run, live DB workflow, or populated production-model artifact has been
  verified. SDK-internal retry behavior and the KB version remain unavailable.
* Decision: Step 16 is **partially complete**, not complete. The artifact
  generation and offline trace/scoring paths are tested, but a generated
  artifact from a safe local test database and its runtime provenance still
  need verification.

Do not mark pending work complete without inspecting the code and running the relevant tests.

## Update Rule

Update this file after each completed development stage. Record actual test results, changed files, unresolved issues, and the next stage. Do not rely solely on conversation history.
