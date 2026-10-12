"""
Pydantic response models for the retrieval layer.

These are the ONLY shapes agents are allowed to consume from the KB.
Agents never see raw SQL rows or ORM objects.
"""
from typing import Optional
from pydantic import BaseModel


class CareerOut(BaseModel):
    career_id: str
    canonical_name: str
    domain: str


class OccupationOut(BaseModel):
    occupation_id: str
    canonical_name: str
    classification: str


class CareerOccupationOut(BaseModel):
    occupation: OccupationOut
    mapping_method: str
    confidence: str


class SkillOut(BaseModel):
    skill_id: str
    canonical_name: str
    skill_group_id: str
    status: str


class ProvenanceOut(BaseModel):
    provenance_id: str
    source_name: str
    document_id: str
    document_title: str
    version_or_year: str
    url: Optional[str] = None
    source_type: str


class EvidenceItem(BaseModel):
    """
    A single piece of evidence, normalized regardless of which underlying
    table it came from (skill_source_evidence OR career_skills.evidence_source).
    granularity distinguishes the two so downstream agents/Verification
    Agent can reason about evidence strength correctly.
    """
    granularity: str          # 'skill-level' | 'career-skill-level'
    source_name: str
    reference: str             # source_reference (skill-level) or evidence_source text (career-skill-level)
    confidence: Optional[str] = None
    evidence_type: Optional[str] = None
    provenance: Optional[ProvenanceOut] = None
    mapping_basis: Optional[str] = None  # only set for skill-level rows


class CareerSkillOut(BaseModel):
    relationship_id: str
    skill: SkillOut
    evidence_class: str
    confidence: str
    mapping_method: str
    evidence_source_text: str


class CompetencyUnitOut(BaseModel):
    unit_id: str
    code: str
    title: str
    standard_id: str


class OccupationCompetencyOut(BaseModel):
    standard_id: str
    standard_title: str
    mapping_confidence: str
    units: list[CompetencyUnitOut]


class TaskOut(BaseModel):
    task_id: str
    task_description: str
    task_category: str
    importance: Optional[float] = None
    source: str


class TechnologyOut(BaseModel):
    technology_id: str
    technology_name: str
    technology_type: str
    frequency_pct: Optional[float] = None
    source: str


class OccupationSourceMappingOut(BaseModel):
    mapping_id: str
    source_name: str
    source_code: str
    confidence: str
    mapping_basis: str
    provenance: Optional[ProvenanceOut] = None


class OccupationalContextOut(BaseModel):
    """
    Full evidence-grounded bundle for one career, as consumed by the
    Career Recommendation / Skill Gap / Roadmap / Verification agents.
    See RetrievalService.get_occupational_context for field semantics.
    """
    career: CareerOut
    occupations: list[OccupationOut]
    career_skills: list[CareerSkillOut]
    competencies: list[OccupationCompetencyOut]      # per-occupation, deduplicated by standard
    tasks: dict[str, list[TaskOut]]                  # occupation_id -> tasks
    technologies: dict[str, list[TechnologyOut]]     # occupation_id -> technologies
    source_mappings: dict[str, list[OccupationSourceMappingOut]]  # occupation_id -> mappings