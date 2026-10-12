"""
Evidence repository.

IMPORTANT (from STEP 4 semantic validation, Check 9):
24/87 skills have zero rows in skill_source_evidence, but 100% of those 24
DO have free-text evidence attached at the career_skills.evidence_source
level. Any function claiming to return "the evidence for skill X" MUST
combine both tables, or it will misreport those 24 skills as unsupported --
a direct violation of Section 18 ("no unsupported claim presented as fact").
"""
from sqlalchemy import text
from sqlalchemy.engine import Connection


def fetch_skill_source_evidence(conn: Connection, skill_id: str) -> list[dict]:
    """Structured, skill-level evidence rows (skill_source_evidence table)."""
    rows = conn.execute(text("""
        SELECT sse.evidence_id, sse.source_name, sse.source_reference,
               sse.evidence_type, sse.confidence, sse.mapping_basis, sse.note,
               p.provenance_id AS p_id, p.source_name AS p_source_name, p.document_id,
               p.document_title, p.version_or_year, p.url, p.source_type
        FROM skill_source_evidence sse
        LEFT JOIN provenance p ON p.provenance_id = sse.provenance_id
        WHERE sse.skill_id = :sid
        ORDER BY sse.evidence_id
    """), {"sid": skill_id}).mappings().all()
    return [dict(r) for r in rows]


def fetch_career_skill_evidence_text(conn: Connection, skill_id: str) -> list[dict]:
    """
    Free-text, career-skill-level evidence (career_skills.evidence_source).
    Coarser granularity: describes why the skill is tied to a given career,
    not a structured citation. Still a legitimate, source-grounded claim
    per the dataset design (see README).
    """
    rows = conn.execute(text("""
        SELECT cs.career_id, cs.relationship_id, cs.evidence_source, cs.confidence
        FROM career_skills cs
        WHERE cs.skill_id = :sid
        ORDER BY cs.career_id
    """), {"sid": skill_id}).mappings().all()
    return [dict(r) for r in rows]


def fetch_provenance(conn: Connection, provenance_id: str) -> dict | None:
    row = conn.execute(
        text("SELECT * FROM provenance WHERE provenance_id = :pid"),
        {"pid": provenance_id},
    ).mappings().first()
    return dict(row) if row else None