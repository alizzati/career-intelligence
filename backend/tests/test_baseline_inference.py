import json
from types import SimpleNamespace

import pytest

from app.evaluation.baseline_inference import (
    BaselineInferenceAgent,
    CareerOutputLabel,
    FrozenProfileBundle,
    FrozenProfileBundleExtractor,
    SkillMention,
)
from app.workflows.career_workflow import CareerWorkflow
from app.evaluation.adapters import case_from_analysis_record


class FakeLLM:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def complete_json(self, *, system, user, max_tokens):
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        return self.result


class SequenceLLM(FakeLLM):
    def __init__(self, results):
        super().__init__(None)
        self.results = list(results)

    def complete_json(self, *, system, user, max_tokens):
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        return self.results.pop(0)


def labels():
    return [CareerOutputLabel(career_id=f"C{i:02d}", career_name=f"Career {i}") for i in range(1, 11)]


def bundle():
    return FrozenProfileBundle(
        extracted_cv_text="Redacted CV: Python used in a project.",
        skill_mentions=[SkillMention(mention_id="m0001", text="Python", evidence_spans=["Python used in a project"] )],
        experience=[{"role_title": "Developer", "company": "Example"}],
        education=[{"institution": "Example University", "degree": "BSc"}],
    )


def ranked(career_labels):
    return [
        {"career_id": item.career_id, "rank": index, "rationale": "Profile evidence supports this ranking."}
        for index, item in enumerate(career_labels, start=1)
    ]


def test_b0_has_only_label_space_and_never_calls_okb_or_deterministic_components(monkeypatch):
    career_labels = labels()
    llm = FakeLLM({"recommendations": ranked(career_labels)})

    def forbidden(*args, **kwargs):
        raise AssertionError("B0 prohibited component was called")

    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_all_careers", forbidden)
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_all_skills", forbidden)
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_career_skills", forbidden)
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_career", forbidden)
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_occupational_context", forbidden)
    monkeypatch.setattr("app.agents.profile_agent.normalize_skill", forbidden)
    monkeypatch.setattr("app.services.career_fit_service.compute_career_fit", forbidden)
    monkeypatch.setattr("app.services.skill_gap_service.analyze_skill_gap", forbidden)

    result = BaselineInferenceAgent(llm_client=llm, configuration_id="B0").run(
        bundle(), career_labels=career_labels,
    )

    prompt = llm.calls[0]["user"]
    assert all(label.career_name in prompt and label.career_id in prompt for label in career_labels)
    assert "relations" not in prompt and "career-skill" not in prompt.lower()
    assert "Python" in prompt and "ground_truth" not in prompt
    assert result.skill_gap.status == "NOT_APPLICABLE"
    assert result.roadmap.status == "NOT_APPLICABLE"
    assert result.verification.status == "NOT_APPLICABLE"
    assert all(row.fit_score is None for row in result.recommendations)


def test_b0_rejects_ground_truth_fields_in_frozen_bundle():
    data = bundle().model_dump()
    data["ground_truth_career_ids"] = ["C01"]
    with pytest.raises(ValueError, match="ground_truth_career_ids"):
        FrozenProfileBundle.model_validate(data)


def test_shared_bundle_extractor_prompt_matches_frozen_bundle_key_contract():
    from app.evaluation.baseline_inference import FrozenProfileBundleExtractor

    system = FrozenProfileBundleExtractor.SYSTEM
    for key in (
        "skill_mentions",
        "role_title",
        "start_date",
        "end_date",
        "description",
        "institution",
        "issue_date",
        "expiry_date",
        "credential_url",
    ):
        assert f'"{key}"' in system
    assert '"dates"' in system  # explicitly disallowed
    assert "Never invent values" in system


def test_shared_bundle_extractor_has_no_okb_or_normalizer_context(monkeypatch):
    from app.evaluation.baseline_inference import FrozenProfileBundleExtractor

    llm = FakeLLM({
        "skill_mentions": [{"text": "Python", "evidence_spans": ["Python project"]}],
        "experience": [{"role_title": "Developer"}],
        "education": [{"institution": "Example University"}],
    })

    def forbidden(*args, **kwargs):
        raise AssertionError("pre-normalization extraction must not retrieve OKB data")

    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_all_careers", forbidden)
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_all_skills", forbidden)
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_career_skills", forbidden)
    frozen = FrozenProfileBundleExtractor(llm).run("Candidate: sinta@example.test; Python project")
    assert frozen.skill_mentions[0].mention_id == "m0001"
    assert frozen.skill_mentions[0].evidence_spans == ["Python project"]
    assert "sinta@example.test" not in frozen.extracted_cv_text
    assert "skill catalog" not in llm.calls[0]["user"].lower()
    assert "ground_truth" not in llm.calls[0]["user"]


def test_b0_workflow_accepts_cv_text_and_uses_extracted_bundle_without_okb(monkeypatch):
    career_labels = labels()
    llm = SequenceLLM([
        {"skill_mentions": [{"text": "Python", "evidence_spans": ["Python project"]}],
         "experience": [], "education": []},
        {"recommendations": ranked(career_labels)},
    ])
    def forbidden(*args, **kwargs):
        raise AssertionError("B0 workflow must not retrieve OKB records")
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_all_careers", forbidden)
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_all_skills", forbidden)
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_career_skills", forbidden)
    workflow = CareerWorkflow(configuration_id="B0", llm_client=llm, career_labels=career_labels)
    result = workflow.run(user_id=101, raw_profile_text="Python project appears in the redacted candidate CV")
    assert result["final_status"] == "UNVERIFIED"
    assert len(llm.calls) == 2
    assert result["baseline_result"].skill_gap.status == "NOT_APPLICABLE"


def test_b0_and_b2_are_executable_workflow_paths_without_verification_or_revision(monkeypatch):
    class ForbiddenAgent:
        def run(self, *args, **kwargs):
            raise AssertionError("prohibited downstream agent was invoked")

        def run_from_bundle(self, *args, **kwargs):
            raise AssertionError("baseline must not normalize or persist the shared bundle")

    b0_labels = labels()
    b0_llm = FakeLLM({"recommendations": ranked(b0_labels)})
    b0 = CareerWorkflow(
        configuration_id="B0", llm_client=b0_llm, career_labels=b0_labels,
        profile_agent=ForbiddenAgent(), career_recommendation_agent=ForbiddenAgent(),
        skill_gap_agent=ForbiddenAgent(), learning_roadmap_agent=ForbiddenAgent(),
        verification_agent=ForbiddenAgent(),
    )
    b0_result = b0.run(user_id=101, profile_bundle=bundle())
    assert b0_result["final_status"] == "UNVERIFIED"
    assert b0_result["revision_count"] == 0
    assert b0_result["verification"] is None
    assert b0_result["baseline_result"].configuration_id == "B0"

    careers = [SimpleNamespace(career_id=f"C{i:02d}", canonical_name=f"Career {i}", domain="IT") for i in range(1, 11)]
    relations = {c.career_id: [SimpleNamespace(
        relationship_id=f"R-{c.career_id}",
        skill=SimpleNamespace(skill_id=f"S-{c.career_id}", canonical_name="Skill", skill_group_id="G", status="active"),
        evidence_class="CORE", confidence="high", mapping_method="approved", evidence_source_text="source",
    )] for c in careers}
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_all_careers", lambda: careers)
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_career_skills", lambda cid: relations[cid])
    b2_llm = FakeLLM({
        "recommendations": ranked([CareerOutputLabel(career_id=c.career_id, career_name=c.canonical_name) for c in careers]),
        "skill_gap": {"career_id": "C01", "matched_evidenced": ["S-C01"], "matched_claimed_only": [], "missing": [], "unmatched_user_claims": [], "claim_matches": {"S-C01": ["m0001"]}, "claim_evidence": {"S-C01": [{"mention_id": "m0001", "evidence_spans": ["Python used in a project"]}]}},
    })
    b2 = CareerWorkflow(
        configuration_id="B2", llm_client=b2_llm,
        profile_agent=ForbiddenAgent(), career_recommendation_agent=ForbiddenAgent(),
        skill_gap_agent=ForbiddenAgent(), learning_roadmap_agent=ForbiddenAgent(),
        verification_agent=ForbiddenAgent(),
    )
    b2_result = b2.run(user_id=101, profile_bundle=bundle())
    assert b2_result["final_status"] == "UNVERIFIED"
    assert b2_result["revision_count"] == 0
    assert b2_result["verification"] is None
    assert b2_result["baseline_result"].configuration_id == "B2"


def test_b2_receives_all_ten_complete_relation_sets_and_uses_no_engines(monkeypatch):
    career_rows = [SimpleNamespace(career_id=f"C{i:02d}", canonical_name=f"Career {i}", domain="IT") for i in range(1, 11)]
    relation_rows = {
        career.career_id: [SimpleNamespace(
            relationship_id=f"R-{career.career_id}",
            skill=SimpleNamespace(skill_id=f"S-{career.career_id}", canonical_name=f"Skill {career.career_id}", skill_group_id="G1", status="active"),
            evidence_class="CORE", confidence="high", mapping_method="approved",
            evidence_source_text="approved source evidence",
        )]
        for career in career_rows
    }
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_all_careers", lambda: career_rows)
    calls = []
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_career_skills", lambda cid: calls.append(cid) or relation_rows[cid])
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_all_skills", lambda *a, **k: pytest.fail("B2 does not need the unrelated full skill catalog"))
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_occupational_context", lambda *a, **k: pytest.fail("B2 does not use semantic/occupational retrieval"))
    monkeypatch.setattr("app.services.career_fit_service.compute_career_fit", lambda *a, **k: pytest.fail("career scoring called"))
    monkeypatch.setattr("app.services.skill_gap_service.analyze_skill_gap", lambda *a, **k: pytest.fail("skill-gap engine called"))

    top_id = "C01"
    llm = FakeLLM({
        "recommendations": ranked([CareerOutputLabel(career_id=c.career_id, career_name=c.canonical_name) for c in career_rows]),
        "skill_gap": {
            "career_id": top_id,
            "matched_evidenced": [f"S-{top_id}"],
            "matched_claimed_only": [], "missing": [], "unmatched_user_claims": [],
            "claim_matches": {f"S-{top_id}": ["m0001"]},
            "claim_evidence": {f"S-{top_id}": [{"mention_id": "m0001", "evidence_spans": ["Python used in a project"]}]},
        },
    })
    result = BaselineInferenceAgent(llm_client=llm, configuration_id="B2").run(bundle())

    assert set(calls) == {career.career_id for career in career_rows}
    prompt_data = json.loads(llm.calls[0]["user"])
    system = llm.calls[0]["system"]
    assert "Return exactly one JSON object" in system
    assert '{"recommendations"' in system
    assert '"skill_gap"' in system
    assert "one mention may support several matched skills" in system
    relation_context = prompt_data["careers_and_complete_relations"]
    assert len(relation_context) == 10
    assert all(len(career["skills"]) == 1 for career in relation_context)
    first_relation = relation_context[0]["skills"][0]
    assert {"relationship_id", "skill_id", "canonical_name", "evidence_class", "confidence", "mapping_method", "evidence_source_text"} <= set(first_relation)
    assert result.skill_gap.career_id == top_id
    assert result.roadmap.status == "NOT_APPLICABLE"
    assert result.verification.status == "NOT_APPLICABLE"
    case = case_from_analysis_record(
        {"baseline_result": result.model_dump(mode="json")}, config_id="B2",
    )
    assert case.recommendation.ranking == [career.career_id for career in career_rows]
    assert case.skill_gap.required_skill_status == {f"S-{top_id}": "matched_evidenced"}
    assert case.roadmap is None and case.verification.status == "unavailable"


def _two_skill_career_rows():
    careers = [SimpleNamespace(career_id=f"C{i:02d}", canonical_name=f"Career {i}", domain="IT") for i in range(1, 11)]
    rows = {
        c.career_id: [SimpleNamespace(
            relationship_id=f"R-{c.career_id}",
            skill=SimpleNamespace(skill_id=f"S-{c.career_id}", canonical_name="Skill", skill_group_id="G", status="active"),
            evidence_class="CORE", confidence="high", mapping_method="approved", evidence_source_text="source",
        )]
        for c in careers
    }
    rows["C01"] = [
        SimpleNamespace(
            relationship_id="R-A",
            skill=SimpleNamespace(skill_id="S-A", canonical_name="Skill A", skill_group_id="G", status="active"),
            evidence_class="CORE", confidence="high", mapping_method="approved", evidence_source_text="source",
        ),
        SimpleNamespace(
            relationship_id="R-B",
            skill=SimpleNamespace(skill_id="S-B", canonical_name="Skill B", skill_group_id="G", status="active"),
            evidence_class="CORE", confidence="high", mapping_method="approved", evidence_source_text="source",
        ),
    ]
    return careers, rows


def test_b2_allows_one_mention_to_support_multiple_matched_skills(monkeypatch):
    careers, rows = _two_skill_career_rows()
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_all_careers", lambda: careers)
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_career_skills", lambda cid: rows[cid])
    llm = FakeLLM({
        "recommendations": ranked([CareerOutputLabel(career_id=c.career_id, career_name=c.canonical_name) for c in careers]),
        "skill_gap": {
            "career_id": "C01",
            "matched_evidenced": ["S-A", "S-B"],
            "matched_claimed_only": [],
            "missing": [],
            "unmatched_user_claims": [],
            "claim_matches": {"S-A": ["m0001"], "S-B": ["m0001"]},
            "claim_evidence": {
                "S-A": [{"mention_id": "m0001", "evidence_spans": ["Python used in a project"]}],
                "S-B": [{"mention_id": "m0001", "evidence_spans": ["Python used in a project"]}],
            },
        },
    })
    result = BaselineInferenceAgent(llm_client=llm, configuration_id="B2").run(bundle())
    assert set(result.skill_gap.matched_evidenced) == {"S-A", "S-B"}
    assert result.skill_gap.claim_evidence["S-A"][0].mention_id == "m0001"
    assert result.skill_gap.claim_evidence["S-B"][0].evidence_spans == ["Python used in a project"]


def test_b2_rejects_untraceable_many_to_many_evidence_relationship(monkeypatch):
    careers, rows = _two_skill_career_rows()
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_all_careers", lambda: careers)
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_career_skills", lambda cid: rows[cid])
    llm = FakeLLM({
        "recommendations": ranked([CareerOutputLabel(career_id=c.career_id, career_name=c.canonical_name) for c in careers]),
        "skill_gap": {
            "career_id": "C01", "matched_evidenced": ["S-A", "S-B"],
            "matched_claimed_only": [], "missing": [], "unmatched_user_claims": [],
            "claim_matches": {"S-A": ["m0001"], "S-B": ["m0001"]},
            "claim_evidence": {
                "S-A": [{"mention_id": "m0001", "evidence_spans": ["Python used in a project"]}],
                "S-B": [{"mention_id": "m0001", "evidence_spans": ["not present in the CV"]}],
            },
        },
    })
    with pytest.raises(ValueError, match="invalid evidence relationship.*S-B.*m0001"):
        BaselineInferenceAgent(llm_client=llm, configuration_id="B2").run(bundle())


def test_b2_rejects_mention_that_is_both_matched_and_unmatched(monkeypatch):
    careers, rows = _two_skill_career_rows()
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_all_careers", lambda: careers)
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_career_skills", lambda cid: rows[cid])
    llm = FakeLLM({
        "recommendations": ranked([CareerOutputLabel(career_id=c.career_id, career_name=c.canonical_name) for c in careers]),
        "skill_gap": {
            "career_id": "C01",
            "matched_evidenced": ["S-A"],
            "matched_claimed_only": [],
            "missing": ["S-B"],
            "unmatched_user_claims": ["m0001"],
            "claim_matches": {"S-A": ["m0001"]},
            "claim_evidence": {"S-A": [{"mention_id": "m0001", "evidence_spans": ["Python used in a project"]}]},
        },
    })
    with pytest.raises(ValueError, match="both matched and unmatched"):
        BaselineInferenceAgent(llm_client=llm, configuration_id="B2").run(bundle())


def test_baseline_system_prompt_is_config_specific_and_hashable():
    b0 = BaselineInferenceAgent.system_prompt("B0")
    b2 = BaselineInferenceAgent.system_prompt("B2")
    assert b0 != b2
    assert "skill_gap" not in b0
    assert '"skill_gap"' in b2
    with pytest.raises(ValueError):
        BaselineInferenceAgent.system_prompt("B3")


def test_frozen_extractor_preserves_explicit_and_absent_proficiency():
    class ExtractorLLM:
        def complete_json(self, **kwargs):
            return {"skill_mentions": [
                {"text": "Python", "proficiency": "advanced", "evidence_spans": ["Python"]},
                {"text": "SQL", "proficiency": None, "evidence_spans": ["SQL"]},
            ]}

    output = FrozenProfileBundleExtractor(ExtractorLLM()).run("Python and SQL")
    serialized = output.model_dump(mode="json")
    restored = FrozenProfileBundle.model_validate(serialized)
    assert [item.proficiency for item in restored.skill_mentions] == ["advanced", None]


def test_frozen_extractor_rejects_invalid_proficiency_type():
    class ExtractorLLM:
        def complete_json(self, **kwargs):
            return {"skill_mentions": [
                {"text": "Python", "proficiency": 5, "evidence_spans": ["Python"]},
            ]}

    with pytest.raises(Exception, match="proficiency"):
        FrozenProfileBundleExtractor(ExtractorLLM()).run("Python")


def test_profile_agent_receives_and_persists_bundle_proficiency(monkeypatch):
    from app.agents.profile_agent import ProfileAgent

    bundle_value = FrozenProfileBundle(
        extracted_cv_text="Database Management in a project",
        skill_mentions=[SkillMention(
            mention_id="m0001", text="Database Management", proficiency="intermediate",
            evidence_spans=["Database Management in a project"],
        )],
    )
    persisted = {}
    monkeypatch.setattr("app.agents.profile_agent.rs.get_all_skills", lambda: [])
    monkeypatch.setattr(
        "app.agents.profile_agent.us.add_user_skill",
        lambda **kwargs: persisted.update(kwargs) or SimpleNamespace(user_skill_id=7),
    )
    monkeypatch.setattr("app.agents.profile_agent.us.add_skill_evidence", lambda *args, **kwargs: None)
    result = ProfileAgent(llm_client=FakeLLM({})).run_from_bundle(3, bundle_value)
    assert persisted["proficiency"] == "intermediate"
    assert result.normalizations[0].mention_id == "m0001"
    assert result.normalizations[0].result.outcome == "unmatched"


def test_b2_rejects_incomplete_or_invented_gap_classification(monkeypatch):
    careers = [SimpleNamespace(career_id=f"C{i:02d}", canonical_name=f"Career {i}", domain="IT") for i in range(1, 11)]
    rows = {c.career_id: [SimpleNamespace(
        relationship_id=f"R-{c.career_id}",
        skill=SimpleNamespace(skill_id=f"S-{c.career_id}", canonical_name="Skill", skill_group_id="G", status="active"),
        evidence_class="CORE", confidence="high", mapping_method="approved", evidence_source_text="source",
    )] for c in careers}
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_all_careers", lambda: careers)
    monkeypatch.setattr("app.evaluation.baseline_inference.rs.get_career_skills", lambda cid: rows[cid])
    llm = FakeLLM({
        "recommendations": ranked([CareerOutputLabel(career_id=c.career_id, career_name=c.canonical_name) for c in careers]),
        "skill_gap": {"career_id": "C01", "matched_evidenced": [], "matched_claimed_only": [], "missing": [], "unmatched_user_claims": [], "claim_matches": {}, "claim_evidence": {}},
    })
    with pytest.raises(ValueError, match="classify each required skill"):
        BaselineInferenceAgent(llm_client=llm, configuration_id="B2").run(bundle())


def test_b0_na_capabilities_project_to_evaluation_without_fake_predictions():
    career_labels = labels()
    result = BaselineInferenceAgent(
        llm_client=FakeLLM({"recommendations": ranked(career_labels)}),
        configuration_id="B0",
    ).run(bundle(), career_labels=career_labels)
    case = case_from_analysis_record(
        {"baseline_result": result.model_dump(mode="json"), "final_result": {"final_status": "UNVERIFIED"}},
        config_id="B0",
    )
    assert case.recommendation is not None
    assert case.recommendation.ranking == [label.career_id for label in career_labels]
    assert case.recommendation.fit_scores == {}
    assert case.skill_gap is None
    assert case.roadmap is None
    assert case.verification.status == "unavailable"
