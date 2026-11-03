# T4-R1A — Audit Clarification for Extended OKB Workbook

**Audit type:** Read-only clarification audit  
**Date:** 2026-11-02  
**Audited workbook:** `data/occupational_knowledge_base_verified_v1_0_extended.xlsx`  
**Workbook SHA-256:** `792FDBFFCE25AD7266514E58A8F890877012D13BA672F13C386BACB4DF39694D`  
**Reference workbook:** `data/occupational_knowledge_base_verified_v1_0.xlsx` (SHA-256 `CE858A6AEBE31D8237BF11217CCE538D3CD657F4572D838866D2707B5536A630`)  
**Context:** Clarifies inconsistencies in [`docs/audits/T4_R1_EXTENDED_WORKBOOK_STRUCTURAL_AUDIT.md`](T4_R1_EXTENDED_WORKBOOK_STRUCTURAL_AUDIT.md). No modifications made to workbook, code, database, or existing audit files.  

---

## 1. Executive Summary

This is a strictly read-only clarification of the extended OKB workbook. Key verified findings:

- **File identity confirmed:** The extended workbook is the correct primary file (25 sheets, 167387 bytes, SHA-256 as above).  
- **Eligibility vs operational evidence are distinct.** `operational_evidence_present` exists on many sheets with TRUE/FALSE values; `eligible_for_career_fit` and `eligible_for_skill_gap` are **all FALSE** on every row that has them (552 rows across CAREER_OCCUPATION/SKILL/CAREER_SKILL/OCCUPATION_COMPETENCY/COMPETENCY_SKILL/OCCUPATION_SOURCE_MAPPING/TECHNOLOGY/TASK/CAREER_KBJI_MAPPING). No `eligible_for_scoring` column exists anywhere. Per README, eligibility requires `validation_status=VALIDATED` and a qualifying link from a source with `can_contribute_to_scores=TRUE`; **there are 0 VALIDATED records**.  
- **EVIDENCE_LINK is polymorphic.** 969/970 record references resolve to their intended target sheets; there is **1 orphan**: `OCCUPATION_SOURCE_MAPPING` record `OSM002` (referenced by EV-00881 with `source_id='SRC'`) does not exist in `OCCUPATION_SOURCE_MAPPING` (and `OSM002` was removed in extended). Source resolution is broken for many links: `SRC` (274), `SRC-` (138) not in `SOURCE_REGISTER`; `SRC-KBJI-2014-2026` used by 8 OSM rows not in `SOURCE_REGISTER`.  
- **35 duplicate triples** on `(record_table, record_id, source_id)` involve 92 rows; they are **not fully identical rows**: all 970 rows are distinct on the 5 fields `(record_table, record_id, source_id, standard_id, evidence_component)`, so each duplicate triple differs in `standard_id` and/or `evidence_component`. The triple is not a valid unique key.  
- **KBJI `2120`** is the classification/code used for O08 (`OCCUPATION.classification='KBJI 2120'`, `OCCUPATION_KBJI2026_LINK.kbji2026_code='2120'`, `OSM023.source_code='2120'`) but **does not appear in `KBJI_HIERARCHY` or `KBJI_OCCUPATION`**. It is plausibly a valid KBJI 2026 code missing from the extracted hierarchy subset; target should be verified against KBJI structure (link basis says "KBJI 2026 text extract line 10869" but hierarchy is curated subset).  
- **24 skills without `SKILL_SOURCE_EVIDENCE` rows** do have evidence: all 24 have non-empty `CAREER_SKILL.evidence_source` and **all 24 have EVIDENCE_LINK rows** (mostly derived via CAREER_SKILL/COMPETENCY_SKILL with `SRC-SKKNI` and `standard_id` SK01/SK03/SK04/SK05/SK06/SK07, plus some `SRC`/`SRC-`/`SRC-INDOTASK` entries). They are not unsupported — they are covered at career/skill-link level with traceability.  
- **SKKNI:** 8/14 standards have 0 units (`SK06`,`SK08`,`SK09`,`SK10`,`SK11`,`SK12`,`SK13`,`SK14`); `SK06`,`SK08`,`SK09` marked `PARTIAL` in `STANDARD_COVERAGE` with "do not infer unit titles"; `SK10-SK14` have no `STANDARD_COVERAGE` row and `record_origin='V0_1_SCREENING'`. README states unit titles intentionally not fabricated.

---

## 2. Audit Scope and Method

- **Read-only only.** No workbook/code/DB/schema/migration changes.  
- **Files inspected:** `data/occupational_knowledge_base_verified_v1_0_extended.xlsx` (primary), `data/occupational_knowledge_base_verified_v1_0.xlsx` (reference), `docs/audits/T4_R1_EXTENDED_WORKBOOK_STRUCTURAL_AUDIT.md`, `backend/app/repositories/evidence_repository.py`, `backend/app/services/retrieval_service.py`, `backend/scripts/import_kb_fixed.py`, `docs/PROJECT_STATE.md`, `instruction.md`.  
- **Method:** OpenPyXL traversal, direct JSON extraction of raw workbook data, cross-sheet validation, candidate key analysis, polymorphic reference validation, duplicate analysis, and code inspection. Temporary scripts created only in `C:\Users\My Thinkpad\AppData\Local\Temp\opencode\` (outside repo).  
- **Hash confirmed:** Extended workbook SHA-256 `792FDBFFCE25AD7266514E58A8F890877012D13BA672F13C386BACB4DF39694D` (matches repository state).  

---

## 3. Eligibility and Operational Flag Clarification

### Flag inventory (verified)

| Sheet | Flag columns | Values (counts) | Notes |
|---|---|---|---|
| CAREER_OCCUPATION (12) | `operational_evidence_present` | TRUE=7 (58.33%), FALSE=5 (41.67%) | `eligible_for_career_fit`=FALSE all, `eligible_for_skill_gap`=FALSE all |
| SKILL (87) | `operational_evidence_present` | TRUE=49 (56.32%), FALSE=38 (43.68%) | both eligibility FALSE all |
| CAREER_SKILL (155) | `operational_evidence_present` | TRUE=94 (60.65%), FALSE=61 (39.35%) | both eligibility FALSE all |
| OCCUPATION_COMPETENCY (10) | `operational_evidence_present` | TRUE=10 (100%) | both eligibility FALSE all |
| COMPETENCY_SKILL (79) | `operational_evidence_present` | TRUE=79 (100%) | both eligibility FALSE all |
| OCCUPATION_SOURCE_MAPPING (25) | `operational_evidence_present` | FALSE=25 (100%) | both eligibility FALSE all |
| TECHNOLOGY (120) | `operational_evidence_present` | FALSE=120 (100%) | both eligibility FALSE all |
| TASK (35) | `operational_evidence_present` | FALSE=35 (100%) | both eligibility FALSE all |
| CAREER_KBJI_MAPPING (29) | `operational_evidence_present` | TRUE=27 (93.1%), FALSE=2 (6.9%) | both eligibility FALSE all |
| SOURCE_REGISTER | `can_contribute_to_scores` | TRUE=2 (SRC-KBJI, SRC-SKKNI), FALSE=22 | Other flags present (selection_status/source_role/verification/permission) |

**Examples by flag value:** `operational_evidence_present=TRUE` → `C01` (CAREER_OCCUPATION), `S001` (SKILL), `C01` (CAREER_SKILL), `OCC-01` (OCCUPATION_COMPETENCY), `CK001` (COMPETENCY_SKILL), `MAP-001` (CAREER_KBJI_MAPPING). `operational_evidence_present=FALSE` → `C03` (CAREER_OCCUPATION), `S003` (SKILL), `CS005` (CAREER_SKILL), `OSM001` (OCCUPATION_SOURCE_MAPPING), `O01` (TECHNOLOGY/TASK), `MAP-009` (CAREER_KBJI_MAPPING). `eligible_for_career_fit` / `eligible_for_skill_gap` → FALSE on every row, e.g. `C01`, `S001`, `CS001`, `OCC-01`, `CK001`, `OSM001`, `MAP-001`.

### Supporting status / source-governance columns (verified)

These columns do **not** grant scoring eligibility; they describe validation, review, lifecycle, or source selection. All have 0 nulls unless stated.

| Sheet | Column | Values (counts) | Example | Meaning / effect on eligibility |
|---|---|---|---|---|
| CAREER_OCCUPATION | `confidence` | medium 8, high 4 | C03 | Mapping confidence only |
| CAREER_SKILL | `confidence` | high 92, medium 63 | C01 | Mapping confidence only |
| OCCUPATION_COMPETENCY | `mapping_confidence` | strong 3, working 2, supporting 2, mixed 1, strong/mixed 1, composite 1 | OCC-03 | Mapping confidence only |
| OCCUPATION_SOURCE_MAPPING | `confidence` | high 20, medium 5 | OSM001 | Mapping confidence only |
| SKILL_SOURCE_EVIDENCE | `confidence` | high 94, medium 3 | SRC-SKKNI | Evidence confidence only |
| PROVENANCE | `record_status` | RETAINED_LEGACY 21, SUPERSEDED_LEGACY 2 | SRC-SKKNI (retained), SRC-KBJI-2014 (superseded) | Provenance lifecycle; does **not** set eligibility |
| SOURCE_REGISTER | `can_contribute_to_scores` | TRUE 2 (`SRC-KBJI`, `SRC-SKKNI`), FALSE 22 | SRC-KBJI | **Scoring-source eligibility** (the only such switch) |
| SOURCE_REGISTER | `selection_status` | PENDING_AUDIT 17, CORE 4, OPTIONAL 3 | SRC-ATS-GREENHOUSE | Source-selection workflow, not record eligibility |
| SOURCE_REGISTER | `source_role` | MARKET_SOURCE_CANDIDATE 11, NON_OPERATIONAL_PENDING_DECISION 3, CARRIER_COPY 3, LEGACY_REFERENCE 2, CANDIDATE_REFERENCE 2, OPERATIONAL_PRIMARY 1, OPERATIONAL_STANDARD 1, HISTORICAL_REFERENCE 1 | SRC-KBJI (`OPERATIONAL_PRIMARY`) | Primary/secondary source classification |
| SOURCE_REGISTER | `permission_status` | NOT_APPLICABLE 12, UNKNOWN 10, NOT_PERMITTED 2 | SRC-JOB-GLINTS (`NOT_PERMITTED`) | Usage permission, not record eligibility |
| SOURCE_REGISTER | `verification_metadata` | NOT_VERIFIED 15, VERIFIED_PRIMARY (docs opened) 3, plus 6 one-off descriptive values | SRC-KBJI | Source verification only |
| SOURCE_REGISTER | `license_status` / `verification_content` | 22 `NOT_VERIFIED` + 2 descriptive / 9 `NOT_VERIFIED` + 15 descriptive | SRC-KBJI-TEXT | Source-level checks only |
| CAREER_KBJI_MAPPING | `validation_status` | NEEDS_REVIEW 27, **UNRESOLVED 2**, **VALIDATED 0** | C01 (NEEDS_REVIEW), C03 (UNRESOLVED) | **Validation gate; no row is VALIDATED** |
| CAREER_KBJI_MAPPING | `expert_review_status` | PENDING 29 | C01 | **No expert review completed** |
| CAREER_KBJI_MAPPING | `coverage_status` | STRONG 14, PARTIAL 13, NOT_VERIFIED 2 | C01 | Coverage assessment only |
| CAREER_KBJI_MAPPING | `confidence_level` | L4_WEAK 14, L3_PARTIAL_SCOPE 6, L2_STRONG_SCOPE 6, L1_EXPLICIT 1, **null 2** | C01 | Mapping confidence; 2 nulls |
| KBJI_HIERARCHY / KBJI_OCCUPATION | `verification_status` | VERIFIED_PRIMARY 30 / 75 | OCC-KBJI26-1 | Source verification only |
| OCCUPATION_KBJI2026_LINK | `match_type` | exact_code+normalized_title 5, exact_code+title_differs 3 | O01 / O04 | Match quality only |
| SKKNI_STANDARD | `status` / `record_origin` | Berlaku 14 / LEGACY_V1_0 9, V0_1_SCREENING 5 | SK01 / SK10 | Enactment status and provenance |
| STANDARD_COVERAGE | `unit_inventory_status` | COMPLETE 5, PARTIAL 3, PROFILE-COMPLETE 1 | SK01 / SK06 / SK03 | Unit-inventory completeness |
| KJN_SOURCE_CLAIMS | `support_status` | STATED_IN_DOCUMENT_TEXT 12, LIMITATION 1 | KJN-C01 | Claim support only |

### Relationship between operational evidence and qualifying sources

Qualifying sources (per SOURCE_REGISTER): `SRC-KBJI`, `SRC-SKKNI` only. Cross-check against EVIDENCE_LINK:

| Sheet | TRUE+qualifying | FALSE+no qualifying | TRUE but no qualifying | FALSE but qualifying | No links |
|---|---|---|---|---|---|
| CAREER_OCCUPATION | 7 | 5 | 0 | 0 | 0 |
| SKILL | 49 | 16 | 0 | 22 | 0 |
| CAREER_SKILL | 94 | 0 | 0 | 61 | 0 |
| OCCUPATION_COMPETENCY | 10 | 0 | 0 | 0 | 0 |
| COMPETENCY_SKILL | 79 | 0 | 0 | 0 | 0 |
| OCCUPATION_SOURCE_MAPPING | 0 | 25 | 0 | 0 | 0 |
| TECHNOLOGY | 0 | 120 | 0 | 0 | 0 |
| TASK | 0 | 35 | 0 | 0 | 0 |
| CAREER_KBJI_MAPPING | 27 | 0 | 0 | 2 (MAP-009, MAP-013) | 0 |

**Interpretation:** `operational_evidence_present` is **not** the same as eligibility, and it is not consistently explained by the README sentence either. README states: *"eligible_* flags are derived from EVIDENCE_LINK (qualifying link from a source with can_contribute_to_scores=TRUE) AND validation_status=VALIDATED (see CONFIG_ELIGIBILITY). operational_evidence_present = has a qualifying link."* Under that definition, every record with at least one `SRC-KBJI` or `SRC-SKKNI` link should be TRUE. Observed exceptions: 22 SKILL rows, 61 CAREER_SKILL rows and 2 CAREER_KBJI_MAPPING rows have a qualifying link but are FALSE (85 rows total). Either the flag uses additional undocumented criteria, or the values are internally inconsistent. The workbook does not contain `CONFIG_ELIGIBILITY`, so the exact derivation cannot be confirmed. The flags are **not equivalent**.

**Conclusions:**
- **Explicitly eligible for scoring?** No. No `eligible_for_scoring` column exists; all `eligible_for_career_fit` and `eligible_for_skill_gap` are FALSE. README says 0 records VALIDATED → 0 records eligible for PRIMARY experiment.
- **Operational evidence but not eligible?** Yes — many records have `operational_evidence_present=TRUE` (and/or have evidence links) but are not eligible because validation status is not VALIDATED (and/or eligibility derivation requires both conditions). Also some have links from qualifying sources but eligibility flags remain FALSE.
- **Usable in primary experiment now?** No, per README: "Working dataset, NOT expert-validated: 0 records VALIDATED, so 0 records are eligible in the PRIMARY experiment." No VALIDATED records exist anywhere.

**Status:** PARTIAL (verified with evidence; derivation logic not fully inspectable from workbook alone).

---

## 4. EVIDENCE_LINK Polymorphic Reference Validation

### Structure
- Rows: 970, cols: `['link_id','record_table','record_id','source_id','standard_id','evidence_component']`  
- `link_id` unique (EV-00001..EV-00970, no gaps).  
- `record_table` values: CAREER_SKILL (432), SKILL (174), TECHNOLOGY (120), COMPETENCY_SKILL (79), CAREER_OCCUPATION (65), TASK (35), CAREER_KBJI_MAPPING (29), OCCUPATION_SOURCE_MAPPING (26), OCCUPATION_COMPETENCY (10). All match exact sheet names.  
- `standard_id`: 286 non-null, values SK01(74), SK02(23), SK03(37), SK04(31), SK05(77), SK06(12), SK07(31), SK08(1) — all exist in SKKNI_STANDARD. 684 null.  
- `source_id`: SRC-SKKNI(348, in register), SRC(274, **not in register**), SRC-(138, **not in register**), SRC-LIGHTCAST(120, in), SRC-KBJI(51, in), SRC-KBJI-2014(20, in), SRC-INDOTASK(19, in).

### Resolution by target

| record_table | Target sheet | Key | Matched | Orphan | Notes |
|---|---|---|---|---|---|
| CAREER_KBJI_MAPPING | CAREER_KBJI_MAPPING | `mapping_id` | 29/29 | 0 | OK |
| CAREER_OCCUPATION | CAREER_OCCUPATION | composite `career_id\|occupation_id` | 65/65 | 0 | OK (uses composite form) |
| CAREER_SKILL | CAREER_SKILL | `relationship_id` | 432/432 | 0 | OK |
| COMPETENCY_SKILL | COMPETENCY_SKILL | `relationship_id` | 79/79 | 0 | OK |
| OCCUPATION_COMPETENCY | OCCUPATION_COMPETENCY | `relationship_id` | 10/10 | 0 | OK |
| OCCUPATION_SOURCE_MAPPING | OCCUPATION_SOURCE_MAPPING | `mapping_id` | 25/26 | **1** | Orphan: `OSM002` (EV-00881, source_id `SRC`, evidence `code 15-1252.00`) — OSM002 not in sheet (removed in extended) |
| SKILL | SKILL | `skill_id` | 174/174 | 0 | OK |
| TASK | TASK | `task_id` | 35/35 | 0 | OK |
| TECHNOLOGY | TECHNOLOGY | `technology_id` | 120/120 | 0 | OK |

### Assessment
- **Polymorphic design:** Yes — requires discriminator (`record_table`) + table-specific key. Cannot be a single ordinary FK column without junction tables or application-level validation.
- **Risks:** Referential integrity not enforceable by simple FK; source resolution broken for `SRC`/`SRC-` (412 links) and `SRC-KBJI-2014-2026` (used in OSM but missing from SOURCE_REGISTER); orphan exists (OSM002).
- **Naming:** `record_table` uses exact sheet names; consistent.

**Status:** PARTIAL (resolution OK where targets exist, but source governance/integrity issues).

---

## 5. Primary Key and Candidate Key Assessment

### Verified candidate keys (by uniqueness, no nulls)

| Sheet | Candidate PK(s) | Notes |
|---|---|---|
| CAREER | `career_id`, `canonical_name` | `career_id` preferred (stable) |
| OCCUPATION | `occupation_id`, `canonical_name`, `classification` | `occupation_id` preferred |
| CAREER_OCCUPATION | `legacy_career_occupation_id` (unique) | Surrogate preferred; composite (career_id, occupation_id) is also unique in the current sheet (12/12 distinct pairs). T4-R1's statement that each pair appears twice is **not supported** by the data. |
| SKILL_GROUP | `skill_group_id`, `name` | Either OK |
| SKILL | `skill_id`, `canonical_name` | `skill_id` preferred |
| CAREER_SKILL | `relationship_id` | Surrogate; (career_id,skill_id) unique but not single-column key |
| SKKNI_STANDARD | `standard_id` (title unique; number has duplicate '47' for SK02/SK12) | `standard_id` preferred |
| COMPETENCY_UNIT | `unit_id`, `code` | Both unique |
| OCCUPATION_COMPETENCY | `relationship_id` | Surrogate; (occupation_id,standard_id) unique |
| COMPETENCY_SKILL | `relationship_id`, `unit_id` | Both unique |
| OCCUPATION_SOURCE_MAPPING | `mapping_id` | Surrogate; natural pairs duplicate ((O07,IndoTask,252) appears twice as OSM020/OSM022; (O08,IndoTask,251) twice as OSM024/OSM025) |
| TECHNOLOGY | `technology_id` | Surrogate; name repeats across occupations/IDs |
| TASK | `task_id` | Surrogate |
| PROVENANCE | `provenance_id` | Surrogate; `document_id` has duplicates (Kepmenaker 191/2024 appears twice, IndoTask-2020 appears 10 times) |
| SKILL_SOURCE_EVIDENCE | `evidence_id` | Surrogate; (skill_id,source_reference) unique |
| SOURCE_REGISTER | `source_id` | Preferred |
| KBJI_HIERARCHY | `node_id`, `kbji_code` | Both unique; self-referential |
| KBJI_OCCUPATION | `occupation_id`, `occupation_code` | Both unique (75 occupations) |
| OCCUPATION_KBJI2026_LINK | `link_id`, `occupation_id` | Both unique (1:1 to OCCUPATION) |
| CAREER_KBJI_MAPPING | `mapping_id` | Surrogate; (career_id,occupation_id) unique |
| EVIDENCE_LINK | `link_id` | Surrogate; (record_table,record_id,source_id) is **not** unique (35 triples duplicated) |
| KJN_SOURCE_CLAIMS | `claim_id` | Surrogate |

**Notes on "unique but not identifier-worthy":**
- `evidence_summary` (CAREER_KBJI_MAPPING) is unique per row but is descriptive text — not stable as identifier.
- `document_title` (PROVENANCE) unique but descriptive.
- `supporting_kbji_mapping_ids` (CAREER_OCCUPATION) is semicolon-delimited multi-value list — not atomic identifier.

**Key-type classification (conceptual):**
- **Assigned stable/surrogate identifiers:** `career_id`, `occupation_id`, `skill_group_id`, `skill_id`, `standard_id`, `unit_id`, `source_id`, `mapping_id`, `relationship_id`, `link_id`, `provenance_id`, `evidence_id`, `claim_id`, `node_id`, `occupation_code`, `technology_id`, `task_id`.
- **Natural/descriptive candidates (unique now, may change):** `canonical_name`, `name`, `title`, `classification`, `document_title`, `evidence_summary`, `source_title`.
- **Composite candidate keys:** `(career_id, occupation_id)` in CAREER_OCCUPATION (unique 12/12), `(career_id, skill_id)` in CAREER_SKILL (unique 155/155), `(occupation_id, standard_id)` in OCCUPATION_COMPETENCY (unique 10/10), `(skill_id, source_reference)` in SKILL_SOURCE_EVIDENCE (unique 97/97), `(record_table, record_id, source_id)` in EVIDENCE_LINK (**not** unique — see §7).
- **Legacy surrogates:** `legacy_career_occupation_id` and other `legacy_*` columns.
- **Explicit PK declaration:** the workbook contains no schema/data-dictionary sheet declaring primary keys; every candidate above is inferred from current uniqueness, not from an authoritative declaration.

**Dependent relations:** `EVIDENCE_LINK` references nine target tables via `(record_table, record_id)`; `CAREER_SKILL.career_id`/`skill_id` depend on CAREER/SKILL; `CAREER_OCCUPATION` depends on CAREER/OCCUPATION; `CAREER_KBJI_MAPPING` depends on CAREER/OCCUPATION; `supporting_kbji_mapping_ids` references `CAREER_KBJI_MAPPING.mapping_id`; `COMPETENCY_SKILL.unit_id` depends on COMPETENCY_UNIT; `OCCUPATION_COMPETENCY.standard_id` depends on SKKNI_STANDARD; `OCCUPATION_SOURCE_MAPPING.occupation_id` depends on OCCUPATION; `SKILL_SOURCE_EVIDENCE.skill_id` depends on SKILL.

**Stability:** surrogate/assigned IDs are stable identifiers. Natural/descriptive candidates (`canonical_name`, `name`, `title`, `classification`, `document_title`, `evidence_summary`, `source_title`) can change when a description is edited or a source is re-verified, so they should not be used as durable PKs even where currently unique.

**Recommendation (conceptual):** Use stable surrogate/single-column keys where assigned; do not promote descriptive/multi-value columns to PKs. No changes to workbook proposed.

**Status:** PASS (with clarifications above).

---

## 6. supporting_kbji_mapping_ids Audit

### Findings
- Sheet: `CAREER_OCCUPATION` (12 rows). `supporting_kbji_mapping_ids` non-null in 7 rows, blank in 5.
- **One ID:** 1 row (`C08/O05` → `MAP-016`). **More than one ID:** 6 rows (`C01/O01` 3, `C02/O02` 4, `C05/O04` 2, `C07/O01` 2, `C09/O07` 7, `C10/O03` 3). **Blank:** 5 rows (`C03/O01`, `C03/O02`, `C04/O08`, `C06/O08`, `C07/O08`).
- Format: all non-blank cells are semicolon-separated `MAP-###` tokens with no surrounding whitespace; no empty tokens; all IDs match `CAREER_KBJI_MAPPING.mapping_id`. No unmatched IDs, no within-cell duplicates, no cross-cell duplicates.
- Total refs: 22, distinct 22. **Never referenced:** `MAP-002`, `MAP-009`, `MAP-010`, `MAP-013`, `MAP-017`, `MAP-025`, `MAP-026` (7 mappings).
- Blank cells correspond to: C03/O01, C03/O02, C04/O08, C06/O08, C07/O08 (CAREER_KBJI_MAPPING shows MAP-009/MAP-013 as UNRESOLVED for C03/C06; others have no mappings).

### Many-to-many & relational implications
- This is effectively a **M:N** relationship between `CAREER_OCCUPATION` and `CAREER_KBJI_MAPPING` stored as semicolon-delimited list. 
- **Consequences if kept as-is in relational DB:** Cannot enforce FK constraints per element, hard to query/join/index efficiently, updates require string parsing, risk of inconsistency, violates normalization.
- **Conceptual alternative:** Create junction table `career_occupation_kbji_mapping` with `(career_occupation_id or (career_id,occupation_id), mapping_id)`, composite PK, FKs to both tables. This enables referential integrity, efficient queries, and proper cardinality.

**Status:** PARTIAL (validated content; relational design issue identified).

---

## 7. EVIDENCE_LINK Duplicate Analysis

### (record_table, record_id, source_id) triples
- Duplicate triples: **35** (92 rows involved out of 970).  
- When compared on all 5 fields (`record_table,record_id,source_id,standard_id,evidence_component`), all 970 rows are distinct (**0 fully identical rows**); every duplicate triple therefore differs in `standard_id` or `evidence_component`. The triple is **not** a unique key.

Breakdown by record_table: SKILL (16 triples, 43 rows), CAREER_OCCUPATION (10 triples, 29 rows), CAREER_SKILL (9 triples, 18 rows).

All duplicate combinations (35 triples, 92 rows):

| # | record_table | record_id | source_id | link_id | standard_id | evidence_component |
|---|---|---|---|---|---|---|
| 1 | CAREER_OCCUPATION | C01\|O01 | SRC-KBJI | EV-00910 | (null) | v0.1 KBJI 2026 candidate MAP-001 |
| 2 | CAREER_OCCUPATION | C01\|O01 | SRC-KBJI | EV-00911 | (null) | v0.1 KBJI 2026 candidate MAP-003 |
| 3 | CAREER_OCCUPATION | C01\|O01 | SRC-KBJI | EV-00912 | (null) | v0.1 KBJI 2026 candidate MAP-004 |
| 4 | CAREER_OCCUPATION | C02\|O02 | SRC-KBJI | EV-00916 | (null) | v0.1 KBJI 2026 candidate MAP-005 |
| 5 | CAREER_OCCUPATION | C02\|O02 | SRC-KBJI | EV-00917 | (null) | v0.1 KBJI 2026 candidate MAP-006 |
| 6 | CAREER_OCCUPATION | C02\|O02 | SRC-KBJI | EV-00918 | (null) | v0.1 KBJI 2026 candidate MAP-007 |
| 7 | CAREER_OCCUPATION | C02\|O02 | SRC-KBJI | EV-00919 | (null) | v0.1 KBJI 2026 candidate MAP-008 |
| 8 | CAREER_OCCUPATION | C04\|O08 | SRC | EV-00928 | (null) | 15-2051.00 |
| 9 | CAREER_OCCUPATION | C04\|O08 | SRC | EV-00929 | (null) | 15-2051.01 |
| 10 | CAREER_OCCUPATION | C05\|O04 | SRC-KBJI | EV-00934 | (null) | v0.1 KBJI 2026 candidate MAP-011 |
| 11 | CAREER_OCCUPATION | C05\|O04 | SRC-KBJI | EV-00935 | (null) | v0.1 KBJI 2026 candidate MAP-012 |
| 12 | CAREER_OCCUPATION | C06\|O08 | SRC | EV-00937 | (null) | 15-2051.00 |
| 13 | CAREER_OCCUPATION | C06\|O08 | SRC | EV-00938 | (null) | 15-2051.01 |
| 14 | CAREER_OCCUPATION | C07\|O01 | SRC-KBJI | EV-00944 | (null) | v0.1 KBJI 2026 candidate MAP-014 |
| 15 | CAREER_OCCUPATION | C07\|O01 | SRC-KBJI | EV-00945 | (null) | v0.1 KBJI 2026 candidate MAP-015 |
| 16 | CAREER_OCCUPATION | C07\|O08 | SRC | EV-00947 | (null) | 15-2051.00 |
| 17 | CAREER_OCCUPATION | C07\|O08 | SRC | EV-00948 | (null) | 15-2051.01 |
| 18 | CAREER_OCCUPATION | C09\|O07 | SRC | EV-00955 | (null) | 15-1212.00 |
| 19 | CAREER_OCCUPATION | C09\|O07 | SRC | EV-00956 | (null) | 15-1299.05 |
| 20 | CAREER_OCCUPATION | C09\|O07 | SRC-KBJI | EV-00958 | (null) | v0.1 KBJI 2026 candidate MAP-018 |
| 21 | CAREER_OCCUPATION | C09\|O07 | SRC-KBJI | EV-00959 | (null) | v0.1 KBJI 2026 candidate MAP-019 |
| 22 | CAREER_OCCUPATION | C09\|O07 | SRC-KBJI | EV-00960 | (null) | v0.1 KBJI 2026 candidate MAP-020 |
| 23 | CAREER_OCCUPATION | C09\|O07 | SRC-KBJI | EV-00961 | (null) | v0.1 KBJI 2026 candidate MAP-021 |
| 24 | CAREER_OCCUPATION | C09\|O07 | SRC-KBJI | EV-00962 | (null) | v0.1 KBJI 2026 candidate MAP-022 |
| 25 | CAREER_OCCUPATION | C09\|O07 | SRC-KBJI | EV-00963 | (null) | v0.1 KBJI 2026 candidate MAP-023 |
| 26 | CAREER_OCCUPATION | C09\|O07 | SRC-KBJI | EV-00964 | (null) | v0.1 KBJI 2026 candidate MAP-024 |
| 27 | CAREER_OCCUPATION | C10\|O03 | SRC-KBJI | EV-00968 | (null) | v0.1 KBJI 2026 candidate MAP-027 |
| 28 | CAREER_OCCUPATION | C10\|O03 | SRC-KBJI | EV-00969 | (null) | v0.1 KBJI 2026 candidate MAP-028 |
| 29 | CAREER_OCCUPATION | C10\|O03 | SRC-KBJI | EV-00970 | (null) | v0.1 KBJI 2026 candidate MAP-029 |
| 30 | CAREER_SKILL | CS048 | SRC-SKKNI | EV-00171 | SK06 | SKKNI 200/2021 |
| 31 | CAREER_SKILL | CS048 | SRC-SKKNI | EV-00172 | SK05 | SKKNI 299/2020 |
| 32 | CAREER_SKILL | CS049 | SRC-SKKNI | EV-00175 | SK06 | SKKNI 200/2021 |
| 33 | CAREER_SKILL | CS049 | SRC-SKKNI | EV-00176 | SK05 | SKKNI 299/2020 |
| 34 | CAREER_SKILL | CS050 | SRC-SKKNI | EV-00179 | SK06 | SKKNI 200/2021 |
| 35 | CAREER_SKILL | CS050 | SRC-SKKNI | EV-00180 | SK05 | SKKNI 299/2020 |
| 36 | CAREER_SKILL | CS051 | SRC-SKKNI | EV-00183 | SK06 | SKKNI 200/2021 |
| 37 | CAREER_SKILL | CS051 | SRC-SKKNI | EV-00184 | SK05 | SKKNI 299/2020 |
| 38 | CAREER_SKILL | CS052 | SRC-SKKNI | EV-00187 | SK06 | SKKNI 200/2021 |
| 39 | CAREER_SKILL | CS052 | SRC-SKKNI | EV-00188 | SK05 | SKKNI 299/2020 |
| 40 | CAREER_SKILL | CS053 | SRC-SKKNI | EV-00191 | SK06 | SKKNI 200/2021 |
| 41 | CAREER_SKILL | CS053 | SRC-SKKNI | EV-00192 | SK05 | SKKNI 299/2020 |
| 42 | CAREER_SKILL | CS054 | SRC-SKKNI | EV-00195 | SK06 | SKKNI 200/2021 |
| 43 | CAREER_SKILL | CS054 | SRC-SKKNI | EV-00196 | SK05 | SKKNI 299/2020 |
| 44 | CAREER_SKILL | CS055 | SRC-SKKNI | EV-00199 | SK06 | SKKNI 200/2021 |
| 45 | CAREER_SKILL | CS055 | SRC-SKKNI | EV-00200 | SK05 | SKKNI 299/2020 |
| 46 | CAREER_SKILL | CS056 | SRC-SKKNI | EV-00203 | SK06 | SKKNI 200/2021 |
| 47 | CAREER_SKILL | CS056 | SRC-SKKNI | EV-00204 | SK05 | SKKNI 299/2020 |
| 48 | SKILL | S003 | SRC | EV-00656 | (null) | derived via CAREER_SKILL CS052: |
| 49 | SKILL | S003 | SRC | EV-00675 | (null) | derived via CAREER_SKILL CS076: |
| 50 | SKILL | S003 | SRC-SKKNI | EV-00654 | SK06 | derived via CAREER_SKILL CS052: SKKNI 200/2021 |
| 51 | SKILL | S003 | SRC-SKKNI | EV-00655 | SK05 | derived via CAREER_SKILL CS052: SKKNI 299/2020 |
| 52 | SKILL | S003 | SRC-SKKNI | EV-00674 | SK05 | derived via CAREER_SKILL CS076: SKKNI 299/2020 |
| 53 | SKILL | S004 | SRC-SKKNI | EV-00568 | (null) | direct unit-title evidence \| J.620100.044.01 |
| 54 | SKILL | S004 | SRC-SKKNI | EV-00569 | (null) | direct unit-title evidence \| J.620100.045.01 |
| 55 | SKILL | S004 | SRC-SKKNI | EV-00570 | (null) | direct unit-title evidence \| J.620100.046.01 |
| 56 | SKILL | S005 | SRC-SKKNI | EV-00600 | (null) | direct unit-title evidence \| J.62KAM00.007.1 |
| 57 | SKILL | S005 | SRC-SKKNI | EV-00601 | (null) | direct unit-title evidence \| J.62KAM00.008.1 |
| 58 | SKILL | S005 | SRC-SKKNI | EV-00602 | (null) | direct unit-title evidence \| J.62KAM00.009.1 |
| 59 | SKILL | S014 | SRC-SKKNI | EV-00658 | SK06 | derived via CAREER_SKILL CS055: SKKNI 200/2021 |
| 60 | SKILL | S014 | SRC-SKKNI | EV-00659 | SK05 | derived via CAREER_SKILL CS055: SKKNI 299/2020 |
| 61 | SKILL | S020 | SRC-SKKNI | EV-00573 | (null) | direct unit-title evidence \| J.62DMS00.004.1 |
| 62 | SKILL | S020 | SRC-SKKNI | EV-00574 | (null) | direct unit-title evidence \| J.62DMI00.011.1 |
| 63 | SKILL | S027 | SRC-SKKNI | EV-00593 | (null) | direct unit-title evidence \| J.62KAM00.001.1 |
| 64 | SKILL | S027 | SRC-SKKNI | EV-00594 | (null) | direct unit-title evidence \| J.62KAM00.002.1 |
| 65 | SKILL | S027 | SRC-SKKNI | EV-00595 | (null) | direct unit-title evidence \| J.62KAM00.003.2 |
| 66 | SKILL | S035 | SRC-SKKNI | EV-00559 | (null) | direct unit-title evidence \| J.620100.020.02 |
| 67 | SKILL | S035 | SRC-SKKNI | EV-00560 | (null) | direct unit-title evidence \| J.620100.021.02 |
| 68 | SKILL | S041 | SRC-SKKNI | EV-00607 | (null) | direct unit-title evidence \| J.62KAM00.005.1 |
| 69 | SKILL | S041 | SRC-SKKNI | EV-00608 | (null) | direct unit-title evidence \| J.62KAM00.006.2 |
| 70 | SKILL | S044 | SRC-SKKNI | EV-00703 | SK03 | derived via CAREER_SKILL CS120: SKKNI 22/2019 |
| 71 | SKILL | S044 | SRC-SKKNI | EV-00723 | SK03 | derived via COMPETENCY_SKILL CK067: SKKNI competency unit title |
| 72 | SKILL | S044 | SRC-SKKNI | EV-00724 | SK03 | derived via COMPETENCY_SKILL CK072: SKKNI competency unit title |
| 73 | SKILL | S061 | SRC | EV-00649 | (null) | derived via CAREER_SKILL CS012: |
| 74 | SKILL | S061 | SRC | EV-00652 | (null) | derived via CAREER_SKILL CS041: |
| 75 | SKILL | S061 | SRC | EV-00672 | (null) | derived via CAREER_SKILL CS069: |
| 76 | SKILL | S061 | SRC- | EV-00650 | (null) | derived via CAREER_SKILL CS012: |
| 77 | SKILL | S061 | SRC- | EV-00653 | (null) | derived via CAREER_SKILL CS041: |
| 78 | SKILL | S061 | SRC- | EV-00673 | (null) | derived via CAREER_SKILL CS069: |
| 79 | SKILL | S061 | SRC-SKKNI | EV-00648 | SK01 | derived via CAREER_SKILL CS012: SKKNI 282/2016 |
| 80 | SKILL | S061 | SRC-SKKNI | EV-00651 | SK01 | derived via CAREER_SKILL CS041: SKKNI 282/2016 |
| 81 | SKILL | S061 | SRC-SKKNI | EV-00671 | SK04 | derived via CAREER_SKILL CS069: SKKNI 268/2020 |
| 82 | SKILL | S061 | SRC-SKKNI | EV-00721 | SK04 | derived via COMPETENCY_SKILL CK013: SKKNI competency unit title |
| 83 | SKILL | S061 | SRC-SKKNI | EV-00722 | SK01 | derived via COMPETENCY_SKILL CK054: SKKNI competency unit title |
| 84 | SKILL | S065 | SRC-SKKNI | EV-00551 | (null) | direct unit-title evidence \| J.620100.010.01 |
| 85 | SKILL | S065 | SRC-SKKNI | EV-00552 | (null) | direct unit-title evidence \| J.620100.016.01 |
| 86 | SKILL | S069 | SRC-SKKNI | EV-00596 | (null) | direct unit-title evidence \| J.62KAM00.004.2 |
| 87 | SKILL | S069 | SRC-SKKNI | EV-00597 | (null) | direct unit-title evidence \| J.62KAM00.012.2 |
| 88 | SKILL | S069 | SRC-SKKNI | EV-00598 | (null) | direct unit-title evidence \| J.62KAM00.013.2 |
| 89 | SKILL | S069 | SRC-SKKNI | EV-00599 | (null) | direct unit-title evidence \| J.62KAM00.016.1 |
| 90 | SKILL | S079 | SRC-SKKNI | EV-00563 | (null) | direct unit-title evidence \| J.620100.033.02 |
| 91 | SKILL | S079 | SRC-SKKNI | EV-00564 | (null) | direct unit-title evidence \| J.620100.034.02 |
| 92 | SKILL | S079 | SRC-SKKNI | EV-00565 | (null) | direct unit-title evidence \| J.620100.035.02 |

### OCCUPATION_SOURCE_MAPPING natural pairs
Full rows:
- **OSM020** — occupation `O07`, source `IndoTask`, `source_id='SRC-INDOTASK'`, `source_code='252'`, title "Information Security Analysts", method `mapped`, confidence `high`.
- **OSM022** — occupation `O07`, source `IndoTask`, `source_id='SRC-INDOTASK'`, `source_code='252'`, title "Database and network professionals", method `mapped`, confidence `medium`.
- **OSM024** — occupation `O08`, source `IndoTask`, `source_id='SRC-INDOTASK'`, `source_code='251'`, title "Data Scientists", method `mapped`, confidence `high`.
- **OSM025** — occupation `O08`, source `IndoTask`, `source_id='SRC-INDOTASK'`, `source_code='251'`, title "Business Intelligence Analysts", method `mapped`, confidence `high`.

These are **not identical duplicates** (different `source_title`; OSM020/OSM022 also differ in confidence). They represent different occupation/source mappings that share `(occupation_id, source_name, source_code)`.

**Conclusion:** All 35 duplicate triples are **different evidence for the same target and source**; 0 are identical duplicates and 0 are uncertain. The triple key is insufficient; uniqueness would need to include `standard_id` and/or `evidence_component` depending on intent.

**Status:** PASS (clarified).

---

## 8. KBJI Code 2120 Clarification

### Evidence
- `OCCUPATION` O08: `canonical_name='Mathematician/Statistician'`, `classification='KBJI 2120'`  
- `OCCUPATION_KBJI2026_LINK` LNK-O08: `kbji2026_code='2120'`, `kbji2026_title='AHLI MATEMATIKA, AKTUARIA, DAN STATISTIKA'`, `match_type='exact_code+normalized_title'`, `match_basis='KBJI 2026 text extract line 10869 (page not verified)'`  
- `OCCUPATION_SOURCE_MAPPING` OSM023: `source_code='2120'`, `source_name='KBJI'`, `source_id='SRC-KBJI-2014-2026'` (not in SOURCE_REGISTER)  
- `EVIDENCE_LINK` references `2120` in 4 rows (EV-00902 for OSM023; EV-00927, EV-00936 and EV-00946 for CAREER_OCCUPATION C04|O08, C06|O08, C07|O08)  
- **Format / data type:** `OCCUPATION_KBJI2026_LINK.kbji2026_code`, `KBJI_HIERARCHY.kbji_code` and `KBJI_OCCUPATION.occupation_code` are all text and contain **no leading-zero values**. `2120` is stored as a 4-character text value. However, `OCCUPATION_SOURCE_MAPPING.source_code` is **mixed-type**: 8 cells are numeric (OSM006, OSM009, OSM012, OSM015, OSM020, OSM021, OSM024, OSM025) while the rest are text. This does not affect `2120` (which is text) but is a data-type inconsistency to handle during import.
- `KBJI_HIERARCHY`: contains codes 1,13,133,1330,2,21,215,2153,25,251,2511,2512,2513,2514,2515,2519,252,2521,2522,2523,2529,3,35,351,3511,3512,3513,3514,352,3522 — **no `2120`**. Has node `21` "AHLI ILMU PENGETAHUAN DAN TEKNIK" with definition mentioning "subgolongan pokok ini diklasifikasikan sebagai berikut 211 ahli fisika dan ilmu bumi; **212 ahli matematika, aktuaria, dan statistika**; ..." so `2120` would be subgolongan level under `21`.  
- `KBJI_OCCUPATION`: 75 occupations with dotted codes like `2512.01`, `2521.02` (4-digit subgolongan + 2-digit occupation suffix), parent_subgolongan_codes include `2512`,`2521` etc., **no `2120`** entries.

### Conclusion
- `2120` is a **4-digit KBJI hierarchy code** (labeled `Subgolongan` in `KBJI_HIERARCHY`), not an occupation code like `2512.01`.  
- Target relation is **`KBJI_HIERARCHY.kbji_code`** (hierarchy node), not `KBJI_OCCUPATION`.  
- The link in `OCCUPATION_KBJI2026_LINK` points to hierarchy level; `KBJI_HIERARCHY` is a curated 30-node subset. It contains `21` (Subgolongan pokok) and `215`/`2153`, but neither the `212` (Golongan) node nor a `2120` (Subgolongan) node; the node-`21` definition text references `211` and `212`.  
- This is **plausibly valid KBJI 2026 content missing from the extracted hierarchy subset**, not necessarily incorrect. Cannot be confirmed from workbook alone.

**Status:** UNRESOLVED (needs verification against actual KBJI 2026 hierarchy; hierarchy coverage is incomplete).

---

## 9. Skill Evidence Coverage Clarification

### 24 skills without SKILL_SOURCE_EVIDENCE rows
All 24 have **EVIDENCE_LINK entries as SKILL records**. EVIDENCE_LINK contains 174 SKILL links spanning all 87 distinct skill IDs, so all 87 skills (63 with SSE + 24 without SSE) have at least one skill-level EVIDENCE_LINK row. All 24 also have non-empty `CAREER_SKILL.evidence_source`.

Classification:
- **Have structured skill-level evidence in `SKILL_SOURCE_EVIDENCE`:** 63 skills (S001,S002,S004,S005,...)
- **No structured skill-level evidence in `SKILL_SOURCE_EVIDENCE` but have career-level evidence:** **24 skills** (S003,S009,S010,S012,S013,S014,S019,S023,S025,S029,S042,S044,S046,S047,S050,S055,S056,S057,S058,S061,S066,S067,S070,S083). All have `CAREER_SKILL.evidence_source` (e.g., "SKKNI 200/2021; 299/2020; IndoTask") and **derived EVIDENCE_LINK rows** (via CAREER_SKILL/COMPETENCY_SKILL) with sources `SRC-SKKNI` (and sometimes `SRC`, `SRC-`, `SRC-INDOTASK`) and `standard_id` values.
- **No traceable evidence:** None found.
- **Uncertain:** None.

This matches the repository note in `evidence_repository.py`: "24/87 skills have zero rows in skill_source_evidence, but 100% of those 24 DO have free-text evidence attached at the career_skills.evidence_source level. Any function claiming to return \"the evidence for skill X\" MUST combine both tables..." The extended workbook confirms this with EVIDENCE_LINK providing additional traceability.

**Status:** PASS (clarified; not unsupported).

---

## 10. SKKNI Completeness Clarification

### Standards inventory (14 total)
| Standard | Units in dataset | OCC comp | Coverage | Notes |
|---|---|---|---|---|
| SK01 (282/2016) | 47 | 2 | COMPLETE | OK |
| SK02 (47/2017) | 12 | 1 | COMPLETE | OK |
| SK03 (22/2019) | 25 | 1 | PROFILE-COMPLETE | "25 System Administrator units included; do not claim all units of the entire 2019 standard" |
| SK04 (268/2020) | 22 | 1 | COMPLETE | OK |
| SK05 (299/2020) | 21 | 2 | COMPLETE | OK |
| SK06 (200/2021) | 0 | 1 | PARTIAL | "Standard existence verified; unit inventory not directly extracted in this pass" — do not infer |
| SK07 (191/2024) | 19 | 1 | COMPLETE | OK |
| SK08 (120/2025) | 0 | 1 | PARTIAL | "Standard existence verified; unit inventory not directly extracted in this pass" — do not infer |
| SK09 (103/2026) | 0 | 0 | PARTIAL | "Standard existence/status verified; unit inventory not directly extracted in this pass" — do not infer |
| SK10 (391/2020) | 0 | 0 | <NO ROW> | V0_1_SCREENING, no coverage row |
| SK11 (24/2022) | 0 | 0 | <NO ROW> | V0_1_SCREENING |
| SK12 (47/2022) | 0 | 0 | <NO ROW> | V0_1_SCREENING (note: SK02 also 47/2017) |
| SK13 (236/2024) | 0 | 0 | <NO ROW> | V0_1_SCREENING |
| SK14 (102/2023) | 0 | 0 | <NO ROW> | V0_1_SCREENING |

### Classification
- **Standards with units but incomplete coverage:** SK03 (profile-complete, partial by design; completeness of the entire 2019 standard cannot be determined).
- **Standards that exist but have no unit data extracted:** SK06, SK08, SK09 (`PARTIAL`) — existence/status verified, unit inventory not extracted; completeness **cannot be determined** and units must not be fabricated.
- **Standards added by screening with no units/coverage:** SK10-SK14 (`V0_1_SCREENING`) — no `STANDARD_COVERAGE` row; units/relations have **not been entered**, rather than being known-absent.
- **All standards exist/enacted:** `status='Berlaku'` for all 14.

**Status:** PARTIAL (documented; do not fabricate missing units).

---

## 11. Consolidated Findings and Severity

| Finding | Severity | Status | Evidence |
|---|---|---|---|
| Candidate keys verified per sheet; no explicit PK declaration; descriptive columns excluded | High | PASS | 12/12 CAREER_OCCUPATION pairs unique; surrogate IDs stable; workbook has no schema/data-dictionary sheet |
| 0 VALIDATED records; all eligibility flags FALSE; no eligible_for_scoring column | High | PASS (verified) | README states 0 VALIDATED; all `eligible_for_*` columns are FALSE; no `eligible_for_scoring` column exists |
| operational_evidence_present != eligibility and does not consistently track qualifying-source links | High | PARTIAL (mismatches verified; derivation logic not documented in workbook) | Cross-check shows 85 rows FALSE despite a qualifying SRC-KBJI/SRC-SKKNI link, in SKILL/CAREER_SKILL/CAREER_KBJI_MAPPING |
| EVIDENCE_LINK source resolution broken (SRC, SRC- not in register; 412 links) | High | FAIL | SOURCE_REGISTER missing entries; EV-00881 uses SRC for orphan OSM002 |
| OCCUPATION_SOURCE_MAPPING references SRC-KBJI-2014-2026 (8 rows) not in SOURCE_REGISTER | High | FAIL | OSM001,OSM005,OSM008,OSM011,OSM014,OSM017,OSM019,OSM023 use SRC-KBJI-2014-2026 not present in register |
| KBJI 2120 missing from KBJI_HIERARCHY/KBJI_OCCUPATION (present in links/mapping) | High | UNRESOLVED | Hierarchy curated subset omits it; match basis says text extract |
| OSM002 orphan in EVIDENCE_LINK (removed from sheet) | Medium | FAIL | EV-00881 references OSM002 not found |
| 35 duplicate (record_table,record_id,source_id) triples — not identical rows | Medium | PASS (clarified) | Different standard_id/evidence_component; triple not unique key |
| OSM pairs (O07,IndoTask,252) and (O08,IndoTask,251) duplicated but different titles | Medium | PASS (clarified) | OSM020/OSM022 and OSM024/OSM025 differ |
| supporting_kbji_mapping_ids is semicolon-delimited M:N | Medium | PARTIAL (content valid; M:N field needs junction table) | 22 refs to 22 mappings, 7 mappings unreferenced; no FK possible per element |
| 24 skills without SSE have career-level + derived EVIDENCE_LINK evidence | Medium | PASS (clarified) | All have CAREER_SKILL.evidence_source and EVIDENCE_LINK rows |
| 8/14 SKKNI standards have 0 units (some screening-only) | Medium | PARTIAL | Do not fabricate units; SK10-SK14 have no coverage row |
| STATUS_AUDIT/README counts stale (Source register says 27 in STATUS_AUDIT but sheet has 24; README says 26 OSM but sheet has 25) | Low | PASS (verified) | STATUS_AUDIT row20 says 27, SOURCE_REGISTER has 24 rows; README row11 says 26, OSM has 25 |

---

## 12. Recommendations for T4-R2

**Do not proceed automatically.** Before import/schema work:

1. **Resolve source governance:** Add `SRC-KBJI-2014-2026`, `SRC`, `SRC-` to `SOURCE_REGISTER` with correct roles/permissions/can_contribute_to_scores, or fix all references. Decide fate of orphan `OSM002` (remove EVIDENCE_LINK row or restore mapping).  
2. **Resolve KBJI 2120:** Verify against KBJI 2026 whether code 2120 exists as hierarchy node; if yes add to `KBJI_HIERARCHY`, if no correct `OCCUPATION_KBJI2026_LINK`/mapping.  
3. **Fix eligibility derivation assumptions:** Clarify how `operational_evidence_present` is computed vs qualifying links; ensure logic matches README (requires VALIDATED + qualifying link).  
4. **Normalize M:N relationships:** Plan junction table for `supporting_kbji_mapping_ids`; consider junctions for polymorphic EVIDENCE_LINK if relational enforcement needed.  
5. **Handle duplicates intentionally:** Document whether EVIDENCE_LINK triple duplicates are required (multiple evidence paths) and design keys accordingly.  
6. **SKKNI completeness:** Do not fabricate units for SK06/SK08/SK09/SK10-SK14; document coverage limitations.  
7. **Update documentation:** Correct stale counts in README/STATUS_AUDIT if they will be used for validation.  
8. **Preserve user data:** Current PostgreSQL has synthetic test user data (per instructions) — any schema changes must be migration-safe.

---

## 13. Limitations and Unresolved Questions

**Limitations:**
- Read-only workbook analysis cannot confirm runtime derivation logic for flags beyond observed values.  
- `KBJI_HIERARCHY` appears to be a curated subset (30 nodes) — full KBJI 2026 structure not present.  
- Some source verification metadata is incomplete (NOT_VERIFIED/UNKNOWN).  

**Unresolved Questions:**
1. Are `SRC`, `SRC-` placeholders to be replaced with proper source_ids, or should those EVIDENCE_LINK rows be reclassified/removed?  
2. Should `SRC-KBJI-2014-2026` be added to SOURCE_REGISTER (and what role/permissions)?  
3. Is KBJI code 2120 valid in KBJI 2026 hierarchy? If yes, why missing from extracted subset?  
4. Are the 35 EVIDENCE_LINK triple-duplicates intentional (multiple evidence components/standards) or data errors?  
5. How is `operational_evidence_present` actually computed in code vs workbook values (mismatches observed)?  
6. Should `OSM002` be restored or its EVIDENCE_LINK orphan removed?  
7. What is required to reach VALIDATED status for records (expert review process)?  
8. Should TECHNOLOGY/TASK remain excluded from primary experiment (currently ineligible)?  

---

**Audit completed.** No workbook, code, or database modifications made. Exactly one new file created: `docs/audits/T4_R1A_AUDIT_CLARIFICATION.md`.  
**Summary:** 1 file created, workbook hash confirmed `792FDBFFCE25AD7266514E58A8F890877012D13BA672F13C386BACB4DF39694D`. Findings: PASS (PKs, duplicates clarified, 24-skill evidence clarified), PARTIAL (eligibility derivation, SKKNI completeness), FAIL (source resolution issues, orphan OSM002), UNRESOLVED (KBJI 2120). T4-R1 needs revision on: "all eligibility flags FALSE" framing (operational_evidence_present differs), duplicate triple characterization, KBJI 2120 assessment, and stale counts. Blockers before T4-R2: resolve source register gaps, KBJI 2120, orphan links, and eligibility derivation. No changes to workbook/code/database made.
