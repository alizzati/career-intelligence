"""
Skill repository. Added for STEP 7 (Profile Agent): the normalizer needs
the FULL canonical skill catalog, not just skills tied to one career
(career_repository.fetch_career_skills is scoped to a career and
insufficient for general-purpose normalization).
"""
from sqlalchemy import text
from sqlalchemy.engine import Connection


def fetch_all_skills(conn: Connection) -> list[dict]:
    rows = conn.execute(text( 
        "SELECT skill_id, canonical_name, skill_group_id, status FROM skills ORDER BY skill_id"
    )).mappings().all()
    return [dict(r) for r in rows]