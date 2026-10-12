from sqlalchemy import text
from sqlalchemy.engine import Connection


def fetch_occupation(conn: Connection, occupation_id: str) -> dict | None:
    row = conn.execute(
        text("SELECT occupation_id, canonical_name, classification FROM occupations WHERE occupation_id = :oid"),
        {"oid": occupation_id},
    ).mappings().first()
    return dict(row) if row else None


def fetch_occupation_competencies(conn: Connection, occupation_id: str) -> list[dict]:
    """
    Returns one row per (standard, unit) pair the occupation is linked to,
    via occupation_competencies -> skkni_standards -> competency_units.
    Caller (service layer) groups these by standard_id.
    """
    rows = conn.execute(text("""
        SELECT oc.standard_id, ss.title AS standard_title, oc.mapping_confidence,
               cu.unit_id, cu.code, cu.title AS unit_title
        FROM occupation_competencies oc
        JOIN skkni_standards ss ON ss.standard_id = oc.standard_id
        LEFT JOIN competency_units cu ON cu.standard_id = oc.standard_id
        WHERE oc.occupation_id = :oid
        ORDER BY oc.standard_id, cu.unit_id
    """), {"oid": occupation_id}).mappings().all()
    return [dict(r) for r in rows]


def fetch_competency_skills(conn: Connection, unit_ids: list[str]) -> list[dict]:
    """Skills linked to a given set of competency unit_ids (already normalized)."""
    if not unit_ids:
        return []
    rows = conn.execute(text("""
        SELECT ck.unit_id, s.skill_id, s.canonical_name
        FROM competency_skills ck
        JOIN skills s ON s.skill_id = ck.skill_id
        WHERE ck.unit_id = ANY(:unit_ids)
    """), {"unit_ids": unit_ids}).mappings().all()
    return [dict(r) for r in rows]


def fetch_tasks_for_occupation(conn: Connection, occupation_id: str) -> list[dict]:
    rows = conn.execute(text("""
        SELECT task_id, task_description, task_category, importance, source
        FROM tasks WHERE occupation_id = :oid
        ORDER BY importance DESC NULLS LAST, task_id
    """), {"oid": occupation_id}).mappings().all()
    return [dict(r) for r in rows]


def fetch_technologies_for_occupation(conn: Connection, occupation_id: str) -> list[dict]:
    rows = conn.execute(text("""
        SELECT technology_id, technology_name, technology_type, frequency_pct, source
        FROM technologies WHERE occupation_id = :oid
        ORDER BY frequency_pct DESC NULLS LAST, technology_id
    """), {"oid": occupation_id}).mappings().all()
    return [dict(r) for r in rows]


def fetch_source_mappings_for_occupation(conn: Connection, occupation_id: str) -> list[dict]:
    rows = conn.execute(text("""
        SELECT osm.mapping_id, osm.source_name, osm.source_code, osm.confidence,
               osm.mapping_basis, osm.provenance_id,
               p.provenance_id AS p_id, p.source_name AS p_source_name, p.document_id,
               p.document_title, p.version_or_year, p.url, p.source_type
        FROM occupation_source_mapping osm
        LEFT JOIN provenance p ON p.provenance_id = osm.provenance_id
        WHERE osm.occupation_id = :oid
        ORDER BY osm.mapping_id
    """), {"oid": occupation_id}).mappings().all()
    return [dict(r) for r in rows]