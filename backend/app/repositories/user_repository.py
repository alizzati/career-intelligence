"""
User repository — parametrized SQL only, mirrors the KB repository pattern.
Writes here are the ONLY place user-domain INSERTs happen; services never
build SQL themselves.
"""
from sqlalchemy import text
from sqlalchemy.engine import Connection


def create_user(conn: Connection, email: str, full_name: str) -> dict:
    row = conn.execute(text("""
        INSERT INTO users (email, full_name) VALUES (:email, :name)
        RETURNING user_id, email, full_name, created_at
    """), {"email": email, "name": full_name}).mappings().first()
    return dict(row)


def fetch_user(conn: Connection, user_id: int) -> dict | None:
    row = conn.execute(
        text("SELECT user_id, email, full_name, created_at FROM users WHERE user_id = :uid"),
        {"uid": user_id},
    ).mappings().first()
    return dict(row) if row else None


def fetch_profile(conn: Connection, user_id: int) -> dict | None:
    row = conn.execute(
        text("SELECT headline, summary, target_domain FROM user_profiles WHERE user_id = :uid"),
        {"uid": user_id},
    ).mappings().first()
    return dict(row) if row else None


def upsert_profile(conn: Connection, user_id: int, headline: str | None,
                    summary: str | None, target_domain: str | None) -> None:
    conn.execute(text("""
        INSERT INTO user_profiles (user_id, headline, summary, target_domain)
        VALUES (:uid, :h, :s, :t)
        ON CONFLICT (user_id) DO UPDATE
        SET headline = EXCLUDED.headline, summary = EXCLUDED.summary,
            target_domain = EXCLUDED.target_domain, updated_at = now()
    """), {"uid": user_id, "h": headline, "s": summary, "t": target_domain})


def create_education(conn: Connection, user_id: int, institution: str, degree: str | None,
                      field_of_study: str | None, start_date, end_date, description: str | None) -> dict:
    row = conn.execute(text("""
        INSERT INTO user_education (user_id, institution, degree, field_of_study, start_date, end_date, description)
        VALUES (:uid, :inst, :deg, :field, :sd, :ed, :desc)
        RETURNING education_id, institution, degree, field_of_study, start_date, end_date, description
    """), {"uid": user_id, "inst": institution, "deg": degree, "field": field_of_study,
           "sd": start_date, "ed": end_date, "desc": description}).mappings().first()
    return dict(row)


def create_experience(conn: Connection, user_id: int, company: str, role_title: str,
                       employment_type: str | None, start_date, end_date, description: str | None) -> dict:
    row = conn.execute(text("""
        INSERT INTO user_experience (user_id, company, role_title, employment_type, start_date, end_date, description)
        VALUES (:uid, :co, :role, :etype, :sd, :ed, :desc)
        RETURNING experience_id, company, role_title, employment_type, start_date, end_date, description
    """), {"uid": user_id, "co": company, "role": role_title, "etype": employment_type,
           "sd": start_date, "ed": end_date, "desc": description}).mappings().first()
    return dict(row)


def create_project(conn: Connection, user_id: int, title: str, description: str | None,
                    url: str | None, role: str | None) -> dict:
    row = conn.execute(text("""
        INSERT INTO user_projects (user_id, title, description, url, role)
        VALUES (:uid, :title, :desc, :url, :role)
        RETURNING project_id, title, description, url, role
    """), {"uid": user_id, "title": title, "desc": description, "url": url, "role": role}).mappings().first()
    return dict(row)


def create_certification(conn: Connection, user_id: int, name: str, issuer: str | None,
                          issue_date, expiry_date, credential_url: str | None) -> dict:
    row = conn.execute(text("""
        INSERT INTO user_certifications (user_id, name, issuer, issue_date, expiry_date, credential_url)
        VALUES (:uid, :name, :issuer, :idate, :edate, :url)
        RETURNING certification_id, name, issuer, issue_date, expiry_date, credential_url
    """), {"uid": user_id, "name": name, "issuer": issuer, "idate": issue_date,
           "edate": expiry_date, "url": credential_url}).mappings().first()
    return dict(row)


def fetch_education(conn: Connection, user_id: int) -> list[dict]:
    rows = conn.execute(text("""
        SELECT education_id, institution, degree, field_of_study, start_date, end_date, description
        FROM user_education WHERE user_id = :uid ORDER BY start_date DESC NULLS LAST
    """), {"uid": user_id}).mappings().all()
    return [dict(r) for r in rows]


def fetch_experience(conn: Connection, user_id: int) -> list[dict]:
    rows = conn.execute(text("""
        SELECT experience_id, company, role_title, employment_type, start_date, end_date, description
        FROM user_experience WHERE user_id = :uid ORDER BY start_date DESC NULLS LAST
    """), {"uid": user_id}).mappings().all()
    return [dict(r) for r in rows]


def fetch_projects(conn: Connection, user_id: int) -> list[dict]:
    rows = conn.execute(text("""
        SELECT project_id, title, description, url, role
        FROM user_projects WHERE user_id = :uid ORDER BY project_id
    """), {"uid": user_id}).mappings().all()
    return [dict(r) for r in rows]


def fetch_certifications(conn: Connection, user_id: int) -> list[dict]:
    rows = conn.execute(text("""
        SELECT certification_id, name, issuer, issue_date, expiry_date, credential_url
        FROM user_certifications WHERE user_id = :uid ORDER BY issue_date DESC NULLS LAST
    """), {"uid": user_id}).mappings().all()
    return [dict(r) for r in rows]


def create_user_skill(conn: Connection, user_id: int, claimed_skill: str,
                       skill_id: str | None, normalized_skill: str | None,
                       proficiency: str | None) -> dict:
    row = conn.execute(text("""
        INSERT INTO user_skills (user_id, claimed_skill, skill_id, normalized_skill, proficiency,
                                  evidence_status, confidence)
        VALUES (:uid, :claimed, :sid, :norm, :prof, 'none', 'unknown')
        ON CONFLICT (user_id, claimed_skill) DO UPDATE
        SET skill_id = EXCLUDED.skill_id, normalized_skill = EXCLUDED.normalized_skill,
            proficiency = EXCLUDED.proficiency
        RETURNING user_skill_id, claimed_skill, skill_id, normalized_skill, proficiency,
                  evidence_status, confidence
    """), {"uid": user_id, "claimed": claimed_skill, "sid": skill_id,
           "norm": normalized_skill, "prof": proficiency}).mappings().first()
    return dict(row)


def fetch_user_skills(conn: Connection, user_id: int) -> list[dict]:
    rows = conn.execute(text("""
        SELECT user_skill_id, claimed_skill, skill_id, normalized_skill, proficiency,
               evidence_status, confidence
        FROM user_skills WHERE user_id = :uid ORDER BY user_skill_id
    """), {"uid": user_id}).mappings().all()
    return [dict(r) for r in rows]


def add_skill_evidence(conn: Connection, user_skill_id: int, evidence_type: str,
                        source_table: str | None, source_id: int | None,
                        description: str | None, url: str | None) -> dict:
    row = conn.execute(text("""
        INSERT INTO user_skill_evidence (user_skill_id, evidence_type, source_table, source_id,
                                          description, url)
        VALUES (:usid, :etype, :stable, :sid, :desc, :url)
        RETURNING evidence_id, evidence_type, source_table, source_id, description, url
    """), {"usid": user_skill_id, "etype": evidence_type, "stable": source_table,
           "sid": source_id, "desc": description, "url": url}).mappings().first()
    # a skill with >=1 evidence row is no longer 'none'
    conn.execute(text(
        "UPDATE user_skills SET evidence_status = 'linked' WHERE user_skill_id = :usid"
    ), {"usid": user_skill_id})
    return dict(row)


def fetch_skill_evidence(conn: Connection, user_skill_id: int) -> list[dict]:
    rows = conn.execute(text("""
        SELECT evidence_id, evidence_type, source_table, source_id, description, url
        FROM user_skill_evidence WHERE user_skill_id = :usid ORDER BY evidence_id
    """), {"usid": user_skill_id}).mappings().all()
    return [dict(r) for r in rows]


def fetch_preferences(conn: Connection, user_id: int) -> dict | None:
    row = conn.execute(text("""
        SELECT preferred_domains, weekly_learning_hours, preferred_learning_format, career_goal_notes
        FROM user_preferences WHERE user_id = :uid
    """), {"uid": user_id}).mappings().first()
    return dict(row) if row else None