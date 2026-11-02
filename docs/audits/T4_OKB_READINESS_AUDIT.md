# T4 — Occupational Knowledge Base Readiness Audit

**Audit type:** Read-only readiness audit of the Occupational Knowledge Base (OKB) against the T1 design freeze, the T2 implementation audit, and the T3 Data Model and Pipeline Contract.
**Audit date:** 2026-11-02
**Repository revision inspected:** `7020a9f18ac3efa02f559f7eaac3faa95e8eef3c` (`7020a9f`, 2026-10-29) plus the pre-existing uncommitted working-tree changes listed by `git status`. No working-tree change was reverted.
**Database inspected:** configured runtime database `career_intelligence` on PostgreSQL 16.4 at `localhost:5433`, through a read-only transaction. Database identity was confirmed by query, not assumed.
**Overall T4 status:** **PARTIAL — audit executed; OKB data-ready gate not passed.**
**Scope safety:** No source code, prompt, schema, migration, SQL, workbook, database record, or configuration was changed. No import, migration, seed, CV analysis, LLM call, browser action, or application workflow was executed. No credential or secret is recorded in this report.

---

## 1. Executive summary and overall readiness status

The OKB's **core occupational layer is present, internally consistent, and live-verified**:

- Exactly **10** careers (`C01`–`C10`), **87** canonical skills (`S001`–`S087`), and **155** Career–Skill relationships are present in both the imported workbook and the live runtime database.
- There are no duplicate career IDs, skill IDs, canonical names, Career–Skill pairs, or relationship IDs; no orphan foreign-key references; no career without skills; and no skill without at least one career relationship.
- The live runtime database was reached read-only and its identity was confirmed. The workbook-derived tables match the live database row-for-row once the importer's documented transforms are applied (`competency_skills` unit-ID padding; numeric formatting for `technologies.frequency_pct` and `tasks.importance`).
- Every one of the 87 skills has career-level evidence text; 63 also have structured skill-source evidence. The 24 skills without structured evidence are handled by `evidence_repository.py`, which deliberately combines both evidence sources.

The OKB is **not yet readiness-complete**. Three material gaps block or constrain T5/T6:

1. **There is no technology catalog and no alias table.** `technologies` is a per-occupation market-signal table (120 rows, only 63 distinct names, 120 different IDs, the same name repeated under different IDs). It cannot serve as the global canonical technology identity required by T1 and T3. This is the primary T5 blocker.
2. **Snapshot/fingerprint behavior is not implemented.** There is no stable snapshot ID, deterministic canonical export, SHA-256 table manifest, source-file hash, or persisted import metadata. `analysis_log_service.py` and `inspection/artifact.py` both record `kb_version` as unavailable. This is a T6/reproducibility blocker.
3. **The schema has no checked-in DDL, migration, or seed artifacts.** The database exists, but the repository does not contain a reproducible schema definition. This is a T6/T10 reproducibility blocker.

Additional non-blocking but material limitations: 24/87 skills lack structured evidence (mitigated by career-level text), SKKNI standards `SK06`, `SK08`, `SK09` have zero units, no SKKNI element/KUK structure exists, IndoTask provenance is unresolved for 2 occupation mappings and 3 skill evidence rows, and the newer extended workbook is not imported and reports **0 VALIDATED records**.

**Readiness verdict:** the OKB is adequate for deterministic career-fit and skill-gap work over the existing 10-career/87-skill/155-relationship matrix, but it is **not ready** for technology normalization, snapshot-based reproducibility, or a fully reproducible database rebuild.

---

## 2. Source inventory and runtime usage

### 2.1 Inventory

| Path | Format | Role | Runtime use | Preparation use | Evidence |
|---|---|---|---|---|---|
| `data/occupational_knowledge_base_verified_v1_0.xlsx` | XLSX, 18 sheets, 55,399 bytes | Imported OKB source workbook (`v1.0-verified-working`) | **No.** The application never reads Excel. | **Yes.** Loaded by `backend/scripts/import_kb.py:13` and `backend/scripts/import_kb_fixed.py:13`. | SHA-256 `ce858a6aebe31d8237bf11217cce538d3cd657f4572d838866d2707b5536a630`; README sheet; importer constant `XLSX_PATH`. |
| `data/occupational_knowledge_base_verified_v1_0_extended.xlsx` | XLSX, 25 sheets, 167,387 bytes | Extended workbook (`v1.0 structure extended with v1.1.1 content`, 2026-11-01) | **No.** No repository file references it. | **No.** Not referenced by any importer, script, or configuration. | SHA-256 `792fdbffce25ad7266514e58a8f890877012d13ba672f13c386bacb4df39694d`; `git status` marks it untracked; repository-wide search for its filename returned no hits. |
| PostgreSQL database `career_intelligence` | Live relational DB, PostgreSQL 16.4, 25 public tables | **Actual runtime OKB** plus user-domain tables | **Yes.** `app/core/db.py` → `app/services/retrieval_service.py` → repositories. | Populated by the importer. | `SELECT current_database(), inet_server_port()` returned `career_intelligence`, `5433`; read-only transaction confirmed. |
| PostgreSQL database `career_intelligence_e2e_test` | Live relational DB | Isolated test/e2e database used by the guarded importer | **No**, unless `CAREER_DB_NAME` is explicitly changed. | Importer only permits this database. | `import_kb.py:15,24-45`; live probe returned 10/87/155/120 and 0 users. |
| `backend/scripts/import_kb.py` | Python | Canonical workbook importer (legacy workbook only) | Indirect (populates DB) | **Yes** | Loads 16 sheet groups; append-only; e2e safety gate; logs transforms to `etl_transform_log`. |
| `backend/scripts/import_kb_fixed.py` | Python | Near-duplicate of `import_kb.py` | Indirect (populates DB) | **Yes**, but redundant with `import_kb.py` | Same `XLSX_PATH` and safety gate. Which script is authoritative is not documented. |
| `backend/check_import_schema.py` | Python | Column-level schema comparison script | No | Diagnostic only | Hard-coded `../data/...v1_0.xlsx`; requires e2e DB; references an `ETL_TRANSFORM_LOG` sheet that does not exist in the legacy workbook. |
| `backend/app/repositories/{career,skill,occupation,evidence}_repository.py` | Python | Parametrized read-only SQL over KB tables | **Yes** | — | No ORM; no writes. |
| `backend/app/services/retrieval_service.py` | Python | Sole agent-facing OKB access layer | **Yes** | — | Opens short-lived connections; returns Pydantic objects. |
| `backend/app/services/analysis_log_service.py` | Python | Run logging | **Yes** | — | `KB_VERSION = "unavailable (Knowledge Base exposes no version identifier)"` (line 41). |
| `backend/app/inspection/artifact.py` | Python | Inspection artifact writer | **Yes** | — | `kb_version: "unavailable (not exposed by the implementation; Step 16 scope)"` (line 895). |
| `backend/artifacts/analysis_logs/*.json` | JSON run logs | Historical run artifacts, not OKB data | No | No | Not an OKB snapshot or manifest. |

### 2.2 What is absent

Repository inspection found **no** checked-in SQL/DDL, migration, Alembic, seed, JSON/CSV OKB export, canonical manifest, or snapshot artifact. The only schema-adjacent file is `backend/check_import_schema.py`, which compares columns on an e2e database and is not a DDL source of truth.

**Runtime source conclusion:** the application's OKB is the PostgreSQL database `career_intelligence`; the legacy workbook is a preparation-time source only; the extended workbook is not used anywhere. Presence of a workbook is not evidence of runtime use.

---

## 3. Exact 10-career verification

T1 and `AGENTS.md` freeze the scope as "exactly the 10 canonical careers in the existing Occupational Knowledge Base". The controlling documents do **not** enumerate an independent name list; the OKB is definitional. Verification therefore checks count, uniqueness, stability, and the absence of additional careers, not a separately approved list.

| `career_id` | `canonical_name` | `domain` | Career–Skill relationships |
|---|---|---|---|
| C01 | Backend Software Engineer | Software Engineering | 15 |
| C02 | Frontend Software Engineer | Software Engineering | 14 |
| C03 | Full-Stack Software Engineer | Software Engineering | 18 |
| C04 | Data Analyst | Data | 9 |
| C05 | Data Engineer | Data | 15 |
| C06 | Data Scientist | Data & AI | 21 |
| C07 | Machine Learning Engineer | AI/ML | 21 |
| C08 | DevOps Engineer | Infrastructure/Operations | 15 |
| C09 | Cybersecurity Engineer/Analyst | Cybersecurity | 12 |
| C10 | QA / Software Test Engineer | Software Quality | 15 |

**Result:**

- Expected count: **10**. Actual count: **10**.
- Missing careers: **none**.
- Unexpected additional careers: **none**.
- Duplicate `career_id`: **0**. Duplicate `canonical_name`: **0**.
- Identical in workbook `CAREER` sheet and live `careers` table.
- **Runtime boundary: not enforced.** `career_recommendation_agent.py:139` enumerates every row from `rs.get_all_careers()`. No allowlist, count assertion, or canonical-ID check exists in `retrieval_service.py`, the agents, or the workflow. The current database happens to contain exactly 10, so behavior is correct today by data, not by code. T2 already recorded this gap; T4 confirms it against the live data.

**WARNING:** because there is no independent enumeration of the 10 careers in the frozen documentation, any future accidental insertion into `careers` would silently expand the recommendation space.

---

## 4. Career–Skill relationship audit

### 4.1 Totals

| Metric | Value | Source |
|---|---|---|
| Career records | 10 | Workbook `CAREER`; live `careers` |
| Canonical skill records | 87 | Workbook `SKILL`; live `skills` |
| Career–Skill relationships | 155 | Workbook `CAREER_SKILL`; live `career_skills` |
| Distinct `relationship_id` | 155 | `CS001`–`CS155`; all unique |
| Duplicate `(career_id, skill_id)` pairs | 0 | live SQL `GROUP BY ... HAVING count(*) > 1` |
| Orphan `career_id` references | 0 | live LEFT JOIN check |
| Orphan `skill_id` references | 0 | live LEFT JOIN check |
| Careers with zero skills | 0 | live NOT EXISTS check |
| Skills with zero career relationships | 0 | live NOT EXISTS check |
| Relationships with blank `evidence_source` | 0 | live SQL |

### 4.2 Per-career counts

| Career | Relationships | CORE | SUPPORTING/COMPOSITE | High confidence | Medium confidence |
|---|---|---|---|---|---|
| C01 Backend Software Engineer | 15 | 15 | 0 | 15 | 0 |
| C02 Frontend Software Engineer | 14 | 14 | 0 | 14 | 0 |
| C03 Full-Stack Software Engineer | 18 | 18 | 0 | 0 | 18 |
| C04 Data Analyst | 9 | 9 | 0 | 0 | 9 |
| C05 Data Engineer | 15 | 15 | 0 | 15 | 0 |
| C06 Data Scientist | 21 | 21 | 0 | 21 | 0 |
| C07 Machine Learning Engineer | 21 | 0 | 21 | 0 | 21 |
| C08 DevOps Engineer | 15 | 15 | 0 | 0 | 15 |
| C09 Cybersecurity Engineer/Analyst | 12 | 12 | 0 | 12 | 0 |
| C10 QA / Software Test Engineer | 15 | 15 | 0 | 15 | 0 |
| **Total** | **155** | **134** | **21** | **92** | **63** |

The split is highly uneven: `C07 Machine Learning Engineer` is the only career whose entire relationship set is `SUPPORTING/COMPOSITE` at medium confidence, and `C03`–`C04`/`C08` are entirely medium-confidence. This is a legacy v1.0 labelling pattern, not a validated quality grade (see W-12).

### 4.3 B2 supply requirement

The data layer **can** supply the complete relationship set for all 10 careers: `retrieval_service.get_career_skills(career_id)` returns every relationship for a career, and the full set is 155 rows. However:

- There is **no implemented B2 all-10 structured payload builder**. The B2 requirement in `docs/evaluation/EXPERIMENT_SPEC.md` §2 and OP-04 is a T5 implementation item, consistent with T2's finding.
- No runtime component asserts that exactly the 10 frozen careers were supplied.

**Verdict:** data completeness **PASS**; runtime/B2 enforcement **FAIL (implementation gap, not a data defect)**.

---

## 5. Canonical skill identity audit

| Check | Result |
|---|---|
| Skills with stable canonical ID | **87/87**. Format `S001`–`S087`; stable in workbook and DB. |
| Duplicate `skill_id` | **0** |
| Duplicate `canonical_name` | **0** (DB also has `skills_canonical_name_key` UNIQUE) |
| Leading/trailing/double whitespace in names | **0** |
| Non-ASCII names | **0** |
| Case-variant name collisions | **0** |
| NFKC + case-fold + whitespace normalized-name collisions | **0** |
| Skill-group foreign keys resolve | **87/87** (`skill_group_id` → `skill_groups`) |
| Same canonical IDs used by profile extraction, career fit, skill gap, roadmap | **Yes.** All use `retrieval_service.get_all_skills()` / `get_career_skills()`; `skill_normalizer.py` only returns IDs present in the catalog. |

### 5.1 Normalization risks

`backend/app/agents/skill_normalizer.py` matches in this order: exact (case/whitespace-insensitive) → fuzzy `difflib` ratio ≥ **0.88** with a unique best → LLM-suggested ID only if it exists in the catalog → unmatched. Two canonical-name pairs sit at or above that fuzzy threshold:

| Similarity | Pair |
|---|---|
| 0.9231 | `S061` Performance Optimization ↔ `S087` Web Performance Optimization |
| 0.8852 | `S010` Cloud Infrastructure Management ↔ `S019` Data Infrastructure Management |

Exact matching resolves the canonical names themselves correctly, and the normalizer records the method used. The risk is a non-canonical user phrase that is closer to the wrong member of either pair; the result would be a wrong-but-real canonical ID rather than an invented one. This is a **WARNING**, not a data-integrity failure. T3 permits fuzzy normalization for competency claims but requires the method be recorded; it does not authorize fuzzy technology assignment.

### 5.2 Uniform status field

All 87 skills carry the identical string `VERIFIED CANONICAL / SOURCE-BACKED THROUGH RELATIONSHIPS`. This is a blanket label, not a per-skill validation result. There is no per-skill validation status column and no skill-alias/synonym table. `S003`, `S009`, `S010`, `S012`, `S013`, `S014`, `S019`, `S023`, `S025`, `S029`, `S042`, `S044`, `S046`, `S047`, `S050`, `S055`, `S056`, `S057`, `S058`, `S061`, `S066`, `S067`, `S070`, `S083` have no structured skill-level evidence, so the blanket status overstates what the structured evidence supports. **WARNING.**

---

## 6. Technology catalog and alias audit

### 6.1 What exists

`technologies` (workbook `TECHNOLOGY`; live table):

| Property | Value |
|---|---|
| Rows | 120 |
| Distinct `technology_id` | 120 (`T001`–`T120`) |
| Distinct `technology_name` | **63** |
| Occupations represented | 7 of 8 (`O01`–`O05`, `O07`, `O08`; `O06` absent) |
| Source | `O*NET/Lightcast`, 2025, geography `United States` (all 120 rows) |
| Rows per occupation | O01=25, O02=24, O08=19, O03=17, O05=14, O04=11, O07=10 |
| Names repeated under different IDs | 30 names, e.g. `Python` → `T001, T035, T050, T068, T084, T095, T102`; `Amazon Web Services AWS` → 7 IDs; `SQL` → 6 IDs |
| IDs mapping to more than one name | 0 |

### 6.2 What does not exist

- **No canonical technology catalog.** There is no table whose primary key is a technology identity independent of occupation. `technologies.technology_id` is effectively a per-occupation signal row, not a canonical technology ID.
- **No alias table.** No `technology_alias`, `technology_names`, or equivalent exists in the workbook, repository, or database. A database search for tables containing `alias`, `snapshot`, `import`, `manifest`, `fingerprint`, or `catalog` returned no results.
- **No NFKC/case-fold/whitespace normalization implementation for technology names.**
- **No exact-match catalog lookup implementation.**
- **No alias-collision validation.**
- **No fuzzy technology-ID assignment in application code** (grep found none). However, `backend/app/agents/skill_gap_grounding.py:166-175` derives ad-hoc grounding aliases from KB technology names (ALL-CAPS tokens and the name without a trailing ALL-CAPS token). That is a text-scanning heuristic, not a canonical alias catalog, and it does not assign technology IDs.

### 6.3 Verdict

**FAIL — blocker for T5.** T1 approved a global OKB technology catalog with an explicit alias list per canonical technology, NFKC/case-fold/whitespace normalization, exact matching, and cross-ID collision errors. T3 requires `technology_id`, `match_status`, `match_method`, and `catalog_fingerprint` against that catalog. None of the catalog/alias/fingerprint layer exists. The existing `technologies` rows are market-signal evidence, not the required catalog. They also carry US 2025 O*NET/Lightcast values and no provenance foreign key.

---

## 7. Occupational source traceability audit

### 7.1 Provenance records

| Check | Result |
|---|---|
| `provenance` rows | 23 |
| Blank `url` / `page_or_section` / `source_type` / `scope_note` | 0 / 0 / 0 / 0 |
| Sources | BPS KBJI (1), BPS (1), SKKNI (9), IndoTask / Bappenas (2), O*NET (9), ESCO (1) |
| `occupation_source_mapping` rows | 26 (O*NET 9, KBJI 8, ESCO 7, IndoTask 2) |
| `occupation_source_mapping.provenance_id` NULL | **2** (IndoTask), deliberately left NULL and logged as `evidence-unavailable-ambiguous-source` |
| `skill_source_evidence` rows | 97 (SKKNI 62, O*NET 32, IndoTask 3) |
| `skill_source_evidence.provenance_id` NULL | **3** (IndoTask), deliberately left NULL and logged |
| Structured evidence coverage | 63/87 skills |
| Skills with zero structured evidence | **24** |
| Those 24 with career-level evidence text | **24/24** |

The 24 skills without structured evidence are:
`S003, S009, S010, S012, S013, S014, S019, S023, S025, S029, S042, S044, S046, S047, S050, S055, S056, S057, S058, S061, S066, S067, S070, S083`.

`evidence_repository.py` explicitly documents that these must be combined with `career_skills.evidence_source`; reporting only `skill_source_evidence` would wrongly present 24 supported skills as unsupported. **PASS with WARNING.**

### 7.2 Career–Skill evidence text

`career_skills.evidence_source` is free text, has 155 non-blank values but only **7 distinct strings**, and has **no foreign key** to `provenance`:

- `SKKNI 282/2016; O*NET; ESCO` (47)
- `SKKNI 299/2020; O*NET; ESCO` (42)
- `SKKNI 268/2020; O*NET; ESCO` (15)
- `SKKNI 22/2019; O*NET` (15)
- `SKKNI 47/2017; O*NET` (15)
- `SKKNI 191/2024; O*NET` (12)
- `SKKNI 200/2021; 299/2020; O*NET; IndoTask where available` (9)

Each named standard resolves to a provenance record by document identifier, but the relationship itself is not machine-resolvable to a provenance row. **WARNING.**

### 7.3 SKKNI structure

| Standard | Number/Year | Unit inventory status | Units in dataset | Live units |
|---|---|---|---|---|
| SK01 | 282/2016 | COMPLETE | 47 | 47 |
| SK02 | 47/2017 | COMPLETE | 12 | 12 |
| SK03 | 22/2019 | PROFILE-COMPLETE | 25 | 25 |
| SK04 | 268/2020 | COMPLETE | 22 | 22 |
| SK05 | 299/2020 | COMPLETE | 21 | 21 |
| SK06 | 200/2021 | **PARTIAL** | **0** | **0** |
| SK07 | 191/2024 | COMPLETE | 19 | 19 |
| SK08 | 120/2025 | **PARTIAL** | **0** | **0** |
| SK09 | 103/2026 | **PARTIAL** | **0** | **0** |

- 9 standards, 146 units, 10 occupation–competency mappings, 79 competency–skill mappings.
- The raw workbook `COMPETENCY_SKILL` references unnormalized unit IDs (`CU191_1`, `CU299_14`, `CU47_9`, etc.). The importer zero-pads them to `CU191_001`, `CU299_014`, `CU47_009`; 34 rows are repointed and logged in `etl_transform_log`. After normalization, **0 orphan unit references** and **0 orphan skill references**.
- **No element or KUK (Kriteria Unjuk Kerja) tables exist** — only unit-level records. The audit cannot verify element/KUK structure because the source data does not contain it. **UNVERIFIED, not fabricated.**
- SK06/SK08/SK09 exist as standards with no units, explicitly flagged `PARTIAL` and "do not infer unit titles." This is honest handling, but it means those standards cannot support unit-level verification.

### 7.4 Other traceability gaps

- `technologies` and `tasks` rows carry a `source` string (`O*NET/Lightcast`, `O*NET`) but **no `provenance_id`**. Their signals cannot be resolved to a provenance record. **WARNING.**
- `O06 Network Professional` has 2 source mappings but **no Career–Occupation link**. It is unreachable from any career. **WARNING.**
- The extended workbook contains a much richer KBJI 2026 layer (75 occupations, 30 hierarchy nodes, 29 career mappings), 14 SKKNI standards, `SOURCE_REGISTER`, `EVIDENCE_LINK` (970 rows), and validation/eligibility flags. Its README states **0 records VALIDATED**, so **0 records are eligible in the PRIMARY experiment**, and it is not imported. Using it now would be an unapproved data-source change. **WARNING — out of runtime scope.**

---

## 8. Runtime/database parity status and limitations

### 8.1 Configuration and identity

- The application reads DB settings from `backend/.env` via `app/core/config.py` and `app/core/db.py` (`CAREER_DB_HOST`, `CAREER_DB_PORT`, `CAREER_DB_NAME`, `CAREER_DB_USER`, `CAREER_DB_PASSWORD`; optional `CAREER_DB_URL`).
- Configured target: database `career_intelligence`, host `localhost`, port `5433`.
- Live identity confirmed by `SELECT current_database(), inet_server_addr(), inet_server_port()` and `SHOW server_version`: `career_intelligence`, `::1:5433`, PostgreSQL 16.4.
- Every audit query ran inside `SET TRANSACTION READ ONLY`; `SHOW transaction_read_only` returned `on`. No write was attempted.

### 8.2 Live counts versus workbook counts

| Table | Workbook rows | Live rows | Match |
|---|---|---|---|
| careers | 10 | 10 | Yes |
| skills | 87 | 87 | Yes |
| career_skills | 155 | 155 | Yes |
| skill_groups | 17 | 17 | Yes |
| occupations | 8 | 8 | Yes |
| career_occupations | 12 | 12 | Yes |
| technologies | 120 | 120 | Yes |
| tasks | 35 | 35 | Yes |
| provenance | 23 | 23 | Yes |
| occupation_source_mapping | 26 | 26 | Yes |
| skill_source_evidence | 97 | 97 | Yes |
| skkni_standards | 9 | 9 | Yes |
| competency_units | 146 | 146 | Yes |
| occupation_competencies | 10 | 10 | Yes |
| competency_skills | 79 | 79 | Yes |
| etl_transform_log | computed | 157 | Yes (123 provenance derivations + 34 padding fixes) |

### 8.3 Row-set parity

A row-set comparison (not just counts) was performed for every workbook-derived table:

- **Exact row-set equality:** `careers`, `skill_groups`, `occupations`, `skills`, `career_occupations`, `career_skills`, `skkni_standards` (including the merged `STANDARD_COVERAGE` columns), `competency_units`, `occupation_competencies`, `provenance`, `occupation_source_mapping`, `skill_source_evidence`.
- **Equality after documented importer transforms:**
  - `competency_skills`: the workbook's raw unit IDs differ; after zero-padding normalization (34 rows, logged), the row set is identical.
  - `technologies`: identical after numeric normalization of `frequency_pct` (workbook `9` vs DB `9.00`).
  - `tasks`: identical after numeric normalization of `importance` (workbook `83` vs DB `83.00`).

No unexplained discrepancy was found. **Workbook → live database parity for the legacy workbook is established.**

### 8.4 Schema and constraints observed

- 25 public tables. KB tables: `careers`, `skills`, `skill_groups`, `occupations`, `career_occupations`, `career_skills`, `skkni_standards`, `competency_units`, `occupation_competencies`, `competency_skills`, `technologies`, `tasks`, `provenance`, `occupation_source_mapping`, `skill_source_evidence`, `etl_transform_log`.
- User-domain tables: `users`, `user_profiles`, `user_skills`, `user_skill_evidence`, `user_experience`, `user_projects`, `user_education`, `user_certifications`, `user_preferences`.
- Primary keys, foreign keys, and uniqueness constraints exist on the KB tables (e.g. `skills_canonical_name_key`, `career_skills_career_id_skill_id_key`, `competency_skills_unit_id_skill_id_key`). `career_occupations` and `occupation_competencies` use surrogate `id` primary keys; the workbook has no such column.
- **No DDL/migration/seed file exists in the repository**, so the live schema cannot be rebuilt from version control. **UNVERIFIED / WARNING.**

### 8.5 Isolation and live-data caution

- The configured database `career_intelligence` is **not empty**: 72 users, 6 profiles, 261 user skills, 90 evidence rows, 54 experiences, 51 projects, 27 education rows, 24 certifications. Any future import or migration must not run against it.
- `import_kb.py` correctly refuses to run unless `CAREER_E2E_ISOLATED_DB_OK=career_intelligence_e2e_test`, the database name is `career_intelligence_e2e_test`, the host is loopback, and `careers` is empty.
- The e2e database exists and currently holds 10 careers / 87 skills / 155 relationships / 120 technologies with 0 users. **Only its counts were checked; full e2e row-set parity was not audited.**

---

## 9. Snapshot/fingerprint readiness

T1 approved: a stable snapshot ID plus a SHA-256 manifest of canonicalized, deterministically ordered table exports, with source-file hash and import metadata recorded separately. T3 requires `catalog_fingerprint` on technology/competency claims and an OKB snapshot for candidate validation. `REPRODUCIBILITY_SPEC.md` §3 requires an OKB version or KB fingerprint in every run manifest.

| Required element | Implemented? | Evidence |
|---|---|---|
| Stable snapshot ID | **No** | No `snapshot_id` anywhere in repository or database. |
| Deterministic canonical export | **No** | No export/serialization code. |
| SHA-256 manifest of KB tables | **No** | No manifest generation; `hashlib` use in `app/inspection/*` is for run artifacts/PII redaction, not the OKB. |
| Source-file hash persisted | **No** | Importer reads the workbook but does not hash or persist its identity. |
| Import metadata persisted | **No** | No import-run table; `etl_transform_log` contains only row-level transforms. |
| Reproducible export ordering | **No** | No export exists. |
| Coverage of careers, skills, relationships, catalogs | **No** | Nothing to cover. |
| `kb_version` recorded in run logs | **No — explicitly unavailable** | `analysis_log_service.py:41`; `inspection/artifact.py:895`. |
| Diagnostics trace snapshot | Partial, not a fingerprint | `diagnostics/trace.py:405-449` records `career_count` and `requirement_count` from observed reads; no hash or version. |

**Verdict: FAIL — not implemented.** The audit computed SHA-256 values for the two workbook files only as audit evidence (reported in §2.1); it did **not** generate or store a production snapshot.

A related limitation: the extended workbook's own validation model reports **0 VALIDATED** records and **0 eligible records in the PRIMARY experiment**. Importing it would not, by itself, create a validated snapshot.

---

## 10. Findings

### 10.1 PASS

| ID | Finding | Evidence |
|---|---|---|
| P-01 | Exactly 10 careers, 10 distinct IDs, 10 distinct names; no missing/unexpected careers. | Workbook `CAREER`; live `careers`; §3. |
| P-02 | 87 canonical skills, 87 distinct IDs and names; no duplicates; stable `S001`–`S087`. | §5; live uniqueness checks. |
| P-03 | 155 Career–Skill relationships; no duplicate pairs, orphan careers, orphan skills, unreferenced skills, or skill-less careers. | §4; live LEFT JOIN / NOT EXISTS / HAVING checks. |
| P-04 | Live runtime DB reached read-only; identity confirmed; all 15 workbook-derived tables match after documented transforms. | §8; `current_database()`, row-set comparison. |
| P-05 | No foreign-key orphans in any KB table, including the normalized competency-skill references. | §8.4; live checks. |
| P-06 | 23 provenance records are complete (URL, page/section, source type, scope note); 87/87 skills have career-level evidence text and 63/87 have structured evidence. | §7.1. |
| P-07 | The evidence repository correctly combines structured and career-level evidence, avoiding a false "unsupported" report for 24 skills. | `backend/app/repositories/evidence_repository.py:1-51`; live 24/24 check. |
| P-08 | Canonical skill IDs are shared by profile extraction, career fit, skill gap, and roadmap through the single retrieval layer. | §5; `retrieval_service.py`, `skill_normalizer.py`. |
| P-09 | The importer is fail-closed and append-only, and refuses production/e2e cross-use unless explicitly opted in. | `import_kb.py:15-52`. |
| P-10 | The e2e database exists with matching core counts and empty user tables. | §8.5. |

### 10.2 FAIL

| ID | Finding | Evidence | Consequence |
|---|---|---|---|
| F-01 | **No global technology catalog.** `technologies` is a per-occupation signal table; 120 rows represent only 63 distinct names, each name repeated under different IDs. | §6; live `count(*)=120`, `count(distinct name)=63`. | T5 Technology Normalizer cannot resolve a canonical `technology_id`. |
| F-02 | **No technology alias table, normalization, exact lookup, or collision validation.** | §6.2; no alias table or code. | T1/T3 approved alias contract cannot be implemented or tested. |
| F-03 | **No snapshot/fingerprint/source-hash/import-metadata implementation.** | §9. | T6 verification cannot identify the OKB used by a run; experiment reproducibility is blocked. |
| F-04 | **No checked-in DDL, migration, or seed artifacts.** The live schema is unreproducible from the repository. | §2.2, §8.4. | T6/T10 cannot rebuild or audit the schema reproducibly; T7 risk. |
| F-05 | **No runtime enforcement of the 10-career boundary and no B2 all-10 structured payload builder.** | `career_recommendation_agent.py:139`; `EXPERIMENT_SPEC.md` §2; T2 gap. | Extra rows would be scored silently; B2 cannot yet be run as specified. |

### 10.3 WARNING

| ID | Finding | Evidence |
|---|---|---|
| W-01 | 24/87 skills have zero structured skill-source evidence; all 24 rely on career-level text. | §7.1; `evidence_repository.py`. |
| W-02 | `career_skills.evidence_source` is free text (7 distinct strings), not a FK to `provenance`. | §7.2. |
| W-03 | SKKNI `SK06`, `SK08`, `SK09` have zero units (explicitly `PARTIAL`); no element/KUK tables exist. | §7.3. |
| W-04 | `technologies` and `tasks` carry a source label but no `provenance_id`. | §7.4; live columns. |
| W-05 | `O06 Network Professional` has source mappings but no Career–Occupation link (unreachable). | §7.4; live NOT EXISTS. |
| W-06 | All 87 skills share one blanket `status` string; no per-skill validation status. | §5.2. |
| W-07 | Two skill-name pairs exceed the normalizer's 0.88 fuzzy threshold (`S061`/`S087`, `S010`/`S019`). | §5.1. |
| W-08 | Technology signals are US 2025 O*NET/Lightcast values with no Indonesian market layer; the extended workbook marks them historical/ineligible. | §6.1; extended README. |
| W-09 | The extended workbook is untracked, unimported, and reports 0 VALIDATED records; it is not a runtime source. | §2.1; extended README. |
| W-10 | The configured runtime DB contains live user data; any future import/migration must be isolated. | §8.5. |
| W-11 | The repository contains two near-duplicate importers (`import_kb.py`, `import_kb_fixed.py`); authority is undocumented. | §2.1. |
| W-12 | `skills.status` and `career_skills` confidence/mapping labels are legacy v1.0 labels, not validated evidence grades. | Workbook README; extended README. |

### 10.4 UNVERIFIED

| ID | Item | Why |
|---|---|---|
| U-01 | SKKNI element/KUK structure | No source tables or records; cannot be verified without fabricating them. |
| U-02 | Full row-set parity of `career_intelligence_e2e_test` | Only counts were checked; full e2e comparison was out of scope. |
| U-03 | Schema reproducibility / migration path | No DDL or migration artifacts exist. |
| U-04 | Extended-workbook validity and eligibility | README reports 0 VALIDATED; not imported; no runtime representation. |
| U-05 | B2 all-10 structured payload | Not implemented; T5 scope. |
| U-06 | Technology alias universe | No catalog or aliases exist to verify. |
| U-07 | Indonesian technology-market relevance | Data is US O*NET/Lightcast 2025; no local source layer. |
| U-08 | Whether the historical isolated snapshot described in `docs/PROJECT_STATE.md` is byte-identical to the current DB | Historical artifact; not required for current parity. |

---

## 11. Evidence and reproducible inspection steps

All inspection was read-only. No temporary artifact was added to the repository.

### 11.1 Repository evidence

- `backend/scripts/import_kb.py:13` — `XLSX_PATH = ... "occupational_knowledge_base_verified_v1_0.xlsx"`.
- `backend/scripts/import_kb.py:15-52` — e2e opt-in, loopback, database-name, and empty-careers gates.
- `backend/scripts/import_kb.py:117-159` — unit-ID padding normalization and transform logging.
- `backend/scripts/import_kb.py:176-252` — provenance FK derivation for occupation mappings and skill evidence.
- `backend/check_import_schema.py:6-25` — legacy workbook path and sheet→table map.
- `backend/app/repositories/skill_repository.py:11-15` — `SELECT skill_id, canonical_name, skill_group_id, status FROM skills`.
- `backend/app/repositories/occupation_repository.py:53-59` — `technologies` is per-occupation; no catalog join.
- `backend/app/repositories/evidence_repository.py:1-51` — dual evidence-source contract.
- `backend/app/services/retrieval_service.py:35-63` — `get_all_skills`, `get_all_careers`, `get_career_skills`.
- `backend/app/agents/career_recommendation_agent.py:137-149` — every DB career is scored.
- `backend/app/agents/skill_normalizer.py:18-66` — exact → fuzzy 0.88 → validated LLM → unmatched.
- `backend/app/services/analysis_log_service.py:41` — KB version unavailable.
- `backend/app/inspection/artifact.py:895` — KB version unavailable.
- `backend/app/diagnostics/trace.py:405-449` — counts only, no fingerprint.
- `docs/design-freeze.md:70-101,169-193,421-424` — OKB authority, technology-catalog/alias contract, snapshot format.
- `docs/design/T3_DATA_MODEL_AND_PIPELINE_CONTRACT.md:66-72,384-386` — technology claim fields and T4 verification dependency.
- `docs/evaluation/DECISIONS.md:12-13` — B0/B2 career and relationship scope.
- `docs/evaluation/EXPERIMENT_SPEC.md:31-46` — B2 all-10 complete relationship requirement.

### 11.2 Workbook evidence

Inspected with the project virtual environment (`backend/.venv/Scripts/python.exe`) and `openpyxl` in read-only mode. Sheets and row counts:

- Legacy: `README, CAREER (10), OCCUPATION (8), CAREER_OCCUPATION (12), SKILL_GROUP (17), SKILL (87), CAREER_SKILL (155), SKKNI_STANDARD (9), COMPETENCY_UNIT (146), OCCUPATION_COMPETENCY (10), COMPETENCY_SKILL (79), STATUS_AUDIT (16), OCCUPATION_SOURCE_MAPPING (26), TECHNOLOGY (120), TASK (35), PROVENANCE (23), SKILL_SOURCE_EVIDENCE (97), STANDARD_COVERAGE (9)`.
- Extended: 25 sheets including `SOURCE_REGISTER (24)`, `KBJI_HIERARCHY (30)`, `KBJI_OCCUPATION (75)`, `OCCUPATION_KBJI2026_LINK (8)`, `CAREER_KBJI_MAPPING (29)`, `EVIDENCE_LINK (970)`, `KJN_SOURCE_CLAIMS (13)`; `SKKNI_STANDARD (14)`; `SKILL` has no `status` column; `TECHNOLOGY` has no `geography`; `PROVENANCE` has no URL/page/source-type columns.

### 11.3 Live database evidence

Read-only SQL executed against `career_intelligence` (exact queries reproduced below; results in §8):

```sql
SET TRANSACTION READ ONLY;
SELECT current_database(), current_user, inet_server_addr()::text, inet_server_port();
SHOW server_version;
SELECT table_name FROM information_schema.tables
 WHERE table_schema = 'public' ORDER BY table_name;

SELECT count(*) FROM careers;            -- 10
SELECT count(*) FROM skills;             -- 87
SELECT count(*) FROM career_skills;      -- 155
SELECT count(*) FROM technologies;       -- 120
SELECT count(*) FROM skill_source_evidence; -- 97

SELECT career_id, count(*) FROM career_skills GROUP BY career_id ORDER BY career_id;

SELECT count(*) FROM career_skills cs
 LEFT JOIN careers c ON c.career_id = cs.career_id WHERE c.career_id IS NULL;  -- 0
SELECT count(*) FROM career_skills cs
 LEFT JOIN skills s ON s.skill_id = cs.skill_id WHERE s.skill_id IS NULL;      -- 0
SELECT count(*) FROM (
  SELECT career_id, skill_id FROM career_skills
  GROUP BY career_id, skill_id HAVING count(*) > 1) x;                          -- 0
SELECT count(*) FROM skills s
 WHERE NOT EXISTS (SELECT 1 FROM career_skills cs WHERE cs.skill_id = s.skill_id); -- 0

SELECT count(*) AS rows, count(DISTINCT technology_id) AS ids,
       count(DISTINCT technology_name) AS names FROM technologies;              -- 120,120,63
SELECT technology_name, count(*), count(DISTINCT technology_id)
 FROM technologies GROUP BY technology_name HAVING count(*) > 1;

SELECT count(*) FROM occupation_source_mapping WHERE provenance_id IS NULL;     -- 2
SELECT count(*) FROM skill_source_evidence WHERE provenance_id IS NULL;         -- 3
```

Row-set parity was computed by exporting each workbook sheet and each live table and comparing tuples after:
(a) dropping `skill_name` where the importer drops it, (b) zero-padding `CU<standard>_<n>` unit IDs, (c) normalizing numeric formatting.

### 11.4 Source-file identity

| File | Size | SHA-256 |
|---|---|---|
| `data/occupational_knowledge_base_verified_v1_0.xlsx` | 55,399 | `ce858a6aebe31d8237bf11217cce538d3cd657f4572d838866d2707b5536a630` |
| `data/occupational_knowledge_base_verified_v1_0_extended.xlsx` | 167,387 | `792fdbffce25ad7266514e58a8f890877012d13ba672f13c386bacb4df39694d` |

These hashes are audit evidence only; they are not a production snapshot.

---

## 12. Blocking issues that must be resolved before T5/T6

### 12.1 T5 blockers

1. **Technology catalog and aliases (F-01, F-02).** T5 cannot implement the approved Technology Normalizer without a global canonical technology catalog and explicit aliases. The current `technologies` table cannot be used as canonical identity because one technology name maps to multiple IDs.
2. **Runtime 10-career boundary and B2 payload (F-05).** T5 must add an allowlist/count check and the structured all-10 Career–Skill payload required by OP-04 and `EXPERIMENT_SPEC.md` §2.
3. **Catalog fingerprint input.** T3 requires `catalog_fingerprint`; it cannot be populated until the snapshot/fingerprint mechanism exists (F-03). This may be staged, but T5 should not silently emit `null` without a documented fallback.

### 12.2 T6 blockers

4. **Snapshot/fingerprint/import metadata (F-03).** T6 verification and experiment manifests need a stable OKB identity. Without it, a verification result cannot be tied to a specific OKB state.
5. **Schema reproducibility (F-04).** T6/T7/T10 need a checked-in schema or migration path to rebuild and test the database reproducibly.
6. **Technology/task provenance (W-04).** Verification of technology provenance cannot resolve because those rows have no `provenance_id`.
7. **Partial SKKNI standards (W-03).** Verification must not require units for `SK06`, `SK08`, `SK09`, and must not claim element/KUK validation.
8. **Dual evidence source (W-01).** Verification must preserve the `career_skills.evidence_source` fallback for the 24 skills or it will incorrectly report supported skills as unsupported.
9. **Live production data (W-10).** T6/T7 must use `career_intelligence_e2e_test`, not `career_intelligence`.

---

## 13. Non-blocking issues that can be deferred

- `O06 Network Professional` has no Career–Occupation link (W-05); harmless while no career maps to it.
- Two near-duplicate skill-name pairs at the fuzzy threshold (W-07); monitor normalizer decisions, do not rename canonical skills without approval.
- Blanket `skills.status` string (W-06); replace with a real per-skill validation status in a later data-quality pass.
- Free-text `career_skills.evidence_source` (W-02); acceptable for explanation, not for machine-resolved provenance.
- Duplicate importer scripts (W-11); consolidate after T4, with tests.
- US-only technology-market data (W-08); a documented scope limitation, not a runtime defect.
- Extended workbook integration (W-09); requires researcher approval and a validation plan, and currently contains 0 VALIDATED records.
- `check_import_schema.py` references a non-existent `ETL_TRANSFORM_LOG` sheet; diagnostic-only script, not on the runtime path.

---

## 14. Recommended remediation order (not implemented)

1. **Record the current OKB identity.** Capture the legacy workbook SHA-256, DB identity, server version, import script revision, and row counts. Treat this as audit evidence until a formal snapshot is approved.
2. **Design and approve the snapshot format** (stable ID + canonical table exports + SHA-256 manifest + source-file hash + import metadata) and add a read-only generator. Do not generate a production snapshot during T4.
3. **Add a canonical technology catalog and alias table** as an approved schema change, with NFKC/case-fold/whitespace exact matching, uniqueness constraints, and cross-ID collision checks. Keep the existing per-occupation `technologies` signals separate.
4. **Populate the technology catalog only from approved sources**, preserving source provenance and the Indonesian-context limitation. Do not convert technology mentions into competency evidence.
5. **Add provenance links for technology and task records**, or explicitly mark them `evidence-unavailable` per the T3 fail-closed rule.
6. **Decide the extended-workbook question**: whether KBJI 2026, the 14 SKKNI standards, `SOURCE_REGISTER`, and `EVIDENCE_LINK` are adopted. It cannot be adopted while `0 VALIDATED`.
7. **Complete or formally scope out SK06/SK08/SK09 unit inventories**, and decide whether element/KUK structure is required.
8. **Add DDL/migrations to version control** and a documented rebuild procedure for the e2e database.
9. **Implement the runtime 10-career allowlist and the B2 all-10 structured payload** in T5.
10. **Add a schema/import-metadata test suite** before any experiment run, and keep all tests on the e2e database.

---

## 15. Explicit T4 exit-criteria table

| # | Exit criterion | Result | Evidence / reason |
|---|---|---|---|
| E1 | All OKB source files and their runtime role are identified. | **PASS** | §2; only the legacy workbook is imported; extended workbook unused. |
| E2 | Exactly 10 canonical careers verified; no duplicates or extras. | **PASS** | §3; 10/10 in workbook and DB. |
| E3 | 87 canonical skills verified with stable IDs and no duplicates. | **PASS** | §5; 87/87, unique IDs/names, NFKC collisions 0. |
| E4 | 155 Career–Skill relationships verified with per-career counts and no orphans/duplicates. | **PASS** | §4; live integrity checks all 0. |
| E5 | Canonical IDs are consistent across profile, fit, gap, and roadmap. | **PASS** | §5; single retrieval layer. |
| E6 | A global technology catalog and alias mechanism exist and are valid. | **FAIL** | §6; no catalog, no aliases, no normalized lookup. |
| E7 | Source provenance is recorded and resolvable per career/skill. | **PASS with WARNING** | §7; 23 provenance records; 24 skills rely on career text; 2+3 IndoTask links NULL. |
| E8 | SKKNI units/elements/KUK are distinguished where the source supports it. | **UNVERIFIED / PARTIAL** | §7.3; 9 standards, 3 with zero units; no element/KUK records. |
| E9 | Runtime database was actually inspected read-only and identified. | **PASS** | §8; `current_database()`, read-only transaction, PG 16.4. |
| E10 | Workbook/database parity is established and discrepancies explained. | **PASS** | §8; 12 tables exact, 3 after documented transforms, 0 unexplained. |
| E11 | Snapshot/fingerprint/source-hash/import-metadata behavior is implemented. | **FAIL** | §9; none implemented; `kb_version` unavailable. |
| E12 | Schema/DDL/migration artifacts exist for reproducibility. | **FAIL (UNVERIFIED)** | §2.2, §8.4; no repository DDL. |
| E13 | All findings have reproducible evidence. | **PASS** | §11; paths, IDs, SQL, hashes. |
| E14 | Blockers for T5/T6 are identified. | **PASS** | §12. |
| E15 | No implementation, import, migration, seed, LLM call, or workflow was executed. | **PASS** | Read-only inspection only; `transaction_read_only=on`. |

**T4 stage decision:** **PARTIAL.** The audit itself is complete for every inspectable item, but the OKB readiness gate is not passed because E6 and E11 fail and E8/E12 remain unverified/absent. `docs/master_checklist_pra_ablation.md` records this as audit progress, not as a completed data-ready gate.

---

## 16. Limitations of this audit

- Parity is established for the legacy workbook only; the extended workbook is not imported and was not compared to the database.
- The audit used the configured live database `career_intelligence`; the e2e database was checked for counts only.
- No independent enumeration of the 10 approved career names exists in the controlling documents; the OKB is definitional.
- The audit did not validate the substantive correctness of occupational requirements against the original SKKNI/O*NET/ESCO documents; it verified presence, identifiers, structure, and internal consistency, not expert content validity.
- No KUK/element data exists to verify.
- The SHA-256 values in §11.4 identify the inspected files; they are not a stored OKB snapshot.

**No T5 work was started and no implementation was modified after T4.**
