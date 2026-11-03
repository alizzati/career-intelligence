BEGIN;

-- Cross-schema FK contract: application claims are bound to the canonical okb skill catalog.
ALTER TABLE app.user_skills
    ADD CONSTRAINT IF NOT EXISTS fk_user_skills_okb_skill
    FOREIGN KEY (skill_id) REFERENCES okb.skills(skill_id)
    ON UPDATE CASCADE ON DELETE RESTRICT
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE app.user_skill_evidence
    ADD CONSTRAINT IF NOT EXISTS fk_user_skill_evidence_user_skill
    FOREIGN KEY (user_skill_id) REFERENCES app.user_skills(user_skill_id)
    ON UPDATE CASCADE ON DELETE CASCADE
    DEFERRABLE INITIALLY DEFERRED;

-- Keep the cross-schema relationship explicit for traceability, without forcing user data migration.
COMMENT ON CONSTRAINT fk_user_skills_okb_skill ON app.user_skills IS
    'Application-claim skill_id must resolve to a canonical okb skill when present. Unmatched claims remain allowed and are reported separately.';

COMMIT;
