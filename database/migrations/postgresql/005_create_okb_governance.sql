BEGIN;

CREATE TABLE IF NOT EXISTS okb.workbook_review_approval (
    approval_id TEXT PRIMARY KEY,
    workbook_sha256 TEXT NOT NULL UNIQUE,
    reviewer_identity TEXT NOT NULL,
    reviewer_role TEXT NOT NULL,
    reviewed_at TIMESTAMPTZ,
    review_scope TEXT NOT NULL,
    approval_status TEXT NOT NULL CHECK (approval_status IN ('APPROVED', 'REJECTED', 'PENDING')),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS okb.import_manifest (
    batch_id TEXT PRIMARY KEY,
    workbook_sha256 TEXT NOT NULL,
    workbook_name TEXT NOT NULL,
    source_file_name TEXT,
    source_file_sha256 TEXT,
    import_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    import_completed_at TIMESTAMPTZ,
    import_status TEXT NOT NULL CHECK (import_status IN ('STARTED', 'IMPORTING', 'COMPLETED', 'FAILED')),
    total_rows_imported INTEGER NOT NULL DEFAULT 0,
    unresolved_target_count INTEGER NOT NULL DEFAULT 0,
    unresolved_source_count INTEGER NOT NULL DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS okb.evidence_link_resolution_audit (
    audit_id TEXT PRIMARY KEY,
    link_id TEXT NOT NULL REFERENCES okb.evidence_link(link_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    record_table TEXT NOT NULL,
    record_id TEXT NOT NULL,
    source_reference_raw TEXT NOT NULL,
    target_resolution_status TEXT NOT NULL,
    source_resolution_status TEXT NOT NULL,
    target_resolution_note TEXT,
    source_resolution_note TEXT,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS okb.quarantine_reference (
    quarantine_id TEXT PRIMARY KEY,
    reference_type TEXT NOT NULL CHECK (reference_type IN ('SOURCE', 'TARGET', 'LINK')),
    raw_reference TEXT NOT NULL,
    record_table TEXT,
    record_id TEXT,
    source_id TEXT,
    reason TEXT NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS okb.etl_transform_log (
    log_id TEXT PRIMARY KEY,
    operation_name TEXT NOT NULL,
    source_table TEXT,
    target_table TEXT,
    details TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
