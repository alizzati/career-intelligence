"""Focused tests for Step 17 evaluation orchestration, contracts, and adapters."""
import json

import pytest
from pydantic import ValidationError

from app.evaluation import (
    CONFIGURATION_DEFINITIONS,
    CareerRelevanceLabel,
    EvaluationCase,
    EvaluationReferences,
    KbReference,
    MetricResult,
    RecommendationPrediction,
    RecommendationReference,
    RoadmapItemPrediction,
    RoadmapPrediction,
    SkillGapPrediction,
    SkillGapReference,
    SkillStatusLabel,
    VerificationPrediction,
    VerificationReference,
    case_from_analysis_record,
    evaluate_case,
    evaluate_report,
    get_configuration,
    recommendation_prediction_from_outputs,
    roadmap_prediction_from_outputs,
    skill_gap_prediction_from_outputs,
    validate_configuration_manifest,
    verification_prediction_from_outputs,
)


def _career_outputs():
    return [
        {
            "career_id": "C1",
            "canonical_name": "Career One",
            "domain": "software",
            "fit_score": 0.75,
            "matched_skills": [{"skill_id": "s1"}],
            "claimed_only_skills": [{"skill_id": "s2"}],
            "missing_skills_preview": [{"skill_id": "s3"}],
        },
        {
            "career_id": "C2",
            "canonical_name": "Career Two",
            "domain": "data",
            "fit_score": 0.25,
            "matched_skills": [],
            "claimed_only_skills": [],
            "missing_skills_preview": [{"skill_id": "s4"}],
        },
    ]


def _gap_output():
    row = {
        "career_id": "C1",
        "matched_evidenced": [{"skill_id": "s1"}],
        "matched_claimed_only": [{"skill_id": "s2"}],
        "missing": [{"skill_id": "s3"}],
        "unmatched_user_claims": [
            {"user_skill_id": 9, "claimed_skill": "unmapped claim"},
        ],
    }
    return {"skill_gap": row, "narrative": {}, "narrative_source": "fallback-template"}


def _roadmap_output():
    return {
        "items": [
            {
                "skill_id": "s3",
                "gap_status": "missing",
                "learning_action": "develop_skill",
                "knowledge_base_basis": "KB record",
            },
        ],
    }


def _verification_output():
    return {
        "status": "PASS",
        "checks": [{"check": "recommendation.ranking", "status": "PASS"}],
        "unsupported_claims": [],
    }


def _analysis_record(final_status="VERIFIED"):
    return {
        "schema_version": "analysis_log/1.0",
        "analysis_id": "abc123",
        "timestamp": "2026-10-30T00:00:00Z",
        "user_profile_id": 7,
        "source": "profile",
        "agent_outputs": {
            "career_recommendation": _career_outputs(),
            "skill_gap": _gap_output(),
            "roadmap": _roadmap_output(),
            "verification": _verification_output(),
        },
        "verification_result": {
            "status": "PASS",
            "checks": [{"check": "recommendation.ranking", "status": "PASS"}],
            "unsupported_claims": [],
            "required_revision": [],
        },
        "revision_count": 2,
        "final_result": {"final_status": final_status},
    }


def _references(profile_id="p1"):
    return EvaluationReferences(
        recommendation=RecommendationReference(
            profile_id=profile_id,
            labels=[
                CareerRelevanceLabel(career_id="C1", relevance=1),
                CareerRelevanceLabel(career_id="C2", relevance=0),
            ],
        ),
        skill_gap=SkillGapReference(
            profile_id=profile_id,
            career_id="C1",
            required_skill_status=[
                SkillStatusLabel(skill_id="s1", status="matched_evidenced"),
                SkillStatusLabel(skill_id="s2", status="missing"),
            ],
            unmatched_user_claim_keys=["user_skill_id:9"],
        ),
        verification=VerificationReference(
            profile_id=profile_id,
            injected_fault_ids=["verification:fake"],
            audited_claim_ids=["verification:fake", "clean:claim"],
        ),
        kb=KbReference(
            canonical_career_ids=["C1", "C2"],
            required_skill_ids_by_career={"C1": ["s1", "s2"], "C2": ["s4"]},
            known_skill_ids=["s1", "s2", "s4"],
        ),
    )


def _case(**overrides):
    values = dict(
        profile_id="p1",
        config_id="F",
        references=_references(),
        recommendation=RecommendationPrediction(
            ranking=["C1", "C2"],
            referenced_skill_ids={"C1": ["s1", "s2"], "C2": ["s4"]},
            evidenced_skill_ids={"C1": ["s1"], "C2": []},
            evidence_reference_counts={"C1": {"s1": 1}, "C2": {}},
        ),
        skill_gap=SkillGapPrediction(
            career_id="C1",
            required_skill_status={"s1": "matched_evidenced", "s2": "missing"},
            unmatched_user_claim_keys=["user_skill_id:9"],
        ),
        roadmap=RoadmapPrediction(items=[
            RoadmapItemPrediction(
                skill_id="s2",
                gap_status="missing",
                learning_action="develop_skill",
                knowledge_base_basis="KB record",
            ),
        ]),
        verification=VerificationPrediction(
            status="PASS",
            checks=[],
            reported_claim_ids=["verification:fake"],
            first_pass_status="FAIL",
            revision_count=1,
        ),
    )
    values.update(overrides)
    return EvaluationCase(**values)


def test_full_case_metrics_are_computed():
    profile = evaluate_case(_case())
    metrics = profile.metrics
    assert metrics["career.hit_at_1"].value == 1.0
    assert metrics["career.hit_at_3"].value == 1.0
    assert metrics["career.ndcg_at_3"].value == pytest.approx(1.0)
    assert metrics["career.mrr"].value == 1.0
    assert metrics["skill_gap.status_macro_f1"].value == pytest.approx(1.0)
    assert metrics["skill_gap.status_accuracy"].value == pytest.approx(1.0)
    assert metrics["skill_gap.over_credit_rate"].value == 0.0
    assert metrics["skill_gap.unmatched_claim_recall"].value == 1.0
    assert metrics["verification.detection_recall"].value == 1.0
    assert metrics["verification.detection_precision"].value == 1.0
    assert metrics["verification.false_positive_rate"].value == 0.0
    assert metrics["verification.resolution"].value == 1.0
    assert metrics["verification.outcome_pass"].value == 1.0
    assert metrics["verification.revision_triggered"].value == 1.0
    assert metrics["verification.revision_count"].value == 1.0
    assert metrics["traceability.recommendation_l1_rate"].value == 1.0
    assert metrics["traceability.recommendation_l2_rate"].value == 1.0
    assert metrics["traceability.recommendation_l3_rate"].value == pytest.approx(0.5)
    assert metrics["traceability.gap_item_lineage_rate"].value == 1.0
    assert metrics["roadmap.coverage"].value == 1.0
    assert metrics["roadmap.unsupported_item_rate"].value == 0.0
    assert metrics["roadmap.grounding_rate"].value == 1.0
    assert metrics["operational.failure"].value == 0.0


def test_missing_reference_labels_skip_label_dependent_metrics():
    case = _case(references=None)
    profile = evaluate_case(case)
    assert "career.hit_at_1" not in profile.metrics
    assert "skill_gap.status_macro_f1" not in profile.metrics
    assert "traceability.recommendation_l1_rate" not in profile.metrics
    assert any("no reference labels" in warning for warning in profile.warnings)


def test_empty_reference_labels_are_reported_as_unavailable():
    references = EvaluationReferences(
        recommendation=RecommendationReference(profile_id="p1", labels=[]),
    )
    metrics = evaluate_case(_case(references=references)).metrics
    assert metrics["career.hit_at_1"].status == "unavailable"
    assert "empty" in metrics["career.hit_at_1"].reason


def test_failed_run_keeps_labels_but_reports_unavailable_prediction():
    case = _case(run_status="failed", recommendation=None)
    metrics = evaluate_case(case).metrics
    assert metrics["career.hit_at_1"].status == "unavailable"
    assert "prediction is unavailable" in metrics["career.hit_at_1"].reason
    assert metrics["operational.failure"].value == 1.0


def test_skill_gap_career_mismatch_is_unavailable():
    case = _case(skill_gap=SkillGapPrediction(
        career_id="C2",
        required_skill_status={"s1": "missing"},
    ))
    metrics = evaluate_case(case).metrics
    assert metrics["skill_gap.status_macro_f1"].status == "unavailable"
    assert "career_id" in metrics["skill_gap.status_macro_f1"].reason


def test_unmatched_user_claims_are_not_reinterpreted_as_missing():
    references = EvaluationReferences(
        skill_gap=SkillGapReference(
            profile_id="p1",
            career_id="C1",
            required_skill_status=[SkillStatusLabel(skill_id="s1", status="missing")],
            unmatched_user_claim_keys=["claim:x"],
        ),
    )
    case = _case(
        references=references,
        skill_gap=SkillGapPrediction(
            career_id="C1",
            required_skill_status={"s1": "missing"},
            unmatched_user_claim_keys=["claim:x"],
        ),
    )
    metrics = evaluate_case(case).metrics
    assert metrics["skill_gap.missing_set.recall"].value == 1.0
    assert metrics["skill_gap.unmatched_claim_recall"].value == 1.0
    assert not any("unmatched_user_claims." in name for name in metrics)


def test_resolution_is_unavailable_when_first_pass_already_passed():
    case = _case(verification=VerificationPrediction(
        status="PASS",
        first_pass_status="PASS",
        revision_count=0,
    ))
    metrics = evaluate_case(case).metrics
    assert metrics["verification.resolution"].status == "unavailable"


def test_roadmap_uses_reference_gap_when_available():
    # The system prediction says s2 is evidenced (so it would not be a roadmap
    # target), while the reference says s2 is missing. The reference wins.
    case = _case(
        skill_gap=SkillGapPrediction(
            career_id="C1",
            required_skill_status={"s1": "matched_evidenced", "s2": "matched_evidenced"},
        ),
    )
    metrics = evaluate_case(case).metrics
    assert metrics["roadmap.coverage"].value == 1.0


def test_report_averages_profile_metrics_and_reports_coverage():
    def make(profile_id, ranking):
        return _case(
            profile_id=profile_id,
            references=_references(profile_id),
            recommendation=RecommendationPrediction(
                ranking=ranking,
                referenced_skill_ids={"C1": ["s1", "s2"], "C2": ["s4"]},
                evidenced_skill_ids={"C1": ["s1"], "C2": []},
                evidence_reference_counts={"C1": {"s1": 1}, "C2": {}},
            ),
        )

    report = evaluate_report([make("p1", ["C1", "C2"]), make("p2", ["C2", "C1"])])
    assert report.case_count == 2
    assert report.failed_case_count == 0
    assert report.metrics["career.hit_at_1"].value == pytest.approx(0.5)
    assert report.metrics["career.hit_at_1"].n == 2
    assert report.metrics["career.hit_at_1"].skipped == 0


def test_report_rejects_empty_batch():
    with pytest.raises(ValueError):
        evaluate_report([])


def test_report_rejects_mixed_configurations():
    with pytest.raises(ValueError):
        evaluate_report([_case(config_id="F"), _case(profile_id="p2", config_id="B3")])


def test_report_is_json_serializable_and_versioned():
    report = evaluate_report([_case()])
    payload = report.to_dict()
    encoded = json.dumps(payload, sort_keys=True)
    assert '"schema_version": "evaluation/1.0"' in encoded
    assert payload["config_id"] == "F"
    assert payload["metrics"]["career.hit_at_1"]["status"] == "computed"


def test_configuration_definitions_match_the_agreed_design():
    assert set(CONFIGURATION_DEFINITIONS) == {"B0", "B2", "B3", "F"}
    assert get_configuration("B0").uses_occupational_kb is False
    assert get_configuration("B0").uses_verification_agent is False
    assert get_configuration("B2").uses_occupational_kb is True
    assert get_configuration("B2").uses_deterministic_matching is False
    assert get_configuration("B3").uses_deterministic_matching is True
    assert get_configuration("B3").uses_verification_agent is False
    assert get_configuration("F").uses_verification_agent is True
    assert get_configuration("F").uses_revision_loop is True


def test_configuration_manifest_validation():
    assert validate_configuration_manifest({"config_id": "F"}).config_id == "F"
    with pytest.raises(ValueError):
        validate_configuration_manifest({"config_id": "A"})
    with pytest.raises(ValueError):
        validate_configuration_manifest({})


def test_recommendation_adapter_preserves_rank_and_lineage():
    prediction = recommendation_prediction_from_outputs(_career_outputs())
    assert prediction.ranking == ["C1", "C2"]
    assert prediction.referenced_skill_ids["C1"] == ["s1", "s2", "s3"]
    assert prediction.evidenced_skill_ids["C1"] == ["s1"]
    assert prediction.evidence_reference_counts["C1"] == {"s1": 1}
    assert prediction.fit_scores["C1"] == pytest.approx(0.75)


def test_skill_gap_adapter_keeps_unmatched_claims_separate():
    prediction = skill_gap_prediction_from_outputs(_gap_output())
    assert prediction.career_id == "C1"
    assert prediction.required_skill_status == {
        "s1": "matched_evidenced",
        "s2": "matched_claimed_only",
        "s3": "missing",
    }
    assert prediction.unmatched_user_claim_keys == ["user_skill_id:9"]
    assert "unmapped claim" not in prediction.required_skill_status


def test_roadmap_and_verification_adapters():
    roadmap = roadmap_prediction_from_outputs(_roadmap_output())
    assert roadmap.items[0].skill_id == "s3"
    assert roadmap.items[0].learning_action == "develop_skill"
    verification = verification_prediction_from_outputs(
        {
            "status": "FAIL",
            "checks": [{"check": "roadmap.coverage", "status": "REVISE"}],
            "unsupported_claims": [
                {"component": "roadmap_summary", "claim": "invented claim"},
            ],
        },
        first_pass_status="FAIL",
        revision_count=2,
    )
    assert verification.status == "FAIL"
    assert verification.checks[0].status == "REVISE"
    assert verification.reported_claim_ids == ["roadmap_summary::invented claim"]
    assert verification.revision_count == 2


def test_case_from_analysis_record_uses_recorded_values():
    case = case_from_analysis_record(_analysis_record(), config_id="F")
    assert case.profile_id == "7"
    assert case.config_id == "F"
    assert case.run_status == "completed"
    assert case.recommendation.ranking == ["C1", "C2"]
    assert case.skill_gap.career_id == "C1"
    assert case.roadmap.items[0].skill_id == "s3"
    assert case.verification.status == "PASS"
    assert case.operational.revision_count == 2


def test_case_from_analysis_record_marks_error_runs_failed():
    case = case_from_analysis_record(_analysis_record("ERROR"), config_id="F")
    assert case.run_status == "failed"


def test_case_from_analysis_record_requires_an_agreed_config():
    with pytest.raises(ValidationError):
        case_from_analysis_record(_analysis_record(), config_id="B1")


@pytest.mark.parametrize(
    "builder",
    [
        lambda: RecommendationReference(
            profile_id="p1",
            labels=[
                CareerRelevanceLabel(career_id="C1", relevance=1),
                CareerRelevanceLabel(career_id="C1", relevance=0),
            ],
        ),
        lambda: RecommendationReference(
            profile_id="p1",
            labels=[CareerRelevanceLabel(career_id="C1", relevance=-1)],
        ),
        lambda: SkillGapReference(
            profile_id="p1",
            career_id="C1",
            required_skill_status=[
                SkillStatusLabel(skill_id="s1", status="missing"),
                SkillStatusLabel(skill_id="s1", status="matched_evidenced"),
            ],
        ),
        lambda: VerificationReference(
            profile_id="p1",
            injected_fault_ids=["f1"],
            audited_claim_ids=["clean"],
        ),
        lambda: KbReference(
            canonical_career_ids=["C1"],
            required_skill_ids_by_career={"C9": ["s1"]},
        ),
        lambda: RoadmapPrediction(items=[
            RoadmapItemPrediction(
                skill_id="s1", gap_status="missing", learning_action="develop_skill",
            ),
            RoadmapItemPrediction(
                skill_id="s1", gap_status="missing", learning_action="develop_skill",
            ),
        ]),
        lambda: EvaluationReferences(
            recommendation=RecommendationReference(profile_id="p1"),
            skill_gap=SkillGapReference(profile_id="p2", career_id="C1"),
        ),
    ],
)
def test_malformed_reference_inputs_are_rejected(builder):
    with pytest.raises(ValidationError):
        builder()


def test_metric_result_requires_consistent_status_and_value():
    with pytest.raises(ValidationError):
        MetricResult(name="m", status="computed", value=None)
    with pytest.raises(ValidationError):
        MetricResult(name="m", status="unavailable", value=1.0)


def _case_with_ranking(profile_id, ranking):
    return _case(
        profile_id=profile_id,
        references=_references(profile_id),
        recommendation=RecommendationPrediction(
            ranking=ranking,
            referenced_skill_ids={"C1": ["s1", "s2"], "C2": ["s4"]},
            evidenced_skill_ids={"C1": ["s1"], "C2": []},
            evidence_reference_counts={"C1": {"s1": 1}, "C2": {}},
        ),
    )


def test_report_averages_repeats_within_a_profile_first():
    # p1 is run twice (0.0 and 1.0 for Hit@1) -> profile mean 0.5.
    # p2 is run once (1.0). Profile-level mean is 0.75, not the raw 2/3.
    report = evaluate_report(
        [
            _case_with_ranking("p1", ["C2", "C1"]),
            _case_with_ranking("p1", ["C1", "C2"]),
            _case_with_ranking("p2", ["C1", "C2"]),
        ]
    )
    assert report.case_count == 3
    assert report.profile_count == 2
    assert report.metrics["career.hit_at_1"].value == pytest.approx(0.75)
    assert report.metrics["career.hit_at_1"].n == 2
    assert report.metrics["career.hit_at_1"].skipped == 0


def test_report_counts_profiles_without_a_value_as_skipped():
    missing_reference = _case(profile_id="p2", references=None)
    report = evaluate_report([_case_with_ranking("p1", ["C1", "C2"]), missing_reference])
    hit = report.metrics["career.hit_at_1"]
    assert hit.status == "computed"
    assert hit.value == pytest.approx(1.0)
    assert hit.n == 1
    assert hit.skipped == 1


def test_report_reports_all_profiles_skipped_as_unavailable():
    report = evaluate_report([
        _case(profile_id="p1", references=None),
        _case(profile_id="p2", references=None),
    ])
    hit = report.metrics.get("career.hit_at_1")
    # No label-dependent metric is even created when no reference exists.
    assert hit is None or hit.status == "unavailable"


def test_tie_at_three_is_reported_from_fit_scores():
    case = _case(
        recommendation=RecommendationPrediction(
            ranking=["C1", "C2", "C3", "C4"],
            fit_scores={"C1": 0.5, "C2": 0.5, "C3": 0.5, "C4": 0.5},
            referenced_skill_ids={"C1": ["s1", "s2"], "C2": ["s4"]},
            evidenced_skill_ids={"C1": ["s1"], "C2": []},
            evidence_reference_counts={"C1": {"s1": 1}, "C2": {}},
        ),
    )
    metric = evaluate_case(case).metrics["career.tie_at_3"]
    assert metric.status == "computed"
    assert metric.value == 1.0


def test_tie_at_three_is_unavailable_without_enough_scored_careers():
    metric = evaluate_case(_case()).metrics["career.tie_at_3"]
    assert metric.status == "unavailable"


def test_report_computes_stability_across_repeated_runs():
    first = _case_with_ranking("p1", ["C1", "C2", "C3"])
    second = _case_with_ranking("p1", ["C1", "C2", "C4"])
    report = evaluate_report([first, second])
    stability = report.metrics["career.stability_at_3"]
    assert stability.status == "computed"
    assert stability.value == pytest.approx(0.5)  # {C1,C2,C3} vs {C1,C2,C4}
    assert stability.n == 1
    assert stability.skipped == 0


def test_analysis_record_feeds_a_report_end_to_end():
    case = case_from_analysis_record(
        _analysis_record(),
        config_id="F",
        references=_references("7"),
    )
    report = evaluate_report([case])
    assert report.schema_version == "evaluation/1.0"
    assert report.config_id == "F"
    assert report.case_count == 1
    assert report.metrics["career.hit_at_1"].value == 1.0
    assert report.metrics["skill_gap.status_accuracy"].value == pytest.approx(0.5)
    assert report.metrics["operational.failure"].value == 0.0
    json.dumps(report.to_dict())


def test_report_stability_is_unavailable_for_single_runs():
    report = evaluate_report([
        _case_with_ranking("p1", ["C1", "C2"]),
        _case_with_ranking("p2", ["C1", "C2"]),
    ])
    stability = report.metrics["career.stability_at_3"]
    assert stability.status == "unavailable"
    assert stability.skipped == 2
