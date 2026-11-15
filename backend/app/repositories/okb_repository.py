"""Deterministic full-OKB readers used by the experiment snapshot.

The snapshot must account for every approved OKB entity and relationship, not
only the three tables that career-fit scoring happens to read. Surrogate keys
(``career_occupations.id`` and ``occupation_competencies.id``) are excluded so
that the fingerprint reflects domain content rather than sequence state.

``etl_transform_log`` is intentionally excluded: it records import mechanics
(including a server-side ``transformed_at`` timestamp and a serial ``log_id``),
not occupational knowledge, and would make the fingerprint non-deterministic.
"""
from sqlalchemy import text
from sqlalchemy.engine import Connection

# component -> (table, selected columns, ORDER BY expression)
OKB_SNAPSHOT_COMPONENTS: dict[str, tuple[str, list[str], str]] = {
    "careers": ("careers", ["career_id", "canonical_name", "domain"], "career_id"),
    "occupations": (
        "occupations",
        ["occupation_id", "canonical_name", "classification"],
        "occupation_id",
    ),
    "career_occupations": (
        "career_occupations",
        ["career_id", "occupation_id", "mapping_method", "confidence"],
        "career_id, occupation_id",
    ),
    "skill_groups": ("skill_groups", ["skill_group_id", "name"], "skill_group_id"),
    "skills": (
        "skills",
        ["skill_id", "canonical_name", "skill_group_id", "status"],
        "skill_id",
    ),
    "career_skills": (
        "career_skills",
        [
            "relationship_id", "career_id", "skill_id", "evidence_source",
            "evidence_class", "mapping_method", "confidence",
        ],
        "relationship_id",
    ),
    "skkni_standards": (
        "skkni_standards",
        [
            "standard_id", "number", "year", "title", "field", "status",
            "unit_inventory_status", "unit_count_in_dataset", "evidence_basis",
            "coverage_action_note",
        ],
        "standard_id",
    ),
    "competency_units": (
        "competency_units",
        ["unit_id", "standard_id", "code", "title"],
        "unit_id",
    ),
    "occupation_competencies": (
        "occupation_competencies",
        ["occupation_id", "standard_id", "mapping_confidence"],
        "occupation_id, standard_id",
    ),
    "competency_skills": (
        "competency_skills",
        ["relationship_id", "unit_id", "skill_id", "mapping_method"],
        "relationship_id",
    ),
    "technologies": (
        "technologies",
        [
            "technology_id", "technology_name", "technology_type", "occupation_id",
            "source", "source_period", "geography", "frequency_pct", "evidence_note",
        ],
        "technology_id",
    ),
    "tasks": (
        "tasks",
        [
            "task_id", "occupation_id", "source_code", "task_description",
            "task_category", "importance", "source", "source_period", "geography",
        ],
        "task_id",
    ),
    "provenance": (
        "provenance",
        [
            "provenance_id", "source_name", "document_id", "document_title",
            "version_or_year", "page_or_section", "url", "source_type", "scope_note",
        ],
        "provenance_id",
    ),
    "occupation_source_mapping": (
        "occupation_source_mapping",
        [
            "mapping_id", "occupation_id", "source_name", "source_code",
            "source_title", "mapping_method", "confidence", "source_scope",
            "provenance_id", "mapping_basis",
        ],
        "mapping_id",
    ),
    "skill_source_evidence": (
        "skill_source_evidence",
        [
            "evidence_id", "skill_id", "source_name", "source_reference",
            "evidence_type", "confidence", "note", "provenance_id", "mapping_basis",
        ],
        "evidence_id",
    ),
}


def fetch_okb_snapshot_rows(conn: Connection) -> dict[str, list[dict]]:
    """Return every OKB component as an ordered list of plain dicts."""
    payload: dict[str, list[dict]] = {}
    for component, (table, columns, order_by) in OKB_SNAPSHOT_COMPONENTS.items():
        select_list = ", ".join(f'"{column}"' for column in columns)
        rows = conn.execute(
            text(f'SELECT {select_list} FROM "{table}" ORDER BY {order_by}')
        ).mappings().all()
        payload[component] = [dict(row) for row in rows]
    return payload
