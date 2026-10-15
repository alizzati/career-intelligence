from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.routes import analysis, health


def create_app() -> FastAPI:
    app = FastAPI(title="Career Intelligence API", version="0.1.0")
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(analysis.router)
    return app


app = create_app()