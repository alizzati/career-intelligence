"""Step 13 LangGraph orchestration tests; all agent dependencies are fakes."""
from types import SimpleNamespace
from unittest import mock

import pytest

from app.schemas.verification import VerificationCheck, VerificationResult
from app.workflows.career_workflow import CareerWorkflow


class FakeProfileAgent:
    def __init__(self, result=None, error=None):
        self.result = result or SimpleNamespace(user_id=17, extracted={"skills": []})
        self.error = error
        self.calls = []

    def run(self, user_id, raw_profile_text):
        self.calls.append((user_id, raw_profile_text))
        if self.error:
            raise self.error
        return self.result


class FakeCareerRecommendationAgent:
    def __init__(self, recommendations=None, error=None):
        self.recommendations = recommendations or [
            SimpleNamespace(career_id="C01", fit_score=0.9),
            SimpleNamespace(career_id="C02", fit_score=0.7),
        ]
        self.error = error
        self.calls = []

    def run(self, user_id):
        self.calls.append(user_id)
        if self.error:
            raise self.error
        return self.recommendations


class FakeSkillGapAgent:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def run(self, user_id, career_id):
        self.calls.append((user_id, career_id))
        if self.error:
            raise self.error
        gap = FakeGap(career_id)
        return SimpleNamespace(skill_gap=gap)


class FakeGap:
    def __init__(self, career_id):
        self.career_id = career_id

    def model_dump(self):
        return {"career_id": self.career_id}


class FakeRoadmapAgent:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def run(self, skill_gap):
        self.calls.append(skill_gap)
        if self.error:
            raise self.error
        return SimpleNamespace(skill_gap=skill_gap.skill_gap)


class FakeVerificationAgent:
    def __init__(self, results=None, error=None):
        self.results = list(results or [VerificationResult(status="PASS", checks=[])])
        self.error = error
        self.calls = []

    def run(self, recommendations, skill_gap, roadmap):
        self.calls.append((recommendations, skill_gap, roadmap))
        if self.error:
            raise self.error
        if len(self.results) > 1:
            return self.results.pop(0)
        return self.results[0]


def verification(status, check, component=None):
    claim_list = []
    if component:
        from app.schemas.verification import UnsupportedClaim

        claim_list.append(UnsupportedClaim(
            component=component, claim="Unsupported claim", source_ids=[],
        ))
    return VerificationResult(
        status=status,
        checks=[
            VerificationCheck(check=check, status=status, reason="test finding")
        ],
        unsupported_claims=claim_list,
        required_revision=["test revision"] if status != "PASS" else [],
    )


def make_workflow(max_revisions=2, **overrides):
    dependencies = {
        "profile_agent": FakeProfileAgent(),
        "career_recommendation_agent": FakeCareerRecommendationAgent(),
        "skill_gap_agent": FakeSkillGapAgent(),
        "learning_roadmap_agent": FakeRoadmapAgent(),
        "verification_agent": FakeVerificationAgent(),
    }
    dependencies.update(overrides)
    return CareerWorkflow(max_revisions=max_revisions, **dependencies), dependencies


def test_graph_compiles_with_expected_nodes_and_edges():
    workflow, _ = make_workflow()
    graph = workflow.graph.get_graph()
    nodes = set(graph.nodes)
    assert {
        "profile_analysis", "career_recommendation", "skill_gap_analysis",
        "learning_roadmap", "verification", "verification_decision", "final_result",
    }.issubset(nodes)
    assert "__start__" in nodes and "__end__" in nodes


def test_successful_workflow_skips_profile_parsing_for_existing_user():
    workflow, dependencies = make_workflow()
    existing_profile = SimpleNamespace(user_id=17)
    with mock.patch(
        "app.workflows.career_workflow.us.get_user_full_profile",
        return_value=existing_profile,
    ):
        result = workflow.run(user_id=17)

    assert result["final_status"] == "VERIFIED"
    assert result["profile_result"] is existing_profile
    assert result["target_career_id"] == "C01"
    assert result["stage"] == "final_result"
    assert result["revision_count"] == 0
    assert result["verification"].status == "PASS"
    assert dependencies["profile_agent"].calls == []
    assert dependencies["skill_gap_agent"].calls == [(17, "C01")]
    assert dependencies["learning_roadmap_agent"].calls == [result["skill_gap"]]
    verified_inputs = dependencies["verification_agent"].calls[0]
    assert verified_inputs[0] is result["recommendations"]
    assert verified_inputs[1] is result["skill_gap"]
    assert verified_inputs[2] is result["roadmap"]


def test_raw_profile_is_analyzed_only_when_supplied():
    profile_agent = FakeProfileAgent()
    workflow, _ = make_workflow(profile_agent=profile_agent)
    result = workflow.run(user_id=17, raw_profile_text="candidate profile text")
    assert result["final_status"] == "VERIFIED"
    assert profile_agent.calls == [(17, "candidate profile text")]


def test_explicit_canonical_career_is_propagated_to_skill_gap_agent():
    workflow, dependencies = make_workflow()
    with mock.patch(
        "app.workflows.career_workflow.us.get_user_full_profile",
        return_value=SimpleNamespace(user_id=17),
    ):
        result = workflow.run(user_id=17, target_career_id="C02")
    assert result["final_status"] == "VERIFIED"
    assert result["target_career_id"] == "C02"
    assert dependencies["skill_gap_agent"].calls == [(17, "C02")]


def test_fail_routes_to_responsible_upstream_agent_and_reverifies_dependents():
    career_agent = FakeCareerRecommendationAgent()
    gap_agent = FakeSkillGapAgent()
    roadmap_agent = FakeRoadmapAgent()
    verifier = FakeVerificationAgent(results=[
        verification("FAIL", "recommendation.C01.deterministic_score"),
        VerificationResult(status="PASS", checks=[]),
    ])
    workflow, _ = make_workflow(
        career_recommendation_agent=career_agent,
        skill_gap_agent=gap_agent,
        learning_roadmap_agent=roadmap_agent,
        verification_agent=verifier,
    )
    with mock.patch(
        "app.workflows.career_workflow.us.get_user_full_profile",
        return_value=SimpleNamespace(user_id=17),
    ):
        result = workflow.run(user_id=17)

    assert result["final_status"] == "VERIFIED"
    assert result["revision_count"] == 1
    assert career_agent.calls == [17, 17]
    assert gap_agent.calls == [(17, "C01"), (17, "C01")]
    assert len(roadmap_agent.calls) == 2
    assert len(verifier.calls) == 2


def test_revise_routes_to_roadmap_only_and_preserves_final_findings():
    gap_agent = FakeSkillGapAgent()
    roadmap_agent = FakeRoadmapAgent()
    verifier = FakeVerificationAgent(results=[
        verification("REVISE", "roadmap.gap_coverage"),
        VerificationResult(status="PASS", checks=[]),
    ])
    workflow, dependencies = make_workflow(
        skill_gap_agent=gap_agent,
        learning_roadmap_agent=roadmap_agent,
        verification_agent=verifier,
    )
    with mock.patch(
        "app.workflows.career_workflow.us.get_user_full_profile",
        return_value=SimpleNamespace(user_id=17),
    ):
        result = workflow.run(user_id=17)
    assert result["final_status"] == "VERIFIED"
    assert result["revision_count"] == 1
    assert len(gap_agent.calls) == 1
    assert len(roadmap_agent.calls) == 2
    assert dependencies["career_recommendation_agent"].calls == [17]


def test_unsupported_claim_routes_to_owning_agent():
    career_agent = FakeCareerRecommendationAgent()
    verifier = FakeVerificationAgent(results=[
        verification("REVISE", "semantic.occupational_claims", "recommendation:C01"),
        VerificationResult(status="PASS", checks=[]),
    ])
    workflow, _ = make_workflow(
        career_recommendation_agent=career_agent,
        verification_agent=verifier,
    )
    with mock.patch(
        "app.workflows.career_workflow.us.get_user_full_profile",
        return_value=SimpleNamespace(user_id=17),
    ):
        result = workflow.run(user_id=17)
    assert result["final_status"] == "VERIFIED"
    assert result["revision_count"] == 1
    assert career_agent.calls == [17, 17]
    assert len(verifier.calls) == 2


def test_revision_limit_terminates_and_does_not_turn_failure_into_success():
    verifier = FakeVerificationAgent(results=[
        verification("FAIL", "skill_gap.deterministic_result"),
        verification("FAIL", "skill_gap.deterministic_result"),
    ])
    workflow, dependencies = make_workflow(
        max_revisions=1,
        verification_agent=verifier,
    )
    with mock.patch(
        "app.workflows.career_workflow.us.get_user_full_profile",
        return_value=SimpleNamespace(user_id=17),
    ):
        result = workflow.run(user_id=17)
    assert result["final_status"] == "REVISION_LIMIT_REACHED"
    assert result["revision_count"] == 1
    assert result["verification"].status == "FAIL"
    assert len(verifier.calls) == 2
    assert len(dependencies["skill_gap_agent"].calls) == 2


def test_nonpassing_result_without_supported_revision_route_stays_nonpassing():
    verifier = FakeVerificationAgent(results=[
        verification("REVISE", "evidence.provenance_references"),
    ])
    workflow, _ = make_workflow(verification_agent=verifier)
    with mock.patch(
        "app.workflows.career_workflow.us.get_user_full_profile",
        return_value=SimpleNamespace(user_id=17),
    ):
        result = workflow.run(user_id=17)
    assert result["final_status"] == "VERIFICATION_FAILED"
    assert result["verification"].status == "REVISE"


def test_pass_status_with_failed_check_cannot_become_verified():
    contradictory_result = VerificationResult(
        status="PASS",
        checks=[
            VerificationCheck(
                check="roadmap.gap_coverage", status="FAIL", reason="coverage failed",
            ),
        ],
    )
    verifier = FakeVerificationAgent(results=[contradictory_result])
    workflow, _ = make_workflow(max_revisions=0, verification_agent=verifier)
    with mock.patch(
        "app.workflows.career_workflow.us.get_user_full_profile",
        return_value=SimpleNamespace(user_id=17),
    ):
        result = workflow.run(user_id=17)
    assert result["final_status"] == "REVISION_LIMIT_REACHED"
    assert result["verification"].status == "PASS"
    assert any(check.status == "FAIL" for check in result["verification"].checks)


@pytest.mark.parametrize(
    ("kwargs", "expected_stage"),
    [
        ({"user_id": 0}, "input_validation"),
        ({"user_id": "bad"}, "input_validation"),
        ({"user_id": 17, "target_career_id": ""}, "input_validation"),
        ({"user_id": 17, "raw_profile_text": " "}, "input_validation"),
    ],
)
def test_invalid_inputs_return_structured_errors(kwargs, expected_stage):
    workflow, dependencies = make_workflow()
    result = workflow.run(**kwargs)
    assert result["final_status"] == "ERROR"
    assert result["errors"][0]["stage"] == expected_stage
    assert dependencies["career_recommendation_agent"].calls == []


@pytest.mark.parametrize(
    ("agent_key", "expected_stage"),
    [
        ("profile_agent", "profile_analysis"),
        ("career_recommendation_agent", "career_recommendation"),
        ("skill_gap_agent", "skill_gap_analysis"),
        ("learning_roadmap_agent", "learning_roadmap"),
        ("verification_agent", "verification"),
    ],
)
def test_agent_exceptions_are_structured_workflow_errors(agent_key, expected_stage):
    dependencies = {
        "profile_agent": FakeProfileAgent(),
        "career_recommendation_agent": FakeCareerRecommendationAgent(),
        "skill_gap_agent": FakeSkillGapAgent(),
        "learning_roadmap_agent": FakeRoadmapAgent(),
        "verification_agent": FakeVerificationAgent(),
    }
    failing_agents = {
        "profile_agent": lambda: FakeProfileAgent(error=RuntimeError("agent failed")),
        "career_recommendation_agent": lambda: FakeCareerRecommendationAgent(
            error=RuntimeError("agent failed")
        ),
        "skill_gap_agent": lambda: FakeSkillGapAgent(error=RuntimeError("agent failed")),
        "learning_roadmap_agent": lambda: FakeRoadmapAgent(error=RuntimeError("agent failed")),
        "verification_agent": lambda: FakeVerificationAgent(error=RuntimeError("agent failed")),
    }
    dependencies[agent_key] = failing_agents[agent_key]()
    workflow, _ = make_workflow(**dependencies)
    kwargs = {"user_id": 17}
    if agent_key == "profile_agent":
        kwargs["raw_profile_text"] = "candidate profile"
    with mock.patch(
        "app.workflows.career_workflow.us.get_user_full_profile",
        return_value=SimpleNamespace(user_id=17),
    ):
        result = workflow.run(**kwargs)
    assert result["final_status"] == "ERROR"
    assert result["errors"][0]["stage"] == expected_stage
    assert result["final_status"] != "VERIFIED"


def test_raw_profile_without_profile_client_is_controlled_error():
    workflow, _ = make_workflow(profile_agent=None)
    workflow.profile_agent = None
    result = workflow.run(user_id=17, raw_profile_text="candidate profile")
    assert result["final_status"] == "ERROR"
    assert result["errors"][0]["stage"] == "profile_analysis"


@pytest.mark.parametrize("max_revisions", [-1, True, 1.5])
def test_revision_limit_must_be_a_nonnegative_integer(max_revisions):
    with pytest.raises(ValueError, match="max_revisions"):
        CareerWorkflow(max_revisions=max_revisions)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
