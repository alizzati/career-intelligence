# Evaluation & Ablation Execution Readiness

**Status:** AUDIT COMPLETE — no changes made
**Date:** 2026-11-04
**Scope:** `data/occupational_knowledge_base_verified_v1_0.xlsx`, the legacy runtime
database schema, the evaluation package, and the B0/B2/B3/F execution path.
**Mode:** Read-only. No dataset, source, configuration, migration, database, or
commit change. Database inventory and column lists were read in read-only
transactions. No secret or `.env` value was read or printed.

---

## 0. Bottom line

The four experiment configurations are **not executable today**. Three hard
blockers remain:

1. **Dataset:** `OCCUPATION` violates its primary key (23 rows, 8 IDs), and
   `TECHNOLOGY`/`TASK` still contain O*NET/Lightcast-derived content that is
   out of thesis scope.
2. **Database:** `career_intelligence_eval` does not exist, and the only
   importer is hard-gated to `career_intelligence_e2e_test` with append-only
   behaviour.
3. **Runner:** no Step 18 runner, configuration switch, manifest, repeated-run
   schedule, or fault-injection harness exists. `CareerWorkflow` is a single
   F-like path with mandatory verification.

The metric layer is implemented and unit-tested, but every label-dependent
metric is `unavailable` until a real annotation corpus exists. No metric value
in this report is invented or estimated.

Shortest defensible path:

```text
fix workbook (D1, D5, D6, D7, source_code typing)
  -> clone legacy public schema into career_intelligence_eval
  -> extend importer gate + add Kominfo provenance branch
  -> import and verify
  -> implement Step 18 runner (B3/F first, then B0/B2)
  -> annotate a minimum S-H corpus in parallel
  -> pilot -> formal runs
```

---

## 1. Dataset blockers and minimal remediation

Dataset of record: `data/occupational_knowledge_base_verified_v1_0.xlsx`
(18 sheets, SHA-256 `12AFB16D3EF7A3FB2812C2377403E7F7BD171625791ADEAAC16E08315EEC2375`,
67,116 bytes). Full evidence is in
[`T5_3_REPAIRED_DATASET_PREFLIGHT_AUDIT.md`](T5_3_REPAIRED_DATASET_PREFLIGHT_AUDIT.md).

### 1.1 `OCCUPATION` — 15 extra rows (BLOCKER)

`OCCUPATION` has 23 data rows but only 8 distinct `occupation_id` values. Rows
9–23 are Kominfo/Kemnaker/BNSP 2018 occupation titles with the same IDs reused:

| Row | `occupation_id` | `canonical_name` | 4th unnamed column |
|---:|---|---|---:|
| 9 | O01 | Systems Programmer | 20506 |
| 10 | O02 | Interface Programmer | 20303 |
| 11 | O01 | Software Engineer | 20606 |
| 12 | O02 | Data Analyst | 1501 |
| 13 | O08 | Data Architect | 10603 |
| 14 | O04 | Data And Systems Engineering Manager | 10703 |
| 15 | O04 | Data Model Administrator | 10601 |
| 16 | O04 | Database Administrator | 10604 |
| 17 | O08 | Big Data Scientist | 10701 |
| 18 | O01 | Software Development Expert | 20708 |
| 19 | O08 | Software Development Expert | 20708 |
| 20 | O05 | Systems Integrator | 10505 |
| 21 | O07 | Cyber Security Engineer | 100718 |
| 22 | O07 | Cyber Security Analyst | 100601 |
| 23 | O03 | It Quality Assurance | 100705 |

**Intended meaning:** these are Kominfo occupation titles mapped onto the
existing 8 KBJI-anchored canonical occupations. They are **source mappings**,
not new canonical occupations.

**They do not belong in `OCCUPATION`.** They duplicate `OCCUPATION_SOURCE_MAPPING`
rows `OSM011`–`OSM025` exactly (same `occupation_id`, `source_code`, and
`source_title`). Keeping them in `OCCUPATION` breaks the `TEXT PRIMARY KEY`,
overloads `classification` with a source label, and adds two unnamed columns.

**Minimal remediation (no information loss):** remove rows 9–23 from
`OCCUPATION` and restore the 3-column header
(`occupation_id | canonical_name | classification`). The same 15 records remain
in `OCCUPATION_SOURCE_MAPPING`, where they are already correctly represented.
Do not delete the mapping rows.

### 1.2 `COMPETENCY_SKILL.unit_id` — 34 unmatched values (pre-existing)

`COMPETENCY_UNIT` uses zero-padded suffixes (`CU47_001`). `COMPETENCY_SKILL`
uses unpadded suffixes (`CU47_8`). 34 of 79 rows fail the join.

**Exact transformation:** for every value matching
`^(CU\d+_)(\d+)$`, keep the prefix and zero-pad the numeric suffix to 3 digits:

```python
import re
m = re.match(r"^(CU\d+_)(\d+)$", str(uid))
normalized = f"{m.group(1)}{int(m.group(2)):03d}" if m else uid
```

Examples: `CU47_8` → `CU47_008`, `CU191_1` → `CU191_001`, `CU299_10` →
`CU299_010`. This resolves all 34. The existing importer already applies this
at import time, but the workbook remains internally inconsistent. Fix the
workbook so validation does not depend on importer magic.

### 1.3 `TECHNOLOGY` and `TASK` — O*NET/Lightcast residue (BLOCKER for KB claims)

| Sheet | Rows | What is actually stored | In-scope? |
|---|---:|---|---|
| `TECHNOLOGY` | 120 | All 120 rows labelled `Lightcast`, `source_period=2025`, `geography='-'`; O*NET/Lightcast-style employer-posting frequency values; 63 distinct technology names repeated per occupation | **No** |
| `TASK` | 35 | All 35 rows labelled `Kominfo_Kemnaker_BNSP`, `source_period=2026`, `geography='Indonesia'`, but `source_code` is still O*NET SOC (`15-1252.00`, `15-1254.00`, `15-1253.00`, `15-1243.00`, `15-1244.00`, `15-1212.00`, `15-2051.00`) and `task_description` is English O*NET task text | **No** |

All 120 `TECHNOLOGY` rows and all 35 `TASK` rows **cannot be supported by the
thesis's in-scope sources** (KBJI, SKKNI, IndoTask, Kominfo/Kemnaker/BNSP).
Relabelling them as Kominfo is not acceptable.

**Minimal remediation for the evaluation run:** exclude both sheets from the
evaluation KB (empty the data rows or skip the two tables during import).
Do **not** relabel. This keeps the 25-table runtime schema intact, leaves
`technologies` and `tasks` empty, and removes an unsupported evidence layer.
Document the limitation: technology signals and task statements are not part of
the evaluated KB. If time permits later, replace them with genuine in-scope
records rather than restoring O*NET/Lightcast.

### 1.4 Provenance and source-mapping consistency

The current file is **internally consistent on provenance scope** after the
repair, with three fixable gaps:

| Check | Current state | Assessment |
|---|---|---|
| `PROVENANCE` | 14 rows: BPS KBJI, BPS crosswalk, 9 SKKNI, 2 IndoTask, 1 Kominfo | All in-scope. O*NET/ESCO records were removed; do not restore them. |
| `OCCUPATION_SOURCE_MAPPING` | 25 rows: 8 KBJI, 2 IndoTask, 15 Kominfo | All in-scope. `OSM011`–`OSM025` duplicate the 15 stray `OCCUPATION` rows. |
| `SKILL_SOURCE_EVIDENCE` | 97 rows: 62 SKKNI, 32 Kominfo, 3 IndoTask | All in-scope, but 32 `evidence_type` values have leading spaces. |
| `CAREER_SKILL.evidence_source` | SKKNI/IndoTask only | 146/155 rows end with `"; "`; strip trailing separators and empty tokens. |
| `OCCUPATION_SOURCE_MAPPING.source_code` | 15 integers, 10 text | Target column is `TEXT NOT NULL`; normalize all values to text before import. |
| Importer provenance derivation | Handles O*NET/KBJI/ESCO/IndoTask | **No Kominfo branch.** All 15 Kominfo OSM rows and 32 Kominfo SSE rows get `provenance_id = NULL` even though `P014` exists. |

**Minimal remediation:** add a Kominfo branch in `derive_osm_provenance()` and
`derive_sse_provenance()` that maps `Kominfo_Kemnaker_BNSP` to the `P014`
provenance record (`document_id = Kominfo_Kemnaker_BNSP_2018`). This is a
source-code change and requires approval. Without it, 47 provenance links are
silently null.

### 1.5 Can the 18-sheet workbook populate the runtime schema?

**Legacy `public` schema (the actual runtime schema): YES — after the §1.1 fix.**

The runtime database uses `public` with 16 OKB tables plus 9 `user_*` tables.
The workbook maps to all 16 OKB tables. The importer already handles the
non-1:1 cases:

- drops `skill_name` from `CAREER_SKILL`, `COMPETENCY_SKILL`,
  `SKILL_SOURCE_EVIDENCE`;
- merges `STANDARD_COVERAGE` into `SKKNI_STANDARD`;
- derives `provenance_id` / `mapping_basis` for OSM and SSE;
- generates `ETL_TRANSFORM_LOG` in memory;
- relies on DB sequence defaults for `career_occupations.id`,
  `occupation_competencies.id`, and `etl_transform_log.log_id`.

The only hard failure is `OCCUPATION`: the two unnamed columns become
`Unnamed: 3` / `Unnamed: 4` in pandas and are not valid target columns. Removing
rows 9–23 and the extra header cells makes the import schema-compatible.

**Target `okb` schema (`career_intelligence_okb`): NO.** That DDL expects
`SOURCE_REGISTER`, the KBJI 2026 layer, `EVIDENCE_LINK`, `KJN_SOURCE_CLAIMS`,
and governance tables that have no sheets in the 18-sheet workbook. Do not use
`career_intelligence_okb` for the evaluation. It currently has `app` and `okb`
schemas with **zero tables** (verified read-only on 2026-11-04).

### 1.6 Dataset remediation checklist (proposed, not executed)

| Step | Change | Risk |
|---|---|---|
| R1 | Remove `OCCUPATION` rows 9–23; restore 3-column header | None; duplicates remain in OSM |
| R2 | Zero-pad the 34 `COMPETENCY_SKILL.unit_id` values | None; matches existing importer behaviour |
| R3 | Strip trailing `"; "` and empty tokens from `CAREER_SKILL.evidence_source` | None |
| R4 | Trim `SKILL_SOURCE_EVIDENCE.evidence_type` | None |
| R5 | Convert `OCCUPATION_SOURCE_MAPPING.source_code` to text | Prevents a `TEXT NOT NULL` insert failure |
| R6 | Empty `TECHNOLOGY` and `TASK` data rows (exclude out-of-scope content) | Loses technology/task context; document as limitation |
| R7 | Update `README` and `STATUS_AUDIT` counts | Integrity only |
| R8 | Re-run the FK/duplicate/header validation and record new SHA-256 | Required gate |

Recommended file handling: keep the current file untouched and produce
`data/occupational_knowledge_base_verified_v1_1.xlsx` with the same 18-sheet
structure, then switch the dataset of record with approval. If an in-place edit
is preferred, create a repository-local backup first and record both hashes.

---

## 2. Database replacement strategy

### 2.1 Schema decision

Use the **legacy `public` 25-table schema**, cloned from the protected
`career_intelligence_e2e_test`, because:

- it is the schema the running application and the existing importer actually
  use;
- it already contains `provenance_id`, `mapping_basis`, `source_scope`, and the
  other columns the workbook/importer expect;
- the target `okb` schema cannot be populated from the 18-sheet workbook without
  adding tables/columns, which is prohibited.

Do not migrate to `okb` for this evaluation. That is a separate future decision.

### 2.2 Evaluation database

`career_intelligence_eval` **does not exist**. Current databases (read-only,
2026-11-04):

```text
career_intelligence, career_intelligence_e2e_test,
career_intelligence_okb, postgres
```

`career_intelligence_okb` exists with `app`/`okb`/`public` schemas and **0
tables** in `app`/`okb`.

### 2.3 Safest minimal method (proposed)

1. **Schema-only clone** from `career_intelligence_e2e_test` (read-only on the
   source). This reproduces exactly 25 tables, sequences, constraints, and
   defaults — no new or removed tables/columns.
2. **Create** `career_intelligence_eval` from `template0` with the same
   encoding/locale as the existing databases.
3. **Restore** the schema dump.
4. **Import** the remediated workbook transactionally.
5. **Verify** before connecting the application.

No user data is copied. The evaluation database is OKB-only; synthetic
evaluation users are created and deleted by the runner. This satisfies
"preserve non-OKB/application data" because no authoritative application data is
present or touched.

### 2.4 Avoiding duplicates on repeated runs

The existing importer is append-only and refuses a non-empty `careers` table.
For the evaluation DB, reset by **dropping and recreating the database** from
the same schema-only dump, not by `TRUNCATE ... CASCADE`. Reasons:

- `TRUNCATE skills CASCADE` would delete `user_skills` / `user_skill_evidence`;
- `TRUNCATE` in the wrong order fails on FK constraints;
- a fresh database is reproducible and leaves no partial import.

If a future evaluation DB must hold user data, import the OKB **before** any
user rows exist and never truncate `skills` afterwards.

### 2.5 Importer gate

`backend/scripts/import_kb.py` currently requires:

```python
ALLOWED_E2E_DB = "career_intelligence_e2e_test"
E2E_OPTIN_ENV = "CAREER_E2E_ISOLATED_DB_OK"
```

It refuses any other database and explicitly refuses `career_intelligence`.
Minimal approved change: add `career_intelligence_eval` as a second allowed
target behind a separate opt-in variable (for example
`CAREER_EVAL_ISOLATED_DB_OK=career_intelligence_eval`), while keeping
`career_intelligence` permanently blocked. Also add the Kominfo provenance
branch from §1.4. Do not weaken the production guard.

`backend/scripts/import_kb_fixed.py` is a near-duplicate with only whitespace
changes plus one unused `skkni_standard_to_prov` variable. Do not maintain two
importers; extend `import_kb.py` only.

### 2.6 Verification gate before application connection

Run on `career_intelligence_eval` only:

```sql
SELECT count(*) FROM careers;                         -- expected 10
SELECT count(*) FROM occupations;                     -- expected 8
SELECT count(DISTINCT occupation_id) FROM occupations;-- expected 8
SELECT count(*) FROM skills;                          -- expected 87
SELECT count(*) FROM career_skills;                   -- expected 155
SELECT count(*) FROM competency_units;                -- expected 146
SELECT count(*) FROM competency_skills;               -- expected 79
SELECT count(*) FROM occupation_source_mapping;       -- expected 25
SELECT count(*) FROM provenance;                      -- expected 14

-- orphan / duplicate checks
SELECT count(*) FROM competency_skills ck
LEFT JOIN competency_units cu USING (unit_id)
WHERE cu.unit_id IS NULL;                             -- expected 0
SELECT occupation_id, count(*) FROM occupations
GROUP BY 1 HAVING count(*) > 1;                       -- expected 0 rows
SELECT count(*) FROM occupation_source_mapping
WHERE provenance_id IS NULL;                          -- expected 0 after Kominfo branch
SELECT count(*) FROM skill_source_evidence
WHERE provenance_id IS NULL;                          -- expected 0 after Kominfo branch
```

Expected `technologies` / `tasks` counts are `0` if §1.3 exclusion is approved,
or `120` / `35` if the out-of-scope content is kept (not recommended).

### 2.7 Rollback

`career_intelligence` and `career_intelligence_e2e_test` are never import
targets and are never dropped. The only destructive operation is
`DROP DATABASE IF EXISTS career_intelligence_eval`, which affects no protected
object. Keep the schema-only dump so the eval DB can be rebuilt identically.

---

## 3. B0/B2/B3/F execution readiness

`backend/app/evaluation/configurations.py` is **descriptive metadata only**.
It has no entry point, no runner, and no runtime effect. `CareerWorkflow` has no
`config_id` parameter and always builds the same graph.

| Config | Definition file | Executable entry point | Enabled components | Executable today? | Missing |
|---|---|---|---|---|---|
| **B0** | `configurations.py` | **None** | Intended: LLM-only, no KB, no `compute_career_fit`, no verification | **No** | B0 prompt/agent, LLM-only output contract, adapter, runner |
| **B2** | `configurations.py` | **None** | Intended: all 10 careers + complete career-skill sets in prompt; LLM decides ranking and gap; no `compute_career_fit`, no `skill_gap_service`, no verification | **No** | B2 prompt builder, structured complete-set context, LLM-decided status schema, runner |
| **B3** | `configurations.py` | **None** | Intended: `retrieval_service` + `compute_career_fit()` + `classify_skill_gap()` + roadmap; verification omitted | **No** | A workflow variant or flag that removes verification/revision; runner |
| **F** | `configurations.py` | `CareerWorkflow.run()` (production path) | Profile → recommendation → skill gap → roadmap → verification → revision loop → final | **Partially** (as production F, not as an experiment) | `config_id`, manifest, run isolation, repeated runs, artifact/report persistence, fault injection |

### 3.1 What F currently does

`backend/app/workflows/career_workflow.py` compiles one graph with mandatory
`verification` and `verification_decision` nodes and a `max_revisions` loop.
`_verification_decision()` routes back to the responsible stage
(recommendation, skill gap, or roadmap) and terminates at
`REVISION_LIMIT_REACHED` or `VERIFICATION_FAILED`. This is the correct F
behaviour, but it is not selectable and not instrumented for experiments.

### 3.2 What B3 requires

B3 is not a small flag on the existing graph: removing verification also removes
the revision edge. The cleanest implementation is a graph builder that takes a
configuration and conditionally adds the verification nodes/edges, leaving the
non-verification stages, schema validation, and deterministic logic unchanged.
Do not fork the agents.

### 3.3 What B0/B2 require

B0 and B2 must not accidentally receive KB context through a shared prompt
builder. They need:

- a shared profile input (redacted CV text or structured profile);
- B0: only the 10 canonical career names + profile text;
- B2: all 10 careers + each career's complete `CAREER_SKILL` set, in structured
  form;
- an output contract that can be projected into `RecommendationPrediction` and
  `SkillGapPrediction` (including `unmatched_user_claim_keys` for B2);
- explicit prohibition of `retrieval_service` / `compute_career_fit` calls.

### 3.4 Planned comparisons

| Comparison | Status | Blocking reason |
|---|---|---|
| **F vs B0** | **Not runnable** | B0 path absent; F not parameterized or manifest-instrumented |
| **F vs B3** | **Not runnable** | B3 path absent (verification cannot be disabled) |
| **B2 vs B3** | **Not runnable** | B2 path absent; B3 path absent |

No paired significance test is implemented either. The evaluator aggregates
per-profile means and stability, but there is no Wilcoxon/paired-test or effect
size layer. Add this to Step 18/analysis, not to the metric formulas.

### 3.5 Shared input and evaluation DB

The production API reads the DB from `CAREER_DB_URL` / `CAREER_DB_*`
(`backend/app/core/db.py`). Experiments must point these variables at
`career_intelligence_eval` for the duration of the run, without permanently
editing `.env`. The existing diagnostic runner
(`backend/app/diagnostics/runner.py`) shows the safe pattern: override only the
`get_workflow` dependency, use a `TestClient`, and keep the production route and
agents. It currently runs only the F-like path and has no config switch, so it is
a reusable harness, not the Step 18 runner.

---

## 4. Metric readiness and required ground truth

The metric layer is implemented in `backend/app/evaluation/` and unit-tested by
`backend/tests/test_evaluation_metrics.py` and
`backend/tests/test_evaluation_framework.py`. It never invents a label and
returns `unavailable` when an input is missing.

| Metric | Implementation | Required inputs | Status today |
|---|---|---|---|
| **nDCG@3** | `metrics.ndcg_at_k`, `evaluator._evaluate_recommendation` | `RecommendationReference.labels[]` with `career_id` + graded `relevance >= 0`; `RecommendationPrediction.ranking` | **Unavailable** — no annotation corpus |
| **Macro-F1 (skill gap)** | `metrics.classification_metrics` | `SkillGapReference.required_skill_status[]` (`skill_id`, one of the 3 statuses) for the evaluated career; `SkillGapPrediction.required_skill_status` | **Unavailable** — no labels |
| **Unsupported-claim rate** | No single metric. Closest: `verification.detection_recall/precision/false_positive_rate` (`metrics.detection_metrics`), `skill_gap.over_credit_rate`, `roadmap.unsupported_item_rate` | `VerificationReference.injected_fault_ids` + `audited_claim_ids`; `VerificationPrediction.reported_claim_ids`; or reference/prediction status maps | **Unavailable** — no fault labels or claim universe |
| **Traceability rate** | `metrics.traceability_metrics` | `KbReference` (`canonical_career_ids`, `required_skill_ids_by_career`, `known_skill_ids`) + `RecommendationPrediction` referenced/evidenced/evidence-count fields + optional `SkillGapPrediction` | **Computable after import** — KB reference is derivable from the eval DB; no human labels needed |
| **Roadmap suitability** | `metrics.roadmap_metrics` | `RoadmapPrediction.items` + authoritative `gap_status_by_skill` (reference labels when available, otherwise the deterministic gap) | **Partially computable** for B3/F after import; B0/B2 need human gap labels or the comparison becomes circular |
| **Latency / retry** | `evaluator._evaluate_operational` reads `OperationalMetadata` | `latency_ms`, `token_usage`, `api_call_count`, `retry_count`, `revision_count` | **Unavailable** — `case_from_analysis_record` sets only `revision_count`; no runner timing or token accounting |

### 4.1 Minimum ground truth package

To produce real values for the primary comparisons, the following must exist and
be frozen before formal runs:

1. **Profile corpus:** at least 20 S-H (human-authored) entry-level IT profiles.
   Real CVs (R) are preferable but not required for a first defensible run.
   S-M (model-generated) profiles must not be the only evidence.
2. **Recommendation labels:** for each profile, a relevance grade for all 10
   canonical careers (0 = not relevant, 1 = acceptable, 2 = good, 3 = strong).
   This yields nDCG@3 and Hit@k.
3. **Skill-gap labels:** for each profile and the evaluated career, a status for
   every required skill (`matched_evidenced`, `matched_claimed_only`, `missing`)
   plus the unmatched user-claim keys. This yields macro-F1, per-category
   precision/recall, and over-credit rate.
4. **Verification fault labels:** for 5–10 controlled runs, the injected
   unsupported claim IDs and the full audited claim universe. This yields
   detection recall/precision and false-positive rate.
5. **KB snapshot:** generated deterministically from the eval DB after import
   (`careers`, `career_skills`, `skills`). This is not human annotation.
6. **Operational measurements:** captured by the runner (wall-clock latency,
   token usage, API-call count, retries, revision count).

The annotation policy in `docs/evaluation/DATASET_AND_ANNOTATION.md` must be
followed: annotators see only the redacted CV text and the canonical catalog,
never the system's scores or recommendations. Freeze an `annotation_version`
before any run.

---

## 5. Exact next commands or scripts

All commands are **proposals** and must not be run until the corresponding
change is approved. Run from the repository root. Authenticate to PostgreSQL
with the existing local credentials; never echo `PGPASSWORD` or write it to a
repository file.

### Phase 0 — This audit (already done)

No command required. Read-only probes used:
`backend\.venv\Scripts\python.exe` with SQLAlchemy and `openpyxl`.

### Phase 1 — Dataset remediation (requires approval)

Proposed new script: `backend/scripts/prepare_eval_workbook.py`

```text
Input : data/occupational_knowledge_base_verified_v1_0.xlsx
Output: data/occupational_knowledge_base_verified_v1_1.xlsx
Steps : R1-R7 from §1.6
Log   : data/occupational_knowledge_base_verified_v1_1.remediation.json
        (input SHA-256, output SHA-256, per-step row counts, no secrets)
```

Then validate:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_evaluation_metrics.py tests/test_evaluation_framework.py -q
.\.venv\Scripts\python.exe <validation-script>  # FK/duplicate/header checks
```

The validation script must re-run the 15 FK-style checks from T5.3 and assert:
`OCCUPATION` has 8 rows and 3 columns; all `COMPETENCY_SKILL.unit_id` values
match `COMPETENCY_UNIT`; `OCCUPATION_SOURCE_MAPPING.source_code` is text;
`technologies`/`tasks` are either empty or explicitly flagged.

### Phase 2 — Evaluation database (requires approval)

```powershell
# 2.1 Schema-only dump from the protected test DB (read-only on source)
pg_dump -h localhost -p 5433 -U postgres -d career_intelligence_e2e_test `
  --schema-only --no-owner --no-privileges `
  -f "$env:TEMP\ci_schema_only.sql"

# 2.2 Create the eval DB (only this DB; protected DBs untouched)
psql -h localhost -p 5433 -U postgres -d postgres -v ON_ERROR_STOP=1 `
  -c "CREATE DATABASE career_intelligence_eval WITH OWNER = postgres ENCODING = 'UTF8' TEMPLATE = template0;"

# 2.3 Restore the exact 25-table public schema
psql -h localhost -p 5433 -U postgres -d career_intelligence_eval -v ON_ERROR_STOP=1 `
  -f "$env:TEMP\ci_schema_only.sql"

# 2.4 Import (after the gate extension + Kominfo branch are approved)
$env:CAREER_DB_HOST = "localhost"
$env:CAREER_DB_PORT = "5433"
$env:CAREER_DB_NAME = "career_intelligence_eval"
$env:CAREER_EVAL_ISOLATED_DB_OK = "career_intelligence_eval"
cd backend
.\.venv\Scripts\python.exe scripts\import_kb.py
```

Reset between batches (eval DB only):

```powershell
psql -h localhost -p 5433 -U postgres -d postgres -v ON_ERROR_STOP=1 -c `
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'career_intelligence_eval' AND pid <> pg_backend_pid();"
psql -h localhost -p 5433 -U postgres -d postgres -v ON_ERROR_STOP=1 -c `
  "DROP DATABASE IF EXISTS career_intelligence_eval;"
# then repeat 2.2-2.4
```

Run the §2.6 verification gate and stop if any expected count differs.

### Phase 3 — Step 18 runner (requires approval and implementation)

Proposed files (not created):

```text
backend/app/evaluation/runner.py        # config switch, per-profile execution
backend/app/evaluation/manifest.py      # user_id, profile hash, config, model,
                                        # prompt hash, KB fingerprint, git state
backend/app/evaluation/faults.py        # controlled fault injection
backend/app/evaluation/annotations.py   # load/freeze reference labels
backend/scripts/run_experiment.py       # CLI: --config B0|B2|B3|F --split pilot|formal
```

Entry points:

- B3/F: reuse `CareerWorkflow` with a configuration-aware graph builder.
- B0/B2: new LLM-only execution paths with their own prompt builders.
- All: `/analysis/profile`-equivalent execution against
  `career_intelligence_eval`, with synthetic users created/deleted per profile.

Required tests: one test per config proving (a) the intended components run,
(b) forbidden components do not run, (c) the output projects into
`EvaluationCase`, and (d) a failed run is recorded as `failed`, not silently
dropped.

### Phase 4 — Annotation (parallel, requires researcher time)

```text
data/evaluation/profiles.jsonl            # 20 S-H profiles, redacted
data/evaluation/annotations_v1.json       # frozen labels
data/evaluation/fault_injection_v1.json   # injected claim IDs + claim universe
```

Validate the annotation files against `backend/app/evaluation/schemas.py` before
running any experiment.

### Phase 5 — Pilot, then formal

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\run_experiment.py --config F   --split pilot
.\.venv\Scripts\python.exe scripts\run_experiment.py --config B3  --split pilot
.\.venv\Scripts\python.exe scripts\run_experiment.py --config B2  --split pilot
.\.venv\Scripts\python.exe scripts\run_experiment.py --config B0  --split pilot
```

Only after the pilot manifests, metric availability, and failure handling are
reviewed should the formal split run.

---

## 6. Estimated execution order and remaining blockers

| Order | Task | Depends on | Estimated effort | Blocker |
|---:|---|---|---|---|
| 1 | Approve dataset remediation choices (R1–R7) | Researcher decision | 0.5 day | **D1, D6** |
| 2 | Produce and validate `v1_1` workbook | Step 1 | 0.5–1 day | — |
| 3 | Approve eval DB strategy and importer changes | Researcher decision | 0.5 day | **Gate, Kominfo branch** |
| 4 | Create `career_intelligence_eval`, import, verify | Steps 2–3 | 0.5–1 day | — |
| 5 | Implement Step 18 runner for B3/F | Step 4 | 2–3 days | **No runner, no config switch** |
| 6 | Implement B0/B2 LLM-only paths | Step 5 | 1–2 days | **No B0/B2 code** |
| 7 | Instrument latency/tokens/retries and manifests | Step 5 | 1 day | **No instrumentation** |
| 8 | Build and annotate minimum S-H corpus | Can start now | 3–5 days | **No annotation corpus** |
| 9 | Build fault-injection harness and labels | Step 5 | 1–2 days | **No fault harness** |
| 10 | Pilot all four configurations | Steps 5–9 | 1 day | — |
| 11 | Formal runs + paired analysis | Step 10 | 1–2 days | No significance-test layer |
| 12 | Write results and limitations | Step 11 | 1–2 days | — |

### Critical path

The **annotation corpus (Step 8)** is the longest independent task. Start it
immediately, in parallel with the runner work. The database and runner work can
proceed without labels because traceability, operational metrics, and
deterministic roadmap grounding are label-independent.

### Go / No-Go gate before formal runs

Formal runs may start only when all of the following are true:

- [ ] `v1_1` workbook passes all FK/duplicate/header checks and its SHA-256 is recorded.
- [ ] `career_intelligence_eval` matches the 25-table legacy schema and the §2.6 counts.
- [ ] `OCCUPATION` has 8 unique IDs and 3 columns.
- [ ] `occupation_source_mapping` and `skill_source_evidence` have zero null `provenance_id` after the Kominfo branch.
- [ ] `technologies` and `tasks` are empty or explicitly approved as out-of-scope.
- [ ] B0/B2/B3/F each run end-to-end and produce `EvaluationCase` inputs.
- [ ] Manifest records `config_id`, model, prompt hash, KB fingerprint, and git state.
- [ ] Annotation files validate against the Step 17 schemas and are frozen.
- [ ] Pilot manifests show no silent failures and no cross-config leakage.
- [ ] Protected databases are unchanged (before/after table and row-count comparison).

### Remaining blockers (explicit)

1. **Dataset D1** — `OCCUPATION` primary-key violation (15 Kominfo rows).
2. **Dataset D6** — all 120 `TECHNOLOGY` and 35 `TASK` rows are O*NET/Lightcast-derived and out of scope.
3. **Importer gate** — `career_intelligence_eval` is rejected by `import_kb.py`.
4. **Provenance derivation** — no Kominfo branch; 47 links would be null.
5. **No Step 18 runner** — no config switch, manifest, repeated runs, or artifact persistence.
6. **No B0/B2 implementation** — only descriptive definitions exist.
7. **No B3 implementation** — verification cannot be disabled in `CareerWorkflow`.
8. **No annotation corpus** — all label-dependent metrics are `unavailable`.
9. **No fault-injection harness** — verification detection metrics cannot be computed.
10. **No operational instrumentation** — latency, tokens, API calls, and retries are not recorded.
11. **No paired significance test** — comparisons cannot be reported with inferential statistics yet.

**STOP.** No dataset, source, configuration, database, migration, or commit change
was made. Await approval before executing any phase above.
