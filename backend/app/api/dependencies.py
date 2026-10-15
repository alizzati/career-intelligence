import logging

from fastapi import Depends

from app.core.config import get_settings
from app.workflows.career_workflow import CareerWorkflow

logger = logging.getLogger(__name__)


def get_llm_client():
    """Reuses the existing GeminiClient; returns None if it cannot be constructed.
    Logs only the exception type."""
    try:
        from app.agents.llm_client import GeminiClient
        return GeminiClient()
    except Exception as exc:
        logger.warning("LLM client unavailable (%s).", type(exc).__name__)
        return None


def get_workflow(settings=Depends(get_settings), llm_client=Depends(get_llm_client)) -> CareerWorkflow:
    return CareerWorkflow(llm_client=llm_client, max_revisions=settings.max_revisions)