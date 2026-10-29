"""Section 19 logging: both normal analysis endpoints must write one safe record."""
import hashlib
import json
import logging
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

import pytest

from app.agents.profile_agent import EXTRACTION_SYSTEM_PROMPT
from app.schemas.skill_gap import MatchedUserClaim, SkillGapItem, UnmatchedUserClaim
from app.schemas.skill_gap_agent import SkillGapAnalysisOut, SkillGapNarrative
from app.schemas.verification import VerificationCheck, VerificationResult
from app.services import analysis_log_service

from tests.test_api_analysis import (
    RAW,
    SENSITIVE,
    TXT,
    FakeGapAgent,
    FakeProfileAgent,
    FakeRecAgent,
    FakeRoadmapAgent,
    FakeVerifier,
    failing,
    make_client,
    make_gap,
    make_workflow,
    upload,
)

REQUIRED_FIELDS = {
    "analysis_id",
    "timestamp",
    "user_profile_id",
    "model",
    "model_version",
    "prompt_version_identifier",
    "kb_version",
    "agents_executed",
    "agent_outputs",
    "verification_result",
    "revision_count",
    "final_result",
}


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("CAREER_API_ACKNOWLEDGE_NO_AUTH", "true")
    monkeypatch.setenv("CAREER_API_ALLOW_REMOTE_CLIENTS", "true")
    monkeypatch.setenv("CAREER_ANALYSIS_LOG_DIR", str(tmp_path / "analysis_logs"))
    with mock.patch("app.api.routes.analysis.us.get_user_full_profile",
                    return_value=SimpleNamespace(user_id=17)), \
         mock.patch("app.api.routes.analysis.rs.get_career",
                    return_value=SimpleNamespace(career_id="C01")):
        yield


def records(tmp_path):
    directory = tmp_path / "analysis_logs"
    return [json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("*.json"))]


def only_record(tmp_path):
    found = records(tmp_path)
    assert len(found) == 1
    return found[0]


def test_cv_analysis_writes_all_section_19_fields(tmp_path):
    client, _ = make_client(make_workflow()[0])
    response = upload(client, TXT, "cv.txt")
    assert response.status_code == 200, response.text
    assert response.json()["final_status"] == "VERIFIED"

    record = only_record(tmp_path)
    assert REQUIRED_FIELDS <= set(record)
    assert record["schema_version"] == analysis_log_service.SCHEMA_VERSION
    assert record["analysis_id"]
    parsed = datetime.fromisoformat(record["timestamp"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert record["user_profile_id"] == 17
    assert record["source"] == "cv_upload"
    assert isinstance(record["model"], str) and record["model"]
    assert record["model_version"].startswith("unavailable")
    assert record["kb_version"].startswith("unavailable")
    assert record["prompt_version_identifier"]["prompts"]["profile_extraction"]["sha256"] == (
        hashlib.sha256(EXTRACTION_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
    )
    assert {item["agent"] for item in record["agents_executed"]} == {
        "profile", "career_recommendation", "skill_gap", "roadmap", "verification",
    }
    assert record["agent_outputs"]["career_recommendation"][0]["career_id"] == "C01"
    assert record["agent_outputs"]["skill_gap"]["skill_gap"]["career_id"] == "C01"
    assert record["verification_result"]["status"] == "PASS"
    assert record["revision_count"] == 0
    assert record["final_result"]["final_status"] == "VERIFIED"
    assert record["final_result"]["verified"] is True
    assert record["final_result"]["target_career_id"] == "C01"
    assert record["final_result"]["errors"] == []
    assert record["workflow_trace"]["nodes"][:5] == [
        "profile_analysis", "career_recommendation", "skill_gap_analysis",
        "learning_roadmap", "verification",
    ]
    assert record["input"]["document"]["format"] == "txt"
    assert "filename" not in record["input"]["document"]
    assert "redacted_profile_text" not in json.dumps(record)


def test_existing_profile_analysis_is_logged_without_profile_agent(tmp_path):
    client, _ = make_client(make_workflow()[0])
    response = client.post("/analysis/profile", json={"user_id": 17})
    assert response.status_code == 200, response.text
    assert response.json()["final_status"] == "VERIFIED"

    record = only_record(tmp_path)
    assert record["source"] == "existing_profile"
    assert record["user_profile_id"] == 17
    assert "profile" not in {item["agent"] for item in record["agents_executed"]}
    assert record["agent_outputs"]["profile"]["executed"] is False
    assert "existing profile reused" in record["agent_outputs"]["profile"]["reason"]
    assert "profile_extraction" not in record["prompt_version_identifier"]["prompts"]
    assert record["verification_result"]["status"] == "PASS"
    assert record["final_result"]["final_status"] == "VERIFIED"


def test_revision_count_and_trace_match_the_final_verification(tmp_path):
    verifier = FakeVerifier([
        failing("roadmap.gap_coverage"),
        VerificationResult(status="PASS", checks=[]),
    ])
    workflow, _ = make_workflow(verification_agent=verifier, max_revisions=2)
    client, _ = make_client(workflow)
    response = upload(client, TXT, "cv.txt")
    assert response.status_code == 200, response.text
    assert response.json()["revision_count"] == 1
    assert response.json()["final_status"] == "VERIFIED"

    record = only_record(tmp_path)
    assert record["revision_count"] == 1
    assert record["workflow_trace"]["nodes"].count("learning_roadmap") == 2
    roadmap = next(item for item in record["agents_executed"] if item["agent"] == "roadmap")
    assert roadmap["attempts"] == 2
    assert record["verification_result"]["status"] == "PASS"
    assert record["final_result"]["final_status"] == "VERIFIED"
    assert record["final_result"]["verified"] is True


def test_failed_analysis_is_logged_without_exception_messages(tmp_path):
    error = RuntimeError(f"provider echo: {RAW}")
    workflow, _ = make_workflow(profile_agent=FakeProfileAgent(error=error))
    client, _ = make_client(workflow)
    response = upload(client, RAW.encode(), "cv.txt")
    assert response.status_code == 500
    assert response.json()["error"]["stage"] == "profile_analysis"

    record = only_record(tmp_path)
    assert record["final_result"]["final_status"] == "ERROR"
    assert record["final_result"]["verified"] is False
    assert record["final_result"]["errors"] == [
        {"stage": "profile_analysis", "error_type": "RuntimeError"}
    ]
    assert record["verification_result"]["status"] == "unavailable"
    assert record["revision_count"] == 0
    assert "profile" in {item["agent"] for item in record["agents_executed"]}
    persisted = json.dumps(record, ensure_ascii=False)
    assert "provider echo" not in persisted
    for value in SENSITIVE:
        assert value not in persisted


def test_log_contains_no_sensitive_cv_or_agent_text(tmp_path):
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
        "matched_claimed_only": [claimed], "missing": [], "unmatched_user_claims": [unmatched],
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

    verifier = FakeVerifier([VerificationResult(
        status="FAIL",
        checks=[VerificationCheck(
            check="semantic.occupational_claims", status="FAIL",
            reason=f"Review claim {email} and proficiency {phone}.",
        )],
        required_revision=[f"Review {email} and {phone}."],
    )])
    workflow, _ = make_workflow(
        career_recommendation_agent=PiiRecommendationAgent(),
        skill_gap_agent=FakeGapAgent(analysis),
        learning_roadmap_agent=PiiRoadmapAgent(),
        verification_agent=verifier,
    )
    client, _ = make_client(workflow)
    response = upload(client, RAW.encode(), "cv.txt")
    assert response.status_code == 200, response.text

    persisted = json.dumps(only_record(tmp_path), ensure_ascii=False)
    for value in (*SENSITIVE, email, phone, "Sinta Contoh"):
        assert value not in persisted
    assert "[REDACTED_EMAIL]" in persisted
    assert "SQL" in persisted


def test_logging_failure_does_not_change_the_analysis_response(tmp_path, caplog):
    client, _ = make_client(make_workflow()[0])
    control = upload(client, TXT, "cv.txt")
    assert control.status_code == 200

    caplog.set_level(logging.WARNING)
    with mock.patch.object(
        analysis_log_service, "_atomic_write",
        side_effect=OSError("sensitive disk detail"),
    ):
        response = upload(client, TXT, "cv.txt")

    assert response.status_code == 200
    assert response.json() == control.json()
    assert "Analysis log was not written (OSError)" in caplog.text
    assert "sensitive disk detail" not in caplog.text
    assert len(records(tmp_path)) == 1      # only the control run was written


def test_one_log_per_analysis_and_no_log_for_rejected_requests(tmp_path):
    client, _ = make_client(make_workflow()[0])
    assert client.post("/analysis/profile", json={"user_id": 17}).status_code == 200
    assert upload(client, TXT, "cv.txt").status_code == 200
    found = records(tmp_path)
    assert len(found) == 2
    assert len({record["analysis_id"] for record in found}) == 2

    assert upload(client, b"plain text", "unsupported.docm").status_code == 415
    assert client.post("/analysis/profile", json={"user_id": 0}).status_code == 422
    assert len(records(tmp_path)) == 2
