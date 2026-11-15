-- Stage 3.4.1 - Evidence acceptance schema
--
-- Purpose
--   Separate candidate evidence from accepted evidence per B2 (D-01..D-17).
--   Candidate rows hold temporary CV spans and a deterministic + semantic
--   decision trail. Accepted rows hold the only credit that may make a
--   skill 'linked'. Raw CV text is cleared from a candidate after its
--   decision; the span hash and source provenance remain for auditing.
--
-- Scope
--   Applied to the designated test database by the guarded importer only.
--   career_intelligence_main is never targeted by this repository script.
--
-- Safety
--   Every statement is idempotent so the importer can re-apply the full set.
--   Rebuilding the occupational knowledge base cascades to evidence rows
--   through the skill_id foreign keys, which is acceptable for the test DB.

CREATE TABLE IF NOT EXISTS user_evidence_candidates (
    candidate_id bigserial NOT NULL,
    candidate_key text NOT NULL,
    user_id integer NOT NULL,
    cv_id text NOT NULL,
    source_type character varying(40) NOT NULL,
    source_table character varying(40) NOT NULL,
    source_id integer,
    skill_id character varying(10),
    claimed_skill text,
    evidence_text text,
    evidence_span_hash character varying(64),
    structural_status character varying(20) NOT NULL DEFAULT 'pending',
    structural_reason text,
    semantic_status character varying(20) NOT NULL DEFAULT 'not_attempted',
    decision_reason text,
    acceptance_status character varying(20) NOT NULL DEFAULT 'pending',
    span_removed_at timestamp with time zone,
    created_at timestamp with time zone NOT NULL DEFAULT now(),
    updated_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT user_evidence_candidates_pkey PRIMARY KEY (candidate_id),
    CONSTRAINT user_evidence_candidates_candidate_key_key UNIQUE (candidate_key),
    CONSTRAINT user_evidence_candidates_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT user_evidence_candidates_skill_id_fkey
        FOREIGN KEY (skill_id) REFERENCES skills(skill_id) ON DELETE CASCADE,
    CONSTRAINT user_evidence_candidates_structural_status_check
        CHECK (structural_status IN ('pending', 'passed', 'failed')),
    CONSTRAINT user_evidence_candidates_semantic_status_check
        CHECK (semantic_status IN ('PASS', 'REVISE', 'FAIL', 'not_attempted')),
    CONSTRAINT user_evidence_candidates_acceptance_status_check
        CHECK (acceptance_status IN ('pending', 'accepted', 'revise', 'rejected'))
);

CREATE INDEX IF NOT EXISTS idx_user_evidence_candidates_user
    ON user_evidence_candidates (user_id, acceptance_status);
CREATE INDEX IF NOT EXISTS idx_user_evidence_candidates_cv_skill
    ON user_evidence_candidates (cv_id, skill_id);

CREATE TABLE IF NOT EXISTS user_accepted_evidence (
    accepted_evidence_id bigserial NOT NULL,
    user_id integer NOT NULL,
    cv_id text NOT NULL,
    skill_id character varying(10) NOT NULL,
    candidate_id bigint,
    source_type character varying(40) NOT NULL,
    source_table character varying(40) NOT NULL,
    source_id integer,
    claimed_skill text,
    accepted_at timestamp with time zone NOT NULL DEFAULT now(),
    CONSTRAINT user_accepted_evidence_pkey PRIMARY KEY (accepted_evidence_id),
    CONSTRAINT user_accepted_evidence_cv_skill_key
        UNIQUE (user_id, cv_id, skill_id),
    CONSTRAINT user_accepted_evidence_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    CONSTRAINT user_accepted_evidence_skill_id_fkey
        FOREIGN KEY (skill_id) REFERENCES skills(skill_id) ON DELETE CASCADE,
    CONSTRAINT user_accepted_evidence_candidate_id_fkey
        FOREIGN KEY (candidate_id) REFERENCES user_evidence_candidates(candidate_id)
        ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_user_accepted_evidence_user
    ON user_accepted_evidence (user_id, skill_id);
