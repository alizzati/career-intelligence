"""Centralized, env-overridable API settings. Contains no secrets."""
import os
from dataclasses import dataclass

from app.services.cv_text_extraction_service import (
    DEFAULT_MAX_FILE_SIZE_BYTES,
    DEFAULT_MAX_PDF_PAGES,
)


def _int_env(name: str, default: int, *, minimum: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True)
class ApiSettings:
    max_upload_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES
    max_pdf_pages: int = DEFAULT_MAX_PDF_PAGES
    upload_chunk_bytes: int = 64 * 1024
    max_revisions: int = 2

    @classmethod
    def from_env(cls) -> "ApiSettings":
        return cls(
            max_upload_bytes=_int_env("CAREER_API_MAX_UPLOAD_BYTES", DEFAULT_MAX_FILE_SIZE_BYTES, minimum=1),
            max_pdf_pages=_int_env("CAREER_API_MAX_PDF_PAGES", DEFAULT_MAX_PDF_PAGES, minimum=1),
            upload_chunk_bytes=_int_env("CAREER_API_UPLOAD_CHUNK_BYTES", 64 * 1024, minimum=1),
            max_revisions=_int_env("CAREER_API_MAX_REVISIONS", 2, minimum=0),
        )


def get_settings() -> ApiSettings:
    return ApiSettings.from_env()