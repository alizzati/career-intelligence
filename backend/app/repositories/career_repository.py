"""
Career repository — parametrized SQL only. No interpretation, no scoring,
no LLM calls. Every function here is a thin, auditable read against the KB.
"""
from sqlalchemy import text
from sqlalchemy.engine import Connection


def fetch_all_careers(conn: Connection) -> list[dict]:
    rows = conn.execute(text(
        "SELECT career_id, canonical_name, domain FROM careers ORDER BY career_id"
    )).mappings().all()
    return [dict(r) for r in rows]


def fetch_career(conn: Connection, career_id: str) -> dict | None:
    row = conn.execute(
        text("SELECT career_id, canonical_name, domain FROM careers WHERE career_id = :cid"),
        {"cid": career_id},
    ).mappings().first()
    return dict(row) if row else None


def fetch_career_skills(conn: Connection, career_id: str) -> list[dict]:
    rows = conn.execute(text("""
        SELECT cs.relationship_id, cs.evidence_class, cs.confidence, cs.mapping_method,
               cs.evidence_source AS evidence_source_text,
               s.skill_id, s.canonical_name, s.skill_group_id, s.status
        FROM career_skills cs
        JOIN skills s ON s.skill_id = cs.skill_id
        WHERE cs.career_id = :cid
        ORDER BY cs.relationship_id
    """), {"cid": career_id}).mappings().all()
    return [dict(r) for r in rows]


def fetch_occupations_for_career(conn: Connection, career_id: str) -> list[dict]:
    rows = conn.execute(text("""
        SELECT o.occupation_id, o.canonical_name, o.classification,
               co.mapping_method, co.confidence
        FROM career_occupations co
        JOIN occupations o ON o.occupation_id = co.occupation_id
        WHERE co.career_id = :cid
        ORDER BY o.occupation_id
    """), {"cid": career_id}).mappings().all()
    return [dict(r) for r in rows]