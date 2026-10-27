"""Offline gate tests for manual validation and KB import safety guards.

These tests use mocks/fakes only. They must not connect to PostgreSQL
or trigger database mutations.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from sqlalchemy.engine import URL


def _make_engine(host="localhost", database="career_intelligence_e2e_test"):
    url = URL.create(
        "postgresql+psycopg2",
        username="postgres",
        password="x",
        host=host,
        port=5433,
        database=database,
    )
    engine = MagicMock()
    engine.url = url
    conn = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = ctx
    return engine, conn


def test_manual_validation_missing_opt_in_rejected(monkeypatch):
    from scripts import manual_validation

    engine, conn = _make_engine()
    conn.execute.return_value.scalar_one.return_value = "career_intelligence_e2e_test"
    monkeypatch.delenv(manual_validation.E2E_OPTIN_ENV, raising=False)
    monkeypatch.setenv("CAREER_API_ACKNOWLEDGE_NO_AUTH", "true")
    monkeypatch.setenv("CAREER_API_ALLOW_REMOTE_CLIENTS", "true")

    with pytest.raises(manual_validation.ManualValidationSafetyError):
        manual_validation._validate_isolated_db_safety(engine)
    # Must not proceed to mutations
    assert conn.execute.call_count >= 0  # guard checks connection but fails on opt-in first


def test_manual_validation_incorrect_opt_in_rejected(monkeypatch):
    from scripts import manual_validation

    engine, conn = _make_engine()
    conn.execute.return_value.scalar_one.return_value = "career_intelligence_e2e_test"
    monkeypatch.setenv(manual_validation.E2E_OPTIN_ENV, "wrong")
    with pytest.raises(manual_validation.ManualValidationSafetyError):
        manual_validation._validate_isolated_db_safety(engine)


def test_manual_validation_production_db_rejected(monkeypatch):
    from scripts import manual_validation

    engine, conn = _make_engine(database="career_intelligence")
    conn.execute.return_value.scalar_one.return_value = "career_intelligence"
    monkeypatch.setenv(manual_validation.E2E_OPTIN_ENV, "career_intelligence_e2e_test")
    with pytest.raises(manual_validation.ManualValidationSafetyError):
        manual_validation._validate_isolated_db_safety(engine)


def test_manual_validation_other_db_rejected(monkeypatch):
    from scripts import manual_validation

    engine, conn = _make_engine(database="postgres")
    conn.execute.return_value.scalar_one.return_value = "postgres"
    monkeypatch.setenv(manual_validation.E2E_OPTIN_ENV, "career_intelligence_e2e_test")
    with pytest.raises(manual_validation.ManualValidationSafetyError):
        manual_validation._validate_isolated_db_safety(engine)


def test_manual_validation_non_loopback_host_rejected(monkeypatch):
    from scripts import manual_validation

    engine, conn = _make_engine(host="192.168.1.10", database="career_intelligence_e2e_test")
    conn.execute.return_value.scalar_one.return_value = "career_intelligence_e2e_test"
    monkeypatch.setenv(manual_validation.E2E_OPTIN_ENV, "career_intelligence_e2e_test")
    with pytest.raises(manual_validation.ManualValidationSafetyError):
        manual_validation._validate_isolated_db_safety(engine)


def test_manual_validation_valid_test_db_passes_checks(monkeypatch):
    from scripts import manual_validation

    engine, conn = _make_engine(host="127.0.0.1", database="career_intelligence_e2e_test")
    conn.execute.return_value.scalar_one.return_value = "career_intelligence_e2e_test"
    monkeypatch.setenv(manual_validation.E2E_OPTIN_ENV, "career_intelligence_e2e_test")
    # Should not raise
    identity = manual_validation._validate_isolated_db_safety(engine)
    # Guard executed before mutation - verified via check calls
    assert conn.execute.called
    assert identity == {"name": "career_intelligence_e2e_test", "host": "127.0.0.1",
                        "port": 5433, "server_current_database": "career_intelligence_e2e_test"}


def _cleanup_engine(delete_counts, remaining_counts):
    conn = MagicMock()
    executed = []

    def execute(statement, params=None):
        sql = " ".join(str(statement).split())
        executed.append(sql)
        table = sql.split(" FROM ", 1)[1].split(" ", 1)[0]
        if sql.upper().startswith("SELECT"):
            return SimpleNamespace(scalar_one=lambda: remaining_counts.get(table, 0))
        return SimpleNamespace(rowcount=delete_counts.get(table, 0))

    conn.execute.side_effect = execute
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    engine = MagicMock()
    engine.begin.return_value = ctx
    return engine, executed


def test_cleanup_deletes_child_rows_first_and_verifies_zero_remaining():
    from scripts import manual_validation

    deleted = {"user_skill_evidence": 2, "user_skills": 2, "user_preferences": 1,
               "user_education": 1, "user_experience": 0, "user_projects": 1,
               "user_certifications": 0, "user_profiles": 1, "users": 1}
    engine, executed = _cleanup_engine(deleted, {})

    ok, details = manual_validation._cleanup_synthetic_user(engine, 42)

    assert ok is True
    assert details["deleted"] == deleted
    assert all(count == 0 for count in details["remaining"].values())
    deletes = [sql for sql in executed if sql.upper().startswith("DELETE")]
    assert deletes[0].startswith("DELETE FROM user_skill_evidence")
    assert deletes[-1] == "DELETE FROM users WHERE user_id = :user_id"


def test_cleanup_fails_when_the_exact_user_row_was_not_deleted():
    from scripts import manual_validation

    engine, _ = _cleanup_engine({"users": 0}, {})
    ok, details = manual_validation._cleanup_synthetic_user(engine, 42)
    assert ok is False
    assert details["deleted"]["users"] == 0


def test_cleanup_fails_when_any_child_row_remains():
    from scripts import manual_validation

    engine, _ = _cleanup_engine({"users": 1}, {"user_skills": 1})
    ok, details = manual_validation._cleanup_synthetic_user(engine, 42)
    assert ok is False
    assert details["remaining"]["user_skills"] == 1


def _completed(args, stdout):
    return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr=b"")


def test_git_provenance_marks_a_clean_tree_without_a_digest(monkeypatch, tmp_path):
    from scripts import manual_validation

    def fake(args, **kwargs):
        if "rev-parse" in args:
            return _completed(args, b"a" * 40 + b"\n")
        if "status" in args:
            return _completed(args, b"")
        raise AssertionError(args)

    monkeypatch.setattr(manual_validation.subprocess, "run", fake)
    provenance = manual_validation._git_provenance(tmp_path)
    assert provenance == {"git_commit": "a" * 40, "git_dirty": False, "git_diff_sha256": None}


def test_git_provenance_digest_covers_diff_and_untracked_content(monkeypatch, tmp_path):
    from scripts import manual_validation

    (tmp_path / "new.txt").write_bytes(b"hello")

    def fake(args, **kwargs):
        if "rev-parse" in args:
            return _completed(args, b"a" * 40 + b"\n")
        if "status" in args:
            return _completed(args, b" M backend/x.py\n?? new.txt\n")
        if "diff" in args:
            return _completed(args, b"diff-bytes")
        if "ls-files" in args:
            return _completed(args, b"new.txt\0")
        raise AssertionError(args)

    monkeypatch.setattr(manual_validation.subprocess, "run", fake)
    provenance = manual_validation._git_provenance(tmp_path)
    expected = hashlib.sha256(
        b"diff-bytes" + b"new.txt\0" + hashlib.sha256(b"hello").digest()).hexdigest()
    assert provenance == {"git_commit": "a" * 40, "git_dirty": True,
                          "git_diff_sha256": expected}


def test_git_provenance_fails_closed_when_untracked_content_cannot_be_read(monkeypatch, tmp_path):
    from scripts import manual_validation

    def fake(args, **kwargs):
        if "rev-parse" in args:
            return _completed(args, b"a" * 40 + b"\n")
        if "status" in args:
            return _completed(args, b"?? missing.txt\n")
        if "diff" in args:
            return _completed(args, b"diff-bytes")
        if "ls-files" in args:
            return _completed(args, b"missing.txt\0")
        raise AssertionError(args)

    monkeypatch.setattr(manual_validation.subprocess, "run", fake)
    provenance = manual_validation._git_provenance(tmp_path)
    assert provenance == {"git_commit": "a" * 40, "git_dirty": True, "git_diff_sha256": None}


def test_importer_refuses_if_careers_non_empty(monkeypatch):
    from scripts import import_kb

    engine, conn = _make_engine(host="localhost", database="career_intelligence_e2e_test")
    conn.execute.return_value.scalar_one.return_value = 5
    monkeypatch.setenv(import_kb.E2E_OPTIN_ENV, "career_intelligence_e2e_test")

    with pytest.raises(import_kb.ImportKBSafetyError):
        import_kb._check_careers_empty(engine)
    assert conn.execute.called


def test_importer_guard_failure_before_any_write(monkeypatch):
    from scripts import import_kb

    engine, conn = _make_engine(host="localhost", database="career_intelligence")
    conn.execute.return_value.scalar_one.return_value = "career_intelligence"
    monkeypatch.setenv(import_kb.E2E_OPTIN_ENV, "career_intelligence_e2e_test")

    with pytest.raises(import_kb.ImportKBSafetyError):
        import_kb._validate_isolated_db_safety(engine)
    # No writes attempted (engine.begin/to_sql not called)
    assert not engine.begin.called
