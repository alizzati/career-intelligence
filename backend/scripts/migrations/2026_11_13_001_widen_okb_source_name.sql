-- Stage 3.2.8 - OKB schema migration 001
--
-- Purpose
--   The approved workbook stores the source name 'Kominfo_Kemnaker_BNSP'
--   (21 characters). The legacy OKB schema declared
--   occupation_source_mapping.source_name and skill_source_evidence.source_name
--   as character varying(20), so those rows could not be imported.
--
--   Widen both columns to 100 characters, matching the already-approved
--   career_intelligence_main schema. The statement is idempotent: applying it
--   to an already-widened column is a no-op in terms of stored data.
--
-- Scope
--   Applied only to career_intelligence_e2e_test by the guarded importer.
--   career_intelligence_main is never targeted by this repository script.

ALTER TABLE occupation_source_mapping
    ALTER COLUMN source_name TYPE character varying(100);

ALTER TABLE skill_source_evidence
    ALTER COLUMN source_name TYPE character varying(100);
