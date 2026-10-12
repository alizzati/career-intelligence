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
    evidence_id: int
    evidence_type: str
    source_table: Optional[str] = None
    source_id: Optional[int] = None
    description: Optional[str] = None
    url: Optional[str] = None


class UserSkillOut(BaseModel):
    """
    Note evidence_status is NEVER 'missing' for a claimed skill with zero
    evidence -- it is 'none'. Absence of evidence is not equivalent to
    absence of the skill (Section 4).
    """
    user_skill_id: int
    claimed_skill: str
    skill_id: Optional[str] = None          # NULL until normalized against KB
    normalized_skill: Optional[str] = None
    proficiency: Optional[str] = None
    evidence_status: str                     # 'none' | 'linked'
    confidence: str
    evidence: list[UserSkillEvidenceOut] = []


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