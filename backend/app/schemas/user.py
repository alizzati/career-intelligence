from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class UserOut(BaseModel):
    user_id: int
    email: str
    full_name: str
    created_at: datetime


class UserProfileOut(BaseModel):
    headline: Optional[str] = None
    summary: Optional[str] = None
    target_domain: Optional[str] = None


class EducationOut(BaseModel):
    education_id: int
    institution: str
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    description: Optional[str] = None


class ExperienceOut(BaseModel):
    experience_id: int
    company: str
    role_title: str
    employment_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    description: Optional[str] = None


class ProjectOut(BaseModel):
    project_id: int
    title: str
    description: Optional[str] = None
    url: Optional[str] = None
    role: Optional[str] = None


class CertificationOut(BaseModel):
    certification_id: int
    name: str
    issuer: Optional[str] = None
    issue_date: Optional[date] = None
    expiry_date: Optional[date] = None
    credential_url: Optional[str] = None


class UserSkillEvidenceOut(BaseModel):
    """Legacy audit row. This is NOT accepted evidence under the B2 policy."""
    evidence_id: int
    evidence_type: str
    source_table: Optional[str] = None
    source_id: Optional[int] = None
    description: Optional[str] = None
    url: Optional[str] = None


class AcceptedEvidenceOut(BaseModel):
    """Accepted evidence provenance (Stage 3.4.1).

    Only rows from ``user_accepted_evidence`` are represented here. Raw CV
    spans are intentionally absent: they are temporary and removed after the
    acceptance lifecycle.
    """
    accepted_evidence_id: int
    cv_id: str
    skill_id: str
    canonical_name: Optional[str] = None
    candidate_id: Optional[int] = None
    source_type: str
    source_table: str
    source_id: Optional[int] = None
    claimed_skill: Optional[str] = None
    accepted_at: datetime


class UserSkillOut(BaseModel):
    """
    Note evidence_status is NEVER 'missing' for a claimed skill with zero
    evidence -- it is 'none'. Absence of evidence is not equivalent to
    absence of the skill (Section 4).

    Stage 3.4.1: ``evidence_status`` in profile reads is the EFFECTIVE
    status derived from accepted evidence only. A legacy ``user_skills.
    evidence_status = 'linked'`` row does not, by itself, produce 'linked'.
    """
    user_skill_id: int
    claimed_skill: str
    skill_id: Optional[str] = None          # NULL until normalized against KB
    normalized_skill: Optional[str] = None
    proficiency: Optional[str] = None
    evidence_status: str                     # effective: 'none' | 'linked'
    confidence: str
    evidence: list[UserSkillEvidenceOut] = []
    evidence_source: str = "claim"           # 'claim' | 'claim_and_evidence'
    accepted_evidence: list[AcceptedEvidenceOut] = []


class EffectiveSkillOut(BaseModel):
    """One skill in the user's effective skill profile.

    A skill may come from an explicit claim, accepted evidence, or both. An
    evidence-only entry has ``user_skill_id=None`` and ``claimed_skill=None``
    so no fabricated user claim is created (D-04/D-17).
    """
    skill_id: str
    normalized_skill: Optional[str] = None
    claimed_skill: Optional[str] = None
    proficiency: Optional[str] = None
    user_skill_id: Optional[int] = None
    evidence_status: str                     # 'linked' only with accepted evidence
    source: str                              # 'claim' | 'evidence' | 'claim_and_evidence'
    accepted_evidence: list[AcceptedEvidenceOut] = []


class EvidenceCandidateOut(BaseModel):
    """Privacy-minimal decision trace for a temporary evidence candidate."""
    candidate_id: int
    skill_id: Optional[str] = None
    source_type: str
    source_table: str
    source_id: Optional[int] = None
    structural_status: str
    semantic_status: str
    acceptance_status: str
    decision_reason: Optional[str] = None


class UserPreferencesOut(BaseModel):
    preferred_domains: Optional[str] = None
    weekly_learning_hours: Optional[int] = None
    preferred_learning_format: Optional[str] = None
    career_goal_notes: Optional[str] = None


class UserFullProfileOut(BaseModel):
    """Everything the Profile Agent needs in one call."""
    user: UserOut
    profile: Optional[UserProfileOut] = None
    education: list[EducationOut] = []
    experience: list[ExperienceOut] = []
    projects: list[ProjectOut] = []
    certifications: list[CertificationOut] = []
    skills: list[UserSkillOut] = []
    # Canonical, de-duplicated view used by career-fit/skill-gap. Includes
    # evidence-derived skills that have no explicit claim row.
    effective_skills: list[EffectiveSkillOut] = []
    evidence_candidates: list[EvidenceCandidateOut] = []
    preferences: Optional[UserPreferencesOut] = None


# ---- Write-side (input) schemas ----

class UserCreateIn(BaseModel):
    email: str
    full_name: str


class UserSkillCreateIn(BaseModel):
    claimed_skill: str
    proficiency: Optional[str] = None
    skill_id: Optional[str] = None       # may be pre-normalized by caller, else left NULL


class UserSkillEvidenceCreateIn(BaseModel):
    evidence_type: str
    source_table: Optional[str] = None
    source_id: Optional[int] = None
    description: Optional[str] = None
    url: Optional[str] = None
