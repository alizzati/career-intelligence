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

Steps 5–11 regression tests were run locally during Step 12 implementation and passed.
Step 12 deterministic checks and mocked semantic-review tests passed; a local-KB
integration smoke run returned PASS for 41 checks without a live LLM call.
Step 13's focused tests and local workflow integration run passed.

## Current Checkpoint

Step 13.2 is complete. Stop here; upload/API integration is not implemented.

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
* PII redaction is best-effort pattern matching, not a guarantee that all
  personal information is detected. CV file extraction is implemented as a
  standalone in-memory service. Its output must pass through the existing PII
  redactor before any Profile Agent/LLM call. API upload handling remains
  pending and must enforce this order.
* Orchestration revision limit is configurable; a workflow is only marked
  VERIFIED when the overall verification and every check pass without unresolved
  unsupported claims or required revisions.

## Pending Work

1. Integrate the API and complete end-to-end workflow.
2. Review logging, reproducibility, and evaluation support.
3. Implement and evaluate baseline and ablation configurations.
4. Implement or review frontend integration.

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

Do not mark pending work complete without inspecting the code and running the relevant tests.

## Update Rule

Update this file after each completed development stage. Record actual test results, changed files, unresolved issues, and the next stage. Do not rely solely on conversation history.
