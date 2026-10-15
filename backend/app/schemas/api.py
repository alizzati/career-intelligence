"""API request/response models. Reuses existing agent schemas unchanged."""
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.career_fit import CareerRecommendationOut
from app.schemas.learning_roadmap import LearningRoadmapOut
from app.schemas.skill_gap_agent import SkillGapAnalysisOut
from app.schemas.verification import VerificationResult


class ErrorBody(BaseModel):
    code: str
    message: str
    stage: str | None = None
    error_type: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ok"]


CareerId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class ExistingProfileRequest(BaseModel):
    user_id: int = Field(gt=0)
    target_career_id: CareerId | None = None


class DocumentInfo(BaseModel):
    """Safe metadata only: no filename, no content."""
    format: str
    size_bytes: int
    page_count: int | None = None
    character_count: int


class RedactionInfo(BaseModel):
    detected_types: list[str]
    replacement_count: int


class ProfileExtractionSummary(BaseModel):
    skills_persisted: int
    evidence_persisted: int


class AnalysisResponse(BaseModel):
    user_id: int
    source: Literal["cv_upload", "existing_profile"]
    final_status: Literal["VERIFIED", "VERIFICATION_FAILED", "REVISION_LIMIT_REACHED"]
    verified: bool
    revision_count: int
    target_career_id: str | None = None
    document: DocumentInfo | None = None
    redaction: RedactionInfo | None = None
    profile_extraction: ProfileExtractionSummary | None = None
    recommendations: list[CareerRecommendationOut] = []
    skill_gap: SkillGapAnalysisOut | None = None
    roadmap: LearningRoadmapOut | None = None
    verification: VerificationResult | None = None