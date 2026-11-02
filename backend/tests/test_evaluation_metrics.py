"""Focused unit tests for the Step 17 metric calculations."""
import math

import pytest

from app.evaluation.metrics import (
    classification_metrics,
    detection_metrics,
    gap_set_metrics,
    hit_at_k,
    mean_pairwise_top_k_stability,
    ndcg_at_k,
    over_credit_rate,
    reciprocal_rank,
    roadmap_metrics,
    set_metrics,
    tie_at_cutoff,
    top_k_overlap,
    traceability_metrics,
    unmatched_claim_metrics,
)
from app.evaluation.schemas import (
    CareerRelevanceLabel,
    KbReference,
    RecommendationPrediction,
    RoadmapItemPrediction,
    RoadmapPrediction,
    SkillGapPrediction,
)


def _relevance(**values):
    return {key: float(value) for key, value in values.items()}


def test_hit_at_k_binary():
    relevance = _relevance(C1=0, C2=1, C3=0)
    ranking = ["C1", "C2", "C3"]
    assert hit_at_k(ranking, relevance, 1) == 0.0
    assert hit_at_k(ranking, relevance, 3) == 1.0


def test_hit_at_k_without_relevant_labels_is_undefined():
    assert hit_at_k(["C1", "C2"], _relevance(C1=0, C2=0), 1) is None


def test_hit_at_k_rejects_non_positive_k():
    with pytest.raises(ValueError):
        hit_at_k(["C1"], _relevance(C1=1), 0)


def test_ndcg_at_3_matches_hand_computation():
    # Rel(C2)=2, Rel(C1)=1, ranking C1 then C2.
    relevance = _relevance(C1=1, C2=2)
    dcg = 1.0 / math.log2(2) + 3.0 / math.log2(3)
    idcg = 3.0 / math.log2(2) + 1.0 / math.log2(3)
    assert ndcg_at_k(["C1", "C2"], relevance, 3) == pytest.approx(dcg / idcg)


def test_ndcg_at_3_is_one_for_ideal_order():
    assert ndcg_at_k(["C2", "C1"], _relevance(C1=1, C2=2), 3) == pytest.approx(1.0)


def test_ndcg_is_undefined_without_positive_relevance():
    assert ndcg_at_k(["C1"], _relevance(C1=0), 3) is None


def test_reciprocal_rank_uses_first_relevant_position():
    relevance = _relevance(C1=0, C2=1)
    assert reciprocal_rank(["C1", "C2"], relevance) == pytest.approx(0.5)
    assert reciprocal_rank(["C1"], relevance) == 0.0
    assert reciprocal_rank(["C1"], _relevance(C1=0)) is None


def test_classification_metrics_hand_computed():
    reference = {
        "s1": "matched_evidenced",
        "s2": "missing",
        "s3": "matched_claimed_only",
        "s4": "missing",
    }
    prediction = {
        "s1": "matched_evidenced",
        "s2": "missing",
        "s3": "matched_evidenced",  # wrong: credited a claimed-only skill
        "s4": "missing",
    }
    result = classification_metrics(reference, prediction)
    assert result["status_accuracy"] == pytest.approx(3 / 4)
    assert result["per_status"]["matched_evidenced"]["precision"] == pytest.approx(0.5)
    assert result["per_status"]["matched_evidenced"]["recall"] == pytest.approx(1.0)
    assert result["per_status"]["matched_evidenced"]["f1"] == pytest.approx(2 / 3)
    assert result["per_status"]["matched_claimed_only"]["f1"] == 0.0
    assert result["per_status"]["missing"]["f1"] == pytest.approx(1.0)
    assert result["status_macro_f1"] == pytest.approx((2 / 3 + 0.0 + 1.0) / 3)


def test_classification_missing_prediction_counts_as_false_negative():
    result = classification_metrics({"s1": "missing"}, {})
    assert result["per_status"]["missing"]["recall"] == 0.0
    assert result["per_status"]["missing"]["precision"] == 0.0
    assert result["status_macro_f1"] == 0.0


def test_classification_empty_reference_is_undefined():
    result = classification_metrics({}, {"s1": "missing"})
    assert result["status_macro_f1"] is None
    assert result["status_accuracy"] is None


def test_set_metrics_empty_denominators_return_none():
    result = set_metrics(set(), set())
    assert result["precision"] is None
    assert result["recall"] is None
    assert result["f1"] is None


def test_set_metrics_hand_computed():
    result = set_metrics({"a"}, {"a", "b"})
    assert result["precision"] == pytest.approx(0.5)
    assert result["recall"] == pytest.approx(1.0)
    assert result["f1"] == pytest.approx(2 / 3)


def test_gap_set_metrics_separate_categories():
    reference = {"s1": "missing", "s2": "matched_claimed_only"}
    prediction = {"s1": "missing", "s2": "missing"}
    result = gap_set_metrics(reference, prediction)
    assert result["missing"]["recall"] == pytest.approx(1.0)
    assert result["missing"]["precision"] == pytest.approx(0.5)
    assert result["matched_claimed_only"]["recall"] == 0.0


def test_over_credit_rate_counts_only_reference_missing_skills():
    reference = {"s1": "missing", "s2": "missing", "s3": "matched_evidenced"}
    prediction = {"s1": "matched_evidenced", "s2": "missing", "s3": "missing"}
    result = over_credit_rate(reference, prediction)
    assert result["rate"] == pytest.approx(0.5)
    assert result["credited"] == 1
    assert result["reference_missing"] == 2


def test_over_credit_is_undefined_without_reference_missing_skills():
    assert over_credit_rate({"s1": "matched_evidenced"}, {})["rate"] is None


def test_unmatched_claim_metrics_are_claim_level_only():
    result = unmatched_claim_metrics(["u1", "u2"], ["u1"])
    assert result["precision"] == pytest.approx(1.0)
    assert result["recall"] == pytest.approx(0.5)
    assert result["tp"] == 1


def test_detection_metrics_hand_computed():
    result = detection_metrics(
        ["a", "b"], ["a", "c"], ["a", "b", "c", "d"],
    )
    assert result["detection_recall"] == pytest.approx(0.5)
    assert result["detection_precision"] == pytest.approx(0.5)
    assert result["false_positive_rate"] == pytest.approx(0.5)
    assert result["tp"] == 1 and result["fp"] == 1 and result["fn"] == 1


def test_false_positive_rate_unavailable_without_audited_claims():
    result = detection_metrics(["a"], ["a", "b"], None)
    assert result["false_positive_rate"] is None


def test_roadmap_metrics_coverage_and_grounding():
    gap = {"s1": "missing", "s2": "matched_claimed_only", "s3": "matched_evidenced"}
    roadmap = RoadmapPrediction(items=[
        RoadmapItemPrediction(
            skill_id="s1", gap_status="missing", learning_action="develop_skill",
            knowledge_base_basis="KB record 1",
        ),
        RoadmapItemPrediction(
            skill_id="s2", gap_status="matched_claimed_only",
            learning_action="add_linked_evidence", knowledge_base_basis="KB record 2",
        ),
        RoadmapItemPrediction(
            skill_id="s4", gap_status="missing", learning_action="develop_skill",
            knowledge_base_basis="KB record 4",
        ),
    ])
    result = roadmap_metrics(roadmap, gap)
    assert result["coverage"] == pytest.approx(1.0)
    assert result["unsupported_item_rate"] == pytest.approx(1 / 3)
    assert result["grounding_rate"] == pytest.approx(1.0)
    assert result["status_consistency"] == pytest.approx(1.0)
    assert result["action_consistency"] == pytest.approx(1.0)


def test_roadmap_metrics_with_no_expected_items_are_undefined():
    result = roadmap_metrics(RoadmapPrediction(items=[]), {"s1": "matched_evidenced"})
    assert result["coverage"] is None
    assert result["unsupported_item_rate"] is None
    assert result["grounding_rate"] is None


def test_traceability_levels_are_capped_without_evidence():
    kb = KbReference(
        canonical_career_ids=["C1", "C2"],
        required_skill_ids_by_career={"C1": ["s1", "s2"], "C2": ["s3"]},
        known_skill_ids=["s1", "s2", "s3"],
    )
    prediction = RecommendationPrediction(
        ranking=["C1", "C2"],
        referenced_skill_ids={"C1": ["s1", "s2"], "C2": ["s3"]},
        evidenced_skill_ids={"C1": ["s1"], "C2": []},
        evidence_reference_counts={"C1": {"s1": 1}, "C2": {}},
    )
    gap = SkillGapPrediction(
        career_id="C1",
        required_skill_status={"s1": "matched_evidenced", "s2": "missing"},
    )
    result = traceability_metrics(prediction, kb, gap)
    assert result["recommendation_l1_rate"] == pytest.approx(1.0)
    assert result["recommendation_l2_rate"] == pytest.approx(1.0)
    assert result["recommendation_l3_rate"] == pytest.approx(0.5)
    assert result["evidence_lineage_rate"] == pytest.approx(1.0)
    assert result["gap_item_lineage_rate"] == pytest.approx(1.0)


def test_traceability_drops_level_when_skill_is_not_a_kb_requirement():
    kb = KbReference(
        canonical_career_ids=["C1"],
        required_skill_ids_by_career={"C1": ["s1"]},
        known_skill_ids=["s1", "s9"],
    )
    prediction = RecommendationPrediction(
        ranking=["C1"],
        referenced_skill_ids={"C1": ["s1", "s9"]},
        evidenced_skill_ids={"C1": []},
    )
    result = traceability_metrics(prediction, kb)
    assert result["recommendation_l1_rate"] == pytest.approx(1.0)
    assert result["recommendation_l2_rate"] == pytest.approx(0.0)
    assert result["career_levels"] == {"C1": 1}


def test_traceability_empty_ranking_is_undefined():
    kb = KbReference(canonical_career_ids=["C1"], known_skill_ids=["s1"])
    result = traceability_metrics(RecommendationPrediction(ranking=[]), kb)
    assert result["recommendation_l1_rate"] is None
    assert result["evidence_lineage_rate"] is None


def test_tie_at_cutoff_detects_tie_across_boundary():
    scores = {"C1": 0.5, "C2": 0.5, "C3": 0.1}
    assert tie_at_cutoff(["C1", "C2", "C3"], scores, 1) is True
    assert tie_at_cutoff(["C1", "C2", "C3"], scores, 2) is False


def test_tie_at_cutoff_needs_a_career_beyond_the_cutoff():
    scores = {"C1": 0.5, "C2": 0.5}
    assert tie_at_cutoff(["C1", "C2"], scores, 1) is True
    assert tie_at_cutoff(["C1", "C2"], scores, 2) is None


def test_tie_at_cutoff_is_undefined_when_scores_are_missing():
    assert tie_at_cutoff(["C1", "C2"], {"C1": 0.5}, 1) is None


def test_tie_at_cutoff_rejects_non_positive_k():
    with pytest.raises(ValueError):
        tie_at_cutoff(["C1"], {}, 0)


def test_top_k_overlap_is_jaccard_of_prefix_sets():
    assert top_k_overlap(["C1", "C2", "C3"], ["C1", "C2", "C4"], 2) == pytest.approx(1.0)
    assert top_k_overlap(["C1", "C2", "C3"], ["C1", "C2", "C4"], 3) == pytest.approx(2 / 4)
    assert top_k_overlap([], [], 3) is None


def test_mean_pairwise_stability_averages_all_pairs():
    rankings = [["C1", "C2"], ["C1", "C2"], ["C2", "C1"]]
    # k=2: all top-2 sets are {C1, C2}, so every pair overlaps fully.
    assert mean_pairwise_top_k_stability(rankings, 2) == pytest.approx(1.0)
    # k=1: pairs are 1.0, 0.0, 0.0 -> mean 1/3.
    assert mean_pairwise_top_k_stability(rankings, 1) == pytest.approx(1 / 3)


def test_mean_pairwise_stability_needs_at_least_two_runs():
    assert mean_pairwise_top_k_stability([["C1"]], 1) is None
    assert mean_pairwise_top_k_stability([], 1) is None
