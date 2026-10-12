"""
Schemas for the Skill-Gap Agent (Step 10).

The deterministic Step 9 result (SkillGapResult) is embedded UNCHANGED as
`skill_gap`; the narrative is a separate, validated layer next to it. The
narrative never replaces or edits the deterministic data.

There is deliberately no field here for a priority, ranking, tier, new
score, or a required/target proficiency level.
"""
from typing import Literal, Optional
from pydantic import BaseModel

from app.schemas.skill_gap import SkillGapResult


class SkillObservation(BaseModel):
    """A sentence about specific REQUIRED career skills. `skill_ids` anchors
    the sentence to the deterministic result and is validated against the
    category the observation belongs to."""
    skill_ids: list[str]
    text: str


class UnmatchedClaimObservation(BaseModel):
    """A sentence about user claims that could not be mapped to the KB.
    Anchored by user_skill_id (these claims have no canonical skill_id)."""
    user_skill_ids: list[int]
    text: str


class SkillGapNarrative(BaseModel):
    summary: str
    strengths: list[SkillObservation] = []                  # category: matched_evidenced
    claimed_only_observations: list[SkillObservation] = []  # category: matched_claimed_only
    missing_skill_observations: list[SkillObservation] = [] # category: missing
    unmatched_claim_observations: list[UnmatchedClaimObservation] = []  # category: unmatched_user_claims
    conclusion: str


# 'llm'               every narrative part came from the LLM and passed validation
# 'llm-partial'       the LLM responded, but some parts were dropped/replaced by the deterministic template
# 'fallback-template' no LLM was used, the call failed, or its output was unusable
NarrativeSource = Literal["llm", "llm-partial", "fallback-template"]


class SkillGapAnalysisOut(BaseModel):
    skill_gap: SkillGapResult          # Step 9 output, untouched: the source of truth
    narrative: SkillGapNarrative
    narrative_source: NarrativeSource
    llm_error: Optional[str] = None    # set when the LLM call failed or returned unusable output
    validation_notes: list[str] = []   # what the grounding guard dropped, replaced, or ignored