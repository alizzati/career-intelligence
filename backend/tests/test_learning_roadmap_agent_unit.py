"""Unit tests for the roadmap agent; no database or live LLM is used."""
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents import learning_roadmap_agent as roadmap_module
from app.agents.learning_roadmap_agent import (
    LearningRoadmapAgent,
    RoadmapContextError,
)
from app.schemas.retrieval import (
    CareerOut,
    CareerSkillOut,
    OccupationalContextOut,
    SkillOut,
)
from app.schemas.skill_gap_agent import SkillGapAnalysisOut, SkillGapNarrative
from app.schemas.user import UserSkillEvidenceOut, UserSkillOut
from app.services.skill_gap_service import classify_skill_gap


CAREER = CareerOut(career_id="C_TEST", canonical_name="Test Career", domain="Test Domain")


def required(skill_id: str, name: str, basis: str) -> CareerSkillOut:
    return CareerSkillOut(
        relationship_id=f"R_{skill_id}",
        skill=SkillOut(
            skill_id=skill_id, canonical_name=name,
            skill_group_id="SG_TEST", status="active",
        ),
        evidence_class="CORE",
        confidence="high",
        mapping_method="test",
        evidence_source_text=basis,
    )


REQUIRED = [
    required("S001", "SQL", "Database query and management evidence."),
    required("S002", "Networking", "Network configuration evidence."),
    required("S003", "Database Management", "Database administration evidence."),
]


def make_gap():
    return classify_skill_gap(
        user_id=9,
        career=CAREER,
        career_skills=REQUIRED,
        user_skills=[
            UserSkillOut(
                user_skill_id=1, claimed_skill="SQL", skill_id="S001",
                normalized_skill="SQL", evidence_status="linked", confidence="high",
                evidence=[UserSkillEvidenceOut(evidence_id=1, evidence_type="project")],
            ),
            UserSkillOut(
                user_skill_id=2, claimed_skill="Networking", skill_id="S002",
                normalized_skill="Networking", evidence_status="none", confidence="unknown",
                evidence=[],
            ),
            UserSkillOut(
                user_skill_id=3, claimed_skill="Unknown claim", skill_id=None,
                evidence_status="none", confidence="unknown", evidence=[],
            ),
        ],
    )


GAP = make_gap()
CONTEXT = OccupationalContextOut(
    career=CAREER,
    occupations=[],
    career_skills=REQUIRED,
    competencies=[],
    tasks={},
    technologies={},
    source_mappings={},
)


class ScriptedLLM:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def complete_json(self, system, user, max_tokens=2000):
        self.calls.append((system, user, max_tokens))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def with_context():
    return mock.patch.object(roadmap_module.rs, "get_occupational_context", return_value=CONTEXT)


def main():
    llm = ScriptedLLM({
        "summary": "This focus list follows the existing skill-gap result for Test Career."
    })
    with with_context():
        result = LearningRoadmapAgent(llm).run(GAP)

    assert result.skill_gap is GAP
    assert result.narrative_source == "llm" and result.llm_error is None
    assert [item.skill_id for item in result.items] == ["S002", "S003"]
    assert [item.gap_status for item in result.items] == ["matched_claimed_only", "missing"]
    assert [item.learning_action for item in result.items] == [
        "add_linked_evidence", "develop_skill",
    ]
    assert [item.knowledge_base_basis for item in result.items] == [
        "Network configuration evidence.", "Database administration evidence.",
    ]
    assert "S001" not in llm.calls[0][1] and "Unknown claim" not in llm.calls[0][1]
    assert llm.calls[0][2] == roadmap_module.LLM_MAX_TOKENS
    print("PASS: outstanding skill-gap items stay KB-grounded and keep source order")

    # A Step 10 result is accepted directly; it is not reclassified.
    analysis = SkillGapAnalysisOut(
        skill_gap=GAP,
        narrative=SkillGapNarrative(summary="Existing summary", conclusion="Existing conclusion"),
        narrative_source="fallback-template",
    )
    with with_context():
        wrapped = LearningRoadmapAgent().run(analysis)
    assert wrapped.skill_gap is GAP
    print("PASS: accepts the existing SkillGapAnalysisOut contract unchanged")

    for response in (
        {"summary": "Take a course before learning this."},
        {"summary": "Continue learning SQL."},
        {"summary": "This focus list suggests practicing at work."},
        {"summary": "Focus on the current gap.", "items": []},
    ):
        with with_context():
            rejected = LearningRoadmapAgent(ScriptedLLM(response)).run(GAP)
        assert rejected.narrative_source == "fallback-template"
        assert rejected.llm_error
        assert rejected.skill_gap is GAP
    print("PASS: unsupported resources, unrelated KB skills, and extra output fields fall back")

    with with_context():
        failed = LearningRoadmapAgent(ScriptedLLM(ConnectionError("provider unavailable"))).run(GAP)
    assert failed.narrative_source == "fallback-template" and failed.llm_error
    assert len(failed.items) == 2
    print("PASS: provider failure preserves the deterministic roadmap and reports fallback")

    incomplete_context = CONTEXT.model_copy(update={"career_skills": REQUIRED[:2]})
    with mock.patch.object(
        roadmap_module.rs, "get_occupational_context", return_value=incomplete_context
    ):
        try:
            LearningRoadmapAgent().run(GAP)
            raise AssertionError("missing KB skill context must be surfaced")
        except RoadmapContextError:
            pass
    print("PASS: missing KB grounding is surfaced instead of silently omitted")

    changed_requirement = REQUIRED[2].model_copy(
        update={"skill": REQUIRED[2].skill.model_copy(update={"canonical_name": "Invented Skill"})}
    )
    mismatched_context = CONTEXT.model_copy(
        update={"career_skills": REQUIRED[:2] + [changed_requirement]}
    )
    with mock.patch.object(
        roadmap_module.rs, "get_occupational_context", return_value=mismatched_context
    ):
        try:
            LearningRoadmapAgent().run(GAP)
            raise AssertionError("skill-gap metadata must match the KB")
        except RoadmapContextError:
            pass
    print("PASS: mismatched skill metadata is rejected")

    fields = set(result.model_dump())
    assert not any("priority" in field.lower() or field in {"score", "rank"} for field in fields)
    print("ALL LEARNING ROADMAP UNIT TESTS PASSED.")


if __name__ == "__main__":
    main()
