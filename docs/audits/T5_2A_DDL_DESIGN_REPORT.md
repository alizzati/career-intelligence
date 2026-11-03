# T5.2A — DDL Design and Migration Audit Report

## 1. Correction history

This report was corrected for the T5.2A-R1 follow-up requirements.

Key corrections:
- The earlier design was too narrow on user-domain compatibility and treated the `app` schema as though only a few tables were required.
- The earlier design incorrectly implied that technology was excluded from the operational path entirely, even though the approved design requires dedicated technology normalization and a separate technology bonus path.
- The corrected design keeps the exact legacy application tables and names in the `app` schema and keeps the technology catalog separate from competency evidence.
- The previous report is therefore not treated as authoritative for execution approval; it is a design-only review artifact.

## 2. Files inspected

The following files and directories were inspected during the static review:
- `instruction.md`
- `backend/app/core/db.py`
- `backend/app/repositories/user_repository.py`
- `backend/app/repositories/occupation_repository.py`
- `database/migrations/postgresql/001_create_schemas_and_extensions.sql`
- `database/migrations/postgresql/002_create_okb_core.sql`
- `database/migrations/postgresql/003_create_okb_competency.sql`
- `database/migrations/postgresql/004_create_okb_provenance.sql`
- `database/migrations/postgresql/005_create_okb_governance.sql`
- `database/migrations/postgresql/006_create_app_schema.sql`
- `database/migrations/postgresql/007_add_cross_schema_constraints.sql`
- `database/migrations/postgresql/008_create_indexes_and_views.sql`
- `docs/design/T5_2_TARGET_DDL_DESIGN.md`
- `docs/audits/T5_2A_DDL_DESIGN_REPORT.md`

## 3. Files modified

Modified in this correction cycle:
- `database/migrations/postgresql/002_create_okb_core.sql`
- `docs/design/T5_2_TARGET_DDL_DESIGN.md`
- `docs/audits/T5_2A_DDL_DESIGN_REPORT.md`

Created:
- `docs/audits/T5_2A_R1_LEGACY_COMPATIBILITY_AUDIT.md`

## 4. Static findings

1. Legacy compatibility is not satisfied by a minimal `app` schema alone. The repository expects the full user-domain table set and the exact legacy table names, especially `users`, `user_profiles`, `user_education`, `user_experience`, `user_projects`, `user_certifications`, `user_skills`, `user_skill_evidence`, and `user_preferences`.
2. The no-write requirement is preserved: no SQL was executed, no database objects were created or modified, and no migration was run.
3. The corrected `okb` schema keeps `tasks`, `technology_catalog`, `technology_alias`, and `technologies` as separate operational objects to preserve technology normalization without treating technology mentions as competency evidence.
4. The DDL design remains intentionally conservative: technology bonus weight, formula, and cap are not hardcoded and remain pending design approval.
5. The design still does not authorize DDL execution; it remains review-only pending final compatibility and technology scoring sign-off.

## 5. No execution or runtime validation performed

The following did not occur:
- No PostgreSQL connection
- No INSERT/ALTER/DROP/CREATE execution against the database
- No workbook import
- No migrations executed
- No user-data copy or database write
- No runtime DB validation claim

## 6. Review status

Status: design review complete; DDL execution not approved.

This corrected design is aligned with the repository’s legacy model and the approved invariants, but it remains blocked from execution by unresolved technology scoring approval and the final compatibility sign-off for the remaining legacy schema details.
