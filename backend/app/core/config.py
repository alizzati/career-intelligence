"""Centralized, env-overridable API settings. Contains no secrets."""
import os
from dataclasses import dataclass

from app.services.cv_text_extraction_service import (
    DEFAULT_MAX_FILE_SIZE_BYTES,
    DEFAULT_MAX_PDF_PAGES,
)

DEFAULT_MAX_REQUEST_OVERHEAD_BYTES = 64 * 1024   # multipart boundaries + form fields
DEFAULT_MAX_JSON_BODY_BYTES = 16 * 1024
_TRUE = frozenset({"1", "true", "yes", "on"})


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


def _bool_env(name: str) -> bool:
    """Fail-closed: anything other than an explicit true-ish value is False."""
    return os.environ.get(name, "").strip().lower() in _TRUE


@dataclass(frozen=True)
class ApiSettings:
    max_upload_bytes: int = DEFAULT_MAX_FILE_SIZE_BYTES
    max_pdf_pages: int = DEFAULT_MAX_PDF_PAGES
    upload_chunk_bytes: int = 64 * 1024
    max_revisions: int = 2
    max_request_overhead_bytes: int = DEFAULT_MAX_REQUEST_OVERHEAD_BYTES
    max_json_body_bytes: int = DEFAULT_MAX_JSON_BODY_BYTES

    @property
    def max_request_bytes(self) -> int:
        """Total body limit for POST /analysis/cv (file limit + multipart overhead)."""
        return self.max_upload_bytes + self.max_request_overhead_bytes

    @classmethod
    def from_env(cls) -> "ApiSettings":
        return cls(
            max_upload_bytes=_int_env("CAREER_API_MAX_UPLOAD_BYTES", DEFAULT_MAX_FILE_SIZE_BYTES, minimum=1),
            max_pdf_pages=_int_env("CAREER_API_MAX_PDF_PAGES", DEFAULT_MAX_PDF_PAGES, minimum=1),
            upload_chunk_bytes=_int_env("CAREER_API_UPLOAD_CHUNK_BYTES", 64 * 1024, minimum=1),
            max_revisions=_int_env("CAREER_API_MAX_REVISIONS", 2, minimum=0),
            max_request_overhead_bytes=_int_env(
                "CAREER_API_MAX_REQUEST_OVERHEAD_BYTES", DEFAULT_MAX_REQUEST_OVERHEAD_BYTES, minimum=0),
            max_json_body_bytes=_int_env("CAREER_API_MAX_JSON_BODY_BYTES", DEFAULT_MAX_JSON_BODY_BYTES, minimum=1),
        )


@dataclass(frozen=True)
class AccessSettings:
    """Development-only access boundary. This is NOT authentication."""
    acknowledge_no_auth: bool = False
    allow_remote_clients: bool = False

    @classmethod
    def from_env(cls) -> "AccessSettings":
        return cls(
            acknowledge_no_auth=_bool_env("CAREER_API_ACKNOWLEDGE_NO_AUTH"),
            allow_remote_clients=_bool_env("CAREER_API_ALLOW_REMOTE_CLIENTS"),
        )


def get_settings() -> ApiSettings:
    return ApiSettings.from_env()


def get_access_settings() -> AccessSettings:
    return AccessSettings.from_env()