"""Step 14.1: repeated CV submissions do not duplicate profile rows. Real local DB, synthetic data."""
import copy
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import text

from app.agents.profile_agent import ProfileAgent
from app.core.db import DatabaseConfigurationError, engine, get_engine
from app.repositories import user_repository as repo
from app.services import user_service as us


def extraction(institution="Universitas Contoh", company="StartupX", project="Campus Course Scheduler"):
    return {
        "skills": [{"claimed_skill": "Database Management", "proficiency": "intermediate", "candidate_skill_id": None}],
        "evidence": [{"claimed_skill": "Database Management", "evidence_type": "project",
                      "description": "Designed a normalized schema", "url": None}],
        "education": [{"institution": institution, "degree": "S.Kom", "field_of_study": "Computer Science",
                       "start_date": "2020-08-01", "end_date": "2024-07-01", "description": "Final year"}],
        "experience": [{"company": company, "role_title": "Backend Intern", "employment_type": "internship",
                        "start_date": "2023-06-01", "end_date": "2023-09-01", "description": "Built REST APIs"}],
        "projects": [{"title": project, "description": "Normalized schema + API", "url": None,
                      "role": "Backend developer"}],
        "certifications": [{"name": "Example Certificate", "issuer": "Example Issuer",
                            "issue_date": "2024-01-01", "expiry_date": None, "credential_url": None}],
    }


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, system, user, max_tokens=2000):
        return copy.deepcopy(self.payload)


def counts(user_id):
    full = us.get_user_full_profile(user_id)
    return {"education": len(full.education), "experience": len(full.experience),
            "projects": len(full.projects), "certifications": len(full.certifications),
            "skills": len(full.skills), "evidence": sum(len(s.evidence) for s in full.skills)}


def submit(user_id, payload):
    ProfileAgent(FakeLLM(payload)).run(user_id, raw_profile_text="synthetic profile text")


def _new_user():
    return us.create_user(f"idempotency_{uuid.uuid4().hex[:10]}@example.com", "Idempotency Test").user_id


def _delete(user_id):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE user_id = :uid"), {"uid": user_id})


@pytest.fixture()
def user_id():
    try:
        get_engine()
    except DatabaseConfigurationError:
        pytest.skip("database not configured (set CAREER_DB_PASSWORD or CAREER_DB_URL)")
    uid = _new_user()
    try:
        yield uid
    finally:
        _delete(uid)


ONE_OF_EACH = {"education": 1, "experience": 1, "projects": 1, "certifications": 1, "skills": 1, "evidence": 1}


def test_same_cv_submitted_three_times_creates_one_set_of_rows(user_id):
    for _ in range(3):
        submit(user_id, extraction())
    assert counts(user_id) == ONE_OF_EACH


def test_case_and_whitespace_variants_do_not_duplicate(user_id):
    submit(user_id, extraction())
    submit(user_id, extraction(institution="  universitas   CONTOH ", company="STARTUPX ",
                               project="campus  course   scheduler"))
    assert counts(user_id) == ONE_OF_EACH


def test_a_genuinely_new_entry_is_still_added(user_id):
    submit(user_id, extraction())
    submit(user_id, extraction(institution="Another Institute", company="OtherCo", project="Second Project"))
    after = counts(user_id)
    assert (after["education"], after["experience"], after["projects"]) == (2, 2, 2)
    assert after["certifications"] == 1 and after["skills"] == 1 and after["evidence"] == 1


def test_existing_rows_are_not_modified_by_a_resubmission(user_id):
    submit(user_id, extraction())
    before = us.get_user_full_profile(user_id).education[0]
    changed = extraction()
    changed["education"][0]["description"] = "different text"
    submit(user_id, changed)
    after = us.get_user_full_profile(user_id).education
    assert len(after) == 1 and after[0] == before


def test_other_users_are_unaffected():
    try:
        get_engine()
    except DatabaseConfigurationError:
        pytest.skip("database not configured")
    a, b = _new_user(), _new_user()
    try:
        submit(a, extraction())
        submit(b, extraction())
        submit(a, extraction())
        assert counts(a) == counts(b) == ONE_OF_EACH
    finally:
        _delete(a)
        _delete(b)


def test_concurrent_identical_writes_create_a_single_row(user_id):
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _: us.add_education(user_id, "Concurrent University", "BSc", "CS"), range(12)))
    assert counts(user_id)["education"] == 1


# ---- no database needed below ----
class _Result:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


class _Conn:
    def __init__(self, rows):
        self.rows, self.calls = list(rows), []

    def execute(self, statement, params=None):
        self.calls.append(str(statement))
        return _Result(self.rows.pop(0))


def test_insert_or_fetch_returns_existing_row_when_nothing_was_inserted():
    conn = _Conn([None, {"education_id": 7}])
    assert repo._insert_or_fetch(conn, "INSERT ...", "SELECT ...", {"a": 1}, ("a",)) == {"education_id": 7}
    assert len(conn.calls) == 2


def test_insert_or_fetch_does_not_fetch_after_a_successful_insert():
    conn = _Conn([{"education_id": 1}])
    assert repo._insert_or_fetch(conn, "INSERT ...", "SELECT ...", {}, ()) == {"education_id": 1}
    assert len(conn.calls) == 1


def test_insert_or_fetch_fails_loudly_if_neither_insert_nor_fetch_finds_a_row():
    with pytest.raises(RuntimeError):
        repo._insert_or_fetch(_Conn([None, None]), "INSERT ...", "SELECT ...", {}, ())


def test_each_writer_locks_then_uses_not_exists():
    for call in (
        lambda c: repo.create_education(c, 1, "I", None, None, None, None, None),
        lambda c: repo.create_experience(c, 1, "C", "R", None, None, None, None),
        lambda c: repo.create_project(c, 1, "T", None, None, None),
        lambda c: repo.create_certification(c, 1, "N", None, None, None, None),
        lambda c: repo.add_skill_evidence(c, 1, "project", None, None, None, None),
    ):
        conn = _Conn([None, {"x": 1}, {"x": 1}, {"x": 1}])
        call(conn)
        assert "pg_advisory_xact_lock" in conn.calls[0] and "NOT EXISTS" in conn.calls[1]