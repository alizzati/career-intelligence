"""Step 14.1: request-size and local-development boundary. No DB, no LLM."""
import asyncio
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from app.api.boundary import BodySizeLimitMiddleware, LocalDevelopmentBoundaryMiddleware
from app.api.dependencies import get_workflow
from app.core.config import AccessSettings, ApiSettings, get_settings
from app.main import create_app


async def echo_app(scope, receive, send):
    total = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            break
        total += len(message.get("body", b""))
        if not message.get("more_body"):
            break
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": str(total).encode()})


async def converting_app(scope, receive, send):
    """Mimics FastAPI turning a body-read error into its own 400 response."""
    try:
        while True:
            message = await receive()
            if not message.get("more_body"):
                break
    except Exception:
        await send({"type": "http.response.start", "status": 400, "headers": []})
        await send({"type": "http.response.body", "body": b"bad"})
        return
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def run_asgi(app, chunks, *, headers=(), path="/analysis/cv", client=("127.0.0.1", 50000), scope_type="http"):
    pending, pulled, sent = list(chunks), [], []

    async def receive():
        if pending:
            chunk = pending.pop(0)
            pulled.append(len(chunk))
            return {"type": "http.request", "body": chunk, "more_body": bool(pending)}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {"type": scope_type, "method": "POST", "path": path, "headers": list(headers), "client": client}
    asyncio.run(app(scope, receive, send))
    return sent, pulled


def starts(sent):
    return [m for m in sent if m["type"] == "http.response.start"]


def body(sent):
    return b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")


def sized(limit):
    return BodySizeLimitMiddleware(echo_app, limit_for=lambda scope: limit)


# ---------------- BodySizeLimitMiddleware (raw ASGI; authoritative) ----------------
def test_body_exactly_at_limit_passes():
    sent, _ = run_asgi(sized(10), [b"abcde", b"fghij"])
    assert starts(sent)[0]["status"] == 200 and body(sent) == b"10"


def test_one_byte_over_limit_is_rejected():
    sent, _ = run_asgi(sized(10), [b"abcde", b"fghijk"])
    assert [s["status"] for s in starts(sent)] == [413]
    assert json.loads(body(sent))["error"]["code"] == "request_too_large"


def test_chunked_body_without_content_length_stops_being_read():
    sent, pulled = run_asgi(sized(10), [b"abcd"] * 100)          # no Content-Length header
    assert [s["status"] for s in starts(sent)] == [413]
    assert pulled == [4, 4, 4]                                   # stopped right after exceeding 10


def test_declared_oversized_length_is_rejected_without_reading_the_body():
    sent, pulled = run_asgi(sized(10), [b"x"], headers=[(b"content-length", b"999")])
    assert [s["status"] for s in starts(sent)] == [413] and pulled == []
    assert (b"connection", b"close") in starts(sent)[0]["headers"]


def test_lying_small_content_length_does_not_bypass_the_limit():
    sent, pulled = run_asgi(sized(10), [b"abcd"] * 100, headers=[(b"content-length", b"5")])
    assert [s["status"] for s in starts(sent)] == [413] and len(pulled) == 3


def test_framework_converted_error_is_replaced_by_a_single_413():
    middleware = BodySizeLimitMiddleware(converting_app, limit_for=lambda scope: 10)
    sent, _ = run_asgi(middleware, [b"abcd"] * 10)
    assert [s["status"] for s in starts(sent)] == [413]
    assert b"bad" not in body(sent)


def test_non_http_scopes_and_unlimited_paths_pass_through():
    calls = []

    async def inner(scope, receive, send):
        calls.append(scope["type"])

    asyncio.run(BodySizeLimitMiddleware(inner, limit_for=lambda s: 1)({"type": "lifespan"}, None, None))
    asyncio.run(BodySizeLimitMiddleware(inner, limit_for=lambda s: None)({"type": "http"}, None, None))
    assert calls == ["lifespan", "http"]


# ---------------- LocalDevelopmentBoundaryMiddleware ----------------
def guarded(**flags):
    return LocalDevelopmentBoundaryMiddleware(echo_app, access_settings=lambda: AccessSettings(**flags))


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost"])
def test_loopback_clients_are_allowed(host):
    sent, _ = run_asgi(guarded(acknowledge_no_auth=True), [b"x"], client=(host, 5000))
    assert starts(sent)[0]["status"] == 200


@pytest.mark.parametrize("client", [("203.0.113.7", 5000), ("testclient", 5000), None])
def test_remote_or_unknown_clients_are_refused_before_reading_the_body(client):
    sent, pulled = run_asgi(guarded(acknowledge_no_auth=True), [b"x"], client=client)
    assert starts(sent)[0]["status"] == 403 and pulled == []
    assert json.loads(body(sent))["error"]["code"] == "remote_access_disabled"


def test_remote_clients_can_be_allowed_explicitly():
    sent, _ = run_asgi(guarded(acknowledge_no_auth=True, allow_remote_clients=True), [b"x"],
                       client=("203.0.113.7", 5000))
    assert starts(sent)[0]["status"] == 200


def test_unacknowledged_prototype_refuses_even_loopback():
    sent, pulled = run_asgi(guarded(), [b"x"], path="/analysis/profile")
    assert starts(sent)[0]["status"] == 503 and pulled == []
    assert json.loads(body(sent))["error"]["code"] == "auth_not_configured"


def test_health_and_unrelated_prefixes_are_not_protected():
    for path in ("/health", "/analysis-other"):
        sent, _ = run_asgi(guarded(), [b"x"], path=path, client=("203.0.113.7", 1))
        assert starts(sent)[0]["status"] == 200


# ---------------- through the real app ----------------
@pytest.fixture
def dev_env(monkeypatch):
    monkeypatch.setenv("CAREER_API_ACKNOWLEDGE_NO_AUTH", "true")
    monkeypatch.setenv("CAREER_API_ALLOW_REMOTE_CLIENTS", "true")   # TestClient host is "testclient"


def small_limits_app():
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: ApiSettings(
        max_upload_bytes=10, max_request_overhead_bytes=100, max_json_body_bytes=50)
    app.dependency_overrides[get_workflow] = lambda: pytest.fail("workflow must not be resolved")
    return app


def test_oversized_multipart_is_rejected_before_routing(dev_env):
    with mock.patch("app.api.routes.analysis.us.get_user_full_profile") as users:
        response = TestClient(small_limits_app()).post(
            "/analysis/cv", data={"user_id": "17"},
            files={"file": ("cv.txt", b"x" * 5000, "text/plain")})
    assert response.status_code == 413 and response.json()["error"]["code"] == "request_too_large"
    users.assert_not_called()


def test_oversized_json_body_is_rejected(dev_env):
    response = TestClient(small_limits_app()).post(
        "/analysis/profile", headers={"content-type": "application/json"},
        content=b'{"user_id": 17, "pad": "' + b"x" * 5000 + b'"}')
    assert response.status_code == 413


def test_declared_length_smaller_than_actual_body_is_still_rejected(dev_env):
    response = TestClient(small_limits_app()).post(
        "/analysis/cv", content=b"x" * 5000,
        headers={"content-type": "multipart/form-data; boundary=zz", "content-length": "10"})
    assert response.status_code == 413


def test_streamed_body_without_content_length_is_rejected(dev_env):
    # Best effort: depends on how the installed Starlette TestClient feeds a generator body.
    response = TestClient(small_limits_app()).post(
        "/analysis/cv", content=(b"x" * 500 for _ in range(20)),
        headers={"content-type": "multipart/form-data; boundary=zz"})
    assert response.status_code == 413


def test_analysis_is_refused_until_no_auth_is_acknowledged(monkeypatch):
    monkeypatch.setenv("CAREER_API_ACKNOWLEDGE_NO_AUTH", "false")
    monkeypatch.setenv("CAREER_API_ALLOW_REMOTE_CLIENTS", "true")
    client = TestClient(create_app())
    response = client.post("/analysis/profile", json={"user_id": 17})
    assert response.status_code == 503 and response.json()["error"]["code"] == "auth_not_configured"
    assert client.get("/health").status_code == 200


def test_non_loopback_client_is_refused_by_default(monkeypatch):
    monkeypatch.setenv("CAREER_API_ACKNOWLEDGE_NO_AUTH", "true")
    monkeypatch.setenv("CAREER_API_ALLOW_REMOTE_CLIENTS", "false")
    response = TestClient(create_app()).post("/analysis/profile", json={"user_id": 17})
    assert response.status_code == 403


def test_app_does_not_claim_production_readiness():
    description = create_app().description.lower()
    assert "development prototype" in description and "not production-ready" in description