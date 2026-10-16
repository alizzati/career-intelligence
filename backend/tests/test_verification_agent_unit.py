"""Focused Step 12 tests; services and LLM calls are mocked."""
import os
import sys
from datetime import datetime
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.verification_agent import VerificationAgent
from app.schemas.career_fit import (
    CareerRecommendationOut,
    ScoreBreakdownOut,
    SkillRefOut,
)
from app.schemas.learning_roadmap import LearningRoadmapItem, LearningRoadmapOut
from app.schemas.retrieval import (
    CareerOut,
    CareerSkillOut,
    EvidenceItem,
    OccupationalContextOut,
    ProvenanceOut,
    SkillOut,
)
from app.schemas.skill_gap_agent import (
    SkillGapAnalysisOut,
    SkillGapNarrative,
    SkillObservation,
)
from app.schemas.user import UserFullProfileOut, UserOut, UserSkillEvidenceOut, UserSkillOut
from app.services.career_fit_service import (
    DEFAULT_WEIGHTS,
    RequiredSkillInput,
    UserSkillInput,
    compute_career_fit,
)
from app.services.skill_gap_service import classify_skill_gap


CAREERS = [
    CareerOut(career_id="C001", canonical_name="Backend Engineer", domain="Engineering"),
    CareerOut(career_id="C002", canonical_name="Data Analyst", domain="Data"),
]
REQUIRED = {
    "C001": [
        CareerSkillOut(
            relationship_id="R001",
            skill=SkillOut(skill_id="S001", canonical_name="Python",
                           skill_group_id="G001", status="active"),
            evidence_class="CORE", confidence="high", mapping_method="direct",
            evidence_source_text="Python programming competency.",
        ),
        CareerSkillOut(
            relationship_id="R002",
            skill=SkillOut(skill_id="S002", canonical_name="SQL",
                           skill_group_id="G001", status="active"),
            evidence_class="SUPPORTING", confidence="medium", mapping_method="direct",
            evidence_source_text="Database query evidence.",
        ),
    ],
    "C002": [
        CareerSkillOut(
            relationship_id="R003",
            skill=SkillOut(skill_id="S003", canonical_name="Data Analysis",
                           skill_group_id="G002", status="active"),
            evidence_class="CORE", confidence="high", mapping_method="direct",
            evidence_source_text="Data analysis evidence.",
        ),
    ],
}
PROFILE = UserFullProfileOut(
    user=UserOut(
        user_id=7, email="candidate@example.test", full_name="Candidate",
        created_at=datetime(2026, 1, 1),
    ),
    skills=[
        UserSkillOut(
            user_skill_id=1, claimed_skill="Python", skill_id="S001",
            normalized_skill="Python", proficiency="intermediate",
            evidence_status="linked", confidence="high",
            evidence=[UserSkillEvidenceOut(evidence_id=91, evidence_type="project")],
        ),
        UserSkillOut(
            user_skill_id=2, claimed_skill="Data Analysis", skill_id="S003",
            normalized_skill="Data Analysis", evidence_status="none",
            confidence="unknown", evidence=[],
        ),
        UserSkillOut(
            user_skill_id=3, claimed_skill="Unmapped skill", skill_id=None,
            normalized_skill=None, evidence_status="none",
            confidence="unknown", evidence=[],
        ),
    ],
)
WEIGHTS = dict(DEFAULT_WEIGHTS)


def make_recommendation(career: CareerOut) -> CareerRecommendationOut:
    required = REQUIRED[career.career_id]
    fit = compute_career_fit(
        [
            RequiredSkillInput(item.skill.skill_id, item.evidence_class, item.confidence)
            for item in required
        ],
        [
            UserSkillInput(skill.skill_id, skill.evidence_status, skill.proficiency)
            for skill in PROFILE.skills
        ],
        WEIGHTS,
    )
    lookup = {item.skill.skill_id: item for item in required}

    def refs(ids):
        return [
            SkillRefOut(
                skill_id=skill_id,
                canonical_name=lookup[skill_id].skill.canonical_name,
                evidence_class=lookup[skill_id].evidence_class,
            )
            for skill_id in ids
        ]

    core_count = sum(detail.evidence_class == "CORE" for detail in fit.skill_details)
    return CareerRecommendationOut(
        career_id=career.career_id,
        canonical_name=career.canonical_name,
        domain=career.domain,
        fit_score=round(fit.fit_score, 4),
        score_breakdown=ScoreBreakdownOut(
            total_weight=fit.total_weight,
            total_contribution=fit.total_contribution,
            core_required_count=core_count,
            supporting_required_count=len(fit.skill_details) - core_count,
            matched_linked_count=len(fit.matched_linked_skill_ids),
            matched_claimed_only_count=len(fit.matched_claimed_only_skill_ids),
            missing_count=len(fit.missing_skill_ids),
            weights_used=WEIGHTS,
        ),
        matched_skills=refs(fit.matched_linked_skill_ids),
        claimed_only_skills=refs(fit.matched_claimed_only_skill_ids),
        missing_skills_preview=refs(fit.missing_skill_ids),
        reasoning=f"{career.canonical_name} is evaluated from its listed skills.",
        reasoning_source="fallback-template",
    )


def make_outputs():
    career_by_id = {career.career_id: career for career in CAREERS}
    gap = classify_skill_gap(
        7, career_by_id["C001"], REQUIRED["C001"], PROFILE.skills, WEIGHTS,
    )
    analysis = SkillGapAnalysisOut(
        skill_gap=gap,
        narrative=SkillGapNarrative(
            summary="The result retains the deterministic skill categories.",
            conclusion="Evidence and claims remain separate.",
        ),
        narrative_source="fallback-template",
    )
    roadmap = LearningRoadmapOut(
        skill_gap=gap,
        items=[
            LearningRoadmapItem(
                skill_id="S002", canonical_name="SQL", gap_status="missing",
                evidence_class="SUPPORTING", kb_confidence="medium",
                knowledge_base_basis="Database query evidence.",
                learning_action="develop_skill",
            ),
        ],
        summary="The roadmap follows the existing skill-gap result.",
        narrative_source="fallback-template",
    )
    recommendations = sorted(
        [make_recommendation(career) for career in CAREERS],
        key=lambda item: (-item.fit_score, item.career_id),
    )
    contexts = {
        career.career_id: OccupationalContextOut(
            career=career,
            occupations=[],
            career_skills=REQUIRED[career.career_id],
            competencies=[],
            tasks={},
            technologies={},
            source_mappings={},
        )
        for career in CAREERS
    }
    return recommendations, analysis, roadmap, contexts


class ScriptedLLM:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete_json(self, system, user, max_tokens=2000):
        self.calls.append((system, user, max_tokens))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def run_agent(recommendations=None, skill_gap=None, roadmap=None, llm=None, evidence=None):
    defaults = make_outputs()
    recommendations = recommendations if recommendations is not None else defaults[0]
    skill_gap = skill_gap if skill_gap is not None else defaults[1]
    roadmap = roadmap if roadmap is not None else defaults[2]
    contexts = defaults[3]
    with (
        mock.patch("app.agents.verification_agent.us.get_user_full_profile", return_value=PROFILE),
        mock.patch("app.agents.verification_agent.rs.get_all_careers", return_value=CAREERS),
        mock.patch("app.agents.verification_agent.rs.get_career_skills",
                   side_effect=lambda career_id: REQUIRED[career_id]),
        mock.patch("app.agents.verification_agent.rs.get_skill_evidence",
                   return_value=evidence or []),
        mock.patch("app.agents.verification_agent.rs.get_occupational_context",
                   side_effect=lambda career_id: contexts[career_id]),
    ):
        return VerificationAgent(llm_client=llm, weights=WEIGHTS).run(
            recommendations, skill_gap, roadmap,
        )

def test_all_deterministic_outputs_pass_without_llm_call():
    recommendations, gap, roadmap, _ = make_outputs()
    before = (
        [item.model_dump() for item in recommendations],
        gap.model_dump(),
        roadmap.model_dump(),
    )
    llm = ScriptedLLM({"unsupported_claims": []})
    result = run_agent(recommendations, gap, roadmap, llm)
    after = (
        [item.model_dump() for item in recommendations],
        gap.model_dump(),
        roadmap.model_dump(),
    )
    assert result.status == "PASS"
    assert result.unsupported_claims == []
    assert result.required_revision == []
    assert not llm.calls
    assert all(check.status == "PASS" for check in result.checks)
    assert after == before


def test_semantic_llm_receives_redacted_user_derived_narrative_text():
    email = "semantic.synthetic@example.test"
    phone = "0812-5555-0199"
    recommendations, analysis, roadmap, _ = make_outputs()
    recommendations[0] = recommendations[0].model_copy(update={
        "reasoning": f"Profile claim {email}, contact {phone}.",
        "reasoning_source": "llm",
    })
    analysis = analysis.model_copy(update={
        "narrative": analysis.narrative.model_copy(update={
            "summary": f"Claim {email}; proficiency {phone}.",
        }),
        "narrative_source": "llm",
    })
    roadmap = roadmap.model_copy(update={
        "summary": f"Roadmap derived from {email} and {phone}.",
        "narrative_source": "llm",
    })
    llm = ScriptedLLM({"unsupported_claims": []})

    run_agent(recommendations, analysis, roadmap, llm)

    assert llm.calls
    prompt = llm.calls[0][1]
    assert email not in prompt and phone not in prompt
    assert "[REDACTED_EMAIL]" in prompt and "[REDACTED_PHONE]" in prompt
    assert "Backend Engineer" in prompt and "SQL" in prompt


def test_recommendation_score_tampering_fails_deterministic_check():
    recommendations, gap, roadmap, _ = make_outputs()
    changed = recommendations[0].model_copy(update={"fit_score": 0.1234})
    recommendations[0] = changed
    result = run_agent(recommendations, gap, roadmap)
    assert result.status == "FAIL"
    failed = {check.check for check in result.checks if check.status == "FAIL"}
    assert f"recommendation.{changed.career_id}.deterministic_score" in failed


def test_skill_gap_category_tampering_fails_against_step_9_engine():
    recommendations, gap, roadmap, _ = make_outputs()
    changed_gap = gap.skill_gap.model_copy(update={"missing": []})
    gap = gap.model_copy(update={"skill_gap": changed_gap})
    result = run_agent(recommendations, gap, roadmap)
    assert result.status == "FAIL"
    assert "skill_gap.deterministic_result" in {
        check.check for check in result.checks if check.status == "FAIL"
    }


def test_step_10_narrative_ids_must_remain_in_their_step_9_category():
    recommendations, gap, roadmap, _ = make_outputs()
    narrative = gap.narrative.model_copy(update={
        "strengths": [SkillObservation(skill_ids=["S002"], text="SQL is evidenced.")],
    })
    gap = gap.model_copy(update={"narrative": narrative})
    result = run_agent(recommendations, gap, roadmap)
    assert result.status == "FAIL"
    assert "skill_gap.narrative_categories" in {
        check.check for check in result.checks if check.status == "FAIL"
    }


def test_roadmap_must_cover_all_missing_and_claimed_only_skills():
    recommendations, gap, roadmap, _ = make_outputs()
    roadmap = roadmap.model_copy(update={"items": []})
    result = run_agent(recommendations, gap, roadmap)
    assert result.status == "FAIL"
    assert "roadmap.gap_coverage" in {
        check.check for check in result.checks if check.status == "FAIL"
    }


def test_unsupported_semantic_claim_is_reported_for_responsible_agent():
    recommendations, gap, roadmap, _ = make_outputs()
    recommendations[0] = recommendations[0].model_copy(
        update={"reasoning_source": "llm"},
    )
    llm = ScriptedLLM({
        "unsupported_claims": [{
            "component": f"recommendation:{recommendations[0].career_id}",
            "claim": "This career requires quantum robotics.",
            "source_ids": [recommendations[0].career_id],
        }],
    })
    result = run_agent(recommendations, gap, roadmap, llm)
    assert result.status == "REVISE"
    assert result.unsupported_claims[0].claim == "This career requires quantum robotics."
    assert "career_recommendation_agent" in result.required_revision[0]
    assert len(llm.calls) == 1
    assert "occupational_knowledge_base_records" in llm.calls[0][1]


def test_semantic_response_with_unknown_source_id_is_not_accepted_as_pass():
    recommendations, gap, roadmap, _ = make_outputs()
    recommendations[0] = recommendations[0].model_copy(
        update={"reasoning_source": "llm"},
    )
    llm = ScriptedLLM({
        "unsupported_claims": [{
            "component": "roadmap_summary",
            "claim": "A source claim.",
            "source_ids": ["NOT_IN_THE_KB"],
        }],
    })
    result = run_agent(recommendations, gap, roadmap, llm)
    assert result.status == "REVISE"
    assert result.llm_error
    semantic_check = next(
        check for check in result.checks if check.check == "semantic.occupational_claims"
    )
    assert semantic_check.status == "REVISE"


def test_llm_failure_is_explicit_and_does_not_change_outputs():
    recommendations, gap, roadmap, _ = make_outputs()
    recommendations[0] = recommendations[0].model_copy(
        update={"reasoning_source": "llm"},
    )
    llm = ScriptedLLM(ConnectionError("provider unavailable"))
    result = run_agent(recommendations, gap, roadmap, llm)
    assert result.status == "REVISE"
    assert "ConnectionError" in result.llm_error
    assert any(check.status == "REVISE" for check in result.checks)
    assert recommendations[0].reasoning_source == "llm"


def test_llm_text_without_client_is_reported_as_unreviewed():
    recommendations, gap, roadmap, _ = make_outputs()
    recommendations[0] = recommendations[0].model_copy(
        update={"reasoning_source": "llm"},
    )
    result = run_agent(recommendations, gap, roadmap)
    assert result.status == "REVISE"
    assert "Manually review" in result.required_revision[0]


def test_shared_valid_provenance_reference_is_accepted_and_reported():
    recommendations, gap, roadmap, _ = make_outputs()
    provenance = ProvenanceOut(
        provenance_id="P001", source_name="SKKNI", document_id="STD-1",
        document_title="Competency Standard", version_or_year="2024",
        source_type="standard",
    )
    evidence = [
        EvidenceItem(
            granularity="skill-level", source_name="SKKNI", reference="UNIT-1",
            confidence="high", evidence_type="competency_unit",
            provenance=provenance,
        ),
    ]
    result = run_agent(recommendations, gap, roadmap, evidence=evidence)
    assert result.status == "PASS"
    provenance_check = next(
        check for check in result.checks if check.check == "evidence.provenance_references"
    )
    assert provenance_check.status == "PASS"
    assert provenance_check.source_ids == ["P001"]


def test_provenance_record_missing_source_identity_fails_explicitly():
    recommendations, gap, roadmap, _ = make_outputs()
    evidence = [
        EvidenceItem(
            granularity="skill-level", source_name="SKKNI", reference="UNIT-1",
            provenance=ProvenanceOut(
                provenance_id="P001", source_name="", document_id="STD-1",
                document_title="Competency Standard", version_or_year="2024",
                source_type="standard",
            ),
        ),
    ]
    result = run_agent(recommendations, gap, roadmap, evidence=evidence)
    assert result.status == "FAIL"
    assert any(
        check.check == "evidence.provenance_references" and check.status == "FAIL"
        for check in result.checks
    )


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))
