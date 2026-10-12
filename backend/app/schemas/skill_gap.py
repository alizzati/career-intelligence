"""
Schemas for the deterministic Skill-Gap Engine (Step 9).

Reuses ScoreBreakdownOut from app/schemas/career_fit.py (Step 8) rather
than redefining it. Only objects genuinely specific to skill-gap
classification are defined here.

There is deliberately no field anywhere in this module for ranking,
ordering weight, or a required/target proficiency level: the engine
classifies, it does not rank or score. evidence_class and kb_confidence
are descriptive KB metadata only.
"""
from typing import Literal, Optional
from pydantic import BaseModel

from app.schemas.career_fit import ScoreBreakdownOut

# The three statuses a REQUIRED career skill can have. Values map 1:1 to
# the statuses compute_career_fit() already produces
# ('matched-linked' / 'matched-claimed-only' / 'missing').
SkillGapStatus = Literal["matched_evidenced", "matched_claimed_only", "missing"]


class MatchedUserClaim(BaseModel):
    """Which of the user's claims matched a required skill. Profile
    information only -- proficiency here is whatever the user reported
    and is never compared against any career requirement."""
    claimed_skill: str            # verbatim from user_skills
    proficiency: Optional[str] = None
    evidence_status: str          # 'linked' | 'none'
    evidence_count: int


class SkillGapItem(BaseModel):
    """One REQUIRED career skill and its status."""
    skill_id: str
    canonical_name: str
    status: SkillGapStatus
    evidence_class: str           # KB metadata: CORE / SUPPORTING / ... (descriptive only)
    kb_confidence: str            # KB metadata: career_skills.confidence (descriptive only)
    weight: float                 # echoed from compute_career_fit(), not computed here
    contribution: float           # echoed from compute_career_fit(), not computed here
    matched_user_claim: Optional[MatchedUserClaim] = None   # None when status == 'missing'


class UnmatchedUserClaim(BaseModel):
    """A user claim that Step 7 could not normalize (skill_id IS NULL).
    This is a KB-mapping limitation, NOT a statement that the user lacks
    the skill, and it is never evaluated against career requirements."""
    user_skill_id: int
    claimed_skill: str            # verbatim
    proficiency: Optional[str] = None
    evidence_status: str
    evidence_count: int
    note: str = (
        "Claim could not be normalized to a canonical KB skill_id; it is not "
        "evaluated against this career's requirements. This does NOT mean the "
        "user lacks the skill."
    )


class SkillGapResult(BaseModel):
    user_id: int
    career_id: str
    canonical_name: str
    domain: str

    # Career-fit numbers: all come from compute_career_fit(), the same
    # function Step 8 uses. fit_score is rounded to 4 decimals exactly as
    # Step 8 presents it; total_weight/total_contribution are unrounded.
    fit_score: float
    total_weight: float
    total_contribution: float
    score_breakdown: ScoreBreakdownOut

    # Required skills of the selected career, in the original
    # career_skills order (no reordering, no sorting).
    matched_evidenced: list[SkillGapItem]
    matched_claimed_only: list[SkillGapItem]
    missing: list[SkillGapItem]

    # User claims that are outside canonical matching.
    unmatched_user_claims: list[UnmatchedUserClaim]