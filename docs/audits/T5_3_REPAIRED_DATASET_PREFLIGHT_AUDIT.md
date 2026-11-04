# T5.3 — Repaired Dataset Preflight Audit (`v1_0.xlsx`)

**Status:** COMPLETE (read-only inspection only)

**Date:** 2026-11-04

**Scope:** `data/occupational_knowledge_base_verified_v1_0.xlsx` — the only dataset file currently present in `data/`.

**Mode:** Strictly read-only. No database connection, DDL, migration, import, dataset write, source-code change, configuration change, or commit was made. The workbook was opened with `openpyxl` (`data_only=True`) and compared against the committed original and the committed extended workbook extracted with `git show` into the OS temp directory. No secret or `.env` value was read or recorded.

**Supersedes:** the dataset-identity assumptions in
[`T4_OKB_READINESS_AUDIT.md`](T4_OKB_READINESS_AUDIT.md),
[`T5_2A_R1_LEGACY_COMPATIBILITY_AUDIT.md`](T5_2A_R1_LEGACY_COMPATIBILITY_AUDIT.md), and
[`T5_2A_R2_SQL_AND_RUNTIME_CONTRACT_VERIFICATION.md`](T5_2A_R2_SQL_AND_RUNTIME_CONTRACT_VERIFICATION.md)
for the current working tree only.

---

## 1. File identity and repository state

| Item | Value | Evidence |
|---|---|---|
| Working-tree file | `data/occupational_knowledge_base_verified_v1_0.xlsx` | `Get-ChildItem data` |
| Working-tree size | 67,116 bytes | file metadata |
| Working-tree SHA-256 | `12AFB16D3EF7A3FB2812C2377403E7F7BD171625791ADEAAC16E08315EEC2375` | recomputed during this audit |
| Sheets | 18, same names and order as the committed original | `openpyxl` |
| Workbook creator / last modified by | `openpyxl` / `My Thinkpad` | workbook properties |
| Created / modified | 2026-09-22 11:51:20 / 2026-11-04 02:43:34 | workbook properties |
| Committed original (`HEAD`) | 55,399 bytes, SHA-256 `CE858A6AEBE31D8237BF11217CCE538D3CD657F4572D838866D2707B5536A630`, 18 sheets | `git show HEAD:data/...v1_0.xlsx` |
| Committed extended (`HEAD`, deleted in working tree) | 185,868 bytes, SHA-256 `1314578E44D4A66B21FD19EFFE441ED303DC2DA2239423ABF73DFB7D1C807353`, 25 sheets | `git show HEAD:data/..._extended.xlsx`; `git status` |

`git status --short` confirms:

```text
 M data/occupational_knowledge_base_verified_v1_0.xlsx
 D data/occupational_knowledge_base_verified_v1_0_extended.xlsx
```

Only one dataset file exists in `data/`, so there is no file-selection ambiguity. The file is a **modified replacement** of the committed 18-sheet original, not a new filename.

> Note: earlier audits record a 167,387-byte / `792FDBFF...` extended workbook. That was an untracked working copy. The committed extended workbook is 185,868 bytes / `1314578E...`. The current working tree deletes the extended workbook entirely.

---

## 2. Does it still match the original 18-sheet dataset?

**Structure:** yes, at sheet level. **Headers:** yes, except `OCCUPATION`. **Data:** no.

| Sheet | Committed original rows | Current rows | Delta |
|---|---:|---:|---:|
| `README` | 18 | 18 | 0 |
| `CAREER` | 10 | 10 | 0 |
| `OCCUPATION` | 8 | **23** | **+15** |
| `CAREER_OCCUPATION` | 12 | 12 | 0 |
| `SKILL_GROUP` | 17 | 17 | 0 |
| `SKILL` | 87 | 87 | 0 |
| `CAREER_SKILL` | 155 | 155 | 0 |
| `SKKNI_STANDARD` | 9 | 9 | 0 |
| `COMPETENCY_UNIT` | 146 | 146 | 0 |
| `OCCUPATION_COMPETENCY` | 10 | 10 | 0 |
| `COMPETENCY_SKILL` | 79 | 79 | 0 |
| `STATUS_AUDIT` | 16 | **15** | **−1** |
| `OCCUPATION_SOURCE_MAPPING` | 26 | **25** | **−1** |
| `TECHNOLOGY` | 120 | 120 | 0 |
| `TASK` | 35 | 35 | 0 |
| `PROVENANCE` | 23 | **14** | **−9** |
| `SKILL_SOURCE_EVIDENCE` | 97 | 97 | 0 |
| `STANDARD_COVERAGE` | 9 | 9 | 0 |

Header comparison result: all 18 sheet headers are identical to the committed original **except** `OCCUPATION`:

- Original: `occupation_id | canonical_name | classification` (3 columns)
- Current: `occupation_id | canonical_name | classification | None | None` (5 columns)

The two unnamed columns are not accidental formatting: they are used by the appended Kominfo rows.

---

## 3. Verified structural defects

Severity is assigned for import/readiness risk, not for research significance.

### D1 — BLOCKER — `OCCUPATION` primary key is violated and two taxonomies are mixed

Current `OCCUPATION` has 23 data rows but only 8 distinct `occupation_id` values:

| `occupation_id` | Occurrences |
|---|---:|
| `O01` | 4 |
| `O02` | 3 |
| `O03` | 2 |
| `O04` | 4 |
| `O05` | 2 |
| `O06` | 1 |
| `O07` | 3 |
| `O08` | 4 |

Rows 1–8 are the original KBJI-anchored occupations. Rows 9–23 are 15 Kominfo occupations appended to the same sheet. For those rows:

- `classification` contains the source label `Kominfo_Kemnaker_BNSP_2018`, not a KBJI classification.
- The 4th unnamed column contains the Kominfo source code (e.g. `20506`, `20303`, `20606`).
- `canonical_name` contains the Kominfo title (e.g. `Systems Programmer`, `Interface Programmer`, `Software Engineer`).

`okb.occupations.occupation_id` is a `TEXT PRIMARY KEY`. The current sheet cannot be imported without either failing on the duplicate key or silently collapsing/overwriting the 15 Kominfo rows. The Kominfo occupations are also not represented in `CAREER_OCCUPATION`, so appending them to `OCCUPATION` does not create new career mappings.

**Root cause:** the repair appended a second occupational taxonomy to a table that is designed to hold one row per canonical occupation ID.

### D2 — BLOCKER — `COMPETENCY_SKILL.unit_id` fails the FK to `COMPETENCY_UNIT.unit_id`

Validation of all foreign-key-like workbook references found exactly one failing relation:

```text
COMPETENCY_SKILL.unit_id -> COMPETENCY_UNIT.unit_id:
  rows=79  nonnull=79  matched=45  unmatched=34
```

Examples of unmatched values: `CU47_8`, `CU47_9`, `CU47_10`, `CU47_12`, `CU191_1`, `CU299_1`, `CU299_4`.

`COMPETENCY_UNIT` uses zero-padded numeric suffixes (`CU47_001`, `CU191_001`, `CU299_001`). Zero-padding the numeric suffix of all 34 unmatched values resolves **all 34** against `COMPETENCY_UNIT`; no other unresolved value remains.

**Important:** this defect is **pre-existing in the committed original v1.0**, not introduced by the repair. The original workbook also contains `CU47_8` in `COMPETENCY_SKILL` and `CU47_001` in `COMPETENCY_UNIT`. The T4 audit already documented that the importer applies this padding at import time (`competency_skills` unit-ID padding). The workbook itself remains internally inconsistent.

### D3 — HIGH — `PROVENANCE` lost nine records and cannot satisfy `okb.provenance.source_id`

The committed original has `P001`–`P023` (23 rows), including the O*NET and ESCO provenance records `P015`–`P023`. The current file has `P001`–`P014` (14 rows). `P014` is a new `Kominfo_Kemnaker_BNSP_2018` record.

Consequences:

- The O*NET/ESCO provenance chain referenced by the original `OCCUPATION_SOURCE_MAPPING`, `CAREER_SKILL`, `TECHNOLOGY`, `TASK`, and `SKILL_SOURCE_EVIDENCE` rows no longer exists.
- `okb.provenance` requires `source_id` referencing `okb.source_register(source_id)`, but the 18-sheet workbook has no `SOURCE_REGISTER` sheet and no `source_id` column in `PROVENANCE`.
- The current `PROVENANCE` sheet also contains `page_or_section`, `url`, `source_type`, and `scope_note`, none of which exist in the current `okb.provenance` DDL.

### D4 — HIGH — `OCCUPATION_SOURCE_MAPPING` was renumbered and its source mix changed

The committed original has 26 rows: 8 KBJI, 9 O*NET, 7 ESCO, 2 IndoTask. The current file has 25 rows: 8 KBJI, 2 IndoTask, 15 Kominfo.

- `OSM026` was removed.
- All 9 O*NET and 7 ESCO mappings were removed.
- 15 Kominfo mappings were added.
- The remaining rows were renumbered `OSM001`–`OSM025`, so identifiers no longer mean the same thing as in the original or in any prior audit/import.
- `source_code` is now type-inconsistent: 15 rows are integers (`1501`, `10505`, `10601`, …) and 10 rows are text (`2120`, `2512`, `3513`, …). The target column is `TEXT`, so PostgreSQL will coerce them, but joins and comparisons become fragile.
- `source_scope` is present in the workbook but absent from `okb.occupation_source_mapping`.
- `source_id` is required for full traceability but is absent.

### D5 — HIGH — `CAREER_SKILL.evidence_source` contains dangling separators

`146` of `155` rows end with `"; "` after the source was replaced. Examples:

```text
47x 'SKKNI 282/2016;'
42x 'SKKNI 299/2020;'
15x 'SKKNI 268/2020;'
15x 'SKKNI 22/2019;'
15x 'SKKNI 47/2017;'
12x 'SKKNI 191/2024;'
 9x 'SKKNI 200/2021; 299/2020; IndoTask'
```

The trailing separator implies a removed source but leaves an empty token. Any parser that splits on `;` will produce an empty evidence component for most rows.

### D6 — HIGH — `TECHNOLOGY` and `TASK` provenance was relabeled without replacing the underlying records

This is a research-integrity defect, not only a formatting defect.

- `TECHNOLOGY`: all 120 rows now have `source = Lightcast` and `geography = '-'`. The records retain O*NET/Lightcast-style per-occupation frequency values and 63 distinct technology names repeated under different IDs. The original label was `O*NET/Lightcast`.
- `TASK`: all 35 rows now have `source = Kominfo_Kemnaker_BNSP`, `source_period = 2026`, and `geography = Indonesia`, but the `source_code` values are still O*NET SOC codes (`15-1252.00`, `15-1254.00`, `15-1253.00`, `15-1243.00`, `15-1244.00`, `15-1212.00`, `15-2051.00`) and the `task_description` values are still English O*NET task statements.

Changing the `source` label does not make the content Kominfo/Kemnaker/BNSP-derived. Either the underlying records must be replaced with genuine Indonesian source content, or the original O*NET attribution must be restored and the removal of the O*NET provenance records reversed.

The target DDL also does not contain `tasks.source_period` or `tasks.geography`, or `technologies.geography`; those workbook columns are extra.

### D7 — MEDIUM — `SKILL_SOURCE_EVIDENCE` has leading-space evidence types and generic references

- 32 rows have a leading space in `evidence_type` (e.g. `' task evidence'`, `' occupation description'`).
- 32 rows use `source_name = Kominfo_Kemnaker_BNSP` and `source_reference = Kominfo_Kemnaker_BNSP_2018`.
- The remaining rows are 62 SKKNI `direct unit-title evidence`, 3 IndoTask survey rows.

Leading whitespace is not a schema violation, but it breaks exact-match grouping and should be normalized. The generic Kominfo reference also does not identify a specific document section or page.

### D8 — MEDIUM — README and `STATUS_AUDIT` counts are stale

The workbook still claims:

| Field | Claimed | Actual |
|---|---:|---:|
| Occupation | 8 | **23** |
| Occupation-source mappings | 26 | **25** |
| Provenance records | 23 | **14** |

`STATUS_AUDIT` also lost the original final row:

```text
Total relationships | recalculate from sheets | NOT STORED AS A PROVISIONAL SINGLE TOTAL
```

The remaining `STATUS_AUDIT` counts are correct for the tables that did not change.

### D9 — MEDIUM — Several target columns are absent or extra

The current workbook can populate the core tables, but the following mismatches require importer/schema decisions:

| Table | Missing from workbook | Extra in workbook |
|---|---|---|
| `okb.career_occupations` | `legacy_career_occupation_id`, eligibility flags (have defaults) | — |
| `okb.skills` | eligibility flags (have defaults) | — |
| `okb.career_skills` | eligibility flags (have defaults) | — |
| `okb.skkni_standards` | `jdih_standard_id`, `jdih_source_url`, `jdih_enacted_date`, `record_origin`, `candidate_career_ids_hint` (nullable) | — |
| `okb.competency_units` | `evidence_class`, `crosscheck_source_url` (nullable) | — |
| `okb.occupation_competencies` | `relationship_id` (`TEXT PRIMARY KEY`, no default), eligibility flags | — |
| `okb.competency_skills` | eligibility flags (have defaults) | — |
| `okb.occupation_source_mapping` | `source_id`, eligibility flags | `source_scope` |
| `okb.technologies` | eligibility flags (have defaults) | `geography` |
| `okb.tasks` | eligibility flags (have defaults) | `source_period`, `geography` |
| `okb.provenance` | `source_id`, `record_status` (default `ACTIVE`) | `page_or_section`, `url`, `source_type`, `scope_note` |
| `okb.skill_source_evidence` | `source_id`, `reference_resolution`, `linked_unit_id`, `competency_skill_link_exists` (default `FALSE`) | — |

`relationship_id` for `OCCUPATION_COMPETENCY` must be generated deterministically by the importer (the original importer already does this for several tables).

### D10 — HIGH — the current DDL targets the deleted 25-sheet extended workbook

The migrations and design documents target the extended workbook (`1314578E...`, 25 sheets). The current 18-sheet workbook has no sheet for these required tables:

| Required table | Migration | Workbook source |
|---|---|---|
| `okb.source_register` | 004 | none |
| `okb.kbji_hierarchy` | 002 | none |
| `okb.kbji_occupation` | 002 | none |
| `okb.occupation_kbji2026_link` | 002 | none |
| `okb.career_occupation_kbji_mapping` | 002 | none |
| `okb.career_kbji_mapping` | 002 | none |
| `okb.evidence_link` | 004 | none |
| `okb.kjn_source_claims` | 004 | none |
| `okb.technology_catalog` | 002 | derivable from `TECHNOLOGY`, but no explicit sheet |
| `okb.technology_alias` | 002 | derivable, but no explicit sheet |
| `okb.workbook_review_approval` | 005 | none (import metadata) |
| `okb.import_manifest` | 005 | none (import metadata) |
| `okb.evidence_link_resolution_audit` | 005 | none (import metadata) |
| `okb.quarantine_reference` | 005 | none (import metadata) |
| `okb.etl_transform_log` | 005 | none (import metadata) |

The 18-sheet workbook is therefore **partially compatible** with the current target DDL. It can populate the core, competency, and provenance tables (after D1–D9 are resolved), but it cannot populate the KBJI 2026 layer, `SOURCE_REGISTER`, `EVIDENCE_LINK`, or `KJN_SOURCE_CLAIMS`.

---

## 4. Foreign-key and duplicate validation results

### 4.1 Foreign-key-like checks

| Relation | Rows | Matched | Unmatched |
|---|---:|---:|---:|
| `CAREER_OCCUPATION.career_id → CAREER` | 12 | 12 | 0 |
| `CAREER_OCCUPATION.occupation_id → OCCUPATION` | 12 | 12 | 0 |
| `SKILL.skill_group_id → SKILL_GROUP` | 87 | 87 | 0 |
| `CAREER_SKILL.career_id → CAREER` | 155 | 155 | 0 |
| `CAREER_SKILL.skill_id → SKILL` | 155 | 155 | 0 |
| `COMPETENCY_UNIT.standard_id → SKKNI_STANDARD` | 146 | 146 | 0 |
| `OCCUPATION_COMPETENCY.occupation_id → OCCUPATION` | 10 | 10 | 0 |
| `OCCUPATION_COMPETENCY.standard_id → SKKNI_STANDARD` | 10 | 10 | 0 |
| **`COMPETENCY_SKILL.unit_id → COMPETENCY_UNIT`** | **79** | **45** | **34** |
| `COMPETENCY_SKILL.skill_id → SKILL` | 79 | 79 | 0 |
| `OCCUPATION_SOURCE_MAPPING.occupation_id → OCCUPATION` | 25 | 25 | 0 |
| `TECHNOLOGY.occupation_id → OCCUPATION` | 120 | 120 | 0 |
| `TASK.occupation_id → OCCUPATION` | 35 | 35 | 0 |
| `SKILL_SOURCE_EVIDENCE.skill_id → SKILL` | 97 | 97 | 0 |
| `STANDARD_COVERAGE.standard_id → SKKNI_STANDARD` | 9 | 9 | 0 |

The FK checks for `OCCUPATION` pass only because the duplicated IDs still exist in the sheet. They do not detect the primary-key violation described in D1.

### 4.2 Natural-key duplicate checks

All checked natural keys are unique:

- `CAREER_SKILL(career_id, skill_id)`
- `OCCUPATION_COMPETENCY(occupation_id, standard_id)`
- `COMPETENCY_SKILL(unit_id, skill_id)`
- `OCCUPATION_SOURCE_MAPPING(occupation_id, source_name, source_code)`
- `TASK(occupation_id, task_description)`
- `TECHNOLOGY(occupation_id, technology_name)`
- `SKILL_SOURCE_EVIDENCE(skill_id, source_reference)`
- `PROVENANCE(document_id)`

`OCCUPATION(occupation_id)` is **not** unique (D1).

---

## 5. Match against the existing DB schema

### 5.1 Tables that can be populated after defect fixes

`CAREER`, `OCCUPATION` (after removing the 15 stray rows), `CAREER_OCCUPATION`, `SKILL_GROUP`, `SKILL`, `CAREER_SKILL`, `SKKNI_STANDARD`, `COMPETENCY_UNIT`, `OCCUPATION_COMPETENCY` (after generating `relationship_id`), `COMPETENCY_SKILL` (after unit-ID normalization), `OCCUPATION_SOURCE_MAPPING`, `TECHNOLOGY`, `TASK`, `PROVENANCE`, `SKILL_SOURCE_EVIDENCE`, `STANDARD_COVERAGE`.

### 5.2 Tables that cannot be populated from this workbook

`source_register`, `kbji_hierarchy`, `kbji_occupation`, `occupation_kbji2026_link`, `career_occupation_kbji_mapping`, `career_kbji_mapping`, `evidence_link`, `kjn_source_claims`, and the governance/import-metadata tables.

`technology_catalog` and `technology_alias` can be derived from `TECHNOLOGY`, but the workbook provides no canonical catalog or alias records.

### 5.3 Compatibility verdict

**Partial.** The repaired workbook is structurally close to the committed 18-sheet original, but it is not a drop-in source for the current target DDL, and it is not a valid import source in its current state because of D1 and D2.

---

## 6. Blockers before any import or DB replacement

1. **Choose the dataset of record.** The working tree currently has a repaired 18-sheet file, the committed original 18-sheet file, and a deleted 25-sheet extended workbook. The three are not interchangeable. No import should proceed until the researcher confirms which one is authoritative.
2. **Resolve `OCCUPATION` (D1).** Remove the 15 appended Kominfo rows or move them to a separate mapping sheet; restore the 3-column header; restore exactly 8 unique occupation IDs.
3. **Resolve `COMPETENCY_SKILL.unit_id` (D2).** Either zero-pad the workbook values or document/enforce the importer normalization. The importer currently pads, but the workbook remains inconsistent.
4. **Decide the provenance policy (D3, D4, D6).** Either restore the O*NET/ESCO provenance and mappings, or replace the underlying `TECHNOLOGY`/`TASK` content with genuine Kominfo/Kemnaker/BNSP data and update the research documentation. Relabeling alone is not sufficient.
5. **Reconcile README/`STATUS_AUDIT` counts (D8).** They currently contradict the actual row counts.
6. **Decide schema direction (D10).** Either extend the importer to the current extended DDL (which requires the missing sheets), or revert the DDL to the 18-sheet design. The current DDL cannot be fully populated from the 18-sheet file.
7. **Do not write to the database.** No import, migration, seed, truncate, or table replacement has been performed.

---

## 7. Recommended corrections (not executed)

- Restore the committed original v1.0 if the 18-sheet baseline is authoritative, or produce a corrected 18-sheet file with exactly 8 `OCCUPATION` rows and 3 columns.
- If Kominfo enrichment is desired, add a separate `KOMINFO_OCCUPATION_MAPPING` sheet keyed by `occupation_id` + Kominfo code, rather than appending rows to `OCCUPATION`.
- Normalize `COMPETENCY_SKILL.unit_id` to the same zero-padded format as `COMPETENCY_UNIT.unit_id`.
- Strip trailing separators and empty tokens from `CAREER_SKILL.evidence_source`.
- Normalize `SKILL_SOURCE_EVIDENCE.evidence_type` (trim leading/trailing whitespace).
- Store `OCCUPATION_SOURCE_MAPPING.source_code` consistently as text.
- Restore or explicitly retire the O*NET/ESCO provenance records and update all source labels only after the underlying content is replaced.
- Update the README and `STATUS_AUDIT` row counts, or remove the hard-coded counts and compute them.
- Do not import until the dataset-of-record and schema direction are approved.

---

## 8. Verification commands and evidence

Executed from the repository root with `backend\.venv\Scripts\python.exe` (Python 3.13.0, openpyxl 3.1.5):

```text
git status --short
git show HEAD:data/occupational_knowledge_base_verified_v1_0.xlsx > <temp>\orig_v1_0.xlsx
git show HEAD:data/occupational_knowledge_base_verified_v1_0_extended.xlsx > <temp>\orig_extended.xlsx
python <temp>\validate_2.py
python <temp>\inspect_focus.py
python <temp>\compare_orig.py
python <temp>\header_diff.py
```

Results:

- `validate_2.py`: 15 FK-style checks; 14 pass at 100%; `COMPETENCY_SKILL.unit_id` has 34 unmatched values; zero-padding resolves all 34.
- `inspect_focus.py`: full `OCCUPATION`, `OCCUPATION_SOURCE_MAPPING`, `PROVENANCE`, `TECHNOLOGY`, `TASK`, and `SKKNI_STANDARD` dumps.
- `compare_orig.py`: row counts, `OCCUPATION` rows, `PROVENANCE` IDs, OSM IDs/source mix, `STATUS_AUDIT`, evidence samples for original vs current.
- `header_diff.py`: sheet order identical; only `OCCUPATION` header differs; both file hashes reconfirmed.

No database was contacted. No workbook was modified. No source code, migration, or configuration was changed.

---

## 9. Final conclusion

The current `data/occupational_knowledge_base_verified_v1_0.xlsx` is an **18-sheet workbook with the same sheet inventory and almost the same headers as the committed original**, but it is **not a structurally valid or schema-compatible replacement**:

- It violates the `OCCUPATION` primary key with 15 appended Kominfo rows (D1).
- It still fails the `COMPETENCY_SKILL → COMPETENCY_UNIT` FK on 34 rows (D2, pre-existing).
- It removed the O*NET/ESCO provenance layer and replaced it with a Kominfo layer without replacing the underlying `TECHNOLOGY`/`TASK` content (D3, D4, D6).
- It cannot populate the KBJI 2026, `SOURCE_REGISTER`, `EVIDENCE_LINK`, or `KJN_SOURCE_CLAIMS` tables required by the current DDL (D10).

**The dataset must not be imported or used to replace the database until the blockers in §6 are resolved and explicitly approved.**
