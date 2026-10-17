"""Unit tests for POST /analysis/users. DB mocked; no LLM."""
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.main import create_app


@pytest.fixture(autouse=True)
def local_dev_access(monkeypatch):
    monkeypatch.setenv("CAREER_API_ACKNOWLEDGE_NO_AUTH", "true")
    monkeypatch.setenv("CAREER_API_ALLOW_REMOTE_CLIENTS", "true")


def post(body):
    return TestClient(create_app()).post("/analysis/users", json=body)


def test_creates_user_and_returns_only_user_id():
    with mock.patch("app.api.routes.users.us.create_user", return_value=SimpleNamespace(user_id=42)) as m:
        r = post({"email": "a@example.test", "full_name": "A B"})
    assert r.status_code == 201 and r.json() == {"user_id": 42}
    m.assert_called_once_with("a@example.test", "A B")


def test_invalid_body_is_422_without_echo():
    r = post({"email": "not-an-email", "full_name": "x"})
    assert r.status_code == 422 and "not-an-email" not in r.text


def test_duplicate_email_is_409():
    err = IntegrityError("stmt", {}, Exception("dup"))
    with mock.patch("app.api.routes.users.us.create_user", side_effect=err):
        r = post({"email": "a@example.test", "full_name": "A"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "user_exists"


def test_access_boundary_still_applies(monkeypatch):
    monkeypatch.setenv("CAREER_API_ACKNOWLEDGE_NO_AUTH", "false")
    assert post({"email": "a@example.test", "full_name": "A"}).status_code == 503
