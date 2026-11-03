BEGIN;

CREATE TABLE IF NOT EXISTS okb.skill_groups (
    skill_group_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS okb.careers (
    career_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    domain TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS okb.occupations (
    occupation_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    classification TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS okb.career_occupations (
    career_id TEXT NOT NULL REFERENCES okb.careers(career_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    occupation_id TEXT NOT NULL REFERENCES okb.occupations(occupation_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    mapping_method TEXT,
    confidence TEXT,
    legacy_career_occupation_id TEXT,
    operational_evidence_present BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_career_fit BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_skill_gap BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (career_id, occupation_id)
);

CREATE TABLE IF NOT EXISTS okb.skills (
    skill_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    skill_group_id TEXT NOT NULL REFERENCES okb.skill_groups(skill_group_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'active',
    operational_evidence_present BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_career_fit BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_skill_gap BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS okb.career_skills (
    relationship_id TEXT PRIMARY KEY,
    career_id TEXT NOT NULL REFERENCES okb.careers(career_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    skill_id TEXT NOT NULL REFERENCES okb.skills(skill_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    skill_name TEXT,
    evidence_source TEXT,
    evidence_class TEXT,
    mapping_method TEXT,
    confidence TEXT,
    operational_evidence_present BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_career_fit BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_skill_gap BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (career_id, skill_id)
);

CREATE TABLE IF NOT EXISTS okb.tasks (
    task_id TEXT PRIMARY KEY,
    occupation_id TEXT NOT NULL REFERENCES okb.occupations(occupation_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    source_code TEXT,
    task_description TEXT NOT NULL,
    task_category TEXT,
    importance NUMERIC(8,4),
    source TEXT,
    operational_evidence_present BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_career_fit BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_skill_gap BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS okb.technology_catalog (
    technology_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    technology_type TEXT,
    normalized_value TEXT NOT NULL UNIQUE,
    catalog_fingerprint TEXT,
    source_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS okb.technology_alias (
    alias_id TEXT PRIMARY KEY,
    technology_id TEXT NOT NULL REFERENCES okb.technology_catalog(technology_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    UNIQUE (normalized_alias)
);

CREATE TABLE IF NOT EXISTS okb.technologies (
    technology_id TEXT PRIMARY KEY,
    technology_name TEXT NOT NULL,
    technology_type TEXT,
    occupation_id TEXT NOT NULL REFERENCES okb.occupations(occupation_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    source TEXT,
    source_period TEXT,
    frequency_pct NUMERIC(5,2),
    evidence_note TEXT,
    operational_evidence_present BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_career_fit BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_skill_gap BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS okb.kbji_hierarchy (
    node_id TEXT PRIMARY KEY,
    kbji_code TEXT NOT NULL,
    hierarchy_level TEXT,
    title TEXT NOT NULL,
    parent_code TEXT,
    definition TEXT,
    example_occupations_and_related TEXT,
    evidence_class TEXT,
    verification_status TEXT,
    primary_page_print TEXT,
    conflict_flag BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (kbji_code)
);

CREATE TABLE IF NOT EXISTS okb.kbji_occupation (
    occupation_id TEXT PRIMARY KEY,
    occupation_name TEXT NOT NULL,
    occupation_code TEXT NOT NULL,
    description TEXT,
    parent_subgolongan_code TEXT,
    evidence_class TEXT,
    verification_status TEXT,
    primary_page_print TEXT,
    scope_tag TEXT,
    is_residual BOOLEAN NOT NULL DEFAULT FALSE,
    selection_priority INTEGER,
    inclusion_basis TEXT,
    notes TEXT,
    UNIQUE (occupation_code)
);

CREATE TABLE IF NOT EXISTS okb.occupation_kbji2026_link (
    link_id TEXT PRIMARY KEY,
    occupation_id TEXT NOT NULL REFERENCES okb.occupations(occupation_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    kbji2026_code TEXT NOT NULL,
    kbji2026_title TEXT,
    kbji2014_title_legacy TEXT,
    match_type TEXT,
    match_basis TEXT
);

CREATE TABLE IF NOT EXISTS okb.career_occupation_kbji_mapping (
    career_id TEXT NOT NULL,
    occupation_id TEXT NOT NULL,
    kbji_mapping_id TEXT NOT NULL,
    PRIMARY KEY (career_id, occupation_id, kbji_mapping_id),
    FOREIGN KEY (career_id, occupation_id)
        REFERENCES okb.career_occupations(career_id, occupation_id)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS okb.career_kbji_mapping (
    mapping_id TEXT PRIMARY KEY,
    career_id TEXT NOT NULL REFERENCES okb.careers(career_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    occupation_id TEXT NOT NULL REFERENCES okb.kbji_occupation(occupation_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    mapping_type TEXT,
    mapping_method TEXT,
    confidence_level TEXT,
    evidence_class TEXT,
    source_locator TEXT,
    evidence_summary TEXT,
    evidence_type TEXT,
    coverage_status TEXT,
    validation_status TEXT,
    expert_review_status TEXT,
    mapped_by TEXT,
    operational_evidence_present BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_career_fit BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_skill_gap BOOLEAN NOT NULL DEFAULT FALSE
);

COMMIT;
