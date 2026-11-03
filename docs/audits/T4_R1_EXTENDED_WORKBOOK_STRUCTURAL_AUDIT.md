# T4-R1 — Extended Occupational Knowledge Base Structural Audit

**Audit type:** Read-only structural audit of the new primary OKB workbook  
**Date:** 2026-11-02  
**Role:** Senior data architect, database analyst, and research data auditor  
**Scope:** `data/occupational_knowledge_base_verified_v1_0_extended.xlsx` (primary) compared structurally with `data/occupational_knowledge_base_verified_v1_0.xlsx` (reference)  
**Revision inspected:** Repository at `7020a9f18ac3efa02f559f7eaac3faa95e8eef3c` plus pre-existing uncommitted changes (none modified).  
**Constraints followed:** Strictly read-only. No workbook, source code, SQL, schema, configuration, database records, or data modified. No migrations/imports executed. No LLM/external calls. PostgreSQL not used for this structural workbook audit.

---

## 1. Executive summary

The extended workbook (`v1.0 structure extended with v1.1.1 content`, 2026-11-01) is a **substantially expanded and restructured** version of the old workbook. It adds a new KBJI 2026 layer (7 sheets), an `EVIDENCE_LINK` table (970 rows), a `SOURCE_REGISTER` (24 rows), and additional linkage/eligibility fields across many sheets.

Key findings (verified):

- **Workbook identity:** `occupational_knowledge_base_verified_v1_0_extended.xlsx` — 167387 bytes, SHA-256 `792fdbffce25ad7266514e58a8f890877012d13ba672f13c386bacb4df39694d`. Old: 55399 bytes, `ce858a6aebe31d8237bf11217cce538d3cd657f4572d838866d2707b5536a630`.
- **Sheet count:** Extended has 25 sheets (18 common + 7 new). Old has 18 sheets (no sheets removed from common set).
- **Core counts unchanged:** 10 careers, 8 occupations, 87 skills, 17 skill groups, 155 career-skills, 146 competency units, 79 competency-skills, 10 occupation-competencies, 120 technologies, 35 tasks, 23 provenance, 26/25 occupation-source mappings (OSM002 removed), 97 skill-source evidence, 9/14 SKKNI standards (5 added).
- **FK integrity (value-based):** Most relationships are intact (100% match) including careers/skills/career-skills, competency units/skills/mappings, occupations/tasks/technologies, KBJI hierarchy/occupations/links, career-KBJI mappings. Issues found: `OCCUPATION_SOURCE_MAPPING.source_id` references `SRC-KBJI-2014-2026` not in `SOURCE_REGISTER` (8 rows, 68%); `EVIDENCE_LINK.source_id` has malformed values `SRC` (274) and `SRC-` (138) not in `SOURCE_REGISTER` (57.53% overall); `OCCUPATION_KBJI2026_LINK.kbji2026_code` has `2120` not present in `KBJI_HIERARCHY` (1 unmatched, 87.5%).
- **Validation status:** Per README, the dataset is **NOT expert-validated: 0 records VALIDATED, so 0 records are eligible in the PRIMARY experiment**. Only 4 cells containing "validated" appear anywhere (all in README/STATUS_AUDIT clarifying the non-validated state). No sheet has any row with `validation_status == VALIDATED`. Most entries are `NEEDS_REVIEW`/`UNRESOLVED`/`NOT_ASSESSED`/`PENDING`.
- **Sources:** README states O*NET/ESCO/KBJI 2014/old workbook are HISTORICAL/LEGACY and cannot contribute to scores; only `SRC-KBJI` (KBJI 2026) and `SRC-SKKNI` are marked `OPERATIONAL_PRIMARY/OPERATIONAL_STANDARD` with `can_contribute_to_scores=TRUE`. IndoTask is `NON_OPERATIONAL_PENDING_DECISION` (contrib FALSE). Many sources are `CARRIER_COPY`/`MARKET_SOURCE_CANDIDATE`/`LEGACY_REFERENCE` with `NOT_VERIFIED` permissions.
- **Technology/task provenance:** `TECHNOLOGY` and `TASK` still have no `provenance_id` and no FK to `PROVENANCE`; `EVIDENCE_LINK` links them via `source_id` (`SRC-LIGHTCAST`, `SRC`) but those source_ids are either not in `SOURCE_REGISTER` or malformed. README says they are US O*NET/Lightcast values (historical, ineligible).
- **Duplicate pairs:** No duplicate `(career_id, skill_id)`, no duplicate unit-skill pairs, no duplicate IDs. Notable: `OCCUPATION_SOURCE_MAPPING` has duplicate pairs like (O07, IndoTask, 252) twice; `EVIDENCE_LINK` has 35 duplicate (record_table, record_id, source_id) triples (CAREER_SKILL linked twice in some cases); `CAREER_KBJI_MAPPING` has some occupations mapped twice to different careers but no duplicate (career_id, occupation_id) pairs.
- **Unreferenced:** `O06 Network Professional` unused by CAREER_OCCUPATION/OCCUPATION_COMPETENCY/TECHNOLOGY/TASK; 8 SKKNI standards have 0 units (SK06,SK08,SK09,SK10-SK14); 51/75 KBJI occupations unreferenced by CAREER_KBJI_MAPPING; 24 skills have no structured skill-source evidence (same set as before).
- **Orphans/mismatches:** `EVIDENCE_LINK` has 412 unmatched `source_id` references (`SRC`, `SRC-`), 1 unmatched `standard_id` (none), and `CAREER_OCCUPATION` links use composite form that resolves correctly. `SKILL_SOURCE_EVIDENCE.linked_unit_id` has 35 nulls (35/97) — all non-null link correctly to COMPETENCY_UNIT.

**Overall assessment:** The extended workbook is a richer, more traceable Indonesian-centric structure (KBJI 2026 layer) but is **not validation-complete** (0 VALIDATED). It introduces some structural inconsistencies (malformed `source_id` values, missing `SOURCE_REGISTER` entries for `SRC-KBJI-2014-2026` and `SRC*`, unknown KBJI code `2120` in hierarchy/link) that must be resolved before import. The core 10-career/87-skill/155-relationship set remains intact.

---

## 2. Workbook metadata and file hash

| Item | Value |
|---|---|
| Primary workbook | `data/occupational_knowledge_base_verified_v1_0_extended.xlsx` |
| Old/reference workbook | `data/occupational_knowledge_base_verified_v1_0.xlsx` |
| Extended size (bytes) | 167387 |
| Extended SHA-256 | `792fdbffce25ad7266514e58a8f890877012d13ba672f13c386bacb4df39694d` |
| Old size (bytes) | 55399 |
| Old SHA-256 | `ce858a6aebe31d8237bf11217cce538d3cd657f4572d838866d2707b5536a630` |
| Extended sheets | 25 (visible) |
| Old sheets | 18 (visible) |
| Inspection method | openpyxl (non-readonly for merged_cells), value-based traversal, no modifications |

---

## 3. Complete sheet inventory

### Extended workbook sheets (25)
| Sheet | Rows (data) | Cols | State | Merged | Role (inferred) | Notes |
|---|---|---|---|---|---|---|
| README | 23 | 2 | visible | 0 | Documentation/metadata | States 0 VALIDATED, eligibility rules, source roles, technology/task as historical/ineligible |
| CAREER | 10 | 3 | visible | 0 | Master/entity | 10 careers, unique IDs/names |
| OCCUPATION | 8 | 3 | visible | 0 | Master/entity | 8 anchors; classification KBJI codes (includes 2120 for O08) |
| CAREER_OCCUPATION | 12 | 9 | visible | 0 | Relationship/junction | Added eligibility/operational flags + KBJI mapping IDs; `eligible_*` all FALSE |
| SKILL_GROUP | 17 | 2 | visible | 0 | Lookup/master | Unique |
| SKILL | 87 | 6 | visible | 0 | Master/entity | Replaced `status` with eligibility/operational flags (all `eligible_*` FALSE) |
| CAREER_SKILL | 155 | 11 | visible | 0 | Relationship | Added eligibility/operational flags; `evidence_source` stripped of O*NET/ESCO in many rows vs old |
| SKKNI_STANDARD | 14 | 11 | visible | 0 | Master/registry | Added 5 (SK10-SK14); JDIH fields present for 9 |
| COMPETENCY_UNIT | 146 | 6 | visible | 0 | Entity | Units, codes unique; evidence_class DIRECT; some URLs missing |
| OCCUPATION_COMPETENCY | 10 | 7 | visible | 0 | Relationship | Added relationship_id and flags |
| COMPETENCY_SKILL | 79 | 8 | visible | 0 | Junction/relationship | 34 unit IDs zero-padded vs old (CU*_007 style) |
| STATUS_AUDIT | 22 | 3 | visible | 0 | Audit/log summary | Counts/status labels |
| OCCUPATION_SOURCE_MAPPING | 25 | 11 | visible | 0 | Relationship/evidence link | Reworked sources to Indonesian (KBJI/SKKNI/IndoTask), added `source_id`, removed `source_scope`; 1 row removed vs old (OSM002) |
| TECHNOLOGY | 120 | 11 | visible | 0 | Evidence/signal table | Source changed to Lightcast, geography removed, added flags (all ineligible/false operational) |
| TASK | 35 | 10 | visible | 0 | Evidence/signal table | Sources mixed (SKKNI/IndoTask/KBJI), added flags |
| PROVENANCE | 23 | 7 | visible | 0 | Source registry | Restructured: added `source_id`, `record_status`; removed URL/page/source_type/scope_note |
| SKILL_SOURCE_EVIDENCE | 97 | 12 | visible | 0 | Evidence table | Added provenance/linkage fields; 35 rows have null `linked_unit_id` |
| STANDARD_COVERAGE | 9 | 7 | visible | 0 | Coverage/audit | Unchanged structure; flags SK06/SK08/SK09 partial/zero units |
| SOURCE_REGISTER | 24 | 19 | visible | 0 | **New** source registry/gate | Detailed source metadata, verification/permission/selection, `can_contribute_to_scores`; many NOT_VERIFIED |
| KBJI_HIERARCHY | 30 | 11 | visible | 0 | **New** master/hierarchy | KBJI 2026 hierarchy nodes; parent-child links; verified primary |
| KBJI_OCCUPATION | 75 | 13 | visible | 0 | **New** master/entity | KBJI 2026 occupations; linked to hierarchy; 51 unreferenced by career mappings |
| OCCUPATION_KBJI2026_LINK | 8 | 7 | visible | 0 | **New** junction/link | Links 8 anchors to KBJI 2026 codes; 1 code `2120` not in KBJI_HIERARCHY |
| CAREER_KBJI_MAPPING | 29 | 17 | visible | 0 | **New** relationship/evidence | Career→KBJI occupation mappings; mostly NEEDS_REVIEW/UNRESOLVED/PENDING, eligible_* all FALSE |
| EVIDENCE_LINK | 970 | 6 | visible | 0 | **New** junction/evidence linkage | Links records to sources/standards; has malformed source_ids `SRC`, `SRC-` |
| KJN_SOURCE_CLAIMS | 13 | 5 | visible | 0 | **New** claims/log | Documentary claims from KJN deck; support_status STATED_IN_DOCUMENT_TEXT |

### Old workbook sheets (18) — comparison reference
All 18 common sheets present in extended (no removals). See §11 for diffs.

---

## 4. Column-level analysis (key observations)

- **README:** Expanded to explain validation, eligibility derivation, source roles, and that technologies/tasks are historical/ineligible.
- **Eligibility model introduced:** Many tables now have `operational_evidence_present`, `eligible_for_career_fit`, `eligible_for_skill_gap` — all `FALSE` in extended except where explicitly true (e.g. CAREER_OCCUPATION has 7 TRUE for operational evidence; COMPETENCY_SKILL all TRUE; CAREER_KBJI_MAPPING mostly TRUE for operational evidence but all eligible FALSE).
- **SKILL:** `status` removed; replaced by operational/eligibility flags.
- **CAREER_SKILL:** `evidence_source` simplified (dropped O*NET/ESCO suffixes in many rows).
- **SKKNI_STANDARD:** Expanded to 14 with JDIH metadata for 9; 5 added as screening (SK10-SK14), 0 units.
- **COMPETENCY_SKILL:** Unit IDs normalized to zero-padded form (34 rows changed).
- **OCCUPATION_SOURCE_MAPPING:** Restructured to use `source_id` and Indonesian sources; OSM002 removed.
- **PROVENANCE:** Restructured to use `source_id` and `record_status`; removed URL/page/section/source_type/scope_note.
- **SKILL_SOURCE_EVIDENCE:** Added linkage fields (`source_id`, `reference_resolution`, `linked_unit_id`, `competency_skill_link_exists`).
- **Data types/whitespace:** Some double spaces/trailing spaces in `evidence_source` (old), leading spaces in some `SOURCE_REGISTER` fields, non-ASCII in README/text; generally clean IDs.

---

## 5. Candidate primary key analysis

Verified by value-uniqueness (non-null):

| Sheet | Candidate PK(s) | Unique? | Nulls? | Suitable? | Notes |
|---|---|---|---|---|---|
| CAREER | `career_id`, `canonical_name` | Yes | No | `career_id` preferred (natural name also unique) | Stable |
| OCCUPATION | `occupation_id`, `canonical_name`, `classification` | Yes | No | `occupation_id` preferred | 8 anchors |
| CAREER_OCCUPATION | `legacy_career_occupation_id` | Yes | No | Surrogate preferred; composite (career_id,occupation_id) not unique (each appears twice) | 12 rows, 10 careers × relationships |
| SKILL_GROUP | `skill_group_id`, `name` | Yes | No | Either; `skill_group_id` preferred | 17 groups |
| SKILL | `skill_id`, `canonical_name` | Yes | No | `skill_id` preferred | 87 skills |
| CAREER_SKILL | `relationship_id` | Yes | No | Surrogate | (career_id,skill_id) has no duplicates but not a single-column key |
| SKKNI_STANDARD | `standard_id`, `title`, `field` | Yes | No | `standard_id` preferred | 14 standards |
| COMPETENCY_UNIT | `unit_id`, `code`, `title` | Yes | No | `unit_id` or `code` preferred | 146 units |
| OCCUPATION_COMPETENCY | `relationship_id` | Yes | No | Surrogate | (occupation_id,standard_id) not unique |
| COMPETENCY_SKILL | `relationship_id`, `unit_id` | Yes (unit_id unique alone here) | No | `relationship_id` or `unit_id` (unit appears once) | 79 rows |
| STATUS_AUDIT | `Career` | Yes | No | Text key | Summary rows |
| OCCUPATION_SOURCE_MAPPING | `mapping_id` | Yes | No | Surrogate | Duplicates in (occupation,source_name,source_code) pairs exist |
| TECHNOLOGY | `technology_id` | Yes | No | Surrogate | Same name appears under different IDs |
| TASK | `task_id`, `task_description` | Yes | No | `task_id` preferred | 35 tasks |
| PROVENANCE | `provenance_id`, `document_title` | Yes | No | `provenance_id` preferred | 23 provenance |
| SKILL_SOURCE_EVIDENCE | `evidence_id` | Yes | No | Surrogate | 97 evidence rows |
| STANDARD_COVERAGE | `standard_id`, `number` | Yes | No | Either | 9 standards |
| SOURCE_REGISTER | `source_id`, `source_name` | Yes | No | `source_id` preferred | 24 sources |
| KBJI_HIERARCHY | `node_id`, `kbji_code`, `definition` | Yes | No | `node_id` or `kbji_code` preferred | 30 nodes |
| KBJI_OCCUPATION | `occupation_id`, `occupation_name`, `occupation_code`, `description` | Yes | No | `occupation_id` preferred | 75 occupations |
| OCCUPATION_KBJI2026_LINK | `link_id`, `occupation_id`, `kbji2026_code`, `kbji2026_title`, `kbji2014_title_legacy` | Yes | No | `link_id` preferred | 8 links |
| CAREER_KBJI_MAPPING | `mapping_id`, `evidence_summary` | Yes | No | `mapping_id` preferred | 29 mappings |
| EVIDENCE_LINK | `link_id` | Yes | No | Surrogate | 970 links |
| KJN_SOURCE_CLAIMS | `claim_id`, `claim_topic`, `text_in_document_original_indonesian`, `interpretation_note` | Yes | No | `claim_id` preferred | 13 claims |

**No sheet lacks a reliable candidate key.**

---

## 6. Candidate foreign key and relationship analysis

Value-based checks (only confirmed where all non-null values match):

| Relationship (source → target) | Non-null | Nulls | Matched rows | Unmatched | Integrity | Type | Notes |
|---|---|---|---|---|---|---|---|
| CAREER_OCCUPATION.career_id → CAREER.career_id | 12 | 0 | 12 | 0 | 100% | M:1 | OK |
| CAREER_OCCUPATION.occupation_id → OCCUPATION.occupation_id | 12 | 0 | 12 | 0 | 100% | M:1 | OK |
| CAREER_OCCUPATION.supporting_kbji_mapping_ids → CAREER_KBJI_MAPPING.mapping_id (semicolon) | 7 | 5 | 7 | 0 | 100% | M:N via list | OK |
| SKILL.skill_group_id → SKILL_GROUP.skill_group_id | 87 | 0 | 87 | 0 | 100% | M:1 | OK |
| CAREER_SKILL.career_id → CAREER.career_id | 155 | 0 | 155 | 0 | 100% | M:1 | OK |
| CAREER_SKILL.skill_id → SKILL.skill_id | 155 | 0 | 155 | 0 | 100% | M:1 | OK |
| COMPETENCY_UNIT.standard_id → SKKNI_STANDARD.standard_id | 146 | 0 | 146 | 0 | 100% | M:1 | OK |
| OCCUPATION_COMPETENCY.occupation_id → OCCUPATION.occupation_id | 10 | 0 | 10 | 0 | 100% | M:1 | OK |
| OCCUPATION_COMPETENCY.standard_id → SKKNI_STANDARD.standard_id | 10 | 0 | 10 | 0 | 100% | M:1 | OK |
| COMPETENCY_SKILL.unit_id → COMPETENCY_UNIT.unit_id | 79 | 0 | 79 | 0 | 100% | M:1 | OK |
| COMPETENCY_SKILL.skill_id → SKILL.skill_id | 79 | 0 | 79 | 0 | 100% | M:1 | OK |
| OCCUPATION_SOURCE_MAPPING.occupation_id → OCCUPATION.occupation_id | 25 | 0 | 25 | 0 | 100% | M:1 | OK |
| OCCUPATION_SOURCE_MAPPING.source_id → SOURCE_REGISTER.source_id | 25 | 0 | 17 | 8 | 68.0% | M:1 | **UNMATCHED:** `SRC-KBJI-2014-2026` (8 rows) not in SOURCE_REGISTER |
| TECHNOLOGY.occupation_id → OCCUPATION.occupation_id | 120 | 0 | 120 | 0 | 100% | M:1 | OK |
| TASK.occupation_id → OCCUPATION.occupation_id | 35 | 0 | 35 | 0 | 100% | M:1 | OK |
| PROVENANCE.source_id → SOURCE_REGISTER.source_id | 23 | 0 | 23 | 0 | 100% | M:1 | OK |
| SKILL_SOURCE_EVIDENCE.skill_id → SKILL.skill_id | 97 | 0 | 97 | 0 | 100% | M:1 | OK |
| SKILL_SOURCE_EVIDENCE.source_id → SOURCE_REGISTER.source_id | 97 | 0 | 97 | 0 | 100% | M:1 | OK |
| SKILL_SOURCE_EVIDENCE.linked_unit_id → COMPETENCY_UNIT.unit_id | 62 | 35 | 62 | 0 | 100% | M:1 (nullable) | 35 nulls OK |
| STANDARD_COVERAGE.standard_id → SKKNI_STANDARD.standard_id | 9 | 0 | 9 | 0 | 100% | 1:1 | OK |
| KBJI_HIERARCHY.parent_code → KBJI_HIERARCHY.kbji_code | 27 | 3 | 27 | 0 | 100% | Self-ref M:1 | OK (roots have null parent) |
| KBJI_OCCUPATION.parent_subgolongan_code → KBJI_HIERARCHY.kbji_code | 75 | 0 | 75 | 0 | 100% | M:1 | OK |
| OCCUPATION_KBJI2026_LINK.occupation_id → OCCUPATION.occupation_id | 8 | 0 | 8 | 0 | 100% | M:1 | OK |
| OCCUPATION_KBJI2026_LINK.kbji2026_code → KBJI_HIERARCHY.kbji_code | 8 | 0 | 7 | 1 | 87.5% | M:1 | **UNMATCHED:** `2120` (O08) not in KBJI_HIERARCHY |
| CAREER_KBJI_MAPPING.career_id → CAREER.career_id | 29 | 0 | 29 | 0 | 100% | M:1 | OK |
| CAREER_KBJI_MAPPING.occupation_id → KBJI_OCCUPATION.occupation_id | 27 | 2 | 27 | 0 | 100% | M:1 (nullable) | 2 nulls OK |
| EVIDENCE_LINK.source_id → SOURCE_REGISTER.source_id | 970 | 0 | 558 | 412 | 57.53% | M:1 | **UNMATCHED:** `SRC` (274), `SRC-` (138) not in SOURCE_REGISTER |
| EVIDENCE_LINK.standard_id → SKKNI_STANDARD.standard_id | 286 | 684 | 286 | 0 | 100% | M:1 (nullable) | OK |

**Inferred-only relationships (by name only, not value-verified):** None found that are clean — all checked above use actual values.

---

## 7. Cardinality analysis

| Relationship | Source rows/distinct | Target used/distinct | Cardinality | Notes |
|---|---|---|---|---|
| CAREER_OCCUPATION.career_id → CAREER.career_id | 12 / 10 | 10 / 10 | 1:N (2 careers appear twice) | C03, C07 mapped to 2 occupations each |
| CAREER_OCCUPATION.occupation_id → OCCUPATION.occupation_id | 12 / 7 | 7 / 8 | 1:N | O06 unreferenced |
| SKILL.skill_group_id → SKILL_GROUP.skill_group_id | 87 / 17 | 17 / 17 | 1:N | All groups used |
| CAREER_SKILL.career_id → CAREER.career_id | 155 / 10 | 10 / 10 | 1:N | All careers |
| CAREER_SKILL.skill_id → SKILL.skill_id | 155 / 87 | 87 / 87 | 1:N | 51 skills used once, 36 used multiple times |
| COMPETENCY_UNIT.standard_id → SKKNI_STANDARD.standard_id | 146 / 6 | 6 / 14 | 1:N | 8 standards unused (all have 0 units) |
| OCCUPATION_COMPETENCY.occupation_id → OCCUPATION.occupation_id | 10 / 7 | 7 / 8 | 1:N | O06 unreferenced |
| OCCUPATION_COMPETENCY.standard_id → SKKNI_STANDARD.standard_id | 10 / 8 | 8 / 14 | 1:N | 6 standards unused |
| COMPETENCY_SKILL.unit_id → COMPETENCY_UNIT.unit_id | 79 / 79 | 79 / 146 | 1:1 | Each unit appears once |
| COMPETENCY_SKILL.skill_id → SKILL.skill_id | 79 / 50 | 50 / 87 | 1:N | 37 skills unused |
| OCCUPATION_SOURCE_MAPPING.occupation_id → OCCUPATION.occupation_id | 25 / 8 | 8 / 8 | 1:N | All occupations mapped |
| OCCUPATION_SOURCE_MAPPING.source_id → SOURCE_REGISTER.source_id | 25 / 3 | 2 / 24 | 1:N (partial) | Only 2 of 3 source_ids resolvable |
| TECHNOLOGY.occupation_id → OCCUPATION.occupation_id | 120 / 7 | 7 / 8 | 1:N | O06 unreferenced |
| TASK.occupation_id → OCCUPATION.occupation_id | 35 / 7 | 7 / 8 | 1:N | O06 unreferenced |
| PROVENANCE.source_id → SOURCE_REGISTER.source_id | 23 / 5 | 5 / 24 | 1:N | OK |
| SKILL_SOURCE_EVIDENCE.skill_id → SKILL.skill_id | 97 / 63 | 63 / 87 | 1:N | 24 skills unused |
| SKILL_SOURCE_EVIDENCE.source_id → SOURCE_REGISTER.source_id | 97 / 2 | 2 / 24 | 1:N | OK |
| SKILL_SOURCE_EVIDENCE.linked_unit_id → COMPETENCY_UNIT.unit_id | 62 / 62 | 62 / 146 | 1:1 | 84 units unused |
| KBJI_HIERARCHY.parent_code → KBJI_HIERARCHY.kbji_code | 27 / 13 | 13 / 30 | 1:N (self-ref) | Tree structure |
| KBJI_OCCUPATION.parent_subgolongan_code → KBJI_HIERARCHY.kbji_code | 75 / 17 | 17 / 30 | 1:N | OK |
| OCCUPATION_KBJI2026_LINK.occupation_id → OCCUPATION.occupation_id | 8 / 8 | 8 / 8 | 1:1 | All anchors linked |
| OCCUPATION_KBJI2026_LINK.kbji2026_code → KBJI_HIERARCHY.kbji_code | 8 / 8 | 7 / 30 | 1:1 (partial) | `2120` missing from hierarchy |
| CAREER_KBJI_MAPPING.career_id → CAREER.career_id | 29 / 10 | 10 / 10 | 1:N | All careers mapped |
| CAREER_KBJI_MAPPING.occupation_id → KBJI_OCCUPATION.occupation_id | 27 / 24 | 24 / 75 | 1:N | 51 KBJI occupations unmapped |
| EVIDENCE_LINK.source_id → SOURCE_REGISTER.source_id | 970 / 7 | 5 / 24 | 1:N (partial) | Malformed `SRC`, `SRC-` |
| EVIDENCE_LINK.standard_id → SKKNI_STANDARD.standard_id | 286 / 8 | 8 / 14 | 1:N | OK |

**Junction tables:** `CAREER_OCCUPATION`, `COMPETENCY_SKILL`, `OCCUPATION_COMPETENCY`, `CAREER_KBJI_MAPPING`, `OCCUPATION_KBJI2026_LINK`, `OCCUPATION_SOURCE_MAPPING`, `EVIDENCE_LINK` are junction/relationship tables. `EVIDENCE_LINK` is a polymorphic linkage table (links to multiple record types).

---

## 8. Duplicate and orphan audit

| Check | Result | Details |
|---|---|---|
| Duplicate career IDs/names | None | CAREER unique |
| Duplicate skill IDs/names (exact, normalized) | None | SKILL unique; NFKC normalized no collisions |
| Duplicate skill-group IDs/names | None | SKILL_GROUP unique |
| Duplicate (career_id, skill_id) in CAREER_SKILL | None | 0 duplicates |
| Duplicate relationship IDs | None | All unique |
| Duplicate unit IDs/codes | None | COMPETENCY_UNIT unique |
| Duplicate (unit_id, skill_id) in COMPETENCY_SKILL | None | 0 |
| Duplicate (occupation_id, standard_id) in OCCUPATION_COMPETENCY | None | 0 |
| Duplicate mapping_id / link_id / evidence_id | None | All unique |
| OCCUPATION_SOURCE_MAPPING duplicate natural pairs | **Yes** | (O07, IndoTask, 252) appears twice; (O08, IndoTask, 251) appears twice |
| TECHNOLOGY duplicate (occupation_id, technology_name) | None | Names repeat across different occupations/IDs but pairs unique |
| TASK duplicate (occupation_id, task_description) | None | Unique |
| EVIDENCE_LINK duplicate (record_table, record_id, source_id) | **Yes (35 triples)** | e.g. CAREER_SKILL CS048-CS053 linked twice to SRC-SKKNI; others appear |
| SKILL_SOURCE_EVIDENCE duplicate (skill_id, source_reference) | None | Unique |
| CAREER_KBJI_MAPPING duplicate (career_id, occupation_id) | None | No duplicates |
| Orphan careers/skills/occupations (no relationships) | None for core | All 10 careers have skills/occupations; all 87 skills used in CAREER_SKILL; O06 unused by some tables but exists |
| Orphan references (FK failures) | **Yes** | OCCUPATION_SOURCE_MAPPING.source_id → SRC-KBJI-2014-2026 (8); EVIDENCE_LINK.source_id → SRC, SRC- (412); OCCUPATION_KBJI2026_LINK.kbji2026_code → 2120 (1) |
| Skills with no structured evidence | **Yes (24)** | Same set as before: S003,S009,S010,S012,S013,S014,S019,S023,S025,S029,S042,S044,S046,S047,S050,S055,S056,S057,S058,S061,S066,S067,S070,S083 |
| KBJI occupations unreferenced | **Yes (51/75)** | 51 KBJI occupations not used in CAREER_KBJI_MAPPING |
| Standards with 0 units | **Yes (8/14)** | SK06,SK08,SK09,SK10,SK11,SK12,SK13,SK14 |

**Note:** Repeated names are not automatically duplicates when IDs/contexts differ (e.g. same technology name under different technology_ids/occupations is intentional per structure).

---

## 9. Data quality findings

| Issue | Severity | Location | Details |
|---|---|---|---|
| Malformed source_id values | **High** | EVIDENCE_LINK.source_id | `SRC` (274) and `SRC-` (138) not in SOURCE_REGISTER; links cannot resolve to registered sources |
| Missing SOURCE_REGISTER entries | **High** | SOURCE_REGISTER vs references | `SRC-KBJI-2014-2026` used by OCCUPATION_SOURCE_MAPPING (8) not present; `SRC`/`SRC-` missing |
| Unknown KBJI hierarchy code | **High** | OCCUPATION_KBJI2026_LINK.kbji2026_code | `2120` links O08 but not in KBJI_HIERARCHY (hierarchy has up to 2529) |
| Duplicate evidence links | **Medium** | EVIDENCE_LINK | 35 triples appear twice (CAREER_SKILL items linked twice) — may indicate double-counting or mapping artifact |
| Duplicate occupation-source mappings | **Medium** | OCCUPATION_SOURCE_MAPPING | (O07,IndoTask,252) and (O08,IndoTask,251) duplicated |
| OSM002 removed | **Medium** | OCCUPATION_SOURCE_MAPPING | Old had O*NET mapping for O01 (OSM002); removed in extended (replaced by KBJI/SKKNI/IndoTask) |
| Missing provenance detail | **Medium** | PROVENANCE | URL/page/section/source_type/scope_note removed; replaced by source_id/record_status |
| Null linked units | **Low** | SKILL_SOURCE_EVIDENCE.linked_unit_id | 35/97 null (IndoTask evidence) — expected per notes |
| Whitespace issues | **Low** | CAREER_SKILL.evidence_source, EVIDENCE_LINK.evidence_component, SOURCE_REGISTER | Trailing/double spaces and leading spaces present |
| All eligible flags false | **Medium (by design)** | Most tables | Per README, eligibility requires VALIDATED records; nothing is validated yet |
| Technology/task ineligible | **Medium (by design)** | TECHNOLOGY, TASK | Marked historical/ineligible; no provenance FK |
| Inconsistent source naming | **Medium** | Various | `SKKNI` vs `INDOTASK` vs `IndoTask` casing varies |

**No empty sheets found.** All columns have data as analyzed.

---

## 10. Validation/status analysis

### README claims (verified)
> "Working dataset, NOT expert-validated: 0 records VALIDATED, so 0 records are eligible in the PRIMARY experiment. Layer B (job postings) not started; KJN has no records (NEEDS_SOURCE)."
> "validation_status: NEEDS_REVIEW/UNRESOLVED/NOT_ASSESSED/VALIDATED. eligible_* flags are derived from EVIDENCE_LINK (qualifying link from a source with can_contribute_to_scores=TRUE) AND validation_status=VALIDATED (see CONFIG_ELIGIBILITY). operational_evidence_present = has a qualifying link."

### Direct search for VALIDATED
Only 4 occurrences found (all explanatory):
1. README row19: "NOT expert-validated: 0 records VALIDATED..."
2. README row20: lists VALIDATED as possible status
3. STATUS_AUDIT row5: "9 legacy records + 5 added from JDIH screening; not expert-validated"
4. STATUS_AUDIT row20: "NEEDS_REVIEW (not expert-validated)"

**No cell equals `VALIDATED`.**

### Status/validation columns distribution
| Sheet | Column | Values (counts) | Notes |
|---|---|---|---|
| SKKNI_STANDARD | status | `Berlaku` x14 | All valid/enacted |
| PROVENANCE | record_status | `RETAINED_LEGACY` x21, `SUPERSEDED_LEGACY` x2 | Mostly retained |
| STANDARD_COVERAGE | unit_inventory_status | `COMPLETE` x5, `PARTIAL` x3, `PROFILE-COMPLETE` x1 | Matches prior findings |
| SOURCE_REGISTER | selection_status | `PENDING_AUDIT` x17, `CORE` x4, `OPTIONAL` x3 | Most pending |
| SOURCE_REGISTER | source_role | Mixed (OPERATIONAL_PRIMARY/OPERATIONAL_STANDARD/CARRIER_COPY/MARKET_SOURCE_CANDIDATE/LEGACY_REFERENCE/HISTORICAL_REFERENCE/CANDIDATE_REFERENCE/NON_OPERATIONAL_PENDING_DECISION) | See §2 |
| SOURCE_REGISTER | can_contribute_to_scores | `FALSE` x22, `TRUE` x2 | Only SRC-KBJI and SRC-SKKNI TRUE |
| SOURCE_REGISTER | license_status/verification_metadata/verification_content/permission_status | Mostly `NOT_VERIFIED`/`UNKNOWN`/`NOT_APPLICABLE` | Poorly verified |
| KBJI_HIERARCHY | verification_status | `VERIFIED_PRIMARY` x30 | All verified |
| KBJI_OCCUPATION | verification_status | `VERIFIED_PRIMARY` x75 | All verified |
| CAREER_KBJI_MAPPING | validation_status | `NEEDS_REVIEW` x27, `UNRESOLVED` x2 | None VALIDATED |
| CAREER_KBJI_MAPPING | expert_review_status | `PENDING` x29 | None reviewed |
| CAREER_KBJI_MAPPING | coverage_status | `STRONG` x14, `PARTIAL` x13, `NOT_VERIFIED` x2 | Mixed |
| KJN_SOURCE_CLAIMS | support_status | `STATED_IN_DOCUMENT_TEXT` x12, `CONFLICTS_WITH_KBJI2026` x1 | Mostly stated |

**Conclusion:** Validation status cannot be determined as complete for most sheets; the workbook explicitly states **0 records VALIDATED**. No sheet contains `VALIDATED` records. Eligibility flags are all false across the board per the rules.

---

## 11. Old-versus-extended workbook comparison

### Sheet presence
- **In both:** All 18 old sheets present in extended.
- **Only old:** None.
- **Only new:** `SOURCE_REGISTER`, `KBJI_HIERARCHY`, `KBJI_OCCUPATION`, `OCCUPATION_KBJI2026_LINK`, `CAREER_KBJI_MAPPING`, `EVIDENCE_LINK`, `KJN_SOURCE_CLAIMS`.

### Structural changes (common sheets)
| Sheet | Classification | Changes |
|---|---|---|
| README | Retained with structural changes | 5 new rows added (Column conventions, Constant fields omitted, Evidence class, Not included, Source roles); values updated (v1.0→v1.1.1, 9→14 standards, explicit 0 VALIDATED) |
| CAREER/OCCUPATION/SKILL_GROUP | Retained without significant structural changes | Identical structure/counts/IDs |
| CAREER_OCCUPATION | Retained with structural changes | +5 columns (legacy_career_occupation_id, supporting_kbji_mapping_ids, operational_evidence_present, eligible_for_career_fit, eligible_for_skill_gap) |
| SKILL | Retained with structural changes | -1 (`status`), +3 flags |
| CAREER_SKILL | Retained with structural changes | +3 flags; `evidence_source` values stripped of O*NET/ESCO in many rows |
| SKKNI_STANDARD | Retained with structural changes | +5 columns (JDIH fields, record_origin, candidate_career_ids_hint); +5 rows (SK10-SK14) |
| COMPETENCY_UNIT | Retained with structural changes | +2 columns (evidence_class, crosscheck_source_url) |
| OCCUPATION_COMPETENCY | Retained with structural changes | +4 columns |
| COMPETENCY_SKILL | Retained with structural changes | +3 columns; 34 unit IDs zero-padded |
| STATUS_AUDIT | Retained with structural changes | +6 rows (KBJI/EVIDENCE/SOURCE_REGISTER related) |
| OCCUPATION_SOURCE_MAPPING | Retained with structural changes | -1 (`source_scope`), +4 (source_id, operational flags); -1 row (OSM002); major source rework (ESCO/O*NET→SKKNI/IndoTask/KBJI) |
| TECHNOLOGY | Retained with structural changes | -1 (`geography`), +3 flags; source `O*NET/Lightcast`→`Lightcast`; all rows changed in source field |
| TASK | Retained with structural changes | -2 columns, +3 flags; sources reworked |
| PROVENANCE | Retained with structural changes | -4 columns, +2 (source_id, record_status); major restructuring |
| SKILL_SOURCE_EVIDENCE | Retained with structural changes | +4 columns |
| STANDARD_COVERAGE | Retained without significant structural changes | Identical structure/counts; still shows SK06/SK08/SK09 partial |

### ID-level changes (key sheets)
| Sheet | Only old | Only new | Notes |
|---|---|---|---|
| SKKNI_STANDARD | [] | SK10,SK11,SK12,SK13,SK14 | 5 added |
| OCCUPATION_SOURCE_MAPPING | OSM002 | [] | 1 removed (O*NET mapping) |
| Others (CAREER,SKILL,CAREER_SKILL,COMPETENCY_*) | [] | [] | IDs preserved |

### Value changes
- **CAREER_SKILL.evidence_source:** 155 rows changed (O*NET/ESCO removed, simplified)
- **COMPETENCY_SKILL.unit_id:** 34 rows zero-padded
- **OCCUPATION_SOURCE_MAPPING:** 15 rows changed (sources/codes reworked)
- **TECHNOLOGY.source:** All 120 rows changed
- **TASK.source:** All 35 rows changed
- **PROVENANCE:** 10 rows changed (structure)
- **SKILL_SOURCE_EVIDENCE:** 32 rows changed

### New sheets (7) — all added
`SOURCE_REGISTER`, `KBJI_HIERARCHY`, `KBJI_OCCUPATION`, `OCCUPATION_KBJI2026_LINK`, `CAREER_KBJI_MAPPING`, `EVIDENCE_LINK`, `KJN_SOURCE_CLAIMS` — no removals from old.

**Conclusion:** Extended is **not a strict superset** — it restructures columns, reworks sources, and removes some fields. It adds substantial new Indonesian KBJI layer. Cannot be assumed superset.

---

## 12. Thesis scope relevance analysis

**Thesis scope:** 10 selected IT careers; Indonesian occupational classification; Indonesian national occupational and competency standards (SKKNI); career-skill relationships; skill evidence and source traceability; technology/task only if demonstrably in scope.

### Relevant sheets/categories
| Category | Sheets | Relevance | Notes |
|---|---|---|---|
| Careers (10) | CAREER | **Core** | Exactly 10 IT careers preserved |
| Occupations (Indonesian anchors) | OCCUPATION, OCCUPATION_KBJI2026_LINK | **Core** | KBJI 2026 links added; Indonesian classification |
| Skills/relationships | SKILL_GROUP, SKILL, CAREER_SKILL | **Core** | 87 skills, 155 relationships preserved |
| SKKNI standards/competencies | SKKNI_STANDARD, COMPETENCY_UNIT, OCCUPATION_COMPETENCY, COMPETENCY_SKILL, STANDARD_COVERAGE | **Core** | Indonesian national standards; 8 standards have 0 units (partial) |
| Evidence/traceability | SKILL_SOURCE_EVIDENCE, EVIDENCE_LINK, PROVENANCE | **Core** | Rich linkage added; but many source_ids malformed/unregistered |
| Indonesian occupational layer | KBJI_HIERARCHY, KBJI_OCCUPATION, CAREER_KBJI_MAPPING | **Core (needs validation)** | Strongly aligned with Indonesian scope; mostly NEEDS_REVIEW, not expert-validated |
| Source governance | SOURCE_REGISTER | **Core** | Documents Indonesian sources as primary (SRC-KBJI, SRC-SKKNI); others pending |
| Occupation-source mapping | OCCUPATION_SOURCE_MAPPING | **Core** | Reworked to Indonesian sources |

### Potentially out of scope / historical
| Category | Sheets | Status | Notes |
|---|---|---|---|
| Technologies | TECHNOLOGY | **Historical/ineligible (per README)** | US O*NET/Lightcast, no provenance FK, all eligible FALSE; README says "Python/Java/SQL/AWS/Docker/etc. are stored as technologies, not canonical skills" and "historical, ineligible" |
| Tasks | TASK | **Historical/ineligible (per README)** | Mixed sources, all eligible FALSE |
| Old international sources | Legacy references in old workbook | **Removed/relegated** | O*NET/ESCO removed from many mappings; marked HISTORICAL/LEGACY in README, cannot contribute to scores |
| Job postings/market sources | SOURCE_REGISTER entries for ATS/job boards | **Not started/pending** | Layer B not started; all MARKET_SOURCE_CANDIDATE pending audit |
| KJN | KJN_SOURCE_CLAIMS | **Unclear/needs review** | Has 1 conflict with KBJI 2026 noted; no records in experiment scope per README ("KJN has no records (NEEDS_SOURCE)") |

**Recommendations for eligibility:**
- **Use as primary:** CAREER, OCCUPATION, OCCUPATION_KBJI2026_LINK, SKILL_GROUP, SKILL, CAREER_SKILL, SKKNI_STANDARD, COMPETENCY_UNIT, OCCUPATION_COMPETENCY, COMPETENCY_SKILL, STANDARD_COVERAGE, KBJI_HIERARCHY, KBJI_OCCUPATION, CAREER_KBJI_MAPPING (with validation), SOURCE_REGISTER (for approved sources only), EVIDENCE_LINK, PROVENANCE, SKILL_SOURCE_EVIDENCE, OCCUPATION_SOURCE_MAPPING.
- **Do not import as-scored:** TECHNOLOGY, TASK — treat as descriptive/historical only unless explicitly approved and re-sourced to Indonesian context.
- **Exclude from primary experiment:** Everything marked ineligible/NOT_VERIFIED/pending; only sources with `can_contribute_to_scores=TRUE` and records with `validation_status=VALIDATED` can contribute (and none are VALIDATED).
- **Do not introduce ESCO/O*NET** as thesis data sources — already removed/relegated.

**Records requiring review:** All CAREER_KBJI_MAPPING (NEEDS_REVIEW/UNRESOLVED), KJN claims, sources with NOT_VERIFIED status, entries with malformed source_ids, the `2120` KBJI code mapping.

---

## 13. Initial PostgreSQL design implications

**This section is analysis/recommendation only — no SQL/migrations/tables created.**

### Sheets likely needing new PostgreSQL tables
| Sheet | Priority | Notes |
|---|---|---|
| SOURCE_REGISTER | **High** | New source governance table; needed for EVIDENCE_LINK resolution |
| KBJI_HIERARCHY | **High** | New hierarchy table (self-referential) |
| KBJI_OCCUPATION | **High** | New occupation table (Indonesian) |
| OCCUPATION_KBJI2026_LINK | **High** | Junction between OCCUPATION and KBJI_HIERARCHY/KBJI_OCCUPATION |
| CAREER_KBJI_MAPPING | **High** | Career→KBJI mappings with validation status |
| EVIDENCE_LINK | **High** | Polymorphic evidence linkage table |
| KJN_SOURCE_CLAIMS | **Medium** | Claims table; may be optional/log |

### Existing tables that may need additional columns
| Table | Changes | Notes |
|---|---|---|
| career_occupations | Add legacy_career_occupation_id, supporting_kbji_mapping_ids, operational_evidence_present, eligible_for_career_fit, eligible_for_skill_gap | Match extended structure |
| skills | Remove/add columns (status→flags), add operational/eligible flags | Schema change |
| career_skills | Add operational/eligible flags; may need to handle evidence_source changes | Schema change |
| skkni_standards | Add JDIH fields, record_origin, candidate_career_ids_hint; support more standards (14) | Schema change |
| competency_units | Add evidence_class, crosscheck_source_url | Schema change |
| occupation_competencies | Add relationship_id, operational/eligible flags | Schema change |
| competency_skills | Add operational/eligible flags | Schema change |
| occupation_source_mapping | Restructure (add source_id, add flags, remove source_scope); handle removed OSM002 | Major restructuring |
| technologies | Remove geography, add flags; source values change | Schema change |
| tasks | Remove source_period/geography, add flags | Schema change |
| provenance | Major restructure (add source_id, record_status, remove URL/page/source_type/scope_note) | Major restructuring |
| skill_source_evidence | Add source_id, reference_resolution, linked_unit_id, competency_skill_link_exists | Schema change |

### Existing tables that may need restructuring
- **provenance:** Significant restructuring — need to ensure FK to new source_register
- **occupation_source_mapping:** Source model changes (Indonesian focus)
- **career_skills/skills:** Eligibility/operational evidence model added

### Potential junction tables
Already present as junctions; `EVIDENCE_LINK` is a new polymorphic junction.

### Candidate keys/constraints
- Preserve existing PKs/FKs where possible
- Add FKs to SOURCE_REGISTER once entries exist
- Add FKs for KBJI tables
- Handle nullable fields (supporting_kbji_mapping_ids, linked_unit_id, CAREER_KBJI_MAPPING.occupation_id)
- Consider unique constraints on natural keys where appropriate

### Import order / dependencies
1. **Independent first:** SOURCE_REGISTER, SKILL_GROUP, CAREER, OCCUPATION, SKILL_GROUP/CAREER structure
2. **SKKNI layer:** SKKNI_STANDARD, COMPETENCY_UNIT, STANDARD_COVERAGE
3. **KBJI layer:** KBJI_HIERARCHY (self-ref, parents first), KBJI_OCCUPATION, OCCUPATION_KBJI2026_LINK
4. **Core relationships:** CAREER_OCCUPATION, CAREER_SKILL
5. **Competency mappings:** OCCUPATION_COMPETENCY, COMPETENCY_SKILL
6. **Provenance/sources:** PROVENANCE, OCCUPATION_SOURCE_MAPPING (depends on SOURCE_REGISTER)
7. **Evidence:** SKILL_SOURCE_EVIDENCE, TECHNOLOGY, TASK (may be treated separately as historical)
8. **Linkages:** CAREER_KBJI_MAPPING (depends on careers and KBJI_OCCUPATION), EVIDENCE_LINK (depends on all above, many source_ids may need resolution)

### Circular dependencies
- **KBJI_HIERARCHY:** Self-referential (parent_code → kbji_code) — needs careful import order (roots first) or deferred constraints
- **EVIDENCE_LINK:** Polymorphic, references many tables and sources — complex
- **Potential:** None obvious from structure, but EVIDENCE_LINK creates many-to-many links

### Potentially destructive changes
- **PROVENANCE restructure:** Columns removed; data model changes significantly
- **SKILL:** `status` column removed
- **OCCUPATION_SOURCE_MAPPING:** OSM002 removed; structure changed
- **TECHNOLOGY/TASK:** Column removals and source changes
- **Adding all-FALSE flags:** May affect existing logic expecting different structure
- **Must not modify existing PostgreSQL data** (per instruction 6) — any migration would need to be careful about existing user data

**Notes:** Not every sheet becomes a table (KJN_SOURCE_CLAIMS may be log; README/STATUS_AUDIT are documentation). Some sheets are supporting/lookup. The current PostgreSQL schema differs from old workbook; migrating to extended structure would require careful schema evolution.

---

## 14. Critical findings and unresolved questions

### Critical findings
1. **Zero validated records** — Extended workbook explicitly states 0 VALIDATED, 0 eligible for PRIMARY experiment. No VALIDATED records exist anywhere.
2. **Source resolution broken** — EVIDENCE_LINK has 412 rows with `SRC`/`SRC-` not in SOURCE_REGISTER; OCCUPATION_SOURCE_MAPPING has 8 rows with `SRC-KBJI-2014-2026` not in SOURCE_REGISTER.
3. **KBJI hierarchy gap** — O08 links to KBJI code `2120` not present in KBJI_HIERARCHY (87.5% integrity for that link).
4. **Source model confusion** — Old international sources (O*NET/ESCO) largely removed/relegated to historical; Indonesian sources (KBJI 2026, SKKNI) are primary but some not registered.
5. **Duplicate evidence links** — 35 triple-duplicates in EVIDENCE_LINK may indicate mapping issues.
6. **Technology/task ineligible** — Marked historical/ineligible with no provenance FK; cannot contribute to scores per README.
7. **Partial SKKNI coverage** — 8/14 standards have 0 units (SK06,SK08,SK09,SK10-SK14).
8. **Incomplete KBJI mapping** — Only 24/75 KBJI occupations mapped to careers; all mappings NEEDS_REVIEW.
9. **Structure incompatible with old DB** — Major restructuring vs old workbook; direct import would break assumptions.

### Unresolved questions
1. **SOURCE_REGISTER completeness:** Should `SRC-KBJI-2014-2026`, `SRC`, `SRC-` be added to SOURCE_REGISTER? What are their correct roles/permissions?
2. **KBJI code 2120:** Is `2120` valid in KBJI 2026 but missing from the extracted hierarchy? Should it be added to KBJI_HIERARCHY or is the link incorrect?
3. **EVIDENCE_LINK malformed sources:** Are `SRC`/`SRC-` placeholders that need proper source assignment, or can they be ignored?
4. **Duplicate evidence links:** Are the 35 duplicate triples intentional (multiple evidence paths) or errors?
5. **OSM002 removal:** Was removing the O*NET mapping for O01 intentional? Is KBJI/SKKNI/IndoTask sufficient?
6. **Eligibility derivation:** How exactly does `operational_evidence_present` work when EVIDENCE_LINK has broken source references?
7. **KJN role:** KJN has conflict noted and no records in scope — should it be included/excluded?
8. **Technology/task future:** Will they be re-sourced to Indonesian context or remain historical?
9. **Validation process:** What is needed to get records to VALIDATED status (expert review mentioned)?
10. **Import strategy:** Should extended replace old in DB schema as-is, or is a migration needed? Current DB has user data (per instructions) — must be careful.

---

## 15. Recommended next steps for T4-R2

**Do not proceed to T4-R2 automatically. Wait for explicit approval.**

### Immediate (read-only analysis)
1. **Resolve source registry gaps** — Determine correct entries for `SRC-KBJI-2014-2026`, `SRC`, `SRC-` and add to analysis; verify against SOURCE_REGISTER policy.
2. **Resolve KBJI 2120** — Check if KBJI 2026 contains code 2120; if yes add to KBJI_HIERARCHY, if no fix OCCUPATION_KBJI2026_LINK.
3. **Investigate duplicate evidence links** — Understand why 35 triples duplicate; determine if data error or intentional.
4. **Clarify eligibility logic** — Understand how `operational_evidence_present` is computed given broken EVIDENCE_LINK references.

### Pre-import planning (no execution)
5. **Schema mapping design** — Map extended structure to PostgreSQL schema, identifying all breaking changes and migration needs.
6. **Import order validation** — Verify dependency order can be satisfied (especially KBJI_HIERARCHY self-ref).
7. **Data cleaning plan** — Plan to fix malformed source_ids, add missing source register entries, resolve KBJI 2120 before import.
8. **Validation strategy** — Plan path to get records to VALIDATED status (expert review process).
9. **Scope confirmation** — Confirm TECHNOLOGY/TASK remain historical/ineligible (not imported as scored data).
10. **Backup plan** — Since DB has user data, need explicit backup plan before any changes (though not doing now).

### Documentation
11. **Update audit trail** — Document decisions on source resolution before import.
12. **Create import checklist** — Based on resolved issues.

**T4-R1 is complete. No modifications made. Awaiting approval for T4-R2.**
