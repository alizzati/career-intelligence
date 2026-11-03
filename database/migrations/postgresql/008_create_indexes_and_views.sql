BEGIN;

CREATE INDEX IF NOT EXISTS idx_career_occupations_career_id ON okb.career_occupations(career_id);
CREATE INDEX IF NOT EXISTS idx_career_occupations_occupation_id ON okb.career_occupations(occupation_id);
CREATE INDEX IF NOT EXISTS idx_career_skills_career_id ON okb.career_skills(career_id);
CREATE INDEX IF NOT EXISTS idx_career_skills_skill_id ON okb.career_skills(skill_id);
CREATE INDEX IF NOT EXISTS idx_skills_skill_group_id ON okb.skills(skill_group_id);
CREATE INDEX IF NOT EXISTS idx_competency_units_standard_id ON okb.competency_units(standard_id);
CREATE INDEX IF NOT EXISTS idx_occupation_competencies_occupation_id ON okb.occupation_competencies(occupation_id);
CREATE INDEX IF NOT EXISTS idx_competency_skills_skill_id ON okb.competency_skills(skill_id);
CREATE INDEX IF NOT EXISTS idx_evidence_link_record_table_record_id ON okb.evidence_link(record_table, record_id);
CREATE INDEX IF NOT EXISTS idx_evidence_link_resolved_source_id ON okb.evidence_link(resolved_source_id);
CREATE INDEX IF NOT EXISTS idx_evidence_link_target_status ON okb.evidence_link(target_resolution_status);
CREATE INDEX IF NOT EXISTS idx_evidence_link_source_status ON okb.evidence_link(source_resolution_status);
CREATE INDEX IF NOT EXISTS idx_source_register_can_contribute ON okb.source_register(can_contribute_to_scores);
CREATE INDEX IF NOT EXISTS idx_occupation_source_mapping_occupation_id ON okb.occupation_source_mapping(occupation_id);
CREATE INDEX IF NOT EXISTS idx_skill_source_evidence_skill_id ON okb.skill_source_evidence(skill_id);
CREATE INDEX IF NOT EXISTS idx_occupation_kbji2026_link_occupation_id ON okb.occupation_kbji2026_link(occupation_id);
CREATE INDEX IF NOT EXISTS idx_workbook_review_approval_sha ON okb.workbook_review_approval(workbook_sha256);

CREATE OR REPLACE VIEW okb.v_evidence_link_resolved AS
SELECT *
FROM okb.evidence_link
WHERE target_resolution_status = 'RESOLVED'
  AND source_resolution_status = 'RESOLVED';

CREATE OR REPLACE VIEW okb.v_skill_catalog_joined AS
SELECT s.skill_id,
       s.canonical_name,
       sg.name AS skill_group_name,
       s.operational_evidence_present,
       s.eligible_for_career_fit,
       s.eligible_for_skill_gap
FROM okb.skills AS s
JOIN okb.skill_groups AS sg ON sg.skill_group_id = s.skill_group_id;

CREATE OR REPLACE VIEW app.v_user_skill_catalog AS
SELECT us.user_skill_id,
       us.user_id,
       us.claimed_skill,
       us.skill_id,
       s.canonical_name AS canonical_skill_name,
       us.normalized_skill,
       us.proficiency,
       us.evidence_status,
       us.confidence
FROM app.user_skills AS us
LEFT JOIN okb.skills AS s ON s.skill_id = us.skill_id;

COMMIT;
