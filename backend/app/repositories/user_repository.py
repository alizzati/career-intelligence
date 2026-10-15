"""
User repository — parametrized SQL only, mirrors the KB repository pattern.
Writes here are the ONLY place user-domain INSERTs happen; services never
build SQL themselves. All standard entity creations use idempotent writes with
advisory locks to safely handle concurrent requests.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection

# ---- Idempotent write helpers & Constants ------------------------------------------
_NS_EDUCATION, _NS_EXPERIENCE, _NS_PROJECT, _NS_CERTIFICATION, _NS_EVIDENCE = 14101, 14102, 14103, 14104, 14105


def _advisory_lock(conn: Connection, namespace: int, key: int) -> None:
    """Serialize concurrent writers per (namespace, key) until the transaction ends."""
    conn.execute(text("SELECT pg_advisory_xact_lock(:ns, :key)"), {"ns": namespace, "key": key})


def _norm_sql(expr: str) -> str:
    return f"regexp_replace(lower(btrim(coalesce(CAST({expr} AS text), ''))), '\\s+', ' ', 'g')"


def _same(column: str, param: str) -> str:
    return f"{_norm_sql(column)} = {_norm_sql(':' + param)}"


def _same_exact(column: str, param: str) -> str:  # URLs: case-sensitive paths
    return f"coalesce(btrim({column}), '') = coalesce(btrim(CAST(:{param} AS text)), '')"


def _insert_or_fetch(conn: Connection, insert_sql: str, fetch_sql: str,
                     params: dict, fetch_keys: tuple[str, ...]) -> dict:
    row = conn.execute(text(insert_sql), params).mappings().first()
    if row is None:   # an equivalent row exists: return it unchanged
        row = conn.execute(text(fetch_sql), {k: params[k] for k in fetch_keys}).mappings().first()
    if row is None:
        raise RuntimeError("idempotent insert neither created nor found a row")
    return dict(row)


# ---- User & Profile -------------------------------------------------------------
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


# ---- Education ------------------------------------------------------------------
_EDU_COLS = "education_id, institution, degree, field_of_study, start_date, end_date, description"
_EDU_MATCH = (f"user_id = :uid AND {_same('institution', 'inst')} "
              f"AND {_same('degree', 'deg')} AND {_same('field_of_study', 'field')}")


def create_education(conn: Connection, user_id: int, institution: str, degree: str | None,
                     field_of_study: str | None, start_date, end_date, description: str | None) -> dict:
    _advisory_lock(conn, _NS_EDUCATION, user_id)
    return _insert_or_fetch(
        conn,
        f"""INSERT INTO user_education (user_id, institution, degree, field_of_study, start_date, end_date, description)
            SELECT :uid, :inst, :deg, :field, :sd, :ed, :desc
            WHERE NOT EXISTS (SELECT 1 FROM user_education WHERE {_EDU_MATCH})
            RETURNING {_EDU_COLS}""",
        f"SELECT {_EDU_COLS} FROM user_education WHERE {_EDU_MATCH} ORDER BY education_id LIMIT 1",
        {"uid": user_id, "inst": institution, "deg": degree, "field": field_of_study,
         "sd": start_date, "ed": end_date, "desc": description},
        ("uid", "inst", "deg", "field"),
    )


def fetch_education(conn: Connection, user_id: int) -> list[dict]:
    rows = conn.execute(text("""
        SELECT education_id, institution, degree, field_of_study, start_date, end_date, description
        FROM user_education WHERE user_id = :uid ORDER BY start_date DESC NULLS LAST
    """), {"uid": user_id}).mappings().all()
    return [dict(r) for r in rows]


# ---- Experience -----------------------------------------------------------------
_EXP_COLS = "experience_id, company, role_title, employment_type, start_date, end_date, description"
_EXP_MATCH = f"user_id = :uid AND {_same('company', 'co')} AND {_same('role_title', 'role')}"


def create_experience(conn: Connection, user_id: int, company: str, role_title: str,
                      employment_type: str | None, start_date, end_date, description: str | None) -> dict:
    _advisory_lock(conn, _NS_EXPERIENCE, user_id)
    return _insert_or_fetch(
        conn,
        f"""INSERT INTO user_experience (user_id, company, role_title, employment_type, start_date, end_date, description)
            SELECT :uid, :co, :role, :etype, :sd, :ed, :desc
            WHERE NOT EXISTS (SELECT 1 FROM user_experience WHERE {_EXP_MATCH})
            RETURNING {_EXP_COLS}""",
        f"SELECT {_EXP_COLS} FROM user_experience WHERE {_EXP_MATCH} ORDER BY experience_id LIMIT 1",
        {"uid": user_id, "co": company, "role": role_title, "etype": employment_type,
         "sd": start_date, "ed": end_date, "desc": description},
        ("uid", "co", "role"),
    )


def fetch_experience(conn: Connection, user_id: int) -> list[dict]:
    rows = conn.execute(text("""
        SELECT experience_id, company, role_title, employment_type, start_date, end_date, description
        FROM user_experience WHERE user_id = :uid ORDER BY start_date DESC NULLS LAST
    """), {"uid": user_id}).mappings().all()
    return [dict(r) for r in rows]


# ---- Projects -------------------------------------------------------------------
_PROJ_COLS = "project_id, title, description, url, role"
_PROJ_MATCH = f"user_id = :uid AND {_same('title', 'title')}"


def create_project(conn: Connection, user_id: int, title: str, description: str | None,
                   url: str | None, role: str | None) -> dict:
    _advisory_lock(conn, _NS_PROJECT, user_id)
    return _insert_or_fetch(
        conn,
        f"""INSERT INTO user_projects (user_id, title, description, url, role)
            SELECT :uid, :title, :desc, :url, :role
            WHERE NOT EXISTS (SELECT 1 FROM user_projects WHERE {_PROJ_MATCH})
            RETURNING {_PROJ_COLS}""",
        f"SELECT {_PROJ_COLS} FROM user_projects WHERE {_PROJ_MATCH} ORDER BY project_id LIMIT 1",
        {"uid": user_id, "title": title, "desc": description, "url": url, "role": role},
        ("uid", "title"),
    )


def fetch_projects(conn: Connection, user_id: int) -> list[dict]:
    rows = conn.execute(text("""
        SELECT project_id, title, description, url, role
        FROM user_projects WHERE user_id = :uid ORDER BY project_id
    """), {"uid": user_id}).mappings().all()
    return [dict(r) for r in rows]


# ---- Certifications -------------------------------------------------------------
_CERT_COLS = "certification_id, name, issuer, issue_date, expiry_date, credential_url"
_CERT_MATCH = f"user_id = :uid AND {_same('name', 'name')} AND {_same('issuer', 'issuer')}"


def create_certification(conn: Connection, user_id: int, name: str, issuer: str | None,
                         issue_date, expiry_date, credential_url: str | None) -> dict:
    _advisory_lock(conn, _NS_CERTIFICATION, user_id)
    return _insert_or_fetch(
        conn,
        f"""INSERT INTO user_certifications (user_id, name, issuer, issue_date, expiry_date, credential_url)
            SELECT :uid, :name, :issuer, :idate, :edate, :url
            WHERE NOT EXISTS (SELECT 1 FROM user_certifications WHERE {_CERT_MATCH})
            RETURNING {_CERT_COLS}""",
        f"SELECT {_CERT_COLS} FROM user_certifications WHERE {_CERT_MATCH} ORDER BY certification_id LIMIT 1",
        {"uid": user_id, "name": name, "issuer": issuer, "idate": issue_date,
         "edate": expiry_date, "url": credential_url},
        ("uid", "name", "issuer"),
    )


def fetch_certifications(conn: Connection, user_id: int) -> list[dict]:
    rows = conn.execute(text("""
        SELECT certification_id, name, issuer, issue_date, expiry_date, credential_url
        FROM user_certifications WHERE user_id = :uid ORDER BY issue_date DESC NULLS LAST
    """), {"uid": user_id}).mappings().all()
    return [dict(r) for r in rows]


# ---- Skills & Evidence ----------------------------------------------------------
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


_EVID_COLS = "evidence_id, evidence_type, source_table, source_id, description, url"
_EVID_MATCH = (f"user_skill_id = :usid AND CAST(evidence_type AS text) = CAST(:etype AS text) "
               f"AND {_same('description', 'desc')} AND {_same_exact('url', 'url')}")


def add_skill_evidence(conn: Connection, user_skill_id: int, evidence_type: str,
                       source_table: str | None, source_id: int | None,
                       description: str | None, url: str | None) -> dict:
    _advisory_lock(conn, _NS_EVIDENCE, user_skill_id)
    row = _insert_or_fetch(
        conn,
        f"""INSERT INTO user_skill_evidence (user_skill_id, evidence_type, source_table, source_id, description, url)
            SELECT :usid, :etype, :stable, :sid, :desc, :url
            WHERE NOT EXISTS (SELECT 1 FROM user_skill_evidence WHERE {_EVID_MATCH})
            RETURNING {_EVID_COLS}""",
        f"SELECT {_EVID_COLS} FROM user_skill_evidence WHERE {_EVID_MATCH} ORDER BY evidence_id LIMIT 1",
        {"usid": user_skill_id, "etype": evidence_type, "stable": source_table,
         "sid": source_id, "desc": description, "url": url},
        ("usid", "etype", "desc", "url"),
    )
    # a skill with >=1 evidence row is no longer 'none'
    conn.execute(text("UPDATE user_skills SET evidence_status = 'linked' WHERE user_skill_id = :usid"),
                 {"usid": user_skill_id})
    return row


def fetch_skill_evidence(conn: Connection, user_skill_id: int) -> list[dict]:
    rows = conn.execute(text("""
        SELECT evidence_id, evidence_type, source_table, source_id, description, url
        FROM user_skill_evidence WHERE user_skill_id = :usid ORDER BY evidence_id
    """), {"usid": user_skill_id}).mappings().all()
    return [dict(r) for r in rows]


# ---- Preferences ----------------------------------------------------------------
def fetch_preferences(conn: Connection, user_id: int) -> dict | None:
    row = conn.execute(text("""
        SELECT preferred_domains, weekly_learning_hours, preferred_learning_format, career_goal_notes
        FROM user_preferences WHERE user_id = :uid
    """), {"uid": user_id}).mappings().first()
    return dict(row) if row else None