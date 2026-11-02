# Diagnostic CV Testing

This document describes the repeatable diagnostic CV workflow implemented in
`backend/app/diagnostics/` and `backend/scripts/diagnostic_cv_runner.py`.

**Boundary:** the output is diagnostic evidence, not a formal experiment. It is
not B0, B2, B3, F, or any other evaluation configuration, and it must never be
reported as an experimental result.

## 1. Purpose

The runner sends real CV files through the real application and records every
stage that the pipeline already produced:

1. document text extraction and PII redaction,
2. Profile Agent extraction and skill normalisation,
3. Occupational Knowledge Base retrieval,
4. Career Recommendation Agent and `compute_career_fit()` output,
5. the deterministic Skill-Gap Engine / Skill-Gap Agent result,
6. Learning Roadmap Agent,
7. Verification Agent, revision count, and final status.

It does not change any of those stages. It only observes them, then writes one
JSON trace per CV, a flat CSV row per CV, and a run manifest.

## 2. What is real and what is replaced

Real:

* `POST /analysis/cv` via a FastAPI `TestClient` (the production route).
* The production `CareerWorkflow` graph, the five production agents, the real
  `compute_career_fit()`, the real skill-gap engine, the real knowledge-base
  retrieval services, and the real database user repository.
* The HTTP request/response schemas, upload limits, extractor, PII redaction,
  workflow revisions, and the Step 16 `analysis_log/1.0` writer.

Replaced or added:

* `get_workflow` is overridden with an **instrumented instance of the same
  `CareerWorkflow` class**. The agents are the same classes wrapped by
  `AgentProxy`; the LLM client is wrapped by `RecordingLLMClient`. Proxies
  forward original arguments and return the original objects.
* The synthetic user is created directly through the same
  `user_service.create_user()` path used by `POST /analysis/users`.
* Tests replace the LLM with a scripted client and the database/KB with in-memory
  doubles. The CLI does neither.

Nothing from this package is imported by the API, workflow, agents, or
evaluation code.

## 3. Preconditions

1. **Isolated database.** The runner reuses the manual-validation gate from
   `scripts/manual_validation.py` and refuses to run unless the effective
   database is the opt-in isolated test database. The name must match
   `CAREER_E2E_ISOLATED_DB_OK` (normally `career_intelligence_e2e_test`) and the
   host must be loopback. `CAREER_DB_URL`, if set, overrides `CAREER_DB_NAME`,
   so do not set it for a diagnostic run.
2. **Isolated database contents.** The gate verifies the database name, not that
   it has the schema or all 10 canonical careers. Check readiness separately
   before a live run; an unprepared database will still produce artifacts with
   empty or failed stages.
3. **Live LLM approval.** A real provider call is refused unless
   `--approve-live-llm` is passed. `--fake-llm` selects a labelled plumbing test
   double that proves the runner only and says nothing about model quality.
4. **Input folder.** Default
   `frontend/dignostic_testing/input_cvs/` (currently 7 PDFs). Files are opened
   read-only; the runner never moves, renames, or deletes them.
5. **Output folder.** Default `frontend/dignostic_testing/results/`. A run
   directory that already exists is never reused or overwritten.

## 4. Invocation

From `backend/`:

```powershell
# Plan only: lists CVs, resolved run id, output folder, and LLM mode. No DB, no LLM.
python -m scripts.diagnostic_cv_runner --dry-run

# Plumbing check with a fake LLM. Still uses the isolated database.
python -m scripts.diagnostic_cv_runner --fake-llm --run-id plumbing-01 --max-cvs 1

# Real diagnostic run. Requires the isolated database and explicit approval.
$env:CAREER_DB_NAME = "career_intelligence_e2e_test"
python -m scripts.diagnostic_cv_runner --approve-live-llm --run-id pilot-01
```

Useful options:

| Option | Meaning |
| --- | --- |
| `--input-dir PATH` | CV folder (default `frontend/dignostic_testing/input_cvs`). |
| `--output-dir PATH` | Parent folder for run directories. |
| `--run-id NAME` | Folder name; defaults to `<UTC timestamp>_<6 hex>`. |
| `--cv NAME` | Restrict to a file name or stem; repeatable. |
| `--target-career-id ID` | Optional canonical target career. |
| `--max-cvs N` | Process at most N CVs. |
| `--fake-llm` | Labelled plumbing double; never diagnostic validity. |
| `--approve-live-llm` | Permit real provider calls. |
| `--dry-run` | Print the plan and exit. |

Exit codes: `0` = PASS, `1` = FAIL, `2` = REFUSED by a safety gate.

`--dry-run` prints the original file names to the console only; it writes
nothing and does not persist them.

## 5. Folder structure

```text
frontend/dignostic_testing/results/
├─ .gitignore                     # "*" + "!.gitignore"; CV artifacts stay untracked
└─ <run_id>/
   ├─ run.json                    # diagnostic_manifest/1.0 (written incrementally)
   ├─ manifest.csv                # one flat row per CV (utf-8-sig)
   ├─ summary.md                  # human-readable summary and limitations
   ├─ traces/
   │  └─ <cv_id>.trace.json       # diagnostic_trace/1.0, one per CV
   ├─ analysis_logs/
   │  └─ <cv_id>.analysis_log.json# Step 16 analysis_log/1.0, renamed per CV
   └─ errors/
      └─ <cv_id>.cleanup.txt      # only if synthetic-user cleanup failed
```

`<cv_id>` has the form `cvNN_<sha256-prefix>` where `NN` is the sorted input
position and the prefix is the first 8 hex characters of the file's SHA-256.
The original file name is never used in an artifact.

The Step 16 log is produced by the unchanged `analysis_log_service`. For the
duration of the run, `CAREER_ANALYSIS_LOG_DIR` is pointed at the run's
`analysis_logs/` folder; the previous value is restored afterwards. The log is
renamed to `<cv_id>.analysis_log.json` so that the internal `analysis_id` file
name does not leak into the manifest. `analysis_id` itself is preserved inside
the log and in the trace/CSV.

## 6. Trace JSON (`diagnostic_trace/1.0`)

Top-level keys:

* `schema_version`
* `run` — run id, start time, LLM mode and label, Git commit/dirty/diff digest,
  database identity, Python/trace/manifest versions, effective configuration,
  and model metadata when available.
* `cv` — `cv_id`, SHA-256, format, size, neutral upload name, trace path. No
  original file name, no path.
* `analysis` — HTTP status, request duration, response final status,
  `analysis_id`, analysis-log path, API error metadata (code/stage/type/message),
  and a runner error with a type only.
* `stages` — exactly these keys, in this order:
  `extraction`, `profile`, `okb_retrieval`, `career_fit`, `skill_gap`,
  `roadmap`, `verification`, `final`.
  Each stage has `status` (`ok`, `failed`, `skipped`, `not_reached`),
  `started_at` (currently unavailable), `duration_ms`, `error`, `notes`, and
  `payload`.
* `llm_calls` — call count, per-prompt counts, total duration, per-call stage,
  prompt id, prompt/system-prompt hashes, character counts, max-token limit and
  its source, duration, response metadata (Python type, top-level keys, JSON
  length), and type-only error. Tokens and cost are explicitly unavailable.
* `node_events` — workflow node-update observations.
* `agent_runs` — one entry per agent attempt with duration, type-only error, and
  whether output was produced. Agent output text is not stored here.
* `warnings` — runner/recorder warnings.
* `privacy` — explicit flags (raw text/prompt/response/file name/evidence URL
  not persisted), the redaction helper, artifact location, synthetic-user
  create/delete state, cleanup counts, and database name.
* `unavailable_fields` — every field whose value could not be obtained, with the
  reason. It is never estimated.
* `consistency_note` and `consistency_observations` — read-only cross-checks
  (API response vs workflow state, every OKB career scored, skill-gap coverage,
  roadmap scope, VERIFIED vs verification status). These are **not** the Step 12
  verification result and never modify a stage.

Stage payloads, in brief:

* `extraction`: format, byte size, PDF page count, character count, PII
  replacement count and detected types. No extracted text.
* `profile`: extraction counts; per-skill claimed name, proficiency, LLM
  candidate id, normalised skill id/name/method/score; evidence with type,
  description, and `url_present`; education/experience/projects/certifications
  with sanitised text.
* `okb_retrieval`: the agents' own `get_career_skills` reads, with requirements
  (skill id, canonical name, relationship id, evidence class, confidence,
  mapping method, KB basis text).
* `career_fit`: ranked careers with the existing fit score, score breakdown,
  matched/claimed-only/missing previews, reasoning and reasoning source, plus
  every observed `compute_career_fit()` call.
* `skill_gap`: the deterministic result's career id, fit score, weights, score
  breakdown, and the four frozen categories. No priority, tier, severity, or
  target-proficiency field is added.
* `roadmap`: items (skill, gap status, evidence class, KB basis, learning
  action), covered skill ids, summary, narrative source.
* `verification`: status, checks, unsupported claims, required revision, counts,
  revision count/limit. Findings are copied, never rewritten.
* `final`: final status, verified flag, target career and its rank/score, top-1
  and top-2, revision metadata, last stage, safe errors, request duration.

## 7. CSV columns (`manifest.csv`)

The header is fixed and stable; one row per CV. Missing values are empty cells,
never guesses. Empty-string cells are how Python's `csv` round-trips `None`.

```text
run_id, cv_id, cv_sha256, file_format, file_size_bytes, pdf_page_count,
extraction_status, extraction_error_code, http_status, final_status, verified,
target_career_id, revision_count, revision_limit, profile_agent_executed,
profile_skills_persisted, profile_evidence_persisted, skills_extracted_count,
skills_normalized_count, skills_unmatched_count, recommendations_count,
top1_career_id, top1_fit_score, top2_career_id, top2_fit_score,
target_fit_score, target_rank, gap_matched_evidenced_count,
gap_matched_claimed_only_count, gap_missing_count,
gap_unmatched_user_claims_count, gap_narrative_source, roadmap_items_count,
roadmap_narrative_source, verification_status, verification_checks_total,
verification_checks_failed, verification_unsupported_claims_count,
verification_required_revision_count, analysis_id, model, model_version,
sdk_version, prompt_catalog_version, kb_version, llm_mode, total_llm_calls,
total_duration_ms, stage_errors, trace_path, analysis_log_path
```

`stage_errors` joins failed stages as `stage:code` with `;`.

## 8. Run manifest and status semantics

`run.json` contains the schema version, run id, start/finish time, status
(`RUNNING`, `PASS`, `FAIL`), LLM mode and label, database identity, effective
configuration, input label/count/selection, counts, per-CV records, privacy
flags, and the limitation list.

`input.selection_restricted` reports whether `--cv` was used, and
`input.selected_cv_ids` lists the anonymized `cvNN_<sha256-prefix>` ids of the
selected files. The raw `--cv` values are original file names and are
deliberately never written to an artifact.

* `completed` = rows whose HTTP status is `200`.
* `failed` = the remaining rows (for example a `422` unreadable document).
* `errored` = CVs that produced no HTTP response at all (a runner exception).
* `PASS` = at least one row and no `errored` CV. A rejected CV (e.g. `422`) is
  recorded as a failed CV but does not make the run itself `FAIL`.
* `FAIL` = no rows, or at least one CV had no HTTP response.

`run.json`, `manifest.csv`, and `summary.md` are rewritten after every CV, so a
partial run remains readable if the process is interrupted. An existing run
directory is refused before any work starts.

## 9. Privacy safeguards

* Inputs are hashed into `cvNN_<sha8>` identities; artifacts never contain the
  original file name, absolute path, or user name.
* The upload is sent as `<cv_id>.<ext>`; the original name is used only to read
  the file locally.
* Raw CV text, prompt text, and raw LLM responses are not persisted. Prompts and
  system prompts are represented by SHA-256 hashes and lengths.
* Evidence and project/credential URLs are represented by `url_present` only.
* Every string written to a trace passes the existing inspection sanitizer
  `clean_str` (project PII/secret redaction plus a length cap). Exception messages
  are dropped: only stage/error type and numeric/allowlisted status codes remain.
* One synthetic user is created per CV and deleted by exact id through the
  tested manual-validation cleanup. Deletion counts are recorded; a cleanup
  failure is recorded under `errors/` and does not abort the run. A process crash
  between creation and cleanup can leave one synthetic user row.
* Artifacts are written only under the configured output directory. The
  `results/.gitignore` ignores everything except itself, so CV-derived files
  cannot be committed accidentally. Do not weaken that rule.
* For the duration of the run, `CAREER_API_ACKNOWLEDGE_NO_AUTH` and
  `CAREER_API_ALLOW_REMOTE_CLIENTS` are enabled because the in-process
  `TestClient` presents a non-loopback client host. No network listener is
  opened, and the previous values are restored when the run ends.
* The runner refuses live model calls without explicit approval and refuses any
  database other than the opted-in isolated test database.

**Residual risk:** the trace deliberately keeps sanitised structured profile
content (skills, education, experience, projects, certifications, evidence
descriptions) because it is needed to diagnose extraction and normalisation.
The redactor is best-effort and cannot remove every identifying detail from
free text. Treat the whole `results/` tree as sensitive local data.

## 10. Existing capabilities, missing outputs, and limitations

Available from this workflow:

* real endpoint/workflow/agent execution with per-stage payloads,
* real `compute_career_fit()` inputs and outputs and all observed calls,
* the four frozen skill-gap categories exactly as produced,
* roadmap and verification results without rewriting,
* request-level and per-agent/per-LLM-call timings,
* the unchanged Step 16 analysis log per CV,
* Git provenance, database identity, and explicit unavailability records.

Not available, by design or by current interface:

* Token counts, cost, and provider-side usage: the LLM client exposes none.
* `model_version`: the client exposes the model identifier but no separate
  version. `kb_version`: the KB exposes no version identifier.
* Sampling parameters (`temperature`, `top_p`, `top_k`, `seed`): not passed
  through the LLM client.
* Stage `started_at`: the observer exposes completed updates; agent start times
  are not available.
* Separate extraction timing: the extractor is not instrumented. Only the total
  HTTP request duration is recorded, under `analysis.duration_ms` and
  `stages.final.duration_ms`.
* Pre-workflow failures (unreadable/oversized documents, missing user/career)
  produce no downstream stage data by construction.
* Fake-LLM mode proves plumbing only.
* The LLM client has no retry or backoff. A provider 429 becomes
  `LLMQuotaExceededError` immediately, so a CV that needs ~14 requests can
  exhaust a low per-minute quota and the following CVs fail with HTTP 503.
  Space runs out deliberately, or raise the provider quota.
* Live runs on `gemini-3.5-flash-lite` also spend one very large request per CV:
  the semantic-verification prompt was ~280k characters in the first live run.
* The runner does not verify Knowledge Base readiness or the 10-career set; check
  the isolated database separately.
* A crash during a request can leave a synthetic user behind (recorded by the
  absence of cleanup flags; it is not silently ignored).
* `analysis_logs/` keeps the Step 16 schema unchanged; the diagnostic trace is
  an independent additive document.

## 11. Tests

From `backend/`:

```powershell
python -m pytest tests/test_diagnostic_trace.py tests/test_diagnostic_runner.py -q
python -m pytest tests/test_analysis_logging.py tests/test_manual_validation_gate.py tests/test_inspection_integration.py -q
```

The runner tests use the real FastAPI app, route, workflow, agents, recorder,
trace builder, and artifact writers with an in-memory user/KB store, an injected
database seam, a scripted LLM, and `tmp_path`. They do not use PostgreSQL, the
network, or a live provider. See `docs/PROJECT_STATE.md` for the exact recorded
results of the latest run.
