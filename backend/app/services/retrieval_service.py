"""
Retrieval Service — the sole interface between agents and the Occupational
Knowledge Base.

Hard rule (Section 10 / 11 of the master prompt): agents call these
functions and get back Pydantic objects. They never see a raw SQL row,
never construct a query, and never touch a repository directly.

Every function opens its own short-lived connection (via app.core.db.engine)
and is read-only.
"""
from app.core.db import engine
from app.repositories import career_repository as career_repo
from app.repositories import occupation_repository as occ_repo
from app.repositories import evidence_repository as evidence_repo
from app.repositories import skill_repository as skill_repo
from app.schemas.retrieval import (
    CareerOut, OccupationOut, SkillOut, CareerSkillOut, CareerOccupationOut,
    ProvenanceOut, EvidenceItem, CompetencyUnitOut, OccupationCompetencyOut,
    TaskOut, TechnologyOut, OccupationSourceMappingOut, OccupationalContextOut,
)


def _provenance_out(row: dict) -> ProvenanceOut | None:
    if not row.get("p_id"):
        return None
    return ProvenanceOut(
        provenance_id=row["p_id"], source_name=row["p_source_name"],
        document_id=row["document_id"], document_title=row["document_title"],
        version_or_year=row["version_or_year"], url=row.get("url"),
        source_type=row["source_type"],
    )


def get_all_skills() -> list[SkillOut]:
    """
    Full canonical skill catalog. Added for STEP 7 (Profile Agent): the
    skill normalizer needs every skill in the KB as its matching/candidate
    universe, not just skills scoped to one career.
    """
    with engine.connect() as conn:
        return [SkillOut(**r) for r in skill_repo.fetch_all_skills(conn)]


def get_all_careers() -> list[CareerOut]:
    with engine.connect() as conn:
        return [CareerOut(**r) for r in career_repo.fetch_all_careers(conn)]


def list_all_careers() -> list[dict]:
    with engine.connect() as conn:
        return career_repo.fetch_all_careers(conn)


def get_career(career_id: str) -> CareerOut | None:
    with engine.connect() as conn:
        row = career_repo.fetch_career(conn, career_id)
        return CareerOut(**row) if row else None


def get_career_skills(career_id: str) -> list[CareerSkillOut]:
    with engine.connect() as conn:
        rows = career_repo.fetch_career_skills(conn, career_id)
    return [
        CareerSkillOut(
            relationship_id=r["relationship_id"],
            skill=SkillOut(skill_id=r["skill_id"], canonical_name=r["canonical_name"],
                            skill_group_id=r["skill_group_id"], status=r["status"]),
            evidence_class=r["evidence_class"], confidence=r["confidence"],
            mapping_method=r["mapping_method"], evidence_source_text=r["evidence_source_text"],
        ) for r in rows
    ]


def get_occupations_for_career(career_id: str) -> list[CareerOccupationOut]:
    with engine.connect() as conn:
        rows = career_repo.fetch_occupations_for_career(conn, career_id)
    return [
        CareerOccupationOut(
            occupation=OccupationOut(occupation_id=r["occupation_id"], canonical_name=r["canonical_name"],
                                      classification=r["classification"]),
            mapping_method=r["mapping_method"], confidence=r["confidence"],
        ) for r in rows
    ]


def get_occupation_competencies(occupation_id: str) -> list[OccupationCompetencyOut]:
    """Competencies grouped by SKKNI standard, each carrying its competency units."""
    with engine.connect() as conn:
        rows = occ_repo.fetch_occupation_competencies(conn, occupation_id)
    grouped: dict[str, OccupationCompetencyOut] = {}
    for r in rows:
        std = r["standard_id"]
        if std not in grouped:
            grouped[std] = OccupationCompetencyOut(
                standard_id=std, standard_title=r["standard_title"],
                mapping_confidence=r["mapping_confidence"], units=[],
            )
        if r["unit_id"]:
            grouped[std].units.append(CompetencyUnitOut(
                unit_id=r["unit_id"], code=r["code"], title=r["unit_title"], standard_id=std,
            ))
    return list(grouped.values())


def get_skill_evidence(skill_id: str) -> list[EvidenceItem]:
    """
    Combined evidence for one skill, across BOTH granularities.
    See evidence_repository module docstring for why this combination is
    mandatory rather than optional.
    """
    with engine.connect() as conn:
        structured = evidence_repo.fetch_skill_source_evidence(conn, skill_id)
        text_level = evidence_repo.fetch_career_skill_evidence_text(conn, skill_id)

    items: list[EvidenceItem] = []
    for r in structured:
        items.append(EvidenceItem(
            granularity="skill-level", source_name=r["source_name"],
            reference=r["source_reference"], confidence=r["confidence"],
            evidence_type=r["evidence_type"], mapping_basis=r["mapping_basis"],
            provenance=_provenance_out(r),
        ))
    for r in text_level:
        items.append(EvidenceItem(
            granularity="career-skill-level",
            source_name=f"career:{r['career_id']}",
            reference=r["evidence_source"], confidence=r["confidence"],
            evidence_type=None, mapping_basis=None, provenance=None,
        ))
    return items


def get_occupational_context(career_id: str) -> OccupationalContextOut | None:
    """
    Full evidence-grounded bundle for one career. This is what the Career
    Recommendation / Skill Gap / Roadmap / Verification agents receive --
    they never query the KB themselves beyond this call (plus targeted
    get_skill_evidence calls when the Verification Agent needs to double
    check a specific claim).

    Returned fields:
      - career: the career record itself
      - occupations: every occupation this career maps to (career_occupations)
      - career_skills: every required skill with evidence_class/confidence
        and the free-text evidence_source (career-skill-level evidence)
      - competencies: SKKNI standards + competency units linked to any of
        this career's occupations (deduplicated by standard)
      - tasks: occupation_id -> O*NET/IndoTask task list
      - technologies: occupation_id -> current-market technology signals
        (NOTE: technologies are NOT canonical skill requirements -- Section
        18 rule 2 -- agents must not treat these as required skills without
        an explicit external/current-market tag)
      - source_mappings: occupation_id -> KBJI/O*NET/ESCO/IndoTask mapping
        records with resolved provenance where deterministic
    """
    career = get_career(career_id)
    if career is None:
        return None

    occ_links = get_occupations_for_career(career_id)
    occupations = [link.occupation for link in occ_links]
    career_skills = get_career_skills(career_id)

    competencies_by_standard: dict[str, OccupationCompetencyOut] = {}
    tasks: dict[str, list[TaskOut]] = {}
    technologies: dict[str, list[TechnologyOut]] = {}
    source_mappings: dict[str, list[OccupationSourceMappingOut]] = {}

    with engine.connect() as conn:
        for occ in occupations:
            oid = occ.occupation_id

            for comp in get_occupation_competencies(oid):
                if comp.standard_id not in competencies_by_standard:
                    competencies_by_standard[comp.standard_id] = comp

            tasks[oid] = [TaskOut(**t) for t in occ_repo.fetch_tasks_for_occupation(conn, oid)]
            technologies[oid] = [TechnologyOut(**t) for t in occ_repo.fetch_technologies_for_occupation(conn, oid)]

            sm_rows = occ_repo.fetch_source_mappings_for_occupation(conn, oid)
            source_mappings[oid] = [
                OccupationSourceMappingOut(
                    mapping_id=r["mapping_id"], source_name=r["source_name"],
                    source_code=r["source_code"], confidence=r["confidence"],
                    mapping_basis=r["mapping_basis"], provenance=_provenance_out(r),
                ) for r in sm_rows
            ]

    return OccupationalContextOut(
        career=career, occupations=occupations, career_skills=career_skills,
        competencies=list(competencies_by_standard.values()),
        tasks=tasks, technologies=technologies, source_mappings=source_mappings,
    )