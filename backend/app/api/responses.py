"""Builds API-safe responses from workflow state. Never returns profile_result,
redacted/raw text, or raw exception messages."""
from app.agents.profile_agent import ProfileAgentResult
from app.agents.llm_errors import LLMInvalidResponseError, LLMQuotaExceededError
from app.api.errors import ApiError
from app.schemas.api import (
    AnalysisResponse, DocumentInfo, ProfileExtractionSummary, RedactionInfo,
)
from app.services.profile_privacy_service import (
    redact_recommendations, redact_roadmap, redact_skill_gap_analysis,
    redact_verification,
)

LLM_ERROR_OMITTED = "An LLM step failed or its output was rejected; details omitted."


def _omit_llm_error(model):
    if model is not None and getattr(model, "llm_error", None):
        return model.model_copy(update={"llm_error": LLM_ERROR_OMITTED})
    return model


def build_analysis_response(state, *, user_id, source, document=None, redaction=None):
    profile_result = state.get("profile_result")
    summary = None
    if source == "cv_upload" and (
        isinstance(profile_result, ProfileAgentResult)
        or hasattr(profile_result, "skills_persisted")
    ):
        summary = ProfileExtractionSummary(
            skills_persisted=int(profile_result.skills_persisted),
            evidence_persisted=int(profile_result.evidence_persisted),
        )
    status = state["final_status"]
    return AnalysisResponse(
        user_id=user_id, source=source, final_status=status,
        verified=status == "VERIFIED",
        revision_count=state["revision_count"],
        target_career_id=state.get("target_career_id"),
        document=DocumentInfo(
            format=document.format, size_bytes=document.size_bytes,
            page_count=document.page_count, character_count=document.character_count,
        ) if document else None,
        redaction=RedactionInfo(
            detected_types=list(redaction.detected_types),
            replacement_count=redaction.replacement_count,
        ) if redaction else None,
        profile_extraction=summary,
        recommendations=redact_recommendations(state.get("recommendations") or []),
        skill_gap=(
            _omit_llm_error(redact_skill_gap_analysis(state["skill_gap"]))
            if state.get("skill_gap") is not None else None
        ),
        roadmap=(
            _omit_llm_error(redact_roadmap(state["roadmap"]))
            if state.get("roadmap") is not None else None
        ),
        verification=(
            _omit_llm_error(redact_verification(state["verification"]))
            if state.get("verification") is not None else None
        ),
    )


def finish(state, **kwargs):
    if state["final_status"] == "ERROR":
        err = (state.get("errors") or [{}])[0]
        stage = err.get("stage") or "workflow"
        if stage == "input_validation":
            raise ApiError(400, "invalid_request", "The request parameters were rejected.", stage=stage)
        if err.get("error_type") == LLMQuotaExceededError.__name__:
            raise ApiError(
                503,
                "llm_quota_exceeded",
                "AI analysis is temporarily unavailable because the model quota has been reached. Please try again later.",
                stage=stage,
            )
        if err.get("error_type") == LLMInvalidResponseError.__name__:
            raise ApiError(
                502,
                "llm_invalid_response",
                "AI analysis could not process the model response. Please try again later.",
                stage=stage,
            )
        raise ApiError(500, "workflow_error",
                       f"The analysis could not be completed (stage: {stage}).",
                       stage=stage, error_type=err.get("error_type"))
    return build_analysis_response(state, **kwargs)