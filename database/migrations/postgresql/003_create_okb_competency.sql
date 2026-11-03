BEGIN;

CREATE TABLE IF NOT EXISTS okb.skkni_standards (
    standard_id TEXT PRIMARY KEY,
    number TEXT NOT NULL,
    year INTEGER,
    title TEXT NOT NULL,
    field TEXT,
    status TEXT NOT NULL CHECK (status IN ('Berlaku', 'Tidak Berlaku')),
    jdih_standard_id TEXT,
    jdih_source_url TEXT,
    jdih_enacted_date DATE,
    record_origin TEXT,
    candidate_career_ids_hint TEXT
);

CREATE TABLE IF NOT EXISTS okb.skkni_standard_coverage (
    standard_id TEXT NOT NULL REFERENCES okb.skkni_standards(standard_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    number TEXT,
    year INTEGER,
    unit_inventory_status TEXT NOT NULL CHECK (unit_inventory_status IN ('COMPLETE', 'PROFILE-COMPLETE', 'PARTIAL', 'NONE')),
    unit_count_in_dataset INTEGER NOT NULL DEFAULT 0,
    evidence_basis TEXT,
    action TEXT,
    PRIMARY KEY (standard_id)
);

CREATE TABLE IF NOT EXISTS okb.competency_units (
    unit_id TEXT PRIMARY KEY,
    standard_id TEXT NOT NULL REFERENCES okb.skkni_standards(standard_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    code TEXT NOT NULL,
    title TEXT NOT NULL,
    evidence_class TEXT,
    crosscheck_source_url TEXT,
    UNIQUE (standard_id, code)
);

CREATE TABLE IF NOT EXISTS okb.occupation_competencies (
    relationship_id TEXT PRIMARY KEY,
    occupation_id TEXT NOT NULL REFERENCES okb.occupations(occupation_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    standard_id TEXT NOT NULL REFERENCES okb.skkni_standards(standard_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    mapping_confidence TEXT,
    operational_evidence_present BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_career_fit BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_skill_gap BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (occupation_id, standard_id)
);

CREATE TABLE IF NOT EXISTS okb.competency_skills (
    relationship_id TEXT PRIMARY KEY,
    unit_id TEXT NOT NULL REFERENCES okb.competency_units(unit_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    skill_id TEXT NOT NULL REFERENCES okb.skills(skill_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    skill_name TEXT,
    mapping_method TEXT,
    operational_evidence_present BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_career_fit BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_skill_gap BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (unit_id, skill_id)
);

COMMIT;
