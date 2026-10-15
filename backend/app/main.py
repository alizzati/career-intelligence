import logging

from fastapi import FastAPI

from app.api.boundary import (
    BodySizeLimitMiddleware, LocalDevelopmentBoundaryMiddleware, request_limit_for,
)
from app.api.errors import install_error_handlers
from app.api.routes import analysis, health

logger = logging.getLogger(__name__)

DESCRIPTION = (
    "DEVELOPMENT PROTOTYPE - NOT production-ready. There is no authentication, authorization, "
    "user-ownership check, or rate limiting: any permitted caller can analyze or write to any "
    "user_id. Analysis endpoints are served only when CAREER_API_ACKNOWLEDGE_NO_AUTH=true and, by "
    "default, only to loopback clients. Run behind 127.0.0.1 only."
)


def create_app() -> FastAPI:
    app = FastAPI(title="Career Intelligence API (development prototype)",
                  version="0.1.0", description=DESCRIPTION)
    install_error_handlers(app)
    # Last added = outermost: the access boundary rejects before any body byte is counted/read.
    app.add_middleware(BodySizeLimitMiddleware, limit_for=request_limit_for)
    app.add_middleware(LocalDevelopmentBoundaryMiddleware)
    app.include_router(health.router)
    app.include_router(analysis.router)
    logger.warning("Career Intelligence API is a development prototype without authentication.")
    return app


app = create_app()