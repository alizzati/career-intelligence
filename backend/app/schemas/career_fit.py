from typing import Optional
from pydantic import BaseModel


class SkillRefOut(BaseModel):
    """A skill reference attached to a recommendation -- always traced
    back to a real row in the KB skills table, never invented."""
    skill_id: str
    canonical_name: str
    evidence_class: str


class ScoreBreakdownOut(BaseModel):
    total_weight: float
    total_contribution: float
    core_required_count: int
    supporting_required_count: int
    matched_linked_count: int
    matched_claimed_only_count: int
    missing_count: int
    weights_used: dict   # echoes the exact weights applied, for reproducibility (Section 19)


class CareerRecommendationOut(BaseModel):
    career_id: str
    canonical_name: str
    domain: str
    fit_score: float
    score_breakdown: ScoreBreakdownOut
    matched_skills: list[SkillRefOut]           # evidence_status='linked'
    claimed_only_skills: list[SkillRefOut]      # claimed but evidence_status='none'
    missing_skills_preview: list[SkillRefOut]   # NOT a full gap analysis -- that is Step 9's job
    reasoning: str
    reasoning_source: str   # 'llm' | 'fallback-template' -- transparency on how reasoning was produced