BEGIN;

CREATE TABLE IF NOT EXISTS okb.source_register (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_type TEXT,
    organization TEXT,
    official_url TEXT,
    exact_document_or_download_url TEXT,
    version_edition_pinned TEXT,
    publication_year INTEGER,
    access_date DATE,
    geography TEXT,
    license_status TEXT,
    verification_metadata TEXT,
    verification_content TEXT,
    permission_status TEXT,
    selection_status TEXT,
    can_contribute_to_scores BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS okb.provenance (
    provenance_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    document_id TEXT,
    document_title TEXT,
    version_or_year TEXT,
    source_id TEXT REFERENCES okb.source_register(source_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    record_status TEXT NOT NULL DEFAULT 'ACTIVE'
);

CREATE TABLE IF NOT EXISTS okb.occupation_source_mapping (
    mapping_id TEXT PRIMARY KEY,
    occupation_id TEXT NOT NULL REFERENCES okb.occupations(occupation_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    source_name TEXT,
    source_code TEXT,
    source_title TEXT,
    mapping_method TEXT,
    confidence TEXT,
    source_id TEXT REFERENCES okb.source_register(source_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    operational_evidence_present BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_career_fit BOOLEAN NOT NULL DEFAULT FALSE,
    eligible_for_skill_gap BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS okb.skill_source_evidence (
    evidence_id TEXT PRIMARY KEY,
    skill_id TEXT NOT NULL REFERENCES okb.skills(skill_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    skill_name TEXT,
    source_name TEXT,
    source_reference TEXT,
    evidence_type TEXT,
    confidence TEXT,
    note TEXT,
    source_id TEXT REFERENCES okb.source_register(source_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    reference_resolution TEXT,
    linked_unit_id TEXT REFERENCES okb.competency_units(unit_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    competency_skill_link_exists BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS okb.evidence_link (
    link_id TEXT PRIMARY KEY,
    record_table TEXT NOT NULL,
    record_id TEXT NOT NULL,
    source_reference_raw TEXT NOT NULL,
    resolved_source_id TEXT REFERENCES okb.source_register(source_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    standard_id TEXT REFERENCES okb.skkni_standards(standard_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    evidence_component TEXT,
    target_resolution_status TEXT NOT NULL CHECK (target_resolution_status IN ('RESOLVED', 'ORPHAN_TARGET', 'INVALID_TABLE', 'AMBIGUOUS')),
    source_resolution_status TEXT NOT NULL CHECK (source_resolution_status IN ('RESOLVED', 'UNRESOLVED', 'QUARANTINED')),
    target_resolution_note TEXT,
    source_resolution_note TEXT,
    resolution_checked_at TIMESTAMPTZ,
    source_resolved_at TIMESTAMPTZ,
    CHECK (record_table IN (
        'CAREER_KBJI_MAPPING',
        'CAREER_OCCUPATION',
        'CAREER_SKILL',
        'COMPETENCY_SKILL',
        'OCCUPATION_COMPETENCY',
        'OCCUPATION_SOURCE_MAPPING',
        'SKILL'
    ))
);

CREATE TABLE IF NOT EXISTS okb.kjn_source_claims (
    claim_id TEXT PRIMARY KEY,
    claim_topic TEXT NOT NULL,
    text_in_document_original_indonesian TEXT,
    interpretation_note TEXT,
    support_status TEXT NOT NULL CHECK (support_status IN ('SUPPORTED', 'PARTIAL', 'UNSUPPORTED', 'UNKNOWN'))
);

COMMIT;
