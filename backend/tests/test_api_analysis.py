"""Step 14 API tests: synthetic files, fake agents, mocked DB lookups, no live LLM."""
import asyncio
import logging
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from app.agents.profile_agent import ProfileAgent
from app.agents.llm_errors import LLMInvalidResponseError, LLMQuotaExceededError
from app.api.dependencies import get_llm_client, get_workflow
from app.api.errors import ApiError
from app.api.uploads import read_upload_bounded
from app.core.config import ApiSettings, get_settings
from app.main import create_app
from app.schemas.career_fit import CareerRecommendationOut, ScoreBreakdownOut, SkillRefOut
from app.schemas.learning_roadmap import LearningRoadmapItem, LearningRoadmapOut
from app.schemas.skill_gap import MatchedUserClaim, SkillGapItem, SkillGapResult, UnmatchedUserClaim
from app.schemas.skill_gap_agent import SkillGapAnalysisOut, SkillGapNarrative
from app.schemas.verification import VerificationCheck, VerificationResult
from app.workflows.career_workflow import CareerWorkflow
from tests.test_cv_text_extraction_service import make_docx, make_pdf

from app.core.db import DatabaseConfigurationError

RAW = (
    "Name: Sinta Contoh\nEmail: sinta@example.test\nPhone: +62 812-3456-7890\n"
    "Address: Jl. Melati No. 10, Bandung\nNIK: 3174012345678901\n"
    "Backend engineer with Python experience."
)
SENSITIVE = ("Sinta Contoh", "sinta@example.test", "+62 812-3456-7890",
             "Jl. Melati No. 10, Bandung", "3174012345678901")
TXT = "Synthetic candidate with backend development experience.".encode()


# ---------- schema factories (real objects; the workflow validates them) ----------
def _breakdown():
    return ScoreBreakdownOut(total_weight=1.0, total_contribution=0.0, core_required_count=1,
                             supporting_required_count=0, matched_linked_count=0,
                             matched_claimed_only_count=0, missing_count=1, weights_used={})


def make_gap() -> SkillGapResult:
    return SkillGapResult(
        user_id=17, career_id="C01", canonical_name="Backend Engineer", domain="Engineering",
        fit_score=0.0, total_weight=1.0, total_contribution=0.0, score_breakdown=_breakdown(),
        matched_evidenced=[], matched_claimed_only=[],
        missing=[SkillGapItem(skill_id="S001", canonical_name="SQL", status="missing",
                              evidence_class="CORE", kb_confidence="high", weight=1.0, contribution=0.0)],
        unmatched_user_claims=[],
    )


class FakeProfileAgent:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def run(self, user_id, raw_profile_text):
        self.calls.append((user_id, raw_profile_text))
        if self.error:
            raise self.error
        return SimpleNamespace(skills_persisted=2, evidence_persisted=1, extracted={"skills": []})


class FakeRecAgent:
    def run(self, user_id):
        return [CareerRecommendationOut(
            career_id="C01", canonical_name="Backend Engineer", domain="Engineering", fit_score=0.0,
            score_breakdown=_breakdown(), matched_skills=[], claimed_only_skills=[],
            missing_skills_preview=[SkillRefOut(skill_id="S001", canonical_name="SQL", evidence_class="CORE")],
            reasoning="Deterministic template.", reasoning_source="fallback-template")]


class FakeGapAgent:
    def __init__(self, result=None):
        self.result = result

    def run(self, user_id, career_id):
        if self.result is not None:
            return self.result
        return SkillGapAnalysisOut(
            skill_gap=make_gap(), narrative=SkillGapNarrative(summary="s", conclusion="c"),
            narrative_source="fallback-template")


class FakeRoadmapAgent:
    def run(self, analysis):
        return LearningRoadmapOut(
            skill_gap=analysis.skill_gap,
            items=[LearningRoadmapItem(skill_id="S001", canonical_name="SQL", gap_status="missing",
                                       evidence_class="CORE", kb_confidence="high",
                                       knowledge_base_basis="KB basis.", learning_action="develop_skill")],
            summary="Template summary.", narrative_source="fallback-template")


class FakeVerifier:
    def __init__(self, results=None, error=None):
        self.results = list(results or [VerificationResult(status="PASS", checks=[])])
        self.error = error
        self.calls = []

    def run(self, recommendations, skill_gap, roadmap):
        self.calls.append((recommendations, skill_gap, roadmap))
        if self.error:
            raise self.error
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]


def failing(check, status="FAIL"):
    return VerificationResult(
        status=status, checks=[VerificationCheck(check=check, status=status, reason="test finding")],
        required_revision=["test revision"])


def make_workflow(**overrides):
    deps = dict(profile_agent=FakeProfileAgent(), career_recommendation_agent=FakeRecAgent(),
                skill_gap_agent=FakeGapAgent(), learning_roadmap_agent=FakeRoadmapAgent(),
                verification_agent=FakeVerifier(), max_revisions=2)
    deps.update(overrides)
    return CareerWorkflow(**deps), deps


def make_client(workflow, settings=None, **extra_overrides):
    app = create_app()
    app.dependency_overrides[get_workflow] = lambda: workflow
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides.update(extra_overrides)
    return TestClient(app), app


def upload(client, content, filename, user_id="17", **data):
    return client.post("/analysis/cv", data={"user_id": user_id, **data},
                       files={"file": (filename, content, "application/octet-stream")})


@pytest.fixture(autouse=True)
def local_dev_access(monkeypatch):
    monkeypatch.setenv("CAREER_API_ACKNOWLEDGE_NO_AUTH", "true")
    monkeypatch.setenv("CAREER_API_ALLOW_REMOTE_CLIENTS", "true")

@pytest.fixture(autouse=True)
def isolated_lookups():
    with mock.patch("app.api.routes.analysis.us.get_user_full_profile",
                    return_value=SimpleNamespace(user_id=17)) as users, \
         mock.patch("app.api.routes.analysis.rs.get_career",
                    return_value=SimpleNamespace(career_id="C01")) as careers, \
         mock.patch("app.agents.llm_client.genai.Client",
                    side_effect=AssertionError("live LLM client constructed in a test")):
        yield SimpleNamespace(users=users, careers=careers)


# ---------- tests ----------
def test_health():
    client, _ = make_client(make_workflow()[0])
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize(("content", "filename", "fmt"), [
    pytest.param(make_pdf("Synthetic candidate profile with backend engineering experience."),
                 "cv.pdf", "pdf", id="pdf"),
    pytest.param(make_docx(), "cv.docx", "docx", id="docx"),
    pytest.param(TXT, "cv.txt", "txt", id="txt"),
])
def test_valid_uploads_run_workflow_to_verified(content, filename, fmt):
    workflow, deps = make_workflow()
    client, _ = make_client(workflow)
    response = upload(client, content, filename)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["final_status"] == "VERIFIED" and body["verified"] is True
    assert body["document"]["format"] == fmt and "filename" not in body["document"]
    assert body["verification"]["status"] == "PASS"
    assert body["recommendations"][0]["career_id"] == "C01"
    assert len(deps["profile_agent"].calls) == 1
    assert not {"profile_result", "extracted", "redacted_profile_text", "raw_profile_text"} & set(body)


@pytest.mark.parametrize(("content", "filename", "status", "code"), [
    pytest.param(b"plain text", "unsupported.docm", 415, "unsupported_format", id="docm"),
    pytest.param(b"%PDF-1.7", "disguised.txt", 422, "format_mismatch", id="pdf-as-txt"),
    pytest.param(b"synthetic text", "fake.pdf", 422, "format_mismatch", id="text-as-pdf"),
    pytest.param(b"", "empty.txt", 422, "empty_file", id="empty"),
    pytest.param(b" \r\n\t", "blank.txt", 422, "empty_document", id="blank"),
    pytest.param(b"%PDF-1.7 broken", "broken.pdf", 422, "unreadable_document", id="broken-pdf"),
    pytest.param(make_pdf("", image_only=True), "scanned.pdf", 422,
                 "scanned_pdf_unsupported", id="scanned-pdf"),
])

def test_invalid_documents_are_rejected_before_the_workflow(content, filename, status, code):
    workflow, deps = make_workflow()
    client, _ = make_client(workflow)
    response = upload(client, content, filename)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert deps["profile_agent"].calls == []
    assert filename not in response.text


def test_oversized_upload_is_rejected_with_413():
    workflow, deps = make_workflow()
    client, _ = make_client(workflow, ApiSettings(max_upload_bytes=10, upload_chunk_bytes=4))
    response = upload(client, b"x" * 50, "big.txt")
    assert response.status_code == 413 and response.json()["error"]["code"] == "file_too_large"
    assert deps["profile_agent"].calls == []


def test_upload_reading_stops_once_the_limit_is_exceeded():
    class CountingUpload:
        def __init__(self, total):
            self.remaining, self.calls = total, 0

        async def read(self, n):
            self.calls += 1
            take = min(n, self.remaining)
            self.remaining -= take
            return b"x" * take

    source = CountingUpload(1000)
    with pytest.raises(ApiError) as exc_info:
        asyncio.run(read_upload_bounded(source, max_bytes=10, chunk_bytes=4))
    assert exc_info.value.status_code == 413
    assert source.calls == 3 and source.remaining == 988


def test_unknown_user_and_unknown_career(isolated_lookups):
    workflow, deps = make_workflow()
    client, _ = make_client(workflow)
    isolated_lookups.users.return_value = None
    assert upload(client, TXT, "cv.txt").status_code == 404
    isolated_lookups.users.return_value = SimpleNamespace(user_id=17)
    isolated_lookups.careers.return_value = None
    response = upload(client, TXT, "cv.txt", target_career_id="C99")
    assert response.status_code == 404 and response.json()["error"]["code"] == "career_not_found"
    assert deps["profile_agent"].calls == []


def test_missing_file_gives_structured_validation_error():
    client, _ = make_client(make_workflow()[0])
    response = client.post("/analysis/cv", data={"user_id": "17"})
    assert response.status_code == 422
    assert response.json() == {"error": {"code": "invalid_request",
            "message": "The request is malformed or missing required fields."}}


class FakeExtractionLLM:
    def __init__(self):
        self.prompts = []

    def complete_json(self, system, user, max_tokens=2000):
        self.prompts.append(user)
        return {
            "skills": [{"claimed_skill": "Python", "proficiency": "intermediate", "candidate_skill_id": None}],
            "evidence": [{"claimed_skill": "Python", "evidence_type": "project",
                          "description": "Contact sinta@example.test at 0812-3456-7890", "url": None}],
            "education": [{"institution": "Example University", "degree": "BSc",
                           "field_of_study": "Computer Science", "start_date": None, "end_date": None,
                           "description": "Address: Jl. Melati No. 10, Bandung"}],
            "experience": [], "projects": [], "certifications": [],
        }


@contextmanager
def patched_persistence():
    ids = SimpleNamespace(education_id=1, experience_id=2, project_id=3,
                          certification_id=4, user_skill_id=5, evidence_id=6)
    with ExitStack() as stack:
        mocks = {name: stack.enter_context(mock.patch(f"app.agents.profile_agent.us.{name}", return_value=ids))
                 for name in ("add_education", "add_experience", "add_project",
                              "add_certification", "add_user_skill", "add_skill_evidence")}
        stack.enter_context(mock.patch("app.agents.profile_agent.rs.get_all_skills", return_value=[]))
        yield mocks


def test_profile_agent_and_llm_receive_only_redacted_text_and_nothing_leaks(caplog):
    caplog.set_level(logging.DEBUG)
    llm = FakeExtractionLLM()
    workflow, _ = make_workflow(profile_agent=ProfileAgent(llm))
    client, _ = make_client(workflow)
    with patched_persistence() as persisted, \
         mock.patch("app.api.routes.analysis.redact_pii", wraps=__import__(
             "app.services.pii_redaction_service", fromlist=["redact_pii"]).redact_pii) as spy:
        response = upload(client, RAW.encode(), "cv.txt")

    assert response.status_code == 200, response.text
    assert "sinta@example.test" in spy.call_args_list[0].args[0]   # raw text goes to the redactor first
    assert len(llm.prompts) == 1
    for value in SENSITIVE:
        assert value not in llm.prompts[0]
        assert value not in response.text
        assert value not in caplog.text
        assert value not in repr([m.call_args_list for m in persisted.values()])
    assert "[REDACTED_EMAIL]" in llm.prompts[0]
    body = response.json()
    assert body["redaction"]["replacement_count"] >= 5
    assert "email" in body["redaction"]["detected_types"]
    assert "cv.txt" not in response.text


def test_verification_failures_are_reported_not_hidden():
    verifier = FakeVerifier([failing("evidence.provenance_references")])
    client, _ = make_client(make_workflow(verification_agent=verifier)[0])
    body = upload(client, TXT, "cv.txt").json()
    assert body["final_status"] == "VERIFICATION_FAILED" and body["verified"] is False
    assert body["verification"]["status"] == "FAIL"

    verifier = FakeVerifier([failing("roadmap.gap_coverage")])
    client, _ = make_client(make_workflow(verification_agent=verifier, max_revisions=0)[0])
    body = upload(client, TXT, "cv.txt").json()
    assert body["final_status"] == "REVISION_LIMIT_REACHED" and body["verified"] is False


def test_workflow_errors_return_safe_500_without_internal_text():
    error = RuntimeError(f"provider echo: {RAW}")
    client, _ = make_client(make_workflow(profile_agent=FakeProfileAgent(error=error))[0])
    response = upload(client, RAW.encode(), "cv.txt")
    assert response.status_code == 500
    assert response.json()["error"]["stage"] == "profile_analysis"
    for value in SENSITIVE:
        assert value not in response.text

    secret = "postgresql://user:SECRET@host/db"
    client, _ = make_client(make_workflow(verification_agent=FakeVerifier(error=RuntimeError(secret)))[0])
    response = client.post("/analysis/profile", json={"user_id": 17})
    assert response.status_code == 500 and response.json()["error"]["stage"] == "verification"
    assert "SECRET" not in response.text and "Traceback" not in response.text


@pytest.mark.parametrize(
    ("error", "status", "code", "message_fragment"),
    [
        (
            LLMQuotaExceededError(),
            503,
            "llm_quota_exceeded",
            "model quota has been reached",
        ),
        (
            LLMInvalidResponseError(),
            502,
            "llm_invalid_response",
            "could not process the model response",
        ),
    ],
)
def test_profile_llm_failures_return_safe_actionable_errors(
    error, status, code, message_fragment,
):
    client, _ = make_client(make_workflow(profile_agent=FakeProfileAgent(error=error))[0])

    response = upload(client, TXT, "cv.txt")

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["stage"] == "profile_analysis"
    assert message_fragment in response.json()["error"]["message"]
    assert "synthetic" not in response.text


def test_cv_route_reports_quota_failure_from_real_profile_agent_without_pii(caplog):
    class QuotaLLM:
        def complete_json(self, system, user, max_tokens=2000):
            assert "Sinta Contoh" not in user
            assert "sinta@example.test" not in user
            raise LLMQuotaExceededError() from None

    workflow, _ = make_workflow(profile_agent=ProfileAgent(QuotaLLM()))
    client, _ = make_client(workflow)

    with (
        mock.patch("app.agents.profile_agent.rs.get_all_skills", return_value=[]),
        caplog.at_level(logging.DEBUG),
    ):
        response = upload(client, RAW.encode(), "synthetic.txt")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_quota_exceeded"
    assert response.json()["error"]["stage"] == "profile_analysis"
    assert "synthetic provider details" not in response.text + caplog.text
    for value in SENSITIVE:
        assert value not in response.text + caplog.text.lower()


def test_llm_unavailable_returns_503_without_any_provider_call():
    app_client, app = make_client(make_workflow()[0])
    app.dependency_overrides.pop(get_workflow)
    app.dependency_overrides[get_llm_client] = lambda: None
    response = upload(app_client, TXT, "cv.txt")
    assert response.status_code == 503 and response.json()["error"]["code"] == "llm_unavailable"


def test_uploaded_files_are_closed_on_success_and_failure():
    seen, original = [], UploadFile.close

    async def spy(self):
        seen.append(self)
        await original(self)

    client, _ = make_client(make_workflow()[0])
    with mock.patch.object(UploadFile, "close", spy):
        assert upload(client, TXT, "cv.txt").status_code == 200
        assert upload(client, b"", "empty.txt").status_code == 422
        assert upload(client, b"x", "bad.docm").status_code == 415
    assert len(seen) >= 3 and all(item.file.closed for item in seen)


def test_existing_profile_path_skips_profile_parsing(isolated_lookups):
    workflow, deps = make_workflow()
    client, _ = make_client(workflow)
    response = client.post("/analysis/profile", json={"user_id": 17, "target_career_id": "C01"})
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "existing_profile" and body["verified"] is True
    assert body["document"] is None and body["profile_extraction"] is None
    assert deps["profile_agent"].calls == []

    isolated_lookups.users.return_value = None
    assert client.post("/analysis/profile", json={"user_id": 17}).status_code == 404
    bad = client.post("/analysis/profile", json={"user_id": 0})
    assert bad.status_code == 422 and "input" not in bad.text


def test_existing_profile_pii_is_redacted_at_verification_and_response_boundaries(
    isolated_lookups, caplog,
):
    email = "synthetic.profile@example.test"
    phone = "0812-5555-0199"
    base = make_gap()
    claimed = SkillGapItem(
        skill_id="S001", canonical_name="SQL", status="matched_claimed_only",
        evidence_class="CORE", kb_confidence="high", weight=1.0, contribution=0.0,
        matched_user_claim=MatchedUserClaim(
            claimed_skill=email, proficiency=phone, evidence_status="none", evidence_count=0,
        ),
    )
    unmatched = UnmatchedUserClaim(
        user_skill_id=88, claimed_skill=email, proficiency=phone,
        evidence_status="none", evidence_count=0,
    )
    gap = base.model_copy(update={
        "matched_claimed_only": [claimed],
        "missing": [],
        "unmatched_user_claims": [unmatched],
    })
    analysis = SkillGapAnalysisOut(
        skill_gap=gap,
        narrative=SkillGapNarrative(
            summary=f"Claim: {email}, proficiency {phone}.",
            conclusion=f"Contact {email} at {phone}.",
            unmatched_claim_observations=[
                {"user_skill_ids": [88], "text": f"User provided {email} and {phone}."}
            ],
        ),
        narrative_source="fallback-template",
    )

    class PiiRecommendationAgent(FakeRecAgent):
        def run(self, user_id):
            results = super().run(user_id)
            results[0] = results[0].model_copy(update={
                "reasoning": f"User claim {email}; self-reported proficiency {phone}."
            })
            return results

    class PiiRoadmapAgent(FakeRoadmapAgent):
        def run(self, result):
            roadmap = super().run(result)
            return roadmap.model_copy(update={"summary": f"Roadmap for {email}, {phone}."})

    verifier_result = VerificationResult(
        status="FAIL",
        checks=[VerificationCheck(
            check="semantic.occupational_claims", status="FAIL",
            reason=f"Review claim {email} and proficiency {phone}.",
        )],
        required_revision=[f"Review {email} and {phone}."],
    )
    verifier = FakeVerifier([verifier_result])
    workflow, _ = make_workflow(
        career_recommendation_agent=PiiRecommendationAgent(),
        skill_gap_agent=FakeGapAgent(analysis),
        learning_roadmap_agent=PiiRoadmapAgent(),
        verification_agent=verifier,
    )
    original_gap = gap.model_dump()
    direct_state = workflow.run(user_id=17)
    assert direct_state["skill_gap"].skill_gap.model_dump() == original_gap

    client, _ = make_client(workflow)
    response = client.post("/analysis/profile", json={"user_id": 17})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["skill_gap"]["skill_gap"]["matched_claimed_only"][0]["skill_id"] == "S001"
    assert body["skill_gap"]["skill_gap"]["matched_claimed_only"][0]["canonical_name"] == "SQL"
    assert body["skill_gap"]["skill_gap"]["matched_claimed_only"][0]["status"] == "matched_claimed_only"

    for recommendations, verified_gap, roadmap in verifier.calls:
        captured = repr((recommendations, verified_gap, roadmap))
        assert email not in captured and phone not in captured
        assert "[REDACTED_EMAIL]" in captured and "[REDACTED_PHONE]" in captured
    for value in (email, phone):
        assert value not in response.text
        assert value not in caplog.text
    assert "SQL" in response.text


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("CAREER_API_MAX_UPLOAD_BYTES", "123")
    assert ApiSettings.from_env().max_upload_bytes == 123
    monkeypatch.setenv("CAREER_API_MAX_UPLOAD_BYTES", "0")
    with pytest.raises(ValueError):
        ApiSettings.from_env()



@pytest.mark.parametrize(("make_verifier", "max_revisions", "expected"), [
    pytest.param(lambda: FakeVerifier([failing("evidence.provenance_references")]), 2,
                 "VERIFICATION_FAILED", id="no-revision-route"),
    pytest.param(lambda: FakeVerifier([failing("roadmap.gap_coverage")]), 0,
                 "REVISION_LIMIT_REACHED", id="limit-reached"),
    pytest.param(lambda: FakeVerifier([failing("evidence.occupational_context", "REVISE")]), 2,
                 "VERIFICATION_FAILED", id="revise-status"),
])
def test_failed_verification_is_http_200_with_verified_false(make_verifier, max_revisions, expected):
    workflow, _ = make_workflow(verification_agent=make_verifier(), max_revisions=max_revisions)
    client, _ = make_client(workflow)
    for response in (
        upload(client, TXT, "cv.txt"),
        client.post("/analysis/profile", json={"user_id": 17}),
    ):
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["verified"] is False and body["final_status"] == expected
        assert body["verification"]["status"] in {"FAIL", "REVISE"}
        assert body["verification"]["checks"]          # findings are reported, not hidden


def test_http_status_distinguishes_verification_outcome_from_request_and_server_errors():
    client, _ = make_client(make_workflow()[0])
    assert upload(client, TXT, "cv.txt").status_code == 200                       # verified
    assert upload(client, b"x", "cv.docm").status_code == 415                      # unsupported file
    assert upload(client, b"%PDF-1.7", "cv.txt").status_code == 422                # signature mismatch
    assert client.post("/analysis/profile", json={"user_id": 0}).status_code == 422  # invalid input
    small, _ = make_client(make_workflow()[0], ApiSettings(max_upload_bytes=10, upload_chunk_bytes=4))
    assert upload(small, b"x" * 50, "big.txt").status_code == 413                  # oversized file
    broken, _ = make_client(make_workflow(
        verification_agent=FakeVerifier(error=RuntimeError("boom")))[0])
    assert broken.post("/analysis/profile", json={"user_id": 17}).status_code == 500  # internal failure


def test_missing_database_configuration_is_a_safe_503(isolated_lookups):
    isolated_lookups.users.side_effect = DatabaseConfigurationError("CAREER_DB_PASSWORD secret-detail")
    client, _ = make_client(make_workflow()[0])
    response = client.post("/analysis/profile", json={"user_id": 17})
    assert response.status_code == 503 and response.json()["error"]["code"] == "database_not_configured"
    assert "CAREER_DB" not in response.text and "secret-detail" not in response.text