# T5.2A-R1 — Corrected Target PostgreSQL DDL Design

## 1. Scope and safety boundary

This document corrects the earlier T5.2A design to satisfy the R1 requirements and the controlling `instruction.md` rules.

Safety constraints:
- No PostgreSQL writes or SQL execution were performed.
- No database creation, migration, import, or data copy was performed.
- The target DDL remains a design artifact only.

## 2. Design intent

The corrected target model keeps the following invariants:
- One dedicated database: `career_intelligence_okb`
- Two schemas: `app` and `okb`
- Existing user-domain tables remain intact in the `app` schema, preserving names, keys, and repository contracts
- The OKB remains the grounding source for careers, occupations, skills, competency mappings, provenance, and governance
- Technology claims are normalized via a dedicated operational technology catalog; technology evidence is not conflated with competency evidence
- Technology bonus scoring is explicitly pending design approval and is not hardcoded in DDL or docs
- The four skill-gap categories remain fixed: `matched_evidenced`, `matched_claimed_only`, `missing`, and `unmatched_user_claims`
- `compute_career_fit()` remains the single source of truth for career-fit computation

## 3. Legacy compatibility matrix

| Legacy table | Legacy columns / shape | Target table | Name preserved? | Compatible? | Data preservation requirement | Code references | Findings |
|---|---|---|---|---|---|---|---|
| `users` | `user_id`, `email`, `full_name`, `created_at` | `app.users` | Yes | Yes | Preserve identities and login/profile behavior | `backend/app/repositories/user_repository.py` | Exact names and PK semantics must remain stable |
| `user_profiles` | `user_id`, `headline`, `summary`, `target_domain`, audit timestamps | `app.user_profiles` | Yes | Yes | Preserve profile and target-domain metadata | `user_repository.py` | Keep exact table and FK behaviors |
| `user_education` | `education_id`, `user_id`, institution, degree, field_of_study, dates, description | `app.user_education` | Yes | Yes | Preserve education history and date semantics | `user_repository.py` | Must remain compatible with `fetch_education()` |
| `user_experience` | `experience_id`, `user_id`, company, role_title, employment_type, dates, description | `app.user_experience` | Yes | Yes | Preserve experience timeline | `user_repository.py` | Must remain compatible with `fetch_experience()` |
| `user_projects` | `project_id`, `user_id`, title, description, url, role | `app.user_projects` | Yes | Yes | Preserve project mapping and API behavior | `user_repository.py` | Projects are a first-class user artifact |
| `user_certifications` | `certification_id`, `user_id`, name, issuer, dates, credential_url | `app.user_certifications` | Yes | Yes | Preserve certifications and matching logic | `user_repository.py` | Keep certification matching semantics |
| `user_skills` | `user_skill_id`, `user_id`, `claimed_skill`, `skill_id`, `normalized_skill`, `proficiency`, `evidence_status`, `confidence` | `app.user_skills` | Yes | Yes | Preserve user claims and the valid `skill_id` linkage to `okb.skills` | `user_repository.py`, `skill_gap_service.py` | This is the only cross-schema FK that must remain valid |
| `user_skill_evidence` | `evidence_id`, `user_skill_id`, `evidence_type`, `source_table`, `source_id`, description, url | `app.user_skill_evidence` | Yes | Yes | Preserve evidence records tied to user claims | `user_repository.py` | Must support evidence traceability and idempotence |
| `user_preferences` | `user_id`, domain preferences, hours, format, notes, timestamps | `app.user_preferences` | Yes | Yes | Preserve user preference structure | `user_repository.py` | Keep profile flow intact |

Important: a minimal `app` schema with only a few generic tables is not sufficient. The application expects the full user-domain set and exact legacy names.

## 4. OKB entity coverage

Required OKB entities:
- `careers`
- `occupations`
- `skill_groups`
- `skills`
- `career_skills`
- `career_occupations`
- `skkni_standards`
- `competency_units`
- `occupation_competencies`
- `competency_skills`
- `source_register`
- `provenance`
- `occupation_source_mapping`
- `skill_source_evidence`
- `evidence_link`
- `kbji_hierarchy`
- `kbji_occupation`
- `occupation_kbji2026_link`
- `career_kbji_mapping`
- `career_occupation_kbji_mapping`
- governance and import metadata tables

The corrected migration script covers these entities in the `okb` schema. `career_occupation_kbji_mapping` is retained as the factual junction table for the normalized `career_occupations` pair.

## 5. Technology catalog and evidence-based bonus design

Technology handling is intentionally separated from competency evidence.

Correct requirements:
- Technology claims are extracted from activity descriptions.
- Technology claims are normalized against a dedicated operational technology catalog.
- Technology normalization uses NFKC, case-folding, trimming, whitespace collapsing, and explicit aliases.
- Alias collisions fail deterministically rather than inventing a match.
- Only accepted, verified technology evidence contributes to a separate bonus component.
- A technology mention without accepted evidence receives no bonus.
- Unmatched technology claims remain traceable but receive no bonus.
- Technology evidence does not become `CompetencyEvidence` or hard-skill evidence.
- Technology scoring remains out of scope for the current DDL design because the weight, formula, normalization policy, and cap are still pending approval.

The migration script implements the operational model explicitly:
- `okb.technology_catalog`
- `okb.technology_alias`
- `okb.technologies`
- `okb.tasks`

This preserves the operational design without committing to a scoring formula that has not been approved.

## 6. Invariant compliance matrix

| Invariant | Status | Notes |
|---|---|---|
| Exactly 10 canonical careers | Pass | Design and workbook mapping preserve the 10-career scope |
| Four skill-gap categories remain fixed | Pass | `matched_evidenced`, `matched_claimed_only`, `missing`, `unmatched_user_claims` |
| `compute_career_fit()` stays authoritative | Pass | DDL does not redefine scoring logic |
| User claim without evidence is not automatically missing | Pass | Preserved in the design and user-schema mapping |
| Unmatched user claims remain `unmatched_user_claims` | Pass | Not treated as OKB requirements |
| Technology and competency evidence remain separate | Pass | Dedicated technology catalog acknowledged; no hardcoded bonus |
| No per-record `validation_status` reintroduced | Pass | Kept out of the target operational model |
| Workbook hash preserved | Pass | `1314578e44d4a66b21fd19effe441ed303dc2da2239423abf73dfb7d1c807353` |
| Legacy user tables preserved | Pass | All legacy app tables are explicitly represented in `app` schema |
| Design-only execution boundary preserved | Pass | No SQL executed or DB modified |

## 7. SQL file coverage and required object checks

The following migration files were reviewed and the corrected design is aligned with the actual repository contract:

1. `001_create_schemas_and_extensions.sql` — creates `app` and `okb` schemas and extensions
2. `002_create_okb_core.sql` — creates core taxonomy and technology/task tables, plus `career_occupation_kbji_mapping`
3. `003_create_okb_competency.sql` — creates SKKNI and competency tables
4. `004_create_okb_provenance.sql` — provenance, source, and evidence tables
5. `005_create_okb_governance.sql` — governance/audit metadata tables
6. `006_create_app_schema.sql` — preserves legacy user table names and relationships
7. `007_add_cross_schema_constraints.sql` — cross-schema FK constraints and validation hooks
8. `008_create_indexes_and_views.sql` — indexes and reporting views

Required corrections for the earlier design were limited to preserving compatibility and clarifying the technology evidence boundary; they do not authorize execution of any migration.

## 8. Remaining unresolved decisions

These decisions remain pending explicit design approval before DDL execution can be considered:
- Exact technology bonus weight, formula, and cap
- Final compatibility matrix against any additional legacy tables outside the currently inspected user-domain set
- Any runtime decision to create a dedicated historical staging schema for workbook `TECHNOLOGY` / `TASK` data
- Final sign-off on the completed migration object list after review against the full workbook contract

## 9. Status for separate DDL review

Status: ready for separate review only, not ready for DDL execution.

The corrected design is internally consistent with the repository’s legacy user contract, preserves the project’s no-write boundary, and keeps technology evidence separate from competency evidence. However, the remaining technology scoring formula and exact compatibility sign-off remain unresolved, so the scripts are still design-review artifacts rather than executable migration candidates.
