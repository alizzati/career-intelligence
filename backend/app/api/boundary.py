"""Pure-ASGI request-boundary middlewares.

Raw ASGI (not BaseHTTPMiddleware) so the body is counted and refused WHILE it is
received, before Starlette/FastAPI parse or spool it."""
import ipaddress
import logging
from collections.abc import Callable
from typing import Any

from app.core.config import AccessSettings, ApiSettings, get_access_settings, get_settings
from app.schemas.api import ErrorBody, ErrorResponse

logger = logging.getLogger(__name__)
Scope = dict[str, Any]

TOO_LARGE = (413, "request_too_large", "The request body exceeds the allowed size.")
NO_AUTH_NOT_ACKNOWLEDGED = (
    503, "auth_not_configured",
    "This prototype has no authentication. Set CAREER_API_ACKNOWLEDGE_NO_AUTH=true to run it "
    "for local development only.",
)
REMOTE_REFUSED = (403, "remote_access_disabled", "Only local clients are allowed in development mode.")


def _error_messages(status: int, code: str, message: str) -> list[dict]:
    body = ErrorResponse(error=ErrorBody(code=code, message=message)).model_dump_json(
        exclude_none=True).encode()
    headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode()),
        (b"connection", b"close"),          # unread request body: do not reuse the connection
    ]
    return [{"type": "http.response.start", "status": status, "headers": headers},
            {"type": "http.response.body", "body": body}]


async def _send_error(send, error: tuple[int, str, str]) -> None:
    for message in _error_messages(*error):
        await send(message)


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name.lower() == b"content-length":
            try:
                length = int(value)
            except ValueError:
                return None
            return length if length >= 0 else None
    return None


def resolve_api_settings(scope: Scope) -> ApiSettings:
    """Honors FastAPI dependency overrides so tests/config use one source of truth."""
    overrides = getattr(scope.get("app"), "dependency_overrides", None) or {}
    return overrides.get(get_settings, get_settings)()


def request_limit_for(scope: Scope) -> int | None:
    settings = resolve_api_settings(scope)
    if scope.get("path", "").rstrip("/") == "/analysis/cv":
        return settings.max_request_bytes
    return settings.max_json_body_bytes


class _BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    """Counts actual body bytes (Content-Length is only an early hint, never trusted)."""

    def __init__(self, app, limit_for: Callable[[Scope], int | None]):
        self.app = app
        self.limit_for = limit_for

    async def __call__(self, scope, receive, send):
        limit = self.limit_for(scope) if scope["type"] == "http" else None
        if limit is None:
            await self.app(scope, receive, send)
            return

        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await _send_error(send, TOO_LARGE)          # rejected without reading the body
            return

        received = 0
        exceeded = False
        started = False          # downstream response already begun (within limits)
        replaced = False

        async def limited_receive():
            nonlocal received, exceeded
            if exceeded:
                raise _BodyTooLarge()
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _BodyTooLarge()
            return message

        async def guarded_send(message):
            nonlocal started, replaced
            if not exceeded:
                if message["type"] == "http.response.start":
                    started = True
                await send(message)
                return
            # Frameworks may convert our exception into their own 400/500: replace it.
            if not replaced and not started:
                replaced = True
                await _send_error(send, TOO_LARGE)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLarge:
            pass
        if exceeded and not replaced and not started:
            await _send_error(send, TOO_LARGE)


def _is_loopback(client) -> bool:
    if not client or not isinstance(client[0], str):
        return False
    host = client[0]
    if host.lower() == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (getattr(address, "ipv4_mapped", None) or address).is_loopback


class LocalDevelopmentBoundaryMiddleware:
    """Minimal fail-closed guard for /analysis/*. It is NOT authentication: it does not
    identify callers, separate users, or stop other local processes."""

    def __init__(self, app, access_settings: Callable[[], AccessSettings] = get_access_settings,
                 protected_prefix: str = "/analysis"):
        self.app = app
        self.access_settings = access_settings
        self.prefix = protected_prefix

    def _protected(self, scope: Scope) -> bool:
        path = scope.get("path", "")
        return path == self.prefix or path.startswith(self.prefix + "/")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self._protected(scope):
            await self.app(scope, receive, send)
            return
        access = self.access_settings()
        if not access.acknowledge_no_auth:
            await _send_error(send, NO_AUTH_NOT_ACKNOWLEDGED)
            return
        if not access.allow_remote_clients and not _is_loopback(scope.get("client")):
            await _send_error(send, REMOTE_REFUSED)
            return
        await self.app(scope, receive, send)