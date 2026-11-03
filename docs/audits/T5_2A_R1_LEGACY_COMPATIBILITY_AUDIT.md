# T5.2A-R1 — Legacy Compatibility and Technology Design Audit

## 1. Objective

This audit corrects the earlier T5.2A design to preserve the repository’s legacy user-domain schema while keeping the OKB design coherent, traceable, and review-safe.

This is a design-only audit. No database writes or SQL execution were performed.

## 2. Legacy compatibility matrix

The application repository confirms the user-domain tables that must remain compatible.

| Legacy table | Legacy columns / semantics | Target table | Name preserved? | Structure compatible? | Data preservation requirement | Code references | Findings |
|---|---|---|---|---|---|---|---|
| `users` | `user_id`, `email`, `full_name`, `created_at` | `app.users` | Yes | Yes | Preserve user identity and email uniqueness | `backend/app/repositories/user_repository.py` | Must remain structurally compatible with create/fetch flows |
| `user_profiles` | `user_id`, `headline`, `summary`, `target_domain`, timestamps | `app.user_profiles` | Yes | Yes | Preserve profile-scoped user metadata | `user_repository.py` | Keep exact table and FK semantics |
| `user_education` | `education_id`, `user_id`, institution, degree, dates, description | `app.user_education` | Yes | Yes | Preserve educational background storage and ordering | `user_repository.py` | Fetch logic depends on exact names and sort order |
| `user_experience` | `experience_id`, `user_id`, company, role_title, employment_type, dates, description | `app.user_experience` | Yes | Yes | Preserve employment history | `user_repository.py` | Must keep the repository’s `fetch_experience()` contract |
| `user_projects` | `project_id`, `user_id`, title, description, url, role | `app.user_projects` | Yes | Yes | Preserve project history and alternative evidence | `user_repository.py` | No renaming or structural drift permitted |
| `user_certifications` | `certification_id`, `user_id`, name, issuer, dates, credential_url | `app.user_certifications` | Yes | Yes | Preserve certification records and evidence metadata | `user_repository.py` | Must retain matching behavior for `name` and `issuer` |
| `user_skills` | `user_skill_id`, `user_id`, `claimed_skill`, `skill_id`, `normalized_skill`, `proficiency`, `evidence_status`, `confidence` | `app.user_skills` | Yes | Yes | Preserve user claims and the valid `skill_id` linkage to `okb.skills` | `user_repository.py`, `backend/app/services/skill_gap_service.py` | This is the primary cross-schema compatibility point |
| `user_skill_evidence` | `evidence_id`, `user_skill_id`, `evidence_type`, `source_table`, `source_id`, description, url | `app.user_skill_evidence` | Yes | Yes | Preserve evidence chain for user claims | `user_repository.py` | Support idempotent evidence insertion |
| `user_preferences` | `user_id`, preferences, learning hours, format, notes, timestamps | `app.user_preferences` | Yes | Yes | Preserve user preference behavior | `user_repository.py` | Must retain the repository’s profile flow |

Finding: a schema that only creates a few generic user tables is not compliant. The repository contract expects the full user-domain set and exact legacy names.

## 3. OKB coverage review

The design preserves the required OKB scope and key relationships.

Required OKB entities:
- careers
- occupations
- skill_groups
- skills
- career_skills
- career_occupations
- skkni_standards
- competency_units
- occupation_competencies
- competency_skills
- source_register
- provenance
- occupation_source_mapping
- skill_source_evidence
- evidence_link
- kbji_hierarchy
- kbji_occupation
- occupation_kbji2026_link
- career_kbji_mapping
- career_occupation_kbji_mapping
- governance/import metadata

Coverage status:
- The corrected `database/migrations/postgresql/002_create_okb_core.sql` includes the key core tables and the explicit `career_occupation_kbji_mapping` junction.
- The design keeps the four invariant skill-gap categories and does not reintroduce a per-record `validation_status` field.
- The same `instruction.md` constraints are preserved for the 10-career scope and the workbook SHA-256 fingerprint.

## 4. Technology catalog and scoring design

The previous design erroneously treated technology as excluded from the operational path and therefore under-specified the operational technology flow. The corrected design keeps technology evidence separate from competency evidence.

Requirements preserved:
- Technology claims are extracted from activity descriptions.
- Technology mentions are normalized against a dedicated operational catalog.
- Alias normalization uses NFKC, case-folding, trimming, and whitespace collapsing.
- Alias collisions must fail rather than being silently merged.
- A technology mention without accepted evidence receives no bonus.
- Unmatched technology claims remain traceable but receive no bonus.
- Technology evidence does not become `CompetencyEvidence`.
- Technology scoring remains design-pending and must not be hardcoded into DDL.

The migration file introduces the operational model explicitly:
- `okb.technology_catalog`
- `okb.technology_alias`
- `okb.technologies`
- `okb.tasks`

No formula or bonus weight is committed in this design because the project explicitly requires that formula, weight, and cap remain pending approval in a separate design decision.

## 5. T1–T4 invariant compliance matrix

| Requirement | Status | Evidence |
|---|---|---|
| 10 canonical careers | Pass | Current design and workbook mapping maintain the canonical 10-career scope |
| Four skill-gap categories fixed | Pass | `matched_evidenced`, `matched_claimed_only`, `missing`, `unmatched_user_claims` |
| `compute_career_fit()` source of truth | Pass | DDL does not redefine career-fit logic |
| Unmatched user claims preserved as `unmatched_user_claims` | Pass | Not reinterpreted as missing skills or missing requirements |
| Technology/competency separation maintained | Pass | Dedicated technology catalog and separate evidence path |
| No per-record validation-state reintroduction | Pass | Explicitly excluded from target design |
| Legacy compatibility preserved | Pass | Full app-domain table compatibility retained |
| Workbook hash preserved | Pass | `1314578e44d4a66b21fd19effe441ed303dc2da2239423abf73dfb7d1c807353` |

## 6. Exact SQL files and objects requiring review

The following migration scripts were inspected and corrected where necessary:

- `database/migrations/postgresql/001_create_schemas_and_extensions.sql`
  - `app` and `okb` schema creation
- `database/migrations/postgresql/002_create_okb_core.sql`
  - `okb.skill_groups`
  - `okb.careers`
  - `okb.occupations`
  - `okb.career_occupations`
  - `okb.skills`
  - `okb.career_skills`
  - `okb.tasks`
  - `okb.technology_catalog`
  - `okb.technology_alias`
  - `okb.technologies`
  - `okb.kbji_hierarchy`
  - `okb.kbji_occupation`
  - `okb.occupation_kbji2026_link`
  - `okb.career_occupation_kbji_mapping`
  - `okb.career_kbji_mapping`
- `database/migrations/postgresql/003_create_okb_competency.sql`
  - `okb.skkni_standards`
  - `okb.competency_units`
  - `okb.occupation_competencies`
  - `okb.competency_skills`
- `database/migrations/postgresql/004_create_okb_provenance.sql`
  - `okb.source_register`
  - `okb.provenance`
  - `okb.occupation_source_mapping`
  - `okb.skill_source_evidence`
  - `okb.evidence_link`
- `database/migrations/postgresql/005_create_okb_governance.sql`
  - governance and import metadata tables
- `database/migrations/postgresql/006_create_app_schema.sql`
  - `app.users`
  - `app.user_profiles`
  - `app.user_education`
  - `app.user_experience`
  - `app.user_projects`
  - `app.user_certifications`
  - `app.user_skills`
  - `app.user_skill_evidence`
  - `app.user_preferences`
- `database/migrations/postgresql/007_add_cross_schema_constraints.sql`
  - cross-schema FKs and validation constraints
- `database/migrations/postgresql/008_create_indexes_and_views.sql`
  - performance indexes and read-only views

## 7. Remaining unresolved decisions

These remain unresolved before a DDL execution can be approved:
- final technology bonus formula, weight, normalization contract, and cap
- exact final compatibility sign-off for all legacy tables and edge cases
- whether to keep workbook `TECHNOLOGY` and `TASK` records in a historical staging schema or exclude them fully from the operational model
- final design sign-off on the full migration object list after workbook evidence review

## 8. Blockers preventing DDL execution

The corrected design is not yet approved for execution because:
- the technology bonus formula is still pending approval
- the legacy compatibility matrix requires final sign-off against the full user-domain model
- the historical/staging decision for optional `TASK` and `TECHNOLOGY` records has not been finalized
- the DDL remains a static design artifact rather than an approved deployment artifact

## 9. Final conclusion

The corrected design preserves the repository’s legacy user contract and keeps the OKB grounded and traceable. It also keeps technology and competency evidence separate, which is required by the project rules. However, because the technology scoring formula remains unresolved and the compatibility review still requires final sign-off, the design is not ready for actual postgres execution. It is ready for a separate, explicit DDL review only.
