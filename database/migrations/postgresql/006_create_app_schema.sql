BEGIN;

CREATE TABLE IF NOT EXISTS app.users (
    user_id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.user_profiles (
    user_id BIGINT PRIMARY KEY REFERENCES app.users(user_id) ON UPDATE CASCADE ON DELETE CASCADE,
    headline TEXT,
    summary TEXT,
    target_domain TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.user_education (
    education_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES app.users(user_id) ON UPDATE CASCADE ON DELETE CASCADE,
    institution TEXT NOT NULL,
    degree TEXT,
    field_of_study TEXT,
    start_date DATE,
    end_date DATE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.user_experience (
    experience_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES app.users(user_id) ON UPDATE CASCADE ON DELETE CASCADE,
    company TEXT NOT NULL,
    role_title TEXT NOT NULL,
    employment_type TEXT,
    start_date DATE,
    end_date DATE,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.user_projects (
    project_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES app.users(user_id) ON UPDATE CASCADE ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    url TEXT,
    role TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.user_certifications (
    certification_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES app.users(user_id) ON UPDATE CASCADE ON DELETE CASCADE,
    name TEXT NOT NULL,
    issuer TEXT,
    issue_date DATE,
    expiry_date DATE,
    credential_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.user_skills (
    user_skill_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES app.users(user_id) ON UPDATE CASCADE ON DELETE CASCADE,
    claimed_skill TEXT NOT NULL,
    skill_id TEXT REFERENCES okb.skills(skill_id) ON UPDATE CASCADE ON DELETE RESTRICT,
    normalized_skill TEXT,
    proficiency TEXT,
    evidence_status TEXT NOT NULL DEFAULT 'none',
    confidence TEXT NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, claimed_skill)
);

CREATE TABLE IF NOT EXISTS app.user_skill_evidence (
    evidence_id BIGSERIAL PRIMARY KEY,
    user_skill_id BIGINT NOT NULL REFERENCES app.user_skills(user_skill_id) ON UPDATE CASCADE ON DELETE CASCADE,
    evidence_type TEXT NOT NULL,
    source_table TEXT,
    source_id BIGINT,
    description TEXT,
    url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS app.user_preferences (
    user_id BIGINT PRIMARY KEY REFERENCES app.users(user_id) ON UPDATE CASCADE ON DELETE CASCADE,
    preferred_domains TEXT,
    weekly_learning_hours INTEGER,
    preferred_learning_format TEXT,
    career_goal_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
