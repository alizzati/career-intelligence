# T5.2A-R2 — Focused SQL and Runtime Contract Verification

**Status:** COMPLETE (static verification only)

**Date:** 2026-11-03

**Scope:** Read-only verification of the corrected T5.2A-R1 DDL and runtime contract for the target database `career_intelligence_okb`.

**Workbook:** `data/occupational_knowledge_base_verified_v1_0_extended.xlsx`

**Workbook SHA-256:** `1314578e44d4a66b21fd19effe441ed303dc2da2239423abf73dfb7d1c807353`

**Verification mode:** Static inspection of SQL migrations, Python source, and workbook content. No SQL statement was executed, no PostgreSQL connection was opened, no migration or import was run, no database or runtime configuration was changed, and no database-dependent test was executed. Runtime behavior is assessed from source code only and is reported separately from static facts.

---

## 1. Executive summary

The corrected T5.2A-R1 DDL is **not ready for execution** and the current runtime is **not compatible with the target DDL** as written. The main results are:

1. **Two governing-design conflicts remain unresolved.**
   - The T5.2A-R1/R2 premise of a separate technology bonus contradicts the approved design freeze, which states that a technology signal must not affect career-fit or skill-gap results.
   - T5.2A-R1 places `okb.technologies` and `okb.tasks` in the operational schema, while the controlling T4-R2 design excludes TECHNOLOGY/TASK from operational import and retires the runtime functions that read them.
2. **The technology catalog design has a real identity defect.** `okb.technologies.technology_id` is an occupation-level signal primary key, not a canonical catalog identifier, and there is no foreign key to `okb.technology_catalog`. A simple FK cannot be added without renaming/re-keying the table.
3. **The technology claim-to-evidence pipeline does not exist.** There is no Activity model, no technology-claim model, no technology normalizer, no separate technology evidence store, no technology verification, and no bonus input.
4. **Technology mentions are not fully separated from competency evidence at runtime.** The profile extraction schema has `skills[]` and `evidence[]` but no `technology_claims[]`; a technology mention can enter the skill/evidence path and be persisted as `evidence_status='linked'`, which `compute_career_fit()` treats as fully evidenced.
5. **The target DDL is missing columns that the runtime queries require.** `provenance.url`, `provenance.source_type`, `skill_source_evidence.mapping_basis`, `skill_source_evidence.provenance_id`, `occupation_source_mapping.mapping_basis`, and `occupation_source_mapping.provenance_id` are selected by the repositories but are absent from migrations 004.
6. **Migration 007 cannot execute on PostgreSQL 16.** It uses `ALTER TABLE ... ADD CONSTRAINT IF NOT EXISTS`, which is not valid PostgreSQL syntax. Both constraints it adds are already declared inline in migration 006, so the file is also redundant.
7. **KBJI integrity is incomplete.** `career_occupation_kbji_mapping.kbji_mapping_id` has no FK to `career_kbji_mapping`; `occupation_kbji2026_link.kbji2026_code` has no FK or resolution status and silently admits unresolved code `2120`; two `career_kbji_mapping` workbook rows have `occupation_id = NULL` against a `NOT NULL` column; and parent-code FKs are absent.
8. **Eligibility is not implemented.** The approval, resolution, and source-permission fields exist in part, but no runtime code reads them. `scoring_eligible`, `eligibility_reason`, `eligibility_checked_at`, and `dataset_approval_id` are absent. `v_evidence_link_resolved` checks only the two resolution statuses and is unused.
9. **The full workbook cannot be imported into the current `evidence_link` DDL.** The `record_table` CHECK excludes `TECHNOLOGY` and `TASK`, but the workbook has 120 TECHNOLOGY and 35 TASK evidence-link rows (155 total).
10. **The nine legacy user tables are structurally represented and the repository SQL contract is statically compatible**, subject to the migration-007 defect, the missing runtime columns, and the fact that exact physical parity with the legacy `public` schema could not be verified without database access.

The correct next action is **not** to execute or patch the migrations. It is to resolve the two design conflicts and approve a corrective DDL revision, then re-run this verification.

---

## 2. Scope, method, and safety boundary

### 2.1 Inspected artifacts

- All SQL migrations in `database/migrations/postgresql/` (`001` through `008`).
- The runtime data-access layer, services, agents, schemas, and configuration under `backend/app/` and `backend/config/`.
- The controlling design and audit documents under `docs/design/` and `docs/audits/`.
- The extended workbook, read-only via `openpyxl` for structural probes.
- `backend/.env` for database-name configuration only (credential values were not printed or reproduced).

### 2.2 What "static" means here

A `PASS` in this report means the requirement is satisfied by the inspected SQL/source/workbook artifacts. A `FAIL` means the inspected artifacts demonstrably do not satisfy it. `NOT VERIFIED` means the answer depends on database state, migration execution, runtime execution, or a legacy schema snapshot that this task was not permitted to obtain.

No claim in this report is based on executing a query against PostgreSQL.

### 2.3 No ORM models

There are no SQLAlchemy ORM models in the repository: no `models/` directory, no `declarative_base`, no `DeclarativeBase`, no `mapped_column`, and no `Column(...)` declarations. All data access uses SQLAlchemy `text()` with unqualified table names. The relevant "model" is therefore the migration DDL plus the repository SQL, not an ORM metadata layer.

### 2.4 Status legend

| Status | Meaning |
|---|---|
| `PASS` | Verified statically and consistent with the requirement. |
| `FAIL` | Verified statically; the requirement is not met or the artifact is defective. |
| `NOT VERIFIED` | Requires database/runtime execution, migration execution, or a legacy schema snapshot that was outside this task's safety boundary. |

---

## 3. Static inspection inventory

| Area | File | Symbols / objects inspected |
|---|---|---|
| Schemas | `database/migrations/postgresql/001_create_schemas_and_extensions.sql` | `app`, `okb` schema creation |
| Core DDL | `database/migrations/postgresql/002_create_okb_core.sql` | `skill_groups`, `careers`, `occupations`, `career_occupations`, `skills`, `career_skills`, `tasks`, `technology_catalog`, `technology_alias`, `technologies`, `kbji_hierarchy`, `kbji_occupation`, `occupation_kbji2026_link`, `career_occupation_kbji_mapping`, `career_kbji_mapping` |
| Competency DDL | `database/migrations/postgresql/003_create_okb_competency.sql` | `skkni_standards`, `skkni_standard_coverage`, `competency_units`, `occupation_competencies`, `competency_skills` |
| Provenance DDL | `database/migrations/postgresql/004_create_okb_provenance.sql` | `source_register`, `provenance`, `occupation_source_mapping`, `skill_source_evidence`, `evidence_link`, `kjn_source_claims` |
| Governance DDL | `database/migrations/postgresql/005_create_okb_governance.sql` | `workbook_review_approval`, `import_manifest`, `evidence_link_resolution_audit`, `quarantine_reference`, `etl_transform_log` |
| App DDL | `database/migrations/postgresql/006_create_app_schema.sql` | `users`, `user_profiles`, `user_education`, `user_experience`, `user_projects`, `user_certifications`, `user_skills`, `user_skill_evidence`, `user_preferences` |
| Cross-schema DDL | `database/migrations/postgresql/007_add_cross_schema_constraints.sql` | `fk_user_skills_okb_skill`, `fk_user_skill_evidence_user_skill` |
| Indexes/views | `database/migrations/postgresql/008_create_indexes_and_views.sql` | `v_evidence_link_resolved`, `v_skill_catalog_joined`, `v_user_skill_catalog`, evidence/source indexes |
| DB configuration | `backend/app/core/db.py` | `build_database_url()`, `get_engine()`, `engine`; no `search_path` handling |
| Fit calculator | `backend/app/services/career_fit_service.py` | `DEFAULT_WEIGHTS`, `load_scoring_weights()`, `compute_career_fit()`, `RequiredSkillInput`, `UserSkillInput`, `SkillFitDetail`, `CareerFitResult` |
| Skill gap | `backend/app/services/skill_gap_service.py` | `classify_skill_gap()`, `_STATUS_MAP`, `unmatched_user_claims` |
| Recommendation caller | `backend/app/agents/career_recommendation_agent.py` | `compute_career_fit()` at line 151 |
| Verification caller | `backend/app/agents/verification_agent.py` | `compute_career_fit()` at line 204; `_context_record()` includes task/technology records as non-scoring context |
| Retrieval | `backend/app/services/retrieval_service.py` | `_provenance_out()`, `get_skill_evidence()`, `get_occupational_context()` |
| Repositories | `backend/app/repositories/occupation_repository.py` | `fetch_tasks_for_occupation()`, `fetch_technologies_for_occupation()`, `fetch_source_mappings_for_occupation()` |
| Repositories | `backend/app/repositories/evidence_repository.py` | `fetch_skill_source_evidence()`, `fetch_career_skill_evidence_text()`, `fetch_provenance()` |
| Repositories | `backend/app/repositories/career_repository.py` | `fetch_career_skills()` selects `s.status` |
| Repositories | `backend/app/repositories/user_repository.py` | All nine user-table SQL statements; `add_skill_evidence()` sets `evidence_status='linked'` |
| Profile agent | `backend/app/agents/profile_agent.py` | `EXTRACTION_SYSTEM_PROMPT`, `run()`, skill/evidence persistence |
| Skill normalizer | `backend/app/agents/skill_normalizer.py` | `_norm()`, `normalize_skill()`; fuzzy threshold |
| Response schemas | `backend/app/schemas/retrieval.py` | `ProvenanceOut`, `EvidenceItem`, `TaskOut`, `TechnologyOut`, `OccupationSourceMappingOut`, `OccupationalContextOut` |
| Scoring config | `backend/config/scoring_weights.yaml` | No technology weight |
| Design | `docs/design-freeze.md` | Technology non-scoring decision |
| Design | `docs/design/T3_DATA_MODEL_AND_PIPELINE_CONTRACT.md` | `TechnologyClaim`, pipeline, non-scoring technology edge |
| Design | `docs/design/T4_R2_TARGET_DATABASE_SCHEMA.md` | Eligibility, evidence-link allowlist, TECHNOLOGY/TASK exclusion, KBJI handling |
| Design | `docs/design/T5_2_TARGET_DDL_DESIGN.md` | T5.2A-R1 claims under verification |
| Audit | `docs/audits/T5_2A_R1_LEGACY_COMPATIBILITY_AUDIT.md` | Prior T5.2A-R1 compatibility/technology claims |
| Audit | `docs/audits/T5_1_DATABASE_PROVISIONING_REPORT.md` | Target DB creation and `search_path=app,okb` verification |
| Audit | `docs/audits/T2_IMPLEMENTATION_AUDIT.md` | Prior evidence-boundary finding |
| Workbook | `data/occupational_knowledge_base_verified_v1_0_extended.xlsx` | 25 sheets; structural probes only |

---

## 4. Governing decisions and unresolved conflicts

This section records conflicts before the detailed findings. It does not resolve them. Per `AGENTS.md`, a requirement that conflicts with an approved project decision must be reported, not silently implemented.

### 4.1 The design freeze says technology must not affect fit/gap

`docs/design-freeze.md:81-83` states:

> "Technology-to-competency mapping is optional and requires source/provenance. A technology signal must not itself affect career-fit or skill-gap results."

The decision log at `docs/design-freeze.md:453` records:

> "Technology mentions cannot themselves establish competency evidence or alter fit/gap; technology links require provenance. — **APPROVED — prior decision**"

`docs/design/T3_DATA_MODEL_AND_PIPELINE_CONTRACT.md:305-325` also shows `TechnologyClaim` with a dotted non-scoring edge to `compute_career_fit` and states: "recognition never enters career fit."

`docs/design/T4_R2_TARGET_DATABASE_SCHEMA.md:372` repeats: "Technology mentions never create competency evidence or affect career-fit/skill-gap."

**Conflict C-1.** `instruction.md` §3 and `docs/design/T5_2_TARGET_DDL_DESIGN.md:76-80` require a separate technology bonus component (with formula/weight/cap pending). That is a **new scoring design decision**, not an approved requirement. It contradicts the design freeze and T3/T4-R2. No technology bonus should be designed, implemented, or approved on the basis of the T5.2A-R2 brief alone. The absence of a bonus in the current runtime is consistent with the design freeze, even though it does not satisfy the literal T5.2A-R2 instruction.

**Consequence for this audit:** the technology pipeline is verified as "absent and non-scoring," not as "must be completed with a bonus." A researcher decision is required before any bonus path is introduced.

### 4.2 T4-R2 excludes TECHNOLOGY/TASK from the operational schema

`docs/design/T4_R2_TARGET_DATABASE_SCHEMA.md:122-123` classifies TECHNOLOGY and TASK as:

> "**Excluded from operational** (optional `staging_historical.technologies`)" ... "Never retrieved by operational repositories or agents for scoring/evidence."

`docs/design/T4_R2_TARGET_DATABASE_SCHEMA.md:139` states the decision explicitly and retires `occupation_repository.fetch_tasks_for_occupation` and `fetch_technologies_for_occupation` from the operational path.

**Conflict C-2.** `docs/design/T5_2_TARGET_DDL_DESIGN.md:82-88` instead creates `okb.technologies` and `okb.tasks` in the operational `okb` schema, and the current runtime still calls both repository functions in `backend/app/services/retrieval_service.py:178-179`. The DDL follows T5.2A-R1, not T4-R2. This must be resolved by the researcher before execution. The audit does not treat either side as silently authoritative.

### 4.3 EVIDENCE_LINK allowlist excludes TECHNOLOGY/TASK, but the workbook contains them

`database/migrations/postgresql/004_create_okb_provenance.sql:75-83` allows only:

`CAREER_KBJI_MAPPING`, `CAREER_OCCUPATION`, `CAREER_SKILL`, `COMPETENCY_SKILL`, `OCCUPATION_COMPETENCY`, `OCCUPATION_SOURCE_MAPPING`, `SKILL`.

The workbook `EVIDENCE_LINK` sheet has 970 rows, including 120 `TECHNOLOGY` and 35 `TASK` rows (155 total). A full import into the current `evidence_link` DDL would fail the CHECK constraint unless those rows are filtered or staged elsewhere. This is consistent with T4-R2's exclusion decision, but it is incompatible with the current T5.2A-R1 operational inclusion of `okb.technologies`/`okb.tasks`.

### 4.4 `validation_status` is present despite the T5.2A-R1 "excluded" claim

`docs/design/T5_2_TARGET_DDL_DESIGN.md:100` claims:

> "No per-record `validation_status` reintroduced | Pass | Kept out of the target operational model"

The same claim appears in `docs/audits/T5_2A_R1_LEGACY_COMPATIBILITY_AUDIT.md:90`.

But `database/migrations/postgresql/002_create_okb_core.sql:159-177` creates `okb.career_kbji_mapping` with both `validation_status` and `expert_review_status`.

This is **not necessarily a design violation**: `docs/design/T4_R2_TARGET_DATABASE_SCHEMA.md:345` permits the workbook column to be retained "descriptive only" for data fidelity, and `docs/design/T4_R2_TARGET_DATABASE_SCHEMA.md:352` says to "preserve existing workbook columns for fidelity where they already exist." The defect is the **false claim of exclusion** and the absence of an explicit comment/guard marking the column as non-eligibility. The column should not be removed without tracing its provenance, but the design claim must be corrected.

---

## 5. Technology catalog integrity

### 5.1 As-implemented DDL

`database/migrations/postgresql/002_create_okb_core.sql` defines:

| Table | Key elements | Lines |
|---|---|---|
| `okb.technology_catalog` | `technology_id TEXT PRIMARY KEY`, `canonical_name NOT NULL`, `normalized_value NOT NULL UNIQUE`, `catalog_fingerprint`, `source_note` | 75-83 |
| `okb.technology_alias` | `alias_id TEXT PRIMARY KEY`, `technology_id NOT NULL REFERENCES okb.technology_catalog(technology_id)`, `normalized_alias NOT NULL UNIQUE` | 85-91 |
| `okb.technologies` | `technology_id TEXT PRIMARY KEY`, `technology_name NOT NULL`, `occupation_id NOT NULL REFERENCES okb.occupations(occupation_id)`, `frequency_pct NUMERIC(5,2)`, flags | 93-105 |
| `okb.tasks` | `task_id TEXT PRIMARY KEY`, `occupation_id NOT NULL REFERENCES okb.occupations(occupation_id)`, `task_description NOT NULL`, flags | 62-73 |

### 5.2 Is the missing `technologies` → `technology_catalog` FK a real defect?

**Yes, but the defect is deeper than a missing constraint.**

`okb.technologies.technology_id` is used as a per-occupation signal primary key. The workbook confirms it: `TECHNOLOGY` has 120 rows with 120 unique `technology_id` values (`T001`–`T120` style), 7 occupation IDs, and only 63 distinct case-folded technology names. The same technology name occurs across multiple occupations but with a different `technology_id` per row.

If `okb.technologies.technology_id` were made a FK to `okb.technology_catalog.technology_id`:

- each canonical technology could appear only once because `technologies.technology_id` is the primary key;
- the 120 occupation-level signal rows could not reuse the same canonical ID;
- the model would conflate "one signal about one occupation" with "one canonical global technology."

The correct separation is:

- `technology_catalog`: one row per canonical global technology, with a stable catalog ID.
- `technology_alias`: one row per exact alias, FK to the catalog.
- `technology_signal` (currently `technologies`): one row per occupation-level signal, with its own signal ID and a separate FK to the catalog.
- `tasks`: one row per occupation-level task, unchanged.

The current DDL implements the first two correctly, but the third conflates signal identity and catalog identity. The missing FK is the symptom; the column semantics are the defect.

### 5.3 Proposed corrected relational design (proposal only — no SQL executed)

```sql
-- Canonical global technology entities.
okb.technology_catalog (
    technology_id        TEXT PRIMARY KEY,
    canonical_name       TEXT NOT NULL,
    technology_type      TEXT,
    normalized_value     TEXT NOT NULL UNIQUE,   -- NFKC + case-fold + trim + whitespace collapse
    catalog_fingerprint  TEXT,
    source_note          TEXT,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Exact aliases; every alias resolves to exactly one canonical entity.
okb.technology_alias (
    alias_id          TEXT PRIMARY KEY,
    technology_id     TEXT NOT NULL
        REFERENCES okb.technology_catalog(technology_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    alias             TEXT NOT NULL,
    normalized_alias  TEXT NOT NULL,
    UNIQUE (normalized_alias),                   -- global collision is a hard failure
    UNIQUE (technology_id, normalized_alias)
);

-- Occupation-level signals; replaces the current okb.technologies table.
okb.technology_signal (
    technology_signal_id    TEXT PRIMARY KEY,    -- workbook T001..T120
    catalog_technology_id   TEXT NOT NULL
        REFERENCES okb.technology_catalog(technology_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    occupation_id           TEXT NOT NULL
        REFERENCES okb.occupations(occupation_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    surface_name            TEXT NOT NULL,       -- workbook technology_name, preserved
    technology_type         TEXT,
    source                  TEXT,
    source_period           TEXT,
    frequency_pct           NUMERIC(5,2),
    evidence_note           TEXT,
    operational_evidence_present BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (occupation_id, catalog_technology_id)
);
```

Key points:

- Do **not** simply add a FK to the existing `technologies.technology_id`; that would require illegal ID reuse.
- Rename the signal key to `technology_signal_id` (or keep the table name but rename the column and add `catalog_technology_id`).
- Keep the workbook surface name separate from the canonical name; do not overwrite source text.
- Add `UNIQUE (occupation_id, catalog_technology_id)` so the same canonical technology cannot be duplicated for one occupation.
- `technology_catalog` and `technology_alias` have no workbook source sheet today. The 63 distinct names in `TECHNOLOGY` are not an approved catalog: they are occupation-level signal names with no canonical IDs, aliases, or review status. Seeding the catalog from them would require a reviewed, explicit mapping; fuzzy assignment is prohibited.

### 5.4 Data availability finding

The workbook `TECHNOLOGY` sheet has these columns:

`technology_id`, `technology_name`, `technology_type`, `occupation_id`, `source`, `source_period`, `frequency_pct`, `evidence_note`, `operational_evidence_present`, `eligible_for_career_fit`, `eligible_for_skill_gap`.

It has **no** `canonical_name`, `normalized_value`, `alias`, `catalog_fingerprint`, or `catalog_technology_id` column. There is no `TECHNOLOGY_CATALOG` or `TECHNOLOGY_ALIAS` sheet. Therefore:

- `okb.technology_catalog` and `okb.technology_alias` currently have **no approved source data**;
- the 120 `okb.technologies` rows cannot be linked to canonical catalog rows without an explicit reviewed mapping;
- an importer must not invent catalog rows, aliases, or IDs.

Workbook evidence also shows all three technology flags are `FALSE` for all 120 rows:

| Flag | TRUE count | FALSE count |
|---|---:|---:|
| `operational_evidence_present` | 0 | 120 |
| `eligible_for_career_fit` | 0 | 120 |
| `eligible_for_skill_gap` | 0 | 120 |

The same is true for all 35 `TASK` rows (0 TRUE for each flag).

### 5.5 Technology catalog status

| Requirement | Status | Evidence |
|---|---|---|
| `technology_catalog` has a canonical PK and unique normalized value | PASS | `002:75-83` |
| `technology_alias` has a FK to the catalog and unique normalized alias | PASS | `002:85-91` |
| `technologies` links each signal to a canonical catalog entity | FAIL | No FK; `002:93-105`; signal PK is `T001..T120`, not a catalog ID |
| `technologies` preserves occupation-level signal identity | PASS | `occupation_id` FK; signal PK; `002:93-105` |
| `tasks` is occupation-level | PASS | `002:62-73` |
| Catalog/alias source data or approved seed exists | FAIL | No workbook sheet or importer; only 63 distinct signal names |
| Corrected relational design proposed | PASS | §5.3 of this report |

---

## 6. Technology claim-to-evidence pipeline

### 6.1 Intended pipeline and actual implementation

The intended pipeline in `instruction.md` §2 is:

`Activity description → technology claim extraction → exact catalog/alias normalization → evidence association → verification → accepted technology evidence → career-fit bonus input`.

The actual implementation is:

| Step | Intended artifact | Actual implementation | Status |
|---|---|---|---|
| 1. Activity description | Activity record/model/table | No Activity table or model. The legacy `user_experience` and `user_projects` rows exist, but there is no common Activity abstraction and no activity-text pipeline. | FAIL |
| 2. Technology claim extraction | `TechnologyClaim` model/table/service | No `technology_claims` output in `ProfileAgent.EXTRACTION_SYSTEM_PROMPT` (`profile_agent.py:44-57`); no claim table in any migration. | FAIL |
| 3. Exact catalog/alias normalization | NFKC/case-fold/trim/collapse + explicit alias lookup | No technology normalizer. `skill_normalizer._norm()` only does `strip().lower().split()` (`skill_normalizer.py:29-30`), and it is for skills, not technologies. No NFKC. | FAIL |
| 4. Alias collision handling | Deterministic failure | `technology_alias.normalized_alias` is globally UNIQUE (`002:90`), so a duplicate insert would fail at the database. There is no runtime normalization service to detect and report a collision deterministically before insert. | FAIL |
| 5. No fuzzy technology assignment | Exact-only matching | No technology matcher exists. The only normalizer (`skill_normalizer.py:45-53`) uses `difflib` fuzzy matching at 0.88, and it is reachable for any text emitted in `skills[]`, including a technology term. | FAIL |
| 6. Evidence association | Separate technology evidence store | No technology evidence table. `evidence_link` is generic and cannot target `TECHNOLOGY` or `TASK` because of its CHECK (`004:75-83`). | FAIL |
| 7. Verification | Technology evidence verification | No technology verification path in `verification_agent.py`. The agent only verifies skill/career/roadmap claims; technology records are included as context in `_context_record()` (`verification_agent.py:132-144`) but are not scored or accepted/rejected. | FAIL |
| 8. Accepted technology evidence | Persisted accepted record | No such table or service. | FAIL |
| 9. Career-fit bonus input | Separate bonus parameter | `compute_career_fit()` has no technology parameter (`career_fit_service.py:141-145`); `scoring_weights.yaml` has no technology weight. | FAIL (and not approved — see Conflict C-1) |

### 6.2 Technology evidence vs `CompetencyEvidence`

There is no `CompetencyEvidence` class/table in the repository. The only persisted evidence is:

- `app.user_skill_evidence` (generic, created by `user_repository.add_skill_evidence()`), and
- `okb.skill_source_evidence` / `okb.evidence_link` (OKB provenance).

Technology evidence is **not** stored separately. There is no table whose rows are keyed by a technology claim and an acceptance status. The proposed `technology_catalog`/`technology_alias` tables are catalogs, not evidence.

### 6.3 The runtime boundary loophole

The instruction requires: "technology mentions without accepted evidence cannot contribute to scoring." The current code does not enforce this separation.

The actual path is:

1. `ProfileAgent.EXTRACTION_SYSTEM_PROMPT` asks the LLM for `skills[]` and `evidence[]`, but not `technology_claims[]` (`profile_agent.py:44-57`).
2. A technology term can be emitted as a `skills[]` item with an optional `candidate_skill_id` (`profile_agent.py:46`).
3. `normalize_skill()` accepts an `llm_suggested_skill_id` whenever it exists in the catalog (`skill_normalizer.py:55-62`). It also accepts a fuzzy match at `>= 0.88` (`skill_normalizer.py:45-53`).
4. `ProfileAgent.run()` persists the claim via `us.add_user_skill()` (`profile_agent.py:121-140`).
5. Any `evidence[]` item whose `claimed_skill` matches is persisted via `us.add_skill_evidence()` (`profile_agent.py:143-158`).
6. `user_repository.add_skill_evidence()` unconditionally sets `evidence_status='linked'` after inserting any evidence row (`user_repository.py:265-267`).
7. `compute_career_fit()` treats `evidence_status == 'linked'` as full credit (`career_fit_service.py:178-180`).

There is no type guard that rejects a technology term in `skills[]`, no `technology_claims[]` separation, and no evidence-acceptance check. A technology mention can therefore contribute through the **competency** path, not through a technology bonus path.

A static workbook check shows **zero exact case-folded name overlaps** between the 87 canonical skills and the 63 distinct technology names. That reduces the deterministic collision risk, but it does not remove the LLM-assisted or fuzzy path: an LLM-supplied `candidate_skill_id` is accepted if it is a real catalog ID, and a fuzzy match can be accepted without an alias/catalog rule. The boundary is not enforced.

### 6.4 Technology normalization rules

| Approved rule | Present in runtime? | Evidence |
|---|---|---|
| Unicode NFKC normalization | No | `skill_normalizer._norm()` uses `strip().lower().split()` only; no `unicodedata.normalize("NFKC", ...)` anywhere. |
| Case-folding | Partial | `.lower()` is used for skills; not `casefold()`. No technology normalizer. |
| Trimming | Yes (skills only) | `_norm()` strips. |
| Whitespace collapsing | Yes (skills only) | `" ".join(...split())`. |
| Explicit alias mapping | Schema only | `technology_alias` exists; no runtime alias lookup. |
| Alias collision fails deterministically | Schema only | `UNIQUE (normalized_alias)` exists; no runtime error handling/reporting. |
| No fuzzy technology assignment | Not enforced | No technology matcher; skill fuzzy matcher can process technology text. |

The approved normalization rules are **not implemented** for technologies. The schema is a partial foundation only.

### 6.5 Technology pipeline status

| Requirement | Status | Evidence |
|---|---|---|
| Activity model/table exists | FAIL | No Activity table/model |
| Technology claim extraction exists | FAIL | No `technology_claims` output |
| Exact catalog/alias normalization exists | FAIL | No technology normalizer |
| Technology evidence is separate from competency evidence | FAIL | No technology evidence store |
| Technology evidence verification exists | FAIL | No verification path |
| Only accepted technology evidence can contribute | FAIL | No accepted-evidence gate; no bonus |
| Technology mentions cannot contribute via competency path | FAIL | `skills[]` → `evidence[]` → `linked` → `compute_career_fit` |
| Unmatched technology claims remain traceable | FAIL | No claim table |

---

## 7. Career-fit integration

### 7.1 Single source of truth

`compute_career_fit()` is the only career-fit calculator. All inspected callers use it:

- `backend/app/agents/career_recommendation_agent.py:151`
- `backend/app/services/skill_gap_service.py:95` (inside `classify_skill_gap()`)
- `backend/app/agents/verification_agent.py:204` (re-computation for verification)

`skill_gap_service.py` explicitly documents that it contains no second formula and maps the calculator's statuses to the four approved categories (`skill_gap_service.py:15-20`, `56-58`, `84-96`, `100-141`). `verification_agent.py:257-259` compares the reported score/breakdown/weights against a fresh `compute_career_fit()` result.

**PASS.**

### 7.2 Skill formula preserved

`compute_career_fit()` still uses:

- `core_weight` vs `supporting_weight` by `evidence_class` (`career_fit_service.py:167-170`);
- `confidence_multiplier` by KB confidence (`:169`);
- `linked` → full weight, `none` → `claim_only_multiplier` (`:178-183`);
- the self-reported proficiency modifier, capped at the skill's full weight (`:185-195`);
- `total_contribution / total_weight`, clamped to `[0,1]` (`:204-205`).

`backend/config/scoring_weights.yaml` contains the same five parameters and no technology weight.

**PASS.**

### 7.3 Technology bonus as a separate component

`compute_career_fit()` has no technology parameter, no technology weight, and no separate result field. `CareerFitResult` contains only `fit_score`, `total_weight`, `total_contribution`, and `skill_details` (`career_fit_service.py:105-122`).

The absence is **consistent with the approved design freeze** (Conflict C-1), but it does **not** satisfy the literal T5.2A-R2 instruction to verify a separate bonus component. The T5.2A-R1 design's statement that the bonus is "pending approval" is inaccurate: the design freeze already prohibits technology from affecting fit/gap. Any bonus would be a new, explicit research decision.

**FAIL against the instruction; PASS against the design freeze.** No bonus should be implemented without researcher approval.

### 7.4 Only accepted technology evidence as bonus input

There is no bonus input, no accepted technology evidence, and no technology parameter. The condition is vacuously unimplemented. This is not a defect to fix by adding a bonus; it is a decision to resolve first.

**FAIL as stated (not implemented); the correct action is to confirm whether the bonus is approved at all.**

### 7.5 Formula/weight/cap remain pending

No technology formula, weight, or cap exists in the DDL, `career_fit_service.py`, `scoring_weights.yaml`, or any schema. No values were invented.

**PASS for "no invented weights"; the pending decision itself must be resolved by the researcher.**

---

## 8. Legacy user schema compatibility

### 8.1 Nine-table compatibility matrix

The application repository contract is `backend/app/repositories/user_repository.py`. All table references are unqualified. The target DDL is `database/migrations/postgresql/006_create_app_schema.sql`.

| # | Legacy table | Target DDL columns | PK / FK / unique / index | Repository references | Static status |
|---|---|---|---|---|---|
| 1 | `users` | `user_id BIGSERIAL`, `email TEXT NOT NULL UNIQUE`, `full_name TEXT NOT NULL`, `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()` | PK `user_id`; UNIQUE `email` | `create_user`, `fetch_user`, `fetch_user_by_email` (`user_repository.py:45-66`) | PASS |
| 2 | `user_profiles` | `user_id BIGINT PK`, `headline`, `summary`, `target_domain`, `created_at`, `updated_at` | PK/FK `user_id → users` ON DELETE CASCADE | `fetch_profile`, `upsert_profile` (`:69-85`) | PASS |
| 3 | `user_education` | `education_id BIGSERIAL PK`, `user_id BIGINT NOT NULL FK`, `institution NOT NULL`, `degree`, `field_of_study`, `start_date`, `end_date`, `description`, `created_at` | PK `education_id`; FK `user_id → users` CASCADE | `create_education`, `fetch_education` (`:88-117`) | PASS |
| 4 | `user_experience` | `experience_id BIGSERIAL PK`, `user_id BIGINT NOT NULL FK`, `company NOT NULL`, `role_title NOT NULL`, `employment_type`, `start_date`, `end_date`, `description`, `created_at` | PK `experience_id`; FK `user_id → users` CASCADE | `create_experience`, `fetch_experience` (`:120-147`) | PASS |
| 5 | `user_projects` | `project_id BIGSERIAL PK`, `user_id BIGINT NOT NULL FK`, `title NOT NULL`, `description`, `url`, `role`, `created_at` | PK `project_id`; FK `user_id → users` CASCADE | `create_project`, `fetch_projects` (`:150-174`) | PASS |
| 6 | `user_certifications` | `certification_id BIGSERIAL PK`, `user_id BIGINT NOT NULL FK`, `name NOT NULL`, `issuer`, `issue_date`, `expiry_date`, `credential_url`, `created_at` | PK `certification_id`; FK `user_id → users` CASCADE | `create_certification`, `fetch_certifications` (`:177-207`) | PASS |
| 7 | `user_skills` | `user_skill_id BIGSERIAL PK`, `user_id BIGINT NOT NULL FK`, `claimed_skill TEXT NOT NULL`, `skill_id TEXT FK → okb.skills`, `normalized_skill`, `proficiency`, `evidence_status TEXT NOT NULL DEFAULT 'none'`, `confidence TEXT NOT NULL DEFAULT 'unknown'`, `created_at`, `UNIQUE (user_id, claimed_skill)` | PK `user_skill_id`; FK `user_id → users` CASCADE; FK `skill_id → okb.skills` ON DELETE RESTRICT; UNIQUE `(user_id, claimed_skill)` | `create_user_skill`, `fetch_user_skills` (`:211-242`) | PASS |
| 8 | `user_skill_evidence` | `evidence_id BIGSERIAL PK`, `user_skill_id BIGINT NOT NULL FK`, `evidence_type TEXT NOT NULL`, `source_table`, `source_id BIGINT`, `description`, `url`, `created_at` | PK `evidence_id`; FK `user_skill_id → user_skills` CASCADE | `add_skill_evidence`, `fetch_skill_evidence` (`:245-276`) | PASS |
| 9 | `user_preferences` | `user_id BIGINT PK`, `preferred_domains`, `weekly_learning_hours INTEGER`, `preferred_learning_format`, `career_goal_notes`, `created_at`, `updated_at` | PK/FK `user_id → users` CASCADE | `fetch_preferences` (`:280-285`) | PASS |

No tenth legacy user table is referenced by the runtime. The full runtime table-name scan returned only the nine `user_*`/`users` tables plus the OKB tables.

### 8.2 Schema-qualified vs unqualified references

Every runtime table reference is unqualified. Examples:

- `SELECT ... FROM users` (`user_repository.py:55`)
- `SELECT ... FROM user_profiles` (`:71`)
- `SELECT ... FROM career_skills` (`career_repository.py:29`)
- `SELECT ... FROM skill_source_evidence` (`evidence_repository.py:22`)
- `SELECT ... FROM occupation_source_mapping` (`occupation_repository.py:68`)

There are no `public.`-qualified references and no `app.`/`okb.`-qualified runtime references. The target design therefore relies entirely on `search_path = app, okb`.

### 8.3 `search_path` findings

- `database/migrations/postgresql/001_create_schemas_and_extensions.sql:3-4` creates `app` and `okb`.
- `docs/audits/T5_1_DATABASE_PROVISIONING_REPORT.md:135-141` records `ALTER DATABASE career_intelligence_okb SET search_path TO app, okb;` and verifies `app, okb` from a fresh session.
- `backend/app/core/db.py` does not set `search_path` per connection or per engine. The database-level setting is the only mechanism.
- `backend/.env` currently sets `CAREER_DB_NAME=career_intelligence`, not `career_intelligence_okb`. The running application therefore still resolves unqualified names against the legacy `public` schema. The target `search_path` is **not active** for the current runtime configuration. This is a deployment-state finding, not a DDL defect.

With `search_path = app, okb`:

- `users` resolves to `app.users` because `app` is first;
- `user_*` resolves to `app.*`;
- `skills`, `careers`, `occupations`, `career_skills`, `provenance`, `occupation_source_mapping`, etc. resolve to `okb.*` because `app` contains no same-named table;
- `public` is excluded, so legacy `public` tables are not accidentally visible;
- `pg_catalog` remains implicitly searched.

The design is sufficient **for the target database** under the verified T5.1 setting. It is **not verified** for the current runtime until `CAREER_DB_NAME` is changed and the runtime is exercised, which this task did not do.

### 8.4 Additional legacy/runtime contract findings

#### 8.4.1 Migration 007 is not executable on PostgreSQL 16

`database/migrations/postgresql/007_add_cross_schema_constraints.sql:4-14` contains:

```sql
ALTER TABLE app.user_skills
    ADD CONSTRAINT IF NOT EXISTS fk_user_skills_okb_skill
    FOREIGN KEY (skill_id) REFERENCES okb.skills(skill_id)
    ...
```

PostgreSQL 16 `ALTER TABLE` supports `ADD [COLUMN] [IF NOT EXISTS]` and `ADD table_constraint [NOT VALID]`, but it does **not** support `ADD CONSTRAINT IF NOT EXISTS`. The migration would fail with a syntax error at the first `ADD CONSTRAINT IF NOT EXISTS`. The same applies to the second constraint at lines 10-14.

Both constraints are already declared inline in `006_create_app_schema.sql`:

- `app.user_skills.skill_id REFERENCES okb.skills(skill_id)` at `006:68`;
- `app.user_skill_evidence.user_skill_id REFERENCES app.user_skills(user_skill_id)` at `006:79`.

So 007 is both invalid and redundant. Proposed correction: remove the two duplicate constraints and either delete the migration or replace it with an idempotent `DO $$ ... IF NOT EXISTS (SELECT 1 FROM pg_constraint ...) ... $$` block if a future cross-schema constraint is genuinely needed. Do not execute this correction in this task.

#### 8.4.2 Runtime-selected columns absent from the target DDL

The target DDL does not contain columns that the current repositories and response models require:

| Runtime query | Selected column(s) | Target DDL | Effect |
|---|---|---|---|
| `evidence_repository.fetch_skill_source_evidence()` (`evidence_repository.py:17-26`) | `sse.mapping_basis`, `sse.provenance_id`, `p.url`, `p.source_type` | `okb.skill_source_evidence` has no `mapping_basis` or `provenance_id` (`004:46-59`); `okb.provenance` has no `url` or `source_type` (`004:22-30`) | `UndefinedColumn` at runtime |
| `occupation_repository.fetch_source_mappings_for_occupation()` (`occupation_repository.py:62-73`) | `osm.mapping_basis`, `osm.provenance_id`, `p.url`, `p.source_type` | `okb.occupation_source_mapping` has no `mapping_basis` or `provenance_id` (`004:32-44`); `okb.provenance` has no `url` or `source_type` | `UndefinedColumn` at runtime |
| `career_repository.fetch_career_skills()` (`career_repository.py:24-34`) | `s.status` | `okb.skills.status` exists with `NOT NULL DEFAULT 'active'` (`002:40`) | Compatible via the default, but the workbook `SKILL` sheet has no `status` column; every imported skill would receive an unsourced `'active'` value |
| `retrieval_service._provenance_out()` (`retrieval_service.py:24-32`) | `row["source_type"]`, `row["p_source_name"]`, `row["document_id"]`, `row["document_title"]`, `row["version_or_year"]` | `ProvenanceOut.source_type` is required `str` (`schemas/retrieval.py:36-43`); DDL columns are nullable or absent | Pydantic `ValidationError` if a required field is null; `KeyError` if absent |

The workbook `PROVENANCE` sheet has exactly the DDL columns (`provenance_id`, `source_name`, `document_id`, `document_title`, `version_or_year`, `source_id`, `record_status`) and the workbook values are non-null, but it has no `url` or `source_type`. Those two fields are runtime-only expectations. Likewise, `mapping_basis` and `provenance_id` are runtime-only expectations, not workbook columns.

Proposed correction options (to be approved, not executed):

1. **Align DDL to the runtime contract:** add nullable `provenance.url TEXT`, `provenance.source_type TEXT`, `skill_source_evidence.mapping_basis TEXT`, `skill_source_evidence.provenance_id TEXT REFERENCES okb.provenance(provenance_id)`, and the same two columns to `occupation_source_mapping`. Populate them at import from `source_register`/`mapping_method` under an explicit derivation rule. This preserves the existing repository interface.
2. **Align the runtime to the normalized DDL:** change the two repository queries to join `source_register` for `source_type` and a URL (`COALESCE(exact_document_or_download_url, official_url)`), use `mapping_method` for `mapping_basis`, and replace `provenance_id` with a proper FK/join. This is cleaner but changes application code and the response schema.

Option 2 is preferable for normalization, but it is an application-code change and requires separate approval. Option 1 is the lower-risk compatibility fix. Either way, the chosen contract must be documented and covered by tests.

#### 8.4.3 `source_register` drops three workbook columns

The workbook `SOURCE_REGISTER` has 19 columns, including `source_role`, `role_rationale`, and `notes`. The target DDL `okb.source_register` (`004:3-20`) has 16 columns and omits those three. This is a data-fidelity gap, not a runtime break. Proposed correction: add the three nullable columns if the workbook data must be preserved, or document the deliberate omission and the mapping to `selection_status`/`verification_metadata`.

#### 8.4.4 Exact legacy physical-type parity not verified

The legacy `public` schema DDL is not present in the repository. `docs/audits/T5_1_DATABASE_PROVISIONING_REPORT.md` records table names and row counts but not column types. Without database access, exact physical parity between legacy `public` tables and `app` tables cannot be proven. The repository SQL contract is statically compatible, but a type-level migration comparison remains `NOT VERIFIED`.

### 8.5 Legacy compatibility status

| Requirement | Status | Evidence |
|---|---|---|
| All nine legacy user tables exist in `app` with exact names | PASS | `006:3-96` |
| Repository-required columns exist with compatible names | PASS | §8.1 |
| Primary keys, foreign keys, unique constraints used by code | PASS (static) | §8.1; `006` |
| Migration 007 is valid SQL and non-duplicative | FAIL | Invalid `ADD CONSTRAINT IF NOT EXISTS`; duplicates inline FKs |
| Runtime-selected columns exist in the target DDL | FAIL | §8.4.2 |
| No legacy user table outside the nine is referenced | PASS | Runtime table scan |
| Unqualified SQL resolves under `search_path = app, okb` | PASS (target DB, static/T5.1) | §8.2-8.3 |
| Target `search_path` is active for the current runtime | NOT VERIFIED / FAIL (deployment) | `.env` points to `career_intelligence` |
| Exact legacy physical type/constraint parity | NOT VERIFIED | No legacy DDL/snapshot; no DB access |

---

## 9. KBJI relationship integrity

### 9.1 Findings

| # | Requirement | Finding | Status |
|---|---|---|---|
| 1 | `career_occupation_kbji_mapping.kbji_mapping_id` has a valid FK to `career_kbji_mapping` | The table has a composite FK to `career_occupations(career_id, occupation_id)` but **no FK on `kbji_mapping_id`** (`002:149-157`). `career_kbji_mapping.mapping_id` is the candidate PK (`002:160`). All 22 workbook junction references resolve to existing `MAP-*` IDs, so the FK is feasible. | FAIL |
| 2 | The junction has the intended candidate key/PK | PK `(career_id, occupation_id, kbji_mapping_id)` exists (`002:153`). | PASS |
| 3 | No semicolon-delimited ID field remains as an operational relationship | The DDL has no `supporting_kbji_mapping_ids` column. The workbook's `CAREER_OCCUPATION.supporting_kbji_mapping_ids` is a semicolon field (6 rows, 22 refs) that must be split by an importer. No importer exists, so the migration behavior is unverified. | PASS (DDL) / NOT VERIFIED (import) |
| 4 | `occupation_kbji2026_link.kbji2026_code` has a FK and/or resolution status | `kbji2026_code TEXT NOT NULL` has **no FK** to `kbji_hierarchy(kbji_code)` and **no resolution-status column** (`002:139-147`). `kbji_hierarchy.kbji_code` is UNIQUE (`002:119`), so the FK is feasible. | FAIL |
| 5 | Unresolved KBJI references are not silently converted into valid records | Code `2120` appears in `OCCUPATION.classification` (1 row) and in `OCCUPATION_KBJI2026_LINK` (1 row), but is absent from `KBJI_HIERARCHY` (30 codes, no `2120`) and `KBJI_OCCUPATION`. The DDL accepts the link row with no status, so `2120` is silently admitted as a valid-looking link. | FAIL |
| 6 | `career_kbji_mapping.occupation_id` handles unresolved rows | 2 of 29 workbook rows (`MAP-009`, `MAP-013`) have `occupation_id = NULL` and `validation_status = 'UNRESOLVED'`. The DDL declares `occupation_id TEXT NOT NULL` and a FK to `kbji_occupation` (`002:162`). Those rows cannot be imported as-is. | FAIL |
| 7 | Parent-code FKs exist | `kbji_hierarchy.parent_code` (`002:112`) and `kbji_occupation.parent_subgolongan_code` (`002:127`) have no FKs. All inspected parent values resolve to a hierarchy code, so the FKs are feasible. | FAIL |
| 8 | No fabricated KBJI hierarchy nodes | `2120` is not present in `KBJI_HIERARCHY`; the DDL does not fabricate it. | PASS |
| 9 | Junction reference data is valid | 22/22 `supporting_kbji_mapping_ids` references resolve; 7 mapping IDs are unreferenced (allowed). | PASS |

### 9.2 Proposed corrections (not executed)

- Add `FOREIGN KEY (kbji_mapping_id) REFERENCES okb.career_kbji_mapping(mapping_id) ON UPDATE CASCADE ON DELETE RESTRICT` to `career_occupation_kbji_mapping`.
- Add an explicit resolution model for `occupation_kbji2026_link.kbji2026_code` rather than a bare FK: either
  - add `target_resolution_status TEXT NOT NULL CHECK (...)` and a nullable FK, or
  - keep the code and add a `quarantine_reference` row for `2120` with a documented reason.
  Do **not** infer or fabricate a hierarchy node for `2120`.
- Make `career_kbji_mapping.occupation_id` nullable **or** quarantine the two unresolved rows. If nullable, add a `resolution_status`/`resolution_note` (not `validation_status`) and ensure the runtime never treats an unresolved mapping as a valid KBJI link. Preserve the raw rows for audit.
- Add self-FKs for `kbji_hierarchy.parent_code` and `kbji_occupation.parent_subgolongan_code` after confirming the intended parent target (both currently resolve to `kbji_hierarchy.kbji_code`).
- `career_kbji_mapping` has no `CHECK` on `validation_status`/`expert_review_status`. If retained for fidelity, add a comment and explicit allowed values; do not use them for eligibility.

---

## 10. Governance and eligibility

### 10.1 What the DDL contains

- `okb.workbook_review_approval` with `approval_id`, `workbook_sha256 UNIQUE NOT NULL`, reviewer identity/role, nullable `reviewed_at`, `review_scope`, `approval_status CHECK`, `recorded_at` (`005:3-12`).
- `okb.import_manifest` with workbook SHA-256 and import counts (`005:14-27`).
- `okb.evidence_link` with independent `target_resolution_status` and `source_resolution_status` CHECKs (`004:61-84`).
- `okb.source_register.can_contribute_to_scores BOOLEAN NOT NULL DEFAULT FALSE` (`004:19`).
- `okb.evidence_link_resolution_audit`, `okb.quarantine_reference`, `okb.etl_transform_log` (`005:29-60`).
- `operational_evidence_present`, `eligible_for_career_fit`, `eligible_for_skill_gap` on `career_occupations`, `skills`, `career_skills`, `tasks`, `technologies`, `occupation_source_mapping`, `career_kbji_mapping`.
- `okb.v_evidence_link_resolved` (`008:21-25`) filters `target_resolution_status='RESOLVED'` and `source_resolution_status='RESOLVED'` only.

### 10.2 What the runtime does

A repository-wide search found **zero** runtime references to:

`operational_evidence_present`, `eligible_for_career_fit`, `eligible_for_skill_gap`, `can_contribute_to_scores`, `scoring_eligible`, `eligibility_reason`, `eligibility_checked_at`, `dataset_approval_id`, `workbook_review_approval`, `evidence_link`, `source_register`, `v_evidence_link_resolved`.

The runtime evidence paths are:

- `evidence_repository.fetch_skill_source_evidence()` reads `okb.skill_source_evidence` and `okb.provenance` directly (`evidence_repository.py:17-26`);
- `evidence_repository.fetch_career_skill_evidence_text()` reads `career_skills.evidence_source` directly (`:37-42`);
- `retrieval_service.get_skill_evidence()` combines both (`retrieval_service.py:106-131`);
- `retrieval_service.get_occupational_context()` reads `career_skills`, `tasks`, `technologies`, and `occupation_source_mapping` directly (`:134-194`).

None of these paths filter by target resolution, source resolution, dataset approval, or `can_contribute_to_scores`.

### 10.3 Assessment

| # | Requirement | Finding | Status |
|---|---|---|---|
| 1 | `workbook_review_approval` supports a dataset-level approval bound to the exact workbook hash | The table has `workbook_sha256 UNIQUE NOT NULL` and approval status. | PASS |
| 2 | An approval row is bound to the current workbook hash `1314578e...` | No seed script or migration inserts a row. The only hash recorded in the T4-R2 design is the stale `792fdbff...` (`T4_R2_TARGET_DATABASE_SCHEMA.md:6`, `:322`). The current workbook is `1314578e...`. | FAIL |
| 3 | `scoring_eligible`, `eligibility_reason`, `eligibility_checked_at`, `dataset_approval_id` exist | None exist in any migration. `T4_R2_TARGET_DATABASE_SCHEMA.md:338-349` requires them. | FAIL |
| 4 | Runtime enforces dataset approval | No code reads `workbook_review_approval`. | FAIL |
| 5 | Runtime enforces target resolution | No code reads `evidence_link.target_resolution_status`. | FAIL |
| 6 | Runtime enforces source resolution | No code reads `evidence_link.source_resolution_status`. | FAIL |
| 7 | Runtime enforces `can_contribute_to_scores = TRUE` | No code reads it. Only 2 of 24 `SOURCE_REGISTER` rows have `TRUE`; the runtime would still return evidence from the 22 `FALSE` sources. | FAIL |
| 8 | `v_evidence_link_resolved` encodes the full eligibility rule | It checks only the two resolution statuses, not dataset approval or `can_contribute_to_scores`, and it is unused. | FAIL |
| 9 | Descriptive flags cannot bypass the approved eligibility conditions | The flags are inert at runtime today, so they do not currently bypass anything. But there is no constraint, trigger, or derivation that prevents `eligible_for_* = TRUE` from being set independently of approval/resolution/source permission. The approved conditions are simply not implemented. | FAIL |
| 10 | `operational_evidence_present` is not used as eligibility | No runtime reference. | PASS (narrow) |
| 11 | Workbook `eligible_for_*` flags are not the authority | The DDL imports/stores them but no runtime code reads them. | PASS (narrow) |
| 12 | `career_kbji_mapping.validation_status` is not used as an eligibility input | No runtime code reads it. | PASS (narrow) |
| 13 | The T5.2A-R1 claim "no per-record `validation_status` reintroduced" is true | The column exists in `okb.career_kbji_mapping` (`002:171-172`). | FAIL (claim is false) |
| 14 | The retained `validation_status` is explicitly marked descriptive/non-eligibility | No `COMMENT ON COLUMN` or guard exists. | FAIL |

### 10.4 `career_kbji_mapping.validation_status` provenance and recommendation

The workbook `CAREER_KBJI_MAPPING` has 29 rows:

- `validation_status`: 27 `NEEDS_REVIEW`, 2 `UNRESOLVED`, 0 `VALIDATED`.
- `expert_review_status`: 29 `PENDING`.

The column is part of the source workbook and is imported for fidelity. `T4_R2_TARGET_DATABASE_SCHEMA.md:345` explicitly permits retaining it as "descriptive only" and says it "**must not** be used in the eligibility computation." `T4_R2_TARGET_DATABASE_SCHEMA.md:352` says to preserve existing workbook columns for fidelity.

Therefore:

- **Do not remove the column** without tracing its provenance and purpose.
- Correct the T5.2A-R1 claim: the target model does **not** keep it out; it retains it as descriptive fidelity.
- Add `COMMENT ON COLUMN okb.career_kbji_mapping.validation_status IS 'Descriptive workbook fidelity only; not an eligibility input; runtime must not read.'` and the same for `expert_review_status`.
- Add a read-side guard/view that excludes these columns from eligibility logic, or at minimum document the prohibition in the repository/service layer.
- Do not add a per-record `validation_status = VALIDATED` gate: the approved eligibility model is dataset-level approval plus independent target/source resolution plus source permission (`T4_R2_TARGET_DATABASE_SCHEMA.md:322-336`).

---

## 11. Critical blockers and proposed corrections

No SQL or application code was modified. The following are proposals for a separate, approved change task.

### P0 — Blocks migration execution

**B1. Migration 007 uses invalid PostgreSQL syntax and duplicates inline FKs.**
- Evidence: `007_add_cross_schema_constraints.sql:4-14`; PG16 `ALTER TABLE` does not support `ADD CONSTRAINT IF NOT EXISTS`.
- Impact: migration 007 fails; if it were rewritten naively, it would create duplicate FKs already present in `006:68` and `006:79`.
- Correction: remove the two duplicate constraints; if a cross-schema constraint is genuinely needed, use a `DO $$` block that checks `pg_constraint` before `ALTER TABLE ... ADD CONSTRAINT`. Recommend deleting 007 or reducing it to a documented no-op.

**B2. `okb.technologies` conflates signal identity with catalog identity.**
- Evidence: `002:93-105`; 120 signal IDs, 63 distinct names, no `catalog_technology_id`.
- Impact: no valid FK to `technology_catalog`; catalog linkage is impossible without illegal ID reuse.
- Correction: rename/re-key to `technology_signal` with `technology_signal_id` + `catalog_technology_id` FK + `UNIQUE (occupation_id, catalog_technology_id)`. Do not add a naive FK to the existing column.

**B3. Target DDL lacks runtime-required columns.**
- Evidence: §8.4.2; `provenance.url`, `provenance.source_type`, `skill_source_evidence.mapping_basis`, `skill_source_evidence.provenance_id`, `occupation_source_mapping.mapping_basis`, `occupation_source_mapping.provenance_id`.
- Impact: `UndefinedColumn` against the target; the application cannot run.
- Correction: choose the DDL-compatibility or query-normalization option in §8.4.2, document the derivation, and add tests.

### P1 — Blocks a correct operational import

**B4. `career_occupation_kbji_mapping.kbji_mapping_id` has no FK.**
- Evidence: `002:149-157`; `career_kbji_mapping.mapping_id` is the PK; all 22 workbook refs resolve.
- Impact: orphan junction rows are possible; the intended relationship is not enforced.
- Correction: add the FK after verifying the 22 refs in a dry run.

**B5. `occupation_kbji2026_link.kbji2026_code` has no FK/resolution status; unresolved `2120` is silently admitted.**
- Evidence: `002:139-147`; `KBJI_HIERARCHY` has 30 codes and no `2120`; `OCCUPATION_KBJI2026_LINK` has `2120`.
- Impact: a link that references a non-existent hierarchy node looks valid.
- Correction: add a resolution-status model (target/source-style) and a nullable FK, or quarantine `2120` with an audit row. Do not fabricate a hierarchy node.

**B6. Two `career_kbji_mapping` rows have `occupation_id = NULL` against `NOT NULL`.**
- Evidence: `MAP-009`, `MAP-013`; `002:162`.
- Impact: import failure, or silent coercion if an importer fills a value.
- Correction: make the column nullable with a resolution status, or quarantine those two rows; preserve them for audit.

**B7. `career_kbji_mapping.validation_status`/`expert_review_status` contradict the T5.2A-R1 exclusion claim.**
- Evidence: `002:171-172`; `T5_2_TARGET_DDL_DESIGN.md:100`; `T4_R2_TARGET_DATABASE_SCHEMA.md:345`.
- Impact: reviewers may believe the columns are absent; future code may misuse them.
- Correction: retain for fidelity, add explicit comments/guards, and correct the design report claim.

**B8. `EVIDENCE_LINK` CHECK excludes TECHNOLOGY/TASK while the workbook contains 155 such rows.**
- Evidence: `004:75-83`; workbook counts 120 + 35.
- Impact: full import fails; or the importer silently drops rows without an audit.
- Correction: resolve the T4-R2 vs T5.2A conflict first. If T4-R2 controls, filter and audit the 155 rows; if T5.2A controls, expand the CHECK and add target validation. Do not choose silently.

### P1 — Blocks the approved evidence/eligibility boundary

**B9. No eligibility schema or runtime enforcement.**
- Evidence: §10; no `scoring_eligible`, no `dataset_approval_id`, no code references.
- Impact: any record can be read and scored regardless of approval, resolution, or source permission.
- Correction: add the four eligibility fields (or a central `record_eligibility` table), seed the current-hash approval, update the read views/queries to require all four conditions, and add tests. Do not use `operational_evidence_present` or workbook `eligible_for_*` flags.

**B10. `v_evidence_link_resolved` is incomplete and unused.**
- Evidence: `008:21-25`.
- Impact: even if used, it admits `can_contribute_to_scores = FALSE` sources and ignores dataset approval.
- Correction: add the source-permission join and approval condition, or create a dedicated scoring-eligibility view; wire it into the evidence read path.

**B11. Technology mentions can enter the competency evidence path.**
- Evidence: `profile_agent.py:44-57`, `121-158`; `skill_normalizer.py:45-62`; `user_repository.py:265-267`; `career_fit_service.py:178-180`.
- Impact: a technology mention can become a `linked` skill and receive full career-fit credit, violating the approved separation.
- Correction: add a distinct `technology_claims[]` extraction output, reject technology terms from `skills[]`, add an explicit type guard/allowlist, and add regression tests. Do not rely on the fact that no exact name overlap exists today.

### P2 — Fidelity and consistency

**B12. `source_register` drops `source_role`, `role_rationale`, `notes`.**
- Evidence: workbook 19 columns vs DDL 16 (`004:3-20`).
- Impact: data fidelity loss; no runtime break.
- Correction: add the nullable columns or document the deliberate omission.

**B13. `skills.status` is unsourced.**
- Evidence: `002:40`; workbook `SKILL` has no `status`; `career_repository.py:28` selects it.
- Impact: every imported skill gets `'active'` by DDL default, which is not a workbook fact.
- Correction: document the default as a schema shim, or add a reviewed source/derivation; do not present it as verified data.

**B14. `ProvenanceOut` required fields exceed DDL nullability.**
- Evidence: `schemas/retrieval.py:36-43` requires `document_id`, `document_title`, `version_or_year`, `source_type` as `str`; DDL columns are nullable/absent.
- Impact: Pydantic validation failure on null/absent data.
- Correction: make the fields optional or enforce non-null at import; align the response schema with the chosen DDL contract.

**B15. The T4-R2 approval hash is stale.**
- Evidence: `T4_R2_TARGET_DATABASE_SCHEMA.md:6` and `:322` use `792fdbff...`; current workbook is `1314578e...`.
- Impact: an approval bound to the design hash would not cover the current workbook.
- Correction: bind the approval to `1314578e44d4a66b21fd19effe441ed303dc2da2239423abf73dfb7d1c807353` and update the design text. Do not invent a review date.

### P0 — Unresolved design conflicts (must be decided before correction)

**B16. Technology scoring (Conflict C-1).**
- The design freeze/T3/T4-R2 prohibit technology from affecting fit/gap; the T5.2A-R2 instruction assumes a separate bonus.
- Correction: researcher decision required. If the freeze stands, do not build a bonus; if a bonus is approved, record a new explicit decision and a new audit. Do not treat the T5.2A-R1 "pending" language as approval.

**B17. TECHNOLOGY/TASK operational inclusion (Conflict C-2).**
- T4-R2 excludes them and retires the repository functions; T5.2A-R1 includes them; the runtime still reads them.
- Correction: researcher decision required. If T4-R2 controls, move them to staging or remove them from the operational path and remove the retrieval calls; if T5.2A-R1 controls, update T4-R2 and justify the operational read. Do not leave both contracts active.

---

## 12. Requirement status matrix

### 12.1 Technology catalog integrity

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| TC-1 | `technology_catalog` has a canonical PK and unique normalized value | PASS | `002:75-83` |
| TC-2 | `technology_alias` has a FK to the catalog and unique normalized alias | PASS | `002:85-91` |
| TC-3 | `technologies` links to `technology_catalog` | FAIL | No FK; `002:93-105` |
| TC-4 | `technologies` does not conflate signal and catalog identity | FAIL | Signal PK is `T001..T120`; no `catalog_technology_id` |
| TC-5 | `technologies` has an occupation FK | PASS | `002:97` |
| TC-6 | `tasks` is occupation-level | PASS | `002:62-73` |
| TC-7 | Catalog/alias source data or approved seed exists | FAIL | No workbook sheet/importer |
| TC-8 | Corrected relational design proposed | PASS | §5.3 |

### 12.2 Technology claim-to-evidence pipeline

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| TP-1 | Activity model/table exists | FAIL | No Activity table/model |
| TP-2 | Technology claim extraction exists | FAIL | `profile_agent.py:44-57` |
| TP-3 | Exact catalog/alias normalization exists | FAIL | No technology normalizer; `skill_normalizer.py:29-30` |
| TP-4 | NFKC/case-fold/trim/collapse implemented | FAIL | No NFKC; skills-only lower/strip/split |
| TP-5 | Alias collision fails deterministically | FAIL | Schema UNIQUE only; no runtime service |
| TP-6 | No fuzzy technology assignment | FAIL | `skill_normalizer.py:45-53` |
| TP-7 | Technology evidence stored separately from competency evidence | FAIL | No technology evidence store |
| TP-8 | Technology verification exists | FAIL | No verification path |
| TP-9 | Accepted technology evidence store exists | FAIL | No table/service |
| TP-10 | Bonus input accepts only accepted technology evidence | FAIL | No bonus; no accepted-evidence gate |
| TP-11 | Technology mentions cannot contribute via competency path | FAIL | `skills[]` → `evidence[]` → `linked` → fit |
| TP-12 | Unmatched technology claims remain traceable | FAIL | No claim table |

### 12.3 Career-fit integration

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| CF-1 | `compute_career_fit()` remains the single source of truth | PASS | `career_fit_service.py:141-210`; callers at `career_recommendation_agent.py:151`, `skill_gap_service.py:95`, `verification_agent.py:204` |
| CF-2 | Existing skill-matching formula preserved | PASS | `career_fit_service.py:167-205`; `scoring_weights.yaml` |
| CF-3 | Technology bonus is a separate component | FAIL | No technology parameter/field; conflicts with design freeze |
| CF-4 | Only accepted technology evidence can be bonus input | FAIL | No bonus/accepted-evidence gate |
| CF-5 | Bonus formula/weight/cap remain pending and are not hardcoded | PASS | No technology weight anywhere; no invented values |
| CF-6 | No competing career-fit implementation | PASS | Only `compute_career_fit()` |

### 12.4 Legacy user schema compatibility

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| LS-1 | All nine legacy tables exist with exact names | PASS | `006:3-96` |
| LS-2 | Repository-required columns exist | PASS | §8.1 |
| LS-3 | Primary keys and inline FKs | PASS | `006` |
| LS-4 | Unique constraints used by code (`users.email`, `user_skills(user_id, claimed_skill)`) | PASS | `006:5`, `006:74`; `user_repository.py:47`, `:220` |
| LS-5 | Cascade/relationship behavior | PASS (static) | `006` ON DELETE CASCADE/RESTRICT |
| LS-6 | Unqualified runtime SQL resolves under `search_path=app,okb` | PASS (target DB) | §8.2-8.3; T5.1 |
| LS-7 | Target `search_path` is active for the current runtime | FAIL / NOT VERIFIED | `.env` uses `career_intelligence` |
| LS-8 | No legacy user table outside the nine is referenced | PASS | Runtime scan |
| LS-9 | Migration 007 is executable and non-duplicative | FAIL | `007:4-14`; duplicates `006:68`, `006:79` |
| LS-10 | Runtime-selected columns exist in the target DDL | FAIL | §8.4.2 |
| LS-11 | `skills.status` runtime contract | PASS (shim) | `002:40`; workbook has no `status` |
| LS-12 | Exact legacy physical type/constraint parity | NOT VERIFIED | No legacy DDL/snapshot; no DB access |

### 12.5 KBJI relationship integrity

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| KJ-1 | `career_occupation_kbji_mapping.kbji_mapping_id` has a FK | FAIL | `002:149-157` |
| KJ-2 | Junction candidate key/PK is correct | PASS | `002:153` |
| KJ-3 | No semicolon-delimited operational relationship | PASS (DDL) / NOT VERIFIED (import) | `002`; workbook 22 refs |
| KJ-4 | `occupation_kbji2026_link.kbji2026_code` has a FK/resolution status | FAIL | `002:139-147` |
| KJ-5 | Unresolved `2120` is not silently admitted | FAIL | 2120 absent from hierarchy; no status |
| KJ-6 | `career_kbji_mapping` handles NULL `occupation_id` | FAIL | 2 rows; `002:162` NOT NULL |
| KJ-7 | Parent-code FKs exist | FAIL | `002:112`, `002:127` |
| KJ-8 | No fabricated hierarchy node | PASS | 2120 not added |
| KJ-9 | Junction references are valid | PASS | 22/22 |

### 12.6 Governance and eligibility

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| GV-1 | `workbook_review_approval` supports exact-hash dataset approval | PASS | `005:3-12` |
| GV-2 | Approval is bound to the current workbook hash | FAIL | No row/seed; design uses stale `792fdbff...` |
| GV-3 | `scoring_eligible`/`eligibility_reason`/`eligibility_checked_at`/`dataset_approval_id` exist | FAIL | Absent from migrations |
| GV-4 | Runtime enforces dataset approval | FAIL | No code references |
| GV-5 | Runtime enforces target resolution | FAIL | No code references |
| GV-6 | Runtime enforces source resolution | FAIL | No code references |
| GV-7 | Runtime enforces `can_contribute_to_scores` | FAIL | No code references |
| GV-8 | `v_evidence_link_resolved` encodes the full rule | FAIL | `008:21-25`; only two statuses |
| GV-9 | Descriptive flags cannot bypass eligibility | FAIL | No derivation/constraint; conditions unimplemented |
| GV-10 | `operational_evidence_present` is not treated as eligibility | PASS (narrow) | No runtime reference |
| GV-11 | Workbook `eligible_for_*` flags are not the authority | PASS (narrow) | No runtime reference |
| GV-12 | `validation_status` is not an eligibility input | PASS (narrow) | No runtime reference |
| GV-13 | T5.2A-R1 "no per-record validation_status" claim is true | FAIL | `002:171-172` |
| GV-14 | `validation_status` is explicitly marked descriptive/non-eligibility | FAIL | No comment/guard |

### 12.7 Cross-cutting conflicts and safety

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| X-1 | Technology scoring decision is consistent with the design freeze | FAIL (conflict) | `design-freeze.md:81-83`, `:453`; T5.2A-R1 §5 |
| X-2 | TECHNOLOGY/TASK operational decision is consistent across T4-R2 and T5.2A-R1 | FAIL (conflict) | T4-R2 `:122-123`, `:139`; `002:62-105`; `retrieval_service.py:178-179` |
| X-3 | EVIDENCE_LINK allowlist matches the imported workbook | FAIL | 120 TECHNOLOGY + 35 TASK rows vs `004:75-83` |
| X-4 | Technology mention boundary is enforced | FAIL | §6.3 |
| X-5 | Runtime has been tested against the target DDL | NOT VERIFIED | No SQL/DB/runtime execution in this task |
| X-6 | Migrations have been executed | NOT VERIFIED | Not permitted; T5.1 says target has no tables |
| X-7 | Tests exist for technology pipeline and eligibility | FAIL | No such tests; only skill-gap technology-name prompt-leak checks |
| X-8 | No database writes or configuration changes were made in this task | PASS | Read-only static audit |

---

## 13. Commands and tests actually executed

### 13.1 Static repository inspection

| Command | Result |
|---|---|
| `git status --short` | Listed pre-existing worktree changes; no changes made by this audit. |
| `git log -1 --oneline` | `24ab5c4 To evaluation` |
| `Get-FileHash -Algorithm SHA256 'data/occupational_knowledge_base_verified_v1_0_extended.xlsx'` | `1314578e44d4a66b21fd19effe441ed303dc2da2239423abf73dfb7d1c807353` |
| File reads via the repository file tools | All migrations, runtime modules, schemas, configuration, design/audit documents listed in §3. |
| `webfetch` of PostgreSQL 16 `ALTER TABLE` documentation | Confirmed `ADD table_constraint [NOT VALID]` has no `IF NOT EXISTS`; `ADD [COLUMN] [IF NOT EXISTS]` is column-only. |

### 13.2 Read-only workbook probes

These probes used `openpyxl` with `read_only=True, data_only=True`. They did not modify the workbook.

| Probe | Purpose | Result |
|---|---|---|
| `t52r2_final_probe.py` | Sheet/column inventory, technology/task/evidence-link/KBJI counts | 25 sheets; TECHNOLOGY 120/63 distinct names; TASK 35; EVIDENCE_LINK 970; CAREER_KBJI_MAPPING 27 NEEDS_REVIEW + 2 UNRESOLVED; KBJI_HIERARCHY 30, no 2120 |
| `t52r2_kbji_probe.py` | KBJI parent/code resolution and junction refs | All parents resolve; 22/22 junction refs valid; 2120 missing from hierarchy; 7 mappings unreferenced |
| `t52r2_ckm_probe.py` | `career_kbji_mapping.occupation_id` target namespace | 24 distinct KBJI occupation IDs + one null; none are `O01`-style occupation IDs |
| `t52r2_ckm_null_probe.py` | Null handling in `CAREER_KBJI_MAPPING` | `MAP-009` and `MAP-013` have `occupation_id = NULL` |
| `t52r2_headers_probe.py` | Provenance/source/evidence headers | `PROVENANCE` lacks `url`/`source_type`; `SOURCE_REGISTER` has 19 columns including `source_role`, `role_rationale`, `notes` |
| `t52r2_nulls_probe.py` | Null counts in imported core fields | No nulls in inspected CAREER/OCCUPATION/CAREER_SKILL/PROVENANCE/SOURCE_REGISTER fields |
| `t52r2_source_probe.py` | Source permission distribution | 2 TRUE / 22 FALSE `can_contribute_to_scores` |
| `t52r2_overlap_probe.py` | Exact skill/technology name overlap | 0 exact case-folded overlaps |
| `t52r2_tables_probe.py` | Runtime table-name scan | Only the nine user tables plus OKB tables |

### 13.3 Tests

**No tests were executed.** This task prohibited database-dependent tests, and the instruction's safety boundary was interpreted to exclude running the test suite. In particular, `backend/tests/test_career_fit_service_unit.py` was **not** run. No test result is claimed.

Static test inspection found:

- skill-gap tests use technology names only to assert they do not leak into prompts (`test_skill_gap_agent_unit.py:84`, `:154-160`);
- no test covers a technology claim → evidence → scoring path;
- no test covers eligibility approval, target/source resolution, or `can_contribute_to_scores`;
- no test covers the target DDL against the repository SQL.

---

## 14. Limitations and items not verified

The following are explicitly **not verified**:

1. **Actual migration execution.** No migration was run. The invalid 007 syntax is a static finding; the other migrations were not executed against PostgreSQL.
2. **Actual runtime behavior against the target database.** No connection was opened. All runtime findings are from source inspection.
3. **Exact legacy `public` schema parity.** No legacy DDL snapshot or database access was available; only the repository SQL contract was checked.
4. **Existence/content of a `workbook_review_approval` row.** The target database has no operational tables per T5.1, and this task did not query it. The finding is that no repository mechanism binds the current hash.
5. **Importer behavior.** No importer exists in the inspected runtime for the OKB tables; the workbook-to-table transformation (unit-ID padding, semicolon splitting, resolution computation) is not implemented or tested here.
6. **Pydantic runtime validation.** The nullability mismatches in §8.4.2 are static; no request/response cycle was executed.
7. **Data-level referential validity after import.** Workbook probes show 22/22 KBJI junction refs valid and 2120 unresolved, but no database-level FK check was run.
8. **PostgreSQL syntax of migrations 001-006 and 008 beyond the inspected constructs.** Only 007's `ADD CONSTRAINT IF NOT EXISTS` was checked against the PG16 grammar; the remaining DDL was reviewed statically but not parsed by PostgreSQL.
9. **Any technology bonus behavior.** No bonus exists; no behavior was tested. The design-freeze conflict is unresolved.

---

## 15. Conclusion and next step

The corrected T5.2A-R1 DDL is **not ready for execution** and the runtime is **not compatible with the target DDL** as written. The most important conclusions are:

- The technology catalog separation is conceptually correct but incorrectly keyed: `technologies.technology_id` must become a signal ID with a separate catalog FK.
- The technology claim-to-evidence pipeline is absent, and the runtime does not enforce the technology/competency evidence boundary.
- A technology bonus is **not approved** by the design freeze; the T5.2A-R2 instruction's bonus premise must be resolved by the researcher before any implementation.
- T4-R2 and T5.2A-R1 disagree on whether TECHNOLOGY/TASK are operational; the DDL and runtime currently follow T5.2A-R1, while the evidence-link CHECK follows T4-R2.
- Migration 007 cannot execute, and several runtime-required columns are missing from the target DDL.
- KBJI FKs and unresolved-reference handling are incomplete.
- Eligibility is documented but not implemented; no runtime code consults approval, resolution, or source permission.

**Recommended next step:** the researcher must first resolve the two governing conflicts (technology scoring and TECHNOLOGY/TASK operational inclusion). After that, a separate corrective DDL design task should address B1-B15, followed by a re-run of this verification. No SQL, migration, import, or application change should be made until those decisions are recorded.

---

## Appendix A — Workbook evidence used in this report

| Sheet | Rows | Relevant finding |
|---|---:|---|
| `CAREER` | 10 | Canonical careers; no nulls in inspected fields |
| `OCCUPATION` | 8 | `classification` contains `KBJI 2120` once |
| `CAREER_OCCUPATION` | 12 | 22 semicolon-delimited KBJI refs across 6 rows; all resolve |
| `SKILL` | 87 | No `status` column |
| `CAREER_SKILL` | 155 | Required skill relationships; no nulls in inspected fields |
| `TECHNOLOGY` | 120 | 120 signal IDs; 63 distinct case-folded names; no catalog/alias columns; all eligibility flags FALSE |
| `TASK` | 35 | All eligibility flags FALSE |
| `EVIDENCE_LINK` | 970 | 432 CAREER_SKILL, 174 SKILL, 120 TECHNOLOGY, 79 COMPETENCY_SKILL, 65 CAREER_OCCUPATION, 35 TASK, 29 CAREER_KBJI_MAPPING, 26 OCCUPATION_SOURCE_MAPPING, 10 OCCUPATION_COMPETENCY |
| `CAREER_KBJI_MAPPING` | 29 | 27 NEEDS_REVIEW, 2 UNRESOLVED; 29 PENDING expert review; `MAP-009`/`MAP-013` have NULL `occupation_id` |
| `KBJI_HIERARCHY` | 30 | 30 codes; no `2120` |
| `KBJI_OCCUPATION` | 75 | All parent codes resolve |
| `SOURCE_REGISTER` | 24 | 2 TRUE / 22 FALSE `can_contribute_to_scores`; 19 columns |
| `PROVENANCE` | 23 | 7 columns; no `url`/`source_type` |
| `OCCUPATION_SOURCE_MAPPING` | 25 | 11 columns; no `mapping_basis`/`provenance_id` |
| `SKILL_SOURCE_EVIDENCE` | 97 | 12 columns; no `mapping_basis`/`provenance_id` |

## Appendix B — Exact runtime contract mismatches

| Runtime select | DDL object | Missing/unsupported element | Consequence |
|---|---|---|---|
| `p.url` in `evidence_repository.py:21` | `okb.provenance` (`004:22-30`) | `url` column absent | `UndefinedColumn` |
| `p.source_type` in `evidence_repository.py:21` | `okb.provenance` (`004:22-30`) | `source_type` column absent | `UndefinedColumn` |
| `sse.mapping_basis` in `evidence_repository.py:19` | `okb.skill_source_evidence` (`004:46-59`) | `mapping_basis` column absent | `UndefinedColumn` |
| `sse.provenance_id` in `evidence_repository.py:23` | `okb.skill_source_evidence` (`004:46-59`) | `provenance_id` column absent | `UndefinedColumn` |
| `osm.mapping_basis` in `occupation_repository.py:65` | `okb.occupation_source_mapping` (`004:32-44`) | `mapping_basis` column absent | `UndefinedColumn` |
| `osm.provenance_id` in `occupation_repository.py:65` | `okb.occupation_source_mapping` (`004:32-44`) | `provenance_id` column absent | `UndefinedColumn` |
| `p.url`, `p.source_type` in `occupation_repository.py:67` | `okb.provenance` (`004:22-30`) | Both columns absent | `UndefinedColumn` |
| `s.status` in `career_repository.py:28` | `okb.skills` (`002:40`) | Column exists; workbook has no source value | DDL default `'active'` silently assigns an unsourced status |
| `s.source_type` in `retrieval_service.py:31` | `okb.provenance` / `ProvenanceOut` | Column absent; Pydantic field required `str` | `UndefinedColumn` / `ValidationError` |
| `s.mapping_basis` in `retrieval_service.py:121` | `okb.skill_source_evidence` | Column absent | `UndefinedColumn` |
| `r["mapping_basis"]` in `retrieval_service.py:186` | `okb.occupation_source_mapping` | Column absent | `UndefinedColumn` |

## Appendix C — Files that would need to change in a later, approved correction task

This is a planning aid only; **no file was changed** except the creation of this report.

| File | Proposed change |
|---|---|
| `database/migrations/postgresql/002_create_okb_core.sql` | Correct `technologies` key design; add KBJI FKs/resolution fields; add comments on `validation_status`/`expert_review_status` |
| `database/migrations/postgresql/004_create_okb_provenance.sql` | Add runtime-compatible columns or revise the contract; add source-fidelity columns |
| `database/migrations/postgresql/005_create_okb_governance.sql` | Add eligibility fields or a central eligibility table |
| `database/migrations/postgresql/007_add_cross_schema_constraints.sql` | Remove/replace invalid duplicate constraints |
| `database/migrations/postgresql/008_create_indexes_and_views.sql` | Correct the eligibility view and add indexes for new FKs |
| `backend/app/repositories/evidence_repository.py` | Align with the chosen provenance/evidence contract |
| `backend/app/repositories/occupation_repository.py` | Align with the chosen mapping/provenance contract; retire or stage tasks/technologies per the T4-R2 decision |
| `backend/app/services/retrieval_service.py` | Remove or stage task/technology reads if T4-R2 controls; add eligibility filtering |
| `backend/app/agents/profile_agent.py` | Add `technology_claims[]` and enforce the technology/skill boundary |
| `backend/app/agents/skill_normalizer.py` | Add a separate technology normalizer with NFKC/case-fold/alias rules; do not reuse fuzzy skill matching for technologies |
| `backend/app/schemas/retrieval.py` | Align `ProvenanceOut` nullability with the chosen DDL contract |
| `docs/design/T5_2_TARGET_DDL_DESIGN.md` | Correct the "no validation_status" and "technology bonus pending" claims; record the resolved conflicts |
| `docs/design/T4_R2_TARGET_DATABASE_SCHEMA.md` | Update the stale workbook hash and any TECHNOLOGY/TASK decision after researcher resolution |
