from types import SimpleNamespace
from unittest import mock

from app.agents.profile_agent import ProfileAgent
from app.schemas.verification import VerificationResult
from app.workflows.career_workflow import CareerWorkflow


RAW_PROFILE = (
    "Name: Sinta Contoh\n"
    "Email: sinta@example.test\n"
    "Phone: +62 812-3456-7890\n"
    "Address: Jl. Melati No. 10, Bandung\n"
    "NIK: 3174012345678901\n"
    "Backend engineer with Python experience."
)


class FakeExtractionLLMClient:
    def __init__(self):
        self.prompts = []

    def complete_json(self, system, user, max_tokens=2000):
        self.prompts.append(user)
        return {
            "skills": [
                {"claimed_skill": "Python", "proficiency": "intermediate", "candidate_skill_id": None},
            ],
            "evidence": [{
                "claimed_skill": "Python",
                "evidence_type": "project",
                "description": "Contact sinta@example.test at 0812-3456-7890",
                "url": "https://example.test/?email=sinta@example.test",
            }],
            "education": [{
                "institution": "Example University",
                "degree": "BSc",
                "field_of_study": "Computer Science",
                "start_date": None,
                "end_date": None,
                "description": "Address: Jl. Melati No. 10, Bandung",
            }],
            "experience": [{
                "company": "Example Labs",
                "role_title": "Backend Engineer",
                "employment_type": "full-time",
                "start_date": None,
                "end_date": None,
                "description": "NIK: 3174012345678901",
            }],
            "projects": [{
                "title": "Career Tool",
                "description": "Built an API",
                "url": None,
                "role": "Developer",
            }],
            "certifications": [],
        }


class FailingExtractionLLMClient:
    def complete_json(self, system, user, max_tokens=2000):
        raise RuntimeError(f"provider rejected input: {RAW_PROFILE}")


class FakeRecommendationAgent:
    def __init__(self, error=None):
        self.error = error

    def run(self, user_id):
        if self.error:
            raise self.error
        return [SimpleNamespace(career_id="C01", fit_score=0.9)]


class FakeGap:
    career_id = "C01"

    def model_dump(self):
        return {"career_id": self.career_id}


class FakeSkillGapAgent:
    def run(self, user_id, career_id):
        return SimpleNamespace(skill_gap=FakeGap())


class FakeRoadmapAgent:
    def run(self, skill_gap):
        return SimpleNamespace(skill_gap=skill_gap.skill_gap)


class FakeVerificationAgent:
    def run(self, recommendations, skill_gap, roadmap):
        return VerificationResult(status="PASS", checks=[])


def _persistence_mocks():
    return {
        "add_education": mock.patch(
            "app.agents.profile_agent.us.add_education",
            return_value=SimpleNamespace(education_id=1),
        ),
        "add_experience": mock.patch(
            "app.agents.profile_agent.us.add_experience",
            return_value=SimpleNamespace(experience_id=2),
        ),
        "add_project": mock.patch(
            "app.agents.profile_agent.us.add_project",
            return_value=SimpleNamespace(project_id=3),
        ),
        "add_certification": mock.patch(
            "app.agents.profile_agent.us.add_certification",
            return_value=SimpleNamespace(certification_id=4),
        ),
        "add_user_skill": mock.patch(
            "app.agents.profile_agent.us.add_user_skill",
            return_value=SimpleNamespace(user_skill_id=5),
        ),
        "add_skill_evidence": mock.patch(
            "app.agents.profile_agent.us.add_skill_evidence",
            return_value=SimpleNamespace(evidence_id=6),
        ),
    }


def test_workflow_redacts_before_llm_and_never_returns_or_logs_raw_input(caplog):
    llm = FakeExtractionLLMClient()
    profile_agent = ProfileAgent(llm)
    workflow = CareerWorkflow(
        profile_agent=profile_agent,
        career_recommendation_agent=FakeRecommendationAgent(),
        skill_gap_agent=FakeSkillGapAgent(),
        learning_roadmap_agent=FakeRoadmapAgent(),
        verification_agent=FakeVerificationAgent(),
    )
    stores = _persistence_mocks()

    with (
        mock.patch("app.agents.profile_agent.rs.get_all_skills", return_value=[]),
        stores["add_education"] as add_education,
        stores["add_experience"] as add_experience,
        stores["add_project"] as add_project,
        stores["add_certification"],
        stores["add_user_skill"],
        stores["add_skill_evidence"] as add_evidence,
    ):
        result = workflow.run(user_id=17, raw_profile_text=RAW_PROFILE)

    assert result["final_status"] == "VERIFIED"
    assert "raw_profile_text" not in result
    assert "redacted_profile_text" not in result
    assert len(llm.prompts) == 1
    prompt = llm.prompts[0]
    for sensitive_value in (
        "Sinta Contoh", "sinta@example.test", "+62 812-3456-7890",
        "Jl. Melati No. 10, Bandung", "3174012345678901",
    ):
        assert sensitive_value not in prompt
        assert sensitive_value not in repr(result)
        assert sensitive_value not in caplog.text
    assert "[REDACTED_EMAIL]" in prompt
    assert "[REDACTED_PHONE]" in prompt
    assert "[REDACTED_ADDRESS]" in prompt
    assert "[REDACTED_GOVERNMENT_ID]" in prompt

    persisted_args = repr((
        add_education.call_args,
        add_experience.call_args,
        add_project.call_args,
        add_evidence.call_args,
    ))
    assert "Example University" in persisted_args
    assert "Backend Engineer" in persisted_args
    assert "[REDACTED_ADDRESS]" in str(add_education.call_args)
    assert "[REDACTED_GOVERNMENT_ID]" in str(add_experience.call_args)
    assert "[REDACTED_EMAIL]" in str(add_evidence.call_args)
    assert "[REDACTED_PHONE]" in str(add_evidence.call_args)
    for sensitive_value in (
        "sinta@example.test", "0812-3456-7890", "3174012345678901",
        "Jl. Melati No. 10, Bandung",
    ):
        assert sensitive_value not in persisted_args

    extracted = result["profile_result"].extracted
    assert "[REDACTED_ADDRESS]" in extracted["education"][0]["description"]
    assert "[REDACTED_GOVERNMENT_ID]" in extracted["experience"][0]["description"]
    assert "[REDACTED_EMAIL]" in extracted["evidence"][0]["description"]


def test_profile_provider_exception_cannot_echo_raw_input_in_workflow_error(caplog):
    workflow = CareerWorkflow(
        profile_agent=ProfileAgent(FailingExtractionLLMClient()),
        career_recommendation_agent=FakeRecommendationAgent(),
        skill_gap_agent=FakeSkillGapAgent(),
        learning_roadmap_agent=FakeRoadmapAgent(),
        verification_agent=FakeVerificationAgent(),
    )

    with mock.patch("app.agents.profile_agent.rs.get_all_skills", return_value=[]):
        result = workflow.run(user_id=17, raw_profile_text=RAW_PROFILE)

    assert result["final_status"] == "ERROR"
    assert result["errors"][0]["message"] == (
        "Profile analysis failed; submitted profile details were omitted."
    )
    assert "redacted_profile_text" not in result
    assert "raw_profile_text" not in result
    for sensitive_value in (
        "Sinta Contoh", "sinta@example.test", "+62 812-3456-7890",
        "Jl. Melati No. 10, Bandung", "3174012345678901",
    ):
        assert sensitive_value not in repr(result)
        assert sensitive_value not in caplog.text


def test_later_stage_exception_cannot_echo_submitted_profile(caplog):
    workflow = CareerWorkflow(
        profile_agent=ProfileAgent(FakeExtractionLLMClient()),
        career_recommendation_agent=FakeRecommendationAgent(
            error=RuntimeError(f"downstream error: {RAW_PROFILE}")
        ),
        skill_gap_agent=FakeSkillGapAgent(),
        learning_roadmap_agent=FakeRoadmapAgent(),
        verification_agent=FakeVerificationAgent(),
    )
    stores = _persistence_mocks()

    with (
        mock.patch("app.agents.profile_agent.rs.get_all_skills", return_value=[]),
        stores["add_education"],
        stores["add_experience"],
        stores["add_project"],
        stores["add_certification"],
        stores["add_user_skill"],
        stores["add_skill_evidence"],
    ):
        result = workflow.run(user_id=17, raw_profile_text=RAW_PROFILE)

    assert result["final_status"] == "ERROR"
    assert result["errors"][0]["stage"] == "career_recommendation"
    assert result["errors"][0]["message"] == (
        "career_recommendation failed; submitted profile details were omitted."
    )
    assert "redacted_profile_text" not in result
    for sensitive_value in (
        "Sinta Contoh", "sinta@example.test", "+62 812-3456-7890",
        "Jl. Melati No. 10, Bandung", "3174012345678901",
    ):
        assert sensitive_value not in repr(result)
        assert sensitive_value not in caplog.text
