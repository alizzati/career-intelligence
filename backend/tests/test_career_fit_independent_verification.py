"""Independent numerical checks for the implemented career-fit calculation."""
from types import SimpleNamespace

import pytest

from app.agents.career_recommendation_agent import CareerRecommendationAgent
from app.services import career_fit_service as fit_service
from app.services import retrieval_service as rs
from app.services import user_service as us


WEIGHTS = {
    "core_weight": 1.0,
    "supporting_weight": 0.5,
    "claim_only_multiplier": 0.5,
    "confidence_multiplier": {"high": 1.0, "medium": 0.85, "low": 0.7},
    "proficiency_modifier": 0.1,
}


def requirement(skill_id, evidence_class, confidence):
    return SimpleNamespace(
        skill=SimpleNamespace(skill_id=skill_id, canonical_name=f"Skill {skill_id}"),
        evidence_class=evidence_class,
        confidence=confidence,
    )


def independent_score(required, user_skills, weights):
    """Manual oracle intentionally does not call or import production scoring helpers."""
    total_weight = 0.0
    total_contribution = 0.0
    details = []
    for item in required:
        base_weight = weights["core_weight"] if item.evidence_class.upper() == "CORE" else weights["supporting_weight"]
        confidence_multiplier = weights["confidence_multiplier"].get(item.confidence, 1.0)
        weight = base_weight * confidence_multiplier
        matches = [user for user in user_skills if user.skill_id == item.skill.skill_id]
        match = next((user for user in matches if user.evidence_status == "linked"),
                     matches[0] if matches else None)
        if match is None:
            contribution = 0.0
            status = "missing"
        else:
            contribution = weight if match.evidence_status == "linked" else weight * weights["claim_only_multiplier"]
            has_reported_level = bool(match.proficiency) and match.proficiency.strip().lower() not in (
                "", "unspecified", "none",
            )
            if has_reported_level:
                contribution = min(
                    contribution * (1 + weights["proficiency_modifier"]),
                    weight,
                )
            status = "linked" if match.evidence_status == "linked" else "claim_only"
        total_weight += weight
        total_contribution += contribution
        details.append({
            "skill_id": item.skill.skill_id,
            "weight": weight,
            "contribution": contribution,
            "status": status,
        })
    return {
        "details": details,
        "numerator": total_contribution,
        "denominator": total_weight,
        "score": max(0.0, min(1.0, total_contribution / total_weight)) if total_weight else 0.0,
    }


def test_recommendation_scores_match_independent_calculation_for_each_candidate(monkeypatch):
    candidate_requirements = {
        "CAREER_A": [
            requirement("S1", "CORE", "high"),
            requirement("S2", "SUPPORTING", "medium"),
            requirement("S3", "CORE", "low"),
            requirement("S5", "SUPPORTING", "high"),
        ],
        "CAREER_B": [
            requirement("S2", "CORE", "medium"),
            requirement("S4", "SUPPORTING", "high"),
            requirement("S1", "SUPPORTING", "low"),
        ],
    }
    careers = [
        SimpleNamespace(career_id=career_id, canonical_name=career_id, domain="synthetic")
        for career_id in candidate_requirements
    ]
    user_skills = [
        SimpleNamespace(skill_id="S1", evidence_status="linked", proficiency="intermediate"),
        SimpleNamespace(skill_id="S2", evidence_status="none", proficiency=None),
        SimpleNamespace(skill_id="S2", evidence_status="linked", proficiency=None),
        SimpleNamespace(skill_id="S5", evidence_status="none", proficiency="basic"),
        SimpleNamespace(skill_id=None, evidence_status="none", proficiency="expert"),
    ]
    monkeypatch.setattr(us, "get_user_full_profile", lambda user_id: SimpleNamespace(skills=user_skills))
    monkeypatch.setattr(rs, "get_all_careers", lambda: careers)
    monkeypatch.setattr(rs, "get_career_skills", lambda career_id: candidate_requirements[career_id])

    recommendations = CareerRecommendationAgent(weights=WEIGHTS).run(51)
    by_career = {result.career_id: result for result in recommendations}

    expected_a = independent_score(candidate_requirements["CAREER_A"], user_skills, WEIGHTS)
    expected_b = independent_score(candidate_requirements["CAREER_B"], user_skills, WEIGHTS)
    assert expected_a["details"] == [
        {"skill_id": "S1", "weight": 1.0, "contribution": 1.0, "status": "linked"},
        {"skill_id": "S2", "weight": 0.425, "contribution": 0.425, "status": "linked"},
        {"skill_id": "S3", "weight": 0.7, "contribution": 0.0, "status": "missing"},
        {"skill_id": "S5", "weight": 0.5, "contribution": 0.275, "status": "claim_only"},
    ]
    assert (expected_a["numerator"], expected_a["denominator"]) == pytest.approx((1.7, 2.625))
    assert (expected_b["numerator"], expected_b["denominator"]) == pytest.approx((1.2, 1.7))
    assert expected_a["score"] == pytest.approx(1.7 / 2.625)
    assert expected_b["score"] == pytest.approx(1.2 / 1.7)

    for career_id, expected in (("CAREER_A", expected_a), ("CAREER_B", expected_b)):
        actual = by_career[career_id].fit_score
        difference = abs(actual - expected["score"])
        assert difference <= 0.00005

    assert by_career["CAREER_B"].fit_score > by_career["CAREER_A"].fit_score


def test_empty_requirements_have_zero_score_in_independent_and_production_calculators():
    # Empty denominator rule is explicitly part of the current implementation.
    assert independent_score([], [], WEIGHTS)["score"] == 0.0
    result = fit_service.compute_career_fit([], [], WEIGHTS)
    assert result.fit_score == 0.0
    assert result.total_weight == result.total_contribution == 0.0
