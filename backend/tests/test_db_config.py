"""Step 14.1: DB settings come only from the environment; no secrets in source."""
import re
from pathlib import Path

import pytest

from app.core import db

BACKEND = Path(__file__).resolve().parents[1]
DB_ENV = ("CAREER_DB_URL", "CAREER_DB_HOST", "CAREER_DB_PORT", "CAREER_DB_NAME",
          "CAREER_DB_USER", "CAREER_DB_PASSWORD")
SENTINEL = "pw-for-test-only@:/#"          # synthetic, special characters on purpose


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in DB_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(db, "_load_env_file", lambda: None)      # ignore a developer's real .env
    monkeypatch.setattr(db, "_engine", None)


def test_missing_configuration_fails_with_actionable_error():
    with pytest.raises(db.DatabaseConfigurationError, match="CAREER_DB_PASSWORD"):
        db.build_database_url()
    with pytest.raises(db.DatabaseConfigurationError, match="CAREER_DB_PASSWORD"):
        db.get_engine()


def test_importing_and_repr_of_engine_proxy_need_no_configuration():
    assert repr(db.engine) == "<LazyEngine>" and db._engine is None


def test_url_is_built_from_parts_and_password_is_not_exposed(monkeypatch):
    monkeypatch.setenv("CAREER_DB_PASSWORD", SENTINEL)
    monkeypatch.setenv("CAREER_DB_HOST", "dbhost")
    url = db.build_database_url()
    assert url.password == SENTINEL                      # special characters round-trip
    assert (url.host, url.port, url.database, url.username) == ("dbhost", 5433, "career_intelligence", "postgres")
    assert SENTINEL not in repr(url)


def test_full_url_override_is_returned_unchanged(monkeypatch):
    monkeypatch.setenv("CAREER_DB_URL", "postgresql+psycopg2://u:p@h:1/d")
    assert db.build_database_url() == "postgresql+psycopg2://u:p@h:1/d"


def test_invalid_port_error_does_not_leak_the_password(monkeypatch):
    monkeypatch.setenv("CAREER_DB_PASSWORD", SENTINEL)
    monkeypatch.setenv("CAREER_DB_PORT", "abc")
    with pytest.raises(db.DatabaseConfigurationError) as exc_info:
        db.build_database_url()
    assert SENTINEL not in str(exc_info.value)


def test_engine_is_created_lazily_once(monkeypatch):
    monkeypatch.setenv("CAREER_DB_PASSWORD", SENTINEL)
    first = db.get_engine()
    assert db.get_engine() is first and SENTINEL not in repr(first.url)


def test_no_credential_bearing_connection_url_in_application_sources():
    pattern = re.compile(r"://[^:/\s\"']+:[^@\s\"']+@")
    offenders = []
    for folder in ("app", "scripts"):
        for path in (BACKEND / folder).rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(str(path.relative_to(BACKEND)))
    assert offenders == [], f"credential-bearing URL literal found in: {offenders}"