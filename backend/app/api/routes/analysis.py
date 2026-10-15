"""Step 14 endpoints.

CV order: bounded read -> CVTextExtractor -> redact_pii -> CareerWorkflow
(Profile Agent receives only redacted text). No auth is implemented."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_workflow
from app.api.errors import ApiError
from app.api.responses import finish
from app.api.uploads import read_upload_bounded
from app.core.config import ApiSettings, get_settings
from app.schemas.api import AnalysisResponse, ErrorResponse, ExistingProfileRequest
from app.services import retrieval_service as rs
from app.services import user_service as us
from app.services.cv_text_extraction_service import CVTextExtractionError, CVTextExtractor
from app.services.pii_redaction_service import redact_pii

from app.core.db import DatabaseConfigurationError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/analysis", tags=["analysis"])

_ERRORS = {code: {"model": ErrorResponse} for code in (400, 404, 413, 415, 422, 500, 503)}
_EXTRACTION_STATUS = {
    "unsupported_format": 415,
    "file_too_large": 413,
    "page_limit_exceeded": 413,
    "document_expansion_limit_exceeded": 413,
}


def _precheck(user_id: int, target_career_id: str | None) -> str | None:
    """Existing user + canonical career only. Nothing is created."""
    if us.get_user_full_profile(user_id) is None:
        raise ApiError(404, "user_not_found", "The requested user does not exist.")
    target = (target_career_id or "").strip() or None
    if target is not None and rs.get_career(target) is None:
        raise ApiError(404, "career_not_found", "The requested career is not in the knowledge base.")
    return target


def _internal_error(exc: Exception) -> ApiError:
    if isinstance(exc, DatabaseConfigurationError):
        logger.error("Database is not configured.")
        return ApiError(503, "database_not_configured", "The service database is not configured.")
    logger.error("Analysis request failed (%s).", type(exc).__name__)  # type only
    return ApiError(500, "internal_error", "An internal error occurred.")


@router.post("/cv", response_model=AnalysisResponse, responses=_ERRORS)
async def analyze_cv(
    user_id: Annotated[int, Form(gt=0)],
    file: Annotated[UploadFile, File()],
    target_career_id: Annotated[str | None, Form(max_length=64)] = None,
    settings: ApiSettings = Depends(get_settings),
    workflow=Depends(get_workflow),
) -> AnalysisResponse:
    content = b""
    try:
        target = await run_in_threadpool(_precheck, user_id, target_career_id)
        if workflow.profile_agent is None:
            raise ApiError(503, "llm_unavailable", "CV analysis is unavailable: no LLM client is configured.")

        content = await read_upload_bounded(file, settings.max_upload_bytes, settings.upload_chunk_bytes)
        extractor = CVTextExtractor(
            max_file_size_bytes=settings.max_upload_bytes, max_pdf_pages=settings.max_pdf_pages,
        )
        try:
            extraction = await run_in_threadpool(extractor.extract, content, file.filename or "")
        except CVTextExtractionError as exc:
            # Messages are sanitized by the service (no content, no filename).
            raise ApiError(_EXTRACTION_STATUS.get(exc.code, 422), exc.code, str(exc)) from None
        finally:
            content = b""

        redaction = redact_pii(extraction.extracted_text)
        metadata = extraction.metadata
        extraction = None  # drop the raw text reference

        state = await run_in_threadpool(
            lambda: workflow.run(
                user_id=user_id, target_career_id=target,
                raw_profile_text=redaction.redacted_text,
            )
        )
        return finish(state, user_id=user_id, source="cv_upload",
                      document=metadata, redaction=redaction)
    except ApiError:
        raise
    except Exception as exc:
        raise _internal_error(exc) from None
    finally:
        content = b""
        await file.close()


@router.post("/profile", response_model=AnalysisResponse, responses=_ERRORS)
def analyze_existing_profile(
    body: ExistingProfileRequest,
    workflow=Depends(get_workflow),
) -> AnalysisResponse:
    """Runs the workflow over an already-persisted profile; no profile parsing."""
    try:
        target = _precheck(body.user_id, body.target_career_id)
        state = workflow.run(user_id=body.user_id, target_career_id=target)
        return finish(state, user_id=body.user_id, source="existing_profile")
    except ApiError:
        raise
    except Exception as exc:
        raise _internal_error(exc) from None