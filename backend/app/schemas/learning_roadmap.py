"""Response models for a skill-gap-grounded learning roadmap."""
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.skill_gap import SkillGapResult


RoadmapGapStatus = Literal["matched_claimed_only", "missing"]
LearningAction = Literal["develop_skill", "add_linked_evidence"]
RoadmapNarrativeSource = Literal["llm", "fallback-template"]


class LearningRoadmapItem(BaseModel):
    """A focus item derived from one outstanding required skill."""
    skill_id: str
    canonical_name: str
    gap_status: RoadmapGapStatus
    evidence_class: str
    kb_confidence: str
    knowledge_base_basis: str
    learning_action: LearningAction


class LearningRoadmapOut(BaseModel):
    """Deterministic focus items with a separate, optional LLM summary."""
    skill_gap: SkillGapResult
    items: list[LearningRoadmapItem] = Field(default_factory=list)
    summary: str
    narrative_source: RoadmapNarrativeSource
    llm_error: str | None = None
