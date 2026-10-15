"""Safe, structured API errors. Never carries raw exception text."""
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.api import ErrorBody, ErrorResponse


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, *,
                 stage: str | None = None, error_type: str | None = None):
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.stage = stage
        self.error_type = error_type


def _response(status_code: int, body: ErrorBody) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=body).model_dump(exclude_none=True),
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _response(exc.status_code, ErrorBody(
            code=exc.code, message=exc.message, stage=exc.stage, error_type=exc.error_type,
        ))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Default FastAPI detail echoes submitted input; deliberately omitted.
        return _response(422, ErrorBody(
            code="invalid_request",
            message="The request is malformed or missing required fields.",
        ))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        try:
            phrase = HTTPStatus(exc.status_code).phrase
        except ValueError:
            phrase = "Error"
        return _response(exc.status_code, ErrorBody(code="http_error", message=phrase))