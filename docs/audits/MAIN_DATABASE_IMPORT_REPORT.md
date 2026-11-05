# Main Database Import Report

**Status:** BLOCKED — target provisioned and cloned; approved workbook import and application switch did not pass validation.  
**Date:** 2026-11-04

## 1. Outcome

`career_intelligence_main` was created as a new database and restored from a verified custom-format dump of `career_intelligence`. The target schema and cloned application data remain intact. The approved workbook was not imported because the target schema rejects an approved source value before the import transaction can commit.

The source database and protected E2E/OKB databases were not modified. The application configuration was not switched.

## 2. Workbook identity

| Item | Result |
|---|---|
| Path | `data/occupational_knowledge_base_verified_v1_0.xlsx` |
| SHA-256 | `7f4f95ea9caec51b76cb220772161a50c0efaf95376867d7316938bb703858df` |
| Size | 81,400 bytes at preflight |
| Structure | 18 sheets; expected names and order verified |
| Lock/temporary files | No lock file remained at successful preflight; no files were deleted |

Actual non-empty workbook records were loaded with `pandas.read_excel()`. The sheet reports 97 `SKILL_SOURCE_EVIDENCE` records; two trailing blank rows account for the earlier status value of 99. The actual workbook contents are authoritative.

## 3. Databases and backup

| Item | Result |
|---|---|
| Source | `career_intelligence` |
| Target | `career_intelligence_main` |
| Backup | `artifacts/backups/career_intelligence_20261104.dump` |
| Backup verification | PASS; file exists and is non-empty (91,895 bytes) |
| Target creation | PASS; target was absent before creation |
| Restore | PASS; `pg_restore` completed successfully |
| Application switch | NOT RUN; import validation blocked |

## 4. Schema parity

Read-only inspection showed matching public table sets, columns/types/nullability/defaults, primary keys, foreign keys, unique/check constraints, indexes, and sequences between source and target. Schema-only dumps differed only in serialization of the same `skill_source_evidence_mapping_basis_check` expression; the catalog constraint definitions matched.

**Schema parity: PASS for the cloned legacy schema.** No schema object was changed.

## 5. Import strategy and failure

The existing [import_kb.py](../../backend/scripts/import_kb.py) and [import_kb_fixed.py](../../backend/scripts/import_kb_fixed.py) are E2E-only, append-only importers and are not safe for a populated clone. A dedicated [import_kb_main.py](../../backend/scripts/import_kb_main.py) was created. It:

- refuses all protected databases and requires the exact target database;
- validates the 18-sheet workbook and actual counts;
- preserves the application-linked `skills` table and aborts if skill identities differ;
- replaces only target OKB rows inside one transaction;
- imports Technology and Task rows;
- records unit-ID transformations and unresolved provenance mappings;
- writes a machine-readable manifest only after commit.

The first attempt correctly stopped on the workbook’s two blank SSE rows when the stale expected count of 99 was treated as mandatory. The importer was corrected to use actual non-empty records, retaining the 99-vs-97 discrepancy in validation metadata.

The second attempt then failed and rolled back at `occupation_source_mapping`:

```text
psycopg2.errors.StringDataRightTruncation:
value too long for type character varying(20)
```

The approved value `Kominfo_Kemnaker_BNSP` exceeds the cloned target column `occupation_source_mapping.source_name varchar(20)`. The same limitation exists on `skill_source_evidence.source_name`. Widening those columns is a schema change, and was not applied.

## 6. Workbook vs target counts

These are post-rollback target counts; they show the cloned source state, not a successful workbook import.

| Entity | Workbook actual | Target after rollback | Difference | Status |
|---|---:|---:|---:|---|
| CAREER | 10 | 10 | 0 | PASS / cloned |
| OCCUPATION | 23 | 8 | -15 | BLOCKED |
| CAREER_OCCUPATION | 27 | 12 | -15 | BLOCKED |
| SKILL_GROUP | 17 | 17 | 0 | PASS / cloned |
| SKILL | 87 | 87 | 0 | PASS / cloned |
| CAREER_SKILL | 155 | 155 | 0 | PASS / cloned |
| SKKNI_STANDARD | 9 | 9 | 0 | PASS / cloned |
| COMPETENCY_UNIT | 146 | 146 | 0 | PASS / cloned |
| OCCUPATION_COMPETENCY | 10 | 10 | 0 | PASS / cloned |
| COMPETENCY_SKILL | 79 | 79 | 0 | PASS / cloned |
| OCCUPATION_SOURCE_MAPPING | 25 | 26 | +1 | BLOCKED |
| TECHNOLOGY | 120 | 120 | 0 | PASS / cloned only |
| TASK | 221 | 35 | -186 | BLOCKED |
| PROVENANCE | 14 | 23 | +9 | BLOCKED |
| SKILL_SOURCE_EVIDENCE | 97 | 97 | 0 | PASS / cloned count; import not run |
| STANDARD_COVERAGE | 9 | 9 merged into standards | 0 | PASS / cloned representation |

## 7. Referential integrity and application preservation

The failed transaction made no target data changes. The target still has 74 users, 271 user skills, 6 profiles, and 56 projects, matching the source counts observed during preflight. Existing cloned constraints remain enabled.

Approved-workbook FK validation was **NOT COMPLETED** because import failed before commit. The dedicated importer did validate the normalized competency-unit references before reaching the schema error. It required both suffix padding and prefix-zero normalization, including mappings such as `CU047_008 → CU47_008` and `CU022_003 → CU22_003`.

## 8. Provenance and traceability

The dedicated importer contains deterministic rules for exact Kominfo P014 resolution, KBJI resolution, SKKNI reference resolution, and fail-closed ambiguous IndoTask resolution. These rules were not committed to the database because the OSM insert failed first.

Therefore:

- imported approved-record provenance: **NOT VERIFIED**;
- unresolved provenance count: **NOT VERIFIED**;
- invalid source-reference count: **NOT VERIFIED**;
- no provenance records were invented.

## 9. TECHNOLOGY scoring integration

**FAIL / BLOCKER.** The application retrieval path loads technology records through `fetch_technologies_for_occupation()` and exposes them in occupational context. However, the authoritative `compute_career_fit()` function accepts only required skills and user skills, and its arithmetic contains no technology input, normalization, bonus, or technology contribution. Technology names are used as guarded vocabulary for agent grounding, not as career-fit scoring inputs.

The 120 records therefore cannot be demonstrated to affect career-fit scores or ranking. No scoring formula, weight, cap, or business logic was changed. Application switching is blocked until an approved scoring integration decision and implementation exist.

## 10. TASK accessibility

The repository has a query path: `occupation_repository.fetch_tasks_for_occupation()` reads `tasks`, and `retrieval_service.get_occupational_context()` exposes them. This establishes code-level accessibility, but target accessibility with the approved 221 records is **NOT VERIFIED** because the import did not commit.

## 11. Application configuration and smoke tests

| Check | Result |
|---|---|
| `CAREER_DB_NAME` changed | NO |
| Source/E2E/OKB configuration changed | NO |
| Target connection checked | PASS during importer guard and target inspection |
| Application startup against target | NOT RUN |
| Career/occupation/skill/competency reads against approved import | NOT RUN |
| Technology/task reads against approved import | NOT RUN |
| Career-fit controlled smoke test | NOT RUN; scoring integration is a blocker |
| External LLM/CV processing | NOT RUN |

## 12. Required approval to continue

The immediate blocker is schema compatibility: approve a target-only schema migration widening `occupation_source_mapping.source_name` and `skill_source_evidence.source_name` sufficiently for the approved source value, then re-run schema parity and the dedicated import. This is not a source/protected-database change, but it is a structural change and was intentionally not applied without approval.

After that approval, the remaining gates are provenance/FK validation, technology scoring integration, target smoke tests, and only then application configuration switching.

## 13. Files and artifacts

Modified/created for this stage:

- [import_kb_main.py](../../backend/scripts/import_kb_main.py) — isolated target-specific transactional importer.
- [career_intelligence_20261104.dump](../../artifacts/backups/career_intelligence_20261104.dump) — verified source backup.
- `artifacts/backups/career_intelligence_schema.sql` and `career_intelligence_main_schema.sql` — schema parity evidence.

The requested import manifest was not emitted as a successful-import manifest because the transaction did not commit; a failure manifest is provided separately at `artifacts/career_intelligence_main_import_manifest.json`.
