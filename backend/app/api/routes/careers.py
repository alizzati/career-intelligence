"""GET /careers: list available careers for dropdown."""
import logging

from fastapi import APIRouter

from app.api.errors import ApiError
from app.api.routes.analysis import _internal_error
from app.core.db import DatabaseConfigurationError
from app.services import retrieval_service as rs

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/careers", tags=["careers"])


class CareerItem:
    pass


@router.get("")
def list_careers():
    try:
        careers = rs.list_all_careers()
    except DatabaseConfigurationError:
        logger.error("Database is not configured.")
        raise ApiError(503, "database_not_configured", "The service database is not configured.")
    except Exception as exc:
        raise _internal_error(exc)
    return [{"career_id": c["career_id"], "canonical_name": c["canonical_name"], "domain": c.get("domain")} for c in careers]
