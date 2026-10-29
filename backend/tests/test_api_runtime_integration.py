"""Opt-in runtime/API integration tests against a local PostgreSQL database."""
import copy
import logging
import os
import uuid
from dataclasses import dataclass
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.agents.career_recommendation_agent import CareerRecommendationAgent
from app.agents.learning_roadmap_agent import LearningRoadmapAgent
from app.agents.profile_agent import ProfileAgent
from app.agents.skill_gap_agent import SkillGapAgent
from app.agents.verification_agent import VerificationAgent
from app.api.dependencies import get_workflow
from app.core.config import ApiSettings, get_settings
from app.core.db import DatabaseConfigurationError, get_engine
from app.main import create_app
from app.schemas.verification import VerificationCheck, VerificationResult
from app.services import retrieval_service as rs
from app.services import user_service as us
from app.workflows.career_workflow import CareerWorkflow


EMAIL = "runtime.synthetic@example.test"
PHONE = "0812-5555-0199"
CV_TEXT = (
    "Name: Synthetic Candidate\n"
    f"Email: {EMAIL}\n"
    f"Phone: {PHONE}\n"
    "Backend engineer with database experience."
)


@dataclass(frozen=True)
class SyntheticUser:
    user_id: int
    career_id: str
    skill_id: str
    skill_name: str


def _assert_no_test_pii(text: str) -> None:
    assert EMAIL not in text and PHONE not in text, "synthetic PII crossed a runtime privacy boundary"


@pytest.fixture(scope="module")
def local_database():
    if os.environ.get("CAREER_RUN_RUNTIME_DB_TESTS") != "1":
        pytest.skip(
            "Set CAREER_RUN_RUNTIME_DB_TESTS=1 to explicitly run tests against local PostgreSQL."
        )
    try:
        engine = get_engine()
        host = (engine.url.host or "").lower()
        if host not in {"localhost", "127.0.0.1", "::1"}:
            pytest.fail("Runtime integration tests require a loopback PostgreSQL host; connection details suppressed.")
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            database_name = conn.execute(text("SELECT current_database()")).scalar_one()
            career_count = conn.execute(text("SELECT count(*) FROM careers")).scalar_one()
    except DatabaseConfigurationError:
        pytest.fail(
            "Local database is not configured. Set CAREER_DB_URL or CAREER_DB_PASSWORD "
            "and the optional CAREER_DB_HOST/PORT/NAME/USER settings; values are not printed."
        )
    except pytest.fail.Exception:
        raise
    except Exception as exc:
        pytest.fail(
            f"Local database is unreachable or missing the Knowledge Base ({type(exc).__name__}); "
            "check local PostgreSQL and backend/.env without printing credentials."
        )
    if database_name != "career_intelligence":
        pytest.fail("Runtime integration tests require the local career_intelligence database.")
    if career_count != 10:
        pytest.fail("Runtime integration tests require the ten canonical careers in the local Knowledge Base.")
    return engine


@pytest.fixture()
def test_user(local_database):
    careers = rs.get_all_careers()
    selected = next(
        ((career, skill) for career in careers for skill in rs.get_career_skills(career.career_id)),
        None,
    )
    if selected is None:
        pytest.fail("The local Knowledge Base has no career-skill records.")
    career, career_skill = selected
    user = us.create_user(
        f"runtime-integration-{uuid.uuid4().hex}@example.invalid",
        "Synthetic Runtime Integration User",
    )
    fixture_user = SyntheticUser(
        user_id=user.user_id,
        career_id=career.career_id,
        skill_id=career_skill.skill.skill_id,
        skill_name=career_skill.skill.canonical_name,
    )
    try:
        yield fixture_user
    finally:
        with local_database.begin() as conn:
            result = conn.execute(
                text("DELETE FROM users WHERE user_id = :user_id"),
                {"user_id": fixture_user.user_id},
            )
        if result.rowcount != 1:
            raise AssertionError("The exact synthetic integration user was not deleted.")


@pytest.fixture(autouse=True)
def local_api_access(monkeypatch, tmp_path):
    monkeypatch.setenv("CAREER_API_ACKNOWLEDGE_NO_AUTH", "true")
    monkeypatch.setenv("CAREER_API_ALLOW_REMOTE_CLIENTS", "true")
    monkeypatch.setenv("CAREER_ANALYSIS_LOG_DIR", str(tmp_path / "analysis_logs"))


def extraction_payload(test_user: SyntheticUser, description: str, proficiency: str = "intermediate"):
    return {
        "skills": [
            {
                "claimed_skill": test_user.skill_name,
                "proficiency": proficiency,
                "candidate_skill_id": test_user.skill_id,
            },
            {
                "claimed_skill": EMAIL,
                "proficiency": PHONE,
                "candidate_skill_id": None,
            },
        ],
        "evidence": [{
            "claimed_skill": test_user.skill_name,
            "evidence_type": "project",
            "description": "Synthetic project evidence",
            "url": None,
        }],
        "education": [{
            "institution": "Synthetic University",
            "degree": "Bachelor",
            "field_of_study": "Computer Science",
            "start_date": "2020-08-01",
            "end_date": "2024-07-01",
            "description": description,
        }],
        "experience": [{
            "company": "Synthetic Company",
            "role_title": "Backend Engineer",
            "employment_type": "internship",
            "start_date": "2023-06-01",
            "end_date": "2023-09-01",
            "description": description,
        }],
        "projects": [{
            "title": "Synthetic Project",
            "description": description,
            "url": None,
            "role": "Developer",
        }],
        "certifications": [{
            "name": "Synthetic Certification",
            "issuer": "Synthetic Issuer",
            "issue_date": "2024-01-01",
            "expiry_date": None,
            "credential_url": None,
        }],
    }


class FakeLLM:
    def __init__(self, *, extractions=()):
        self.extractions = list(extractions)
        self.prompts = []

    def complete_json(self, system, user, max_tokens=2000):
        self.prompts.append((system, user, max_tokens))
        if "information-extraction component" in system:
            if not self.extractions:
                raise AssertionError("Unexpected profile extraction call.")
            return copy.deepcopy(self.extractions.pop(0))
        if "semantic grounding checker" in system:
            return {"unsupported_claims": []}
        if "Your ONLY job" in system:
            return {"reasoning": "The deterministic fit reflects the supplied canonical skill information."}
        if "narrative layer of a skill-gap report" in system:
            return {}
        if "short overview of a learning-focus list" in system:
            return {"summary": "The learning focus follows the supplied skill-gap result."}
        raise AssertionError("Unexpected fake LLM request.")


class FixedVerifier:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, recommendations, skill_gap, roadmap):
        self.calls.append((recommendations, skill_gap, roadmap))
        return self.result


def make_real_workflow(fake_llm, *, max_revisions=2, verification_agent=None):
    return CareerWorkflow(
        llm_client=fake_llm,
        max_revisions=max_revisions,
        profile_agent=ProfileAgent(fake_llm),
        career_recommendation_agent=CareerRecommendationAgent(llm_client=fake_llm),
        skill_gap_agent=SkillGapAgent(llm_client=fake_llm),
        learning_roadmap_agent=LearningRoadmapAgent(llm_client=fake_llm),
        verification_agent=verification_agent or VerificationAgent(llm_client=fake_llm),
    )


def make_client(workflow, *, settings=None):
    app = create_app()
    app.dependency_overrides[get_workflow] = lambda: workflow
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def _profile_counts(user_id: int) -> dict[str, int]:
    with get_engine().connect() as conn:
        rows = conn.execute(text("""
            SELECT
                (SELECT count(*) FROM user_profiles WHERE user_id = :uid) AS profiles,
                (SELECT count(*) FROM user_education WHERE user_id = :uid) AS education,
                (SELECT count(*) FROM user_experience WHERE user_id = :uid) AS experience,
                (SELECT count(*) FROM user_projects WHERE user_id = :uid) AS projects,
                (SELECT count(*) FROM user_certifications WHERE user_id = :uid) AS certifications,
                (SELECT count(*) FROM user_skills WHERE user_id = :uid) AS skills,
                (SELECT count(*) FROM user_skill_evidence e
                    JOIN user_skills s ON s.user_skill_id = e.user_skill_id
                    WHERE s.user_id = :uid) AS evidence
        """), {"uid": user_id}).mappings().one()
    return dict(rows)


def _pass_api_user_profile(test_user: SyntheticUser):
    us.add_user_skill(
        test_user.user_id,
        claimed_skill=test_user.skill_name,
        skill_id=test_user.skill_id,
        normalized_skill=test_user.skill_name,
        proficiency="intermediate",
    )
    us.add_user_skill(test_user.user_id, claimed_skill=EMAIL, proficiency=PHONE)


def test_existing_profile_runs_real_database_workflow_and_redacts_persisted_claims(
    test_user, caplog,
):
    _pass_api_user_profile(test_user)
    llm = FakeLLM()
    client = make_client(make_real_workflow(llm))
    caplog.set_level(logging.DEBUG)

    response = client.post(
        "/analysis/profile",
        json={"user_id": test_user.user_id, "target_career_id": test_user.career_id},
    )

    assert response.status_code == 200
    assert response.json()["final_status"] == "VERIFIED"
    assert response.json()["source"] == "existing_profile"
    all_prompts = "\n".join(prompt for _, prompt, _ in llm.prompts)
    _assert_no_test_pii(all_prompts)
    _assert_no_test_pii(response.text)
    _assert_no_test_pii(caplog.text)
    assert "[REDACTED_EMAIL]" in all_prompts
    assert "[REDACTED_PHONE]" in all_prompts
    assert test_user.skill_name in response.text


def test_health_endpoint_is_available_from_the_application(local_database):
    client = make_client(make_real_workflow(FakeLLM()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_user_creation_endpoint_persists_synthetic_user_and_returns_only_id(local_database):
    email = f"runtime-create-{uuid.uuid4().hex}@example.invalid"
    client = make_client(make_real_workflow(FakeLLM()))
    created_user_id = None
    try:
        response = client.post(
            "/analysis/users",
            json={"email": email, "full_name": "Synthetic API User"},
        )

        assert response.status_code == 201
        assert set(response.json()) == {"user_id"}
        created_user_id = response.json()["user_id"]
        with local_database.connect() as conn:
            stored_email = conn.execute(
                text("SELECT email FROM users WHERE user_id = :user_id"),
                {"user_id": created_user_id},
            ).scalar_one()
        assert stored_email == email
    finally:
        if created_user_id is not None:
            with local_database.begin() as conn:
                result = conn.execute(
                    text("DELETE FROM users WHERE user_id = :user_id"),
                    {"user_id": created_user_id},
                )
            assert result.rowcount == 1


def test_cv_upload_runs_real_database_workflow_and_repeat_is_idempotent(
    test_user, caplog,
):
    llm = FakeLLM(extractions=[
        extraction_payload(test_user, "Original synthetic description"),
        extraction_payload(test_user, "Changed synthetic description", proficiency="advanced"),
    ])
    client = make_client(make_real_workflow(llm))
    caplog.set_level(logging.DEBUG)

    first = client.post(
        "/analysis/cv",
        data={"user_id": str(test_user.user_id), "target_career_id": test_user.career_id},
        files={"file": ("synthetic.txt", CV_TEXT.encode(), "text/plain")},
    )
    second = client.post(
        "/analysis/cv",
        data={"user_id": str(test_user.user_id), "target_career_id": test_user.career_id},
        files={"file": ("synthetic.txt", CV_TEXT.encode(), "text/plain")},
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["final_status"] == second.json()["final_status"] == "VERIFIED"
    assert first.json()["document"]["format"] == second.json()["document"]["format"] == "txt"
    assert first.json()["redaction"]["replacement_count"] >= 3
    assert second.json()["profile_extraction"]["skills_persisted"] == 2
    assert _profile_counts(test_user.user_id) == {
        "profiles": 0, "education": 1, "experience": 1, "projects": 1,
        "certifications": 1, "skills": 2, "evidence": 1,
    }
    full_profile = us.get_user_full_profile(test_user.user_id)
    assert full_profile.education[0].description == "Original synthetic description"
    assert full_profile.experience[0].description == "Original synthetic description"
    assert full_profile.projects[0].description == "Original synthetic description"
    assert full_profile.certifications[0].issuer == "Synthetic Issuer"
    persisted_skill = next(skill for skill in full_profile.skills if skill.claimed_skill == test_user.skill_name)
    assert persisted_skill.proficiency == "intermediate"
    all_prompts = "\n".join(prompt for _, prompt, _ in llm.prompts)
    _assert_no_test_pii(all_prompts)
    _assert_no_test_pii(first.text + second.text)
    _assert_no_test_pii(caplog.text)
    assert "[REDACTED_EMAIL]" in all_prompts
    assert "[REDACTED_PHONE]" in all_prompts


def test_missing_user_and_career_are_rejected_against_local_database(test_user):
    client = make_client(make_real_workflow(FakeLLM()))
    with get_engine().connect() as conn:
        missing_user_exists = conn.execute(
            text("SELECT EXISTS(SELECT 1 FROM users WHERE user_id = :user_id)"),
            {"user_id": 2147483647},
        ).scalar_one()
    assert missing_user_exists is False

    missing_user = client.post("/analysis/profile", json={"user_id": 2147483647})
    unknown_career = client.post(
        "/analysis/profile",
        json={"user_id": test_user.user_id, "target_career_id": "SYNTHETIC_UNKNOWN_CAREER"},
    )

    assert missing_user.status_code == 404
    assert missing_user.json()["error"]["code"] == "user_not_found"
    assert unknown_career.status_code == 404
    assert unknown_career.json()["error"]["code"] == "career_not_found"

    missing_cv_user = client.post(
        "/analysis/cv",
        data={"user_id": "2147483647"},
        files={"file": ("synthetic.txt", CV_TEXT.encode(), "text/plain")},
    )
    unknown_cv_career = client.post(
        "/analysis/cv",
        data={
            "user_id": str(test_user.user_id),
            "target_career_id": "SYNTHETIC_UNKNOWN_CAREER",
        },
        files={"file": ("synthetic.txt", CV_TEXT.encode(), "text/plain")},
    )
    assert missing_cv_user.status_code == 404
    assert missing_cv_user.json()["error"]["code"] == "user_not_found"
    assert unknown_cv_career.status_code == 404
    assert unknown_cv_career.json()["error"]["code"] == "career_not_found"


def test_malformed_and_oversized_uploads_are_rejected_before_llm(test_user):
    llm = FakeLLM()
    workflow = make_real_workflow(llm)
    client = make_client(workflow)

    malformed = client.post(
        "/analysis/cv",
        data={"user_id": str(test_user.user_id)},
        files={"file": ("broken.pdf", b"%PDF-1.7 malformed", "application/pdf")},
    )
    small_client = make_client(
        workflow,
        settings=ApiSettings(max_upload_bytes=10, upload_chunk_bytes=4),
    )
    oversized = small_client.post(
        "/analysis/cv",
        data={"user_id": str(test_user.user_id)},
        files={"file": ("large.txt", b"x" * 32, "text/plain")},
    )

    assert malformed.status_code == 422
    assert malformed.json()["error"]["code"] == "unreadable_document"
    assert oversized.status_code == 413
    assert oversized.json()["error"]["code"] == "file_too_large"
    assert llm.prompts == []


def test_verification_failure_and_revision_exhaustion_are_not_success(test_user):
    _pass_api_user_profile(test_user)
    failure = VerificationResult(
        status="FAIL",
        checks=[VerificationCheck(
            check="evidence.provenance_references", status="FAIL",
            reason="Synthetic provenance failure.",
        )],
        required_revision=["Synthetic provenance review."],
    )
    failure_client = make_client(
        make_real_workflow(FakeLLM(), verification_agent=FixedVerifier(failure))
    )
    failed = failure_client.post(
        "/analysis/profile",
        json={"user_id": test_user.user_id, "target_career_id": test_user.career_id},
    )

    exhaustion = VerificationResult(
        status="FAIL",
        checks=[VerificationCheck(
            check="roadmap.gap_coverage", status="FAIL",
            reason="Synthetic roadmap coverage failure.",
        )],
        required_revision=["Synthetic roadmap review."],
    )
    exhausted_client = make_client(make_real_workflow(
        FakeLLM(), max_revisions=0, verification_agent=FixedVerifier(exhaustion),
    ))
    exhausted = exhausted_client.post(
        "/analysis/profile",
        json={"user_id": test_user.user_id, "target_career_id": test_user.career_id},
    )

    assert failed.status_code == 200 and failed.json()["verified"] is False
    assert failed.json()["final_status"] == "VERIFICATION_FAILED"
    assert exhausted.status_code == 200 and exhausted.json()["verified"] is False
    assert exhausted.json()["final_status"] == "REVISION_LIMIT_REACHED"


@pytest.mark.parametrize(
    ("exception", "status", "code"),
    [
        (DatabaseConfigurationError("synthetic config failure"), 503, "database_not_configured"),
        (
            OperationalError("synthetic query", {}, RuntimeError("synthetic connectivity failure")),
            500,
            "internal_error",
        ),
    ],
)
def test_database_configuration_and_connectivity_failures_are_sanitized(
    test_user, caplog, exception, status, code,
):
    llm = FakeLLM()
    client = make_client(make_real_workflow(llm))
    caplog.set_level(logging.DEBUG)

    with mock.patch("app.api.routes.analysis.us.get_user_full_profile", side_effect=exception):
        response = client.post(
            "/analysis/profile",
            json={"user_id": test_user.user_id, "target_career_id": test_user.career_id},
        )

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "synthetic config failure" not in response.text + caplog.text
    assert "synthetic connectivity failure" not in response.text + caplog.text
    assert llm.prompts == []
