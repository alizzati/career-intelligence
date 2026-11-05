# T6 — Dataset Remediation Plan and Operational Technology Catalog Separation

**Status:** READ-ONLY PLAN — no dataset, source code, configuration, or database was changed  
**Date:** 2026-11-04  
**Dataset inspected:** `data/occupational_knowledge_base_verified_v1_0.xlsx` (18 sheets)

## 1. Executive summary

The current workbook is not safe for evaluation import without a small set of approved data and importer corrections. The workbook evidence confirms the previous audit's principal findings, with two important qualifications:

1. `OCCUPATION` contains eight canonical records plus 15 Kominfo records duplicated by `OCCUPATION_SOURCE_MAPPING` OSM011–OSM025. Removing the 15 duplicate rows preserves the Kominfo titles and codes in the mapping sheet and yields 8 rows/8 unique IDs.
2. The 120 `TECHNOLOGY` rows can be retained as an unapproved, independent OTC candidate dataset, but cannot be treated as national OKB evidence. No Lightcast provenance record exists in the workbook, and the technology bonus remains intentionally unimplemented.
3. The 35 `TASK` rows are attributed to `Kominfo_Kemnaker_BNSP` but contain seven O*NET SOC code groups and English O*NET-style descriptions. They must be quarantined or excluded; they must not be relabeled.
4. The current importer has the needed unit-ID normalization, but lacks the Kominfo provenance branch. The 15 OSM Kominfo records plus 32 Kominfo `SKILL_SOURCE_EVIDENCE` records therefore produce 47 missing derived provenance links.

The corrected 18-sheet workbook is structurally compatible with the legacy public 16-table import contract after the `OCCUPATION` correction, subject to the importer changes and validation gates in this report. This is not a claim that the current workbook is ready to import: source suitability, the 47 provenance derivations, and the unsupported technology/task content remain approval gates.

## 2. R1–R8 remediation decision table

| Item | Status | Finding | Proposed disposition | Approval / blocker |
|---|---|---|---|---|
| R1 `OCCUPATION` | **CONFIRMED / BLOCKER** | 23 rows, 8 unique IDs; data rows 9–23 duplicate OSM011–OSM025 | Remove the 15 duplicate rows and restore the three-column header | Required before legacy import |
| R2 `COMPETENCY_SKILL.unit_id` | **CONFIRMED / PROPOSED** | 34 unpadded values point to existing padded `COMPETENCY_UNIT` IDs | Normalize the 34 values to three-digit suffixes | Safe deterministic correction; approve workbook change |
| R3 `TECHNOLOGY` separation | **CONFIRMED / UNRESOLVED** | 120 Lightcast-labeled employer-posting records; no Lightcast provenance record | Keep outside thesis OKB; quarantine as OTC candidates pending source approval | OTC admission and bonus policy require approval |
| R4 `TASK` | **CONFIRMED / BLOCKER** | 35 Kominfo-attributed rows contain O*NET SOC codes and English task text | Quarantine or exclude; do not relabel or import as Kominfo | Required before evaluation import |
| R5 provenance and OSM | **CONFIRMED / PROPOSED** | 14 provenance rows and 25 OSM rows; P014 exactly matches the 47 Kominfo source links | Add deterministic Kominfo→P014 derivation in importer after approval | Current importer leaves 47 links null |
| R6 evidence formatting | **CONFIRMED / PROPOSED** | 146 trailing `CAREER_SKILL` separators and 32 leading `evidence_type` spaces | Strip empty trailing tokens and trim `evidence_type` | Formatting-only, but should be normalized before import |
| R7 README / STATUS_AUDIT | **CONFIRMED / PROPOSED** | Provenance is stated as 23 instead of 14; OSM as 26 instead of 25; Technology/Task wording is misleading | Update counts and mark Technology/Task as non-OKB/quarantined | Documentation approval required |
| R8 legacy compatibility | **CONFIRMED structurally / BLOCKER operationally** | Importer maps the workbook to the legacy 16-table contract; R1 and provenance/source handling still fail safe import | Use legacy public contract only after corrections and validation | No structural schema change is proposed |

## 3. Exact remediation findings

### R1 — OCCUPATION

The first eight data rows are the canonical records O01–O08. The following 15 data rows are duplicated source records:

| Workbook data row | `occupation_id` | title | matching OSM |
|---:|---|---|---|
| 9 | O01 | Systems Programmer | OSM011 |
| 10 | O02 | Interface Programmer | OSM012 |
| 11 | O01 | Software Engineer | OSM013 |
| 12 | O02 | Data Analyst | OSM014 |
| 13 | O08 | Data Architect | OSM015 |
| 14 | O04 | Data And Systems Engineering Manager | OSM016 |
| 15 | O04 | Data Model Administrator | OSM017 |
| 16 | O04 | Database Administrator | OSM018 |
| 17 | O08 | Big Data Scientist | OSM019 |
| 18 | O01 | Software Development Expert | OSM020 |
| 19 | O08 | Software Development Expert | OSM021 |
| 20 | O05 | Systems Integrator | OSM022 |
| 21 | O07 | Cyber Security Engineer | OSM023 |
| 22 | O07 | Cyber Security Analyst | OSM024 |
| 23 | O03 | It Quality Assurance | OSM025 |

The titles and numeric codes match the corresponding OSM source titles/codes (case differences in titles are presentation only). The 15 records therefore carry no unique canonical occupation information. Removing them leaves **8 rows and 8 unique occupation IDs**. OSM011–OSM025 remain valid because each references one of O01–O08 and retains the source title/code.

The proposed correction is to remove only these 15 rows and restore `OCCUPATION` to `occupation_id | canonical_name | classification`. Do not delete the OSM rows.

### R2 — COMPETENCY_SKILL.unit_id

All 34 proposed targets exist in `COMPETENCY_UNIT`; the transformation changes only identifier formatting, not the unit or skill meaning.

| Current | Proposed | Current | Proposed |
|---|---|---|---|
| CU47_8 | CU47_008 | CU47_9 | CU47_009 |
| CU47_10 | CU47_010 | CU47_12 | CU47_012 |
| CU299_1 | CU299_001 | CU299_4 | CU299_004 |
| CU299_5 | CU299_005 | CU299_6 | CU299_006 |
| CU299_8 | CU299_008 | CU299_9 | CU299_009 |
| CU299_10 | CU299_010 | CU299_11 | CU299_011 |
| CU299_12 | CU299_012 | CU299_13 | CU299_013 |
| CU299_14 | CU299_014 | CU299_17 | CU299_017 |
| CU299_19 | CU299_019 | CU191_1 | CU191_001 |
| CU191_2 | CU191_002 | CU191_3 | CU191_003 |
| CU191_4 | CU191_004 | CU191_5 | CU191_005 |
| CU191_6 | CU191_006 | CU191_7 | CU191_007 |
| CU191_8 | CU191_008 | CU191_9 | CU191_009 |
| CU191_10 | CU191_010 | CU191_11 | CU191_011 |
| CU191_12 | CU191_012 | CU191_13 | CU191_013 |
| CU191_16 | CU191_016 | CU191_17 | CU191_017 |
| CU191_18 | CU191_018 | CU191_19 | CU191_019 |

The existing importer already performs this normalization and validates the resulting FK set. Workbook normalization is still recommended so pre-import validation does not depend on importer behavior.

### R3 — TECHNOLOGY and OTC separation

The sheet has 9 columns and 120 rows: `technology_id`, `technology_name`, `technology_type`, `occupation_id`, `source`, `source_period`, `geography`, `frequency_pct`, and `evidence_note`. Every row has:

- `source = Lightcast`;
- `source_period = 2025`;
- `geography = '-'`;
- the same employer-posting evidence note;
- 63 distinct technology names across occupation IDs O01, O02, O03, O04, O05, O07, and O08.

**Source-validation status:** **UNRESOLVED.** The workbook contains a Lightcast label but no Lightcast record in `PROVENANCE`, no source URL/document identifier for these rows, and no approval record establishing Lightcast as an in-scope thesis source. The presence of the label is not source verification.

**Eligibility:** no row is currently eligible to contribute to OKB career fit, skill gap, or technology bonus. All 120 rows are **INELIGIBLE for thesis OKB import** and **UNRESOLVED for independent OTC admission**. They may be preserved as a quarantined candidate extract without being deleted or silently treated as evidence.

Minimum metadata for an independent OTC record:

| Field | Requirement |
|---|---|
| `technology_id` | Stable catalog-record ID, distinct from competency/skill IDs |
| `original_claim` | Exact extracted technology claim/activity text |
| `normalized_technology` | Canonical normalized name |
| `catalog_reference` | Approved catalog ID and version, or explicit unresolved value |
| `alias/match_method` | Deterministic matching method and alias version |
| `occupation_id` | Existing canonical occupation ID, if applicable |
| `source_provenance_id` | FK/reference to an independently verified source record |
| `source_reference_raw` | Original source reference retained verbatim |
| `evidence_status` | Unverified, verified, accepted, rejected, or quarantined |
| `eligible_for_technology_bonus` | Explicit verification-controlled boolean, false by default |

Technology evidence must remain separate from hard-skill `CompetencyEvidence`; no OTC record may be converted automatically into a `CompetencyEvidence` record. A technology mention alone contributes zero. No technology bonus formula, weight, or cap is proposed here, and `compute_career_fit()` must not be changed.

### R4 — TASK

All 35 rows have `source = Kominfo_Kemnaker_BNSP`, `source_period = 2026`, and `geography = Indonesia`. Their actual `source_code` values form seven groups of five rows:

| Source code | Occupation ID | Rows | Evidence concern |
|---|---|---:|---|
| 15-1252.00 | O01 | 5 | O*NET-style Software Developers SOC and English tasks |
| 15-1254.00 | O02 | 5 | O*NET-style Web Developers SOC and English tasks |
| 15-1253.00 | O03 | 5 | O*NET-style Software QA Analysts SOC and English tasks |
| 15-1243.00 | O04 | 5 | O*NET-style Database Architects SOC and English tasks |
| 15-1244.00 | O05 | 5 | O*NET-style Network/System Administrators SOC and English tasks |
| 15-1212.00 | O07 | 5 | O*NET-style Information Security Analysts SOC and English tasks |
| 15-2051.00 | O08 | 5 | O*NET-style Data Scientists SOC and English tasks |

The `source` cell is an attribution, not proof that the descriptions came from that source. P014 exists, but it does not establish that these English O*NET-style task statements are Kominfo records. All 35 rows are therefore **INELIGIBLE for in-scope thesis OKB import** and **UNRESOLVED as to their actual source**.

Recommended disposition: retain an immutable quarantine copy for investigation; exclude from evaluation OKB import; do not relabel as Indonesian national-standard data; do not silently delete.

## 4. R5 — provenance and source mapping

`PROVENANCE` contains 14 records: P001–P002 BPS/KBJI, P003–P011 SKKNI, P012–P013 IndoTask, and P014 `Kominfo_Kemnaker_BNSP_2018`. No O*NET, ESCO, or Lightcast provenance record is present.

`OCCUPATION_SOURCE_MAPPING` contains 25 records: 8 KBJI, 2 IndoTask, and 15 Kominfo. The Kominfo rows OSM011–OSM025 have `source_name = Kominfo_Kemnaker_BNSP`; their `source_code` values are mixed numeric/text cells and must be converted to text before insertion into a text target column.

The 32 Kominfo `SKILL_SOURCE_EVIDENCE` rows (SE063–SE094) all use `source_name = Kominfo_Kemnaker_BNSP` and `source_reference = Kominfo_Kemnaker_BNSP_2018`, exactly matching P014's `document_id`. Together with the 15 Kominfo OSM rows, these are the reported **47 derivable Kominfo links**. They are source-name/reference links in the workbook; neither sheet stores an explicit `provenance_id`.

The importer currently handles O*NET, KBJI, ESCO, SKKNI, and leaves IndoTask ambiguous, but its fallback leaves Kominfo null. The safe proposed importer rule is:

```text
source_name == "Kominfo_Kemnaker_BNSP"
and source/reference resolves exactly to P014.document_id
→ provenance_id = P014
→ mapping_basis = "derived-deterministic"
```

This rule is **PROPOSED**, not executed. It must be applied only after confirming P014 remains the approved provenance record and after source suitability is approved. It must not be used to validate the R4 task rows.

## 5. R6 — formatting and attribution corrections

The following are exact proposed field corrections:

| Sheet / field | Current finding | Proposed correction | Classification |
|---|---|---|---|
| `CAREER_SKILL.evidence_source` | 146/155 values end with `"; "` | Split on `;`, trim tokens, discard empty tokens, rejoin with `; ` | Harmless formatting; **PROPOSED** |
| `SKILL_SOURCE_EVIDENCE.evidence_type` | 32 values have leading spaces: 3 ` occupation/task evidence`, 23 ` task evidence`, 5 ` occupation description`, 1 ` detailed work activity` | Apply `.strip()`; resulting values are `occupation/task evidence`, `task evidence`, `occupation description`, `detailed work activity` | Harmless formatting; **PROPOSED** |
| `SKILL_SOURCE_EVIDENCE.source_reference` | 32 exact values are `Kominfo_Kemnaker_BNSP_2018` | Preserve the value; resolve deterministically to P014 only after approval | Attribution is usable as a link, not independent source validation |
| `OCCUPATION_SOURCE_MAPPING.source_code` | 15 numeric cells and 10 text cells | Convert all values to canonical text without changing code digits | Type normalization; **PROPOSED** |

The formatting defects do not change competency meaning. The provenance derivation is not merely formatting and must remain auditable.

## 6. R7 — README and STATUS_AUDIT corrections

The workbook's actual counts are: 10 careers, 8 occupations, 17 skill groups, 87 skills, 12 career–occupation rows, 155 career–skill rows, 9 SKKNI standards, 146 competency units, 79 competency–skill rows, 10 occupation–competency rows, 25 occupation-source mappings, 120 technology rows, 35 task rows, 14 provenance rows, and 97 skill-source-evidence rows.

The stale values are:

- `README`: `Provenance records = 23` should be **14**; `Occupation-source mappings = 26` should be **25**.
- `STATUS_AUDIT`: `Occupation Source Mapping = 26` should be **25**; `Provenance = 23` should be **14**.
- Technology wording should say **candidate OTC records; excluded from thesis OKB until source validation**, not imply approved canonical technology evidence.
- Task wording should say **quarantined/unverified O*NET-style residue; excluded from thesis OKB**, not merely `POPULATED`.

These are documentation corrections only and were not applied.

## 7. Operational Technology Catalog design

The OTC should be an independent operational catalog and evidence path. It may retain the original 120 rows as quarantined source claims, but it must not be imported into the thesis OKB as accepted technology evidence. The minimum record contract is given in §3 above.

Required processing boundary:

```text
activity description → original technology claim → normalized OTC candidate
                   → catalog match + source verification
                   → accepted technology evidence (separate path)
                   → optional future technology-bonus input
```

Unmatched or unverified claims remain traceable but contribute zero. Accepted technology evidence may contribute only through a separately approved scoring component, with the final score capped at 100%. This plan deliberately specifies no formula, weight, or cap and makes no change to `compute_career_fit()`.

Keeping the OTC separate is possible without changing the existing OKB schema by excluding the current `TECHNOLOGY` rows from the OKB import and maintaining any future OTC store/catalog as a separately approved operational artifact. The current repository does not contain approved Lightcast source metadata or an approved OTC seed, so OTC activation remains **UNRESOLVED**.

## 8. Legacy schema compatibility matrix

The inspected importer defines a 16-table legacy public import contract. The repository does not contain a complete checked-in DDL snapshot of the legacy `public` schema; therefore exact database type parity is **NOT VERIFIED** here. The matrix below records the importer contract and deterministic transformations, without changing any schema.

| Source sheet | Legacy table | Column mapping / transformation | Null/default and key checks | Status |
|---|---|---|---|---|
| `SKILL_GROUP` | `skill_groups` | Direct columns | PK `skill_group_id`; referenced by `SKILL` | **CONFIRMED contract** |
| `CAREER` | `careers` | Direct columns | PK `career_id`; 10 canonical careers | **CONFIRMED** |
| `OCCUPATION` | `occupations` | Direct after dropping duplicate rows and restoring 3 columns | PK `occupation_id`; must be 8 unique IDs | **BLOCKER until R1** |
| `SKILL` | `skills` | Direct columns | PK `skill_id`; FK to skill group | **CONFIRMED contract** |
| `CAREER_OCCUPATION` | `career_occupations` | Direct columns; DB sequence supplies surrogate `id` if present | FKs to career/occupation; validate 12 rows | **CONFIRMED contract** |
| `CAREER_SKILL` | `career_skills` | Drop workbook `skill_name`; retain relationship fields; normalize evidence text | FKs to career/skill; 155 rows | **CONFIRMED with R6 cleanup** |
| `SKKNI_STANDARD` + `STANDARD_COVERAGE` | `skkni_standards` | Left join by `standard_id`; rename `action` to `coverage_action_note` | PK `standard_id`; 9 coverage matches required | **CONFIRMED importer transform** |
| `COMPETENCY_UNIT` | `competency_units` | Normalize unit suffix to 3 digits; insert four target columns | PK `unit_id`; FK to standard; 146 rows | **CONFIRMED with R2** |
| `OCCUPATION_COMPETENCY` | `occupation_competencies` | Direct columns; DB sequence may supply surrogate `id` | FKs to occupation/standard; 10 rows | **CONFIRMED contract** |
| `COMPETENCY_SKILL` | `competency_skills` | Drop `skill_name`; normalize `unit_id`; retain relationship, skill, method | FKs to unit/skill; all 79 normalized refs must resolve | **CONFIRMED with R2** |
| `TECHNOLOGY` | `technologies` | Direct mapping is structurally possible, but rows are excluded from thesis OKB | Empty target for evaluation; no accepted OTC evidence | **PROPOSED exclusion / OTC separation** |
| `TASK` | `tasks` | Direct mapping is structurally possible, but rows are quarantined/excluded | Empty target for evaluation; no relabeling | **PROPOSED exclusion / BLOCKER** |
| `PROVENANCE` | `provenance` | Direct columns | PK `provenance_id`; 14 records; source suitability still requires review | **CONFIRMED rows / UNRESOLVED approval** |
| `OCCUPATION_SOURCE_MAPPING` | `occupation_source_mapping` | Convert source code to text; derive `provenance_id` and `mapping_basis` | FKs to occupation/provenance; Kominfo branch required; IndoTask remains unresolved under current logic | **BLOCKER until R5 decision** |
| `SKILL_SOURCE_EVIDENCE` | `skill_source_evidence` | Drop `skill_name`; trim evidence type; derive provenance fields | FKs to skill/provenance; 47 Kominfo links must not be null after approved derivation | **BLOCKER until R5/R6** |
| generated transform log | `etl_transform_log` | Generated in memory for unit padding and provenance derivations | DB sequence/default for log ID; preserve raw/transformed values | **CONFIRMED importer behavior** |

No workbook sheet supplies the target's additional extended-schema objects such as `source_register`, KBJI-2026 tables, `evidence_link`, or governance tables. Those belong to the extended target design and must not be added to the legacy import for this task.

### Legacy compatibility conclusion

**Structural answer:** **CONFIRMED with qualification** — after R1, the workbook sheets and importer transformations cover the legacy public 16-table contract without adding/removing tables or columns, according to the inspected importer and prior compatibility audit.

**Safe-import answer:** **NO, not yet.** R4 unsupported task content, R3 unapproved technology source content, the 47 missing Kominfo derivations, and the absent checked-in legacy public DDL prevent a final operational sign-off. No existing primary key, foreign key, application table, or scoring implementation should be changed as part of this plan.

## 9. Importer changes required

These are approval-gated implementation requirements, not changes made by this task:

1. Keep the isolated-database safety gate and add an explicit evaluation-database approval path only if separately approved; never loosen protection for `career_intelligence` or `career_intelligence_okb`.
2. Add the exact P014 Kominfo branch to both provenance derivation functions, with fail-closed behavior if the reference does not resolve uniquely.
3. Convert `OCCUPATION_SOURCE_MAPPING.source_code` to text before insert.
4. Add preflight rejection for duplicate occupation primary keys and unsupported/non-approved task/technology source content, or explicitly skip those tables with an audit record.
5. Preserve transformation logs for unit-ID padding, source-code typing, formatting cleanup, and provenance derivation.
6. Do not add technology bonus logic, change career-fit scoring, or turn technology records into competency evidence.

## 10. Pre-import validation checklist

- [ ] Workbook hash and sheet order recorded.
- [ ] `OCCUPATION` has 8 rows and 8 unique IDs; OSM011–OSM025 remain present.
- [ ] All 34 unit-ID mappings match an existing `COMPETENCY_UNIT` row.
- [ ] All 79 `COMPETENCY_SKILL` FKs resolve after normalization.
- [ ] `CAREER_SKILL` evidence tokens have no empty trailing values.
- [ ] All 32 affected `evidence_type` values are trimmed.
- [ ] All 15 numeric OSM source codes are text-normalized without digit loss.
- [ ] P001–P014 are unique and source references are reviewed.
- [ ] The 15 OSM and 32 SSE Kominfo links resolve exactly to P014, or are explicitly quarantined.
- [ ] No O*NET/Lightcast records are silently relabeled as in-scope national-source records.
- [ ] `TECHNOLOGY` is excluded from thesis OKB import unless OTC source approval is separately recorded.
- [ ] `TASK` is excluded/quarantined pending source resolution.
- [ ] Target schema columns, nullability, PKs, and FKs are checked against an approved legacy public schema snapshot.
- [ ] Import runs only against an explicitly approved isolated evaluation database.
- [ ] Post-import row counts, FK checks, provenance null checks, and score eligibility checks pass.

## 11. Remaining decisions requiring user approval

1. Approve the 15-row `OCCUPATION` correction and the 34 unit-ID normalizations.
2. Approve the R6 formatting/type normalizations and README/STATUS_AUDIT wording/count corrections.
3. Decide whether the 120 Lightcast rows remain as quarantined OTC candidates or are archived outside the repository; do not treat them as approved source records yet.
4. Decide the disposition of the 35 O*NET-style task rows: quarantine for investigation or exclude from the evaluation package.
5. Approve P014 as the deterministic provenance target for the 47 Kominfo source links after independent source-suitability review.
6. Provide or approve a checked-in legacy public schema definition for final type-level compatibility sign-off.
7. Defer all technology bonus formula, weight, cap, and scoring changes to a separate approved design decision.

## 12. Validation performed and scope boundary

The workbook, the two required audit reports, the legacy importer, the importer schema checker, the legacy compatibility audit, and the repository migration definitions were inspected. The workbook was read-only inspected for sheet structure, row counts, IDs, source values, and exact field-level findings. No tests were required for this planning-only deliverable; no import or database operation was run.

No workbook, corrected workbook, source code, importer, migration, schema, configuration, database, or `.env` file was modified. Implementation and database provisioning remain out of scope pending explicit approval.
