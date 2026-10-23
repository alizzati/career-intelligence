"""Edge cases of the CURRENT career-fit formula. Expected values are hand-computed literals
(documented in comments), not produced by any helper. Tests named *_current_behaviour pin existing
behaviour that may deserve a design review; the formula is intentionally NOT changed here."""
import pytest

from app.services.career_fit_service import RequiredSkillInput as R
from app.services.career_fit_service import UserSkillInput as U
from app.services.career_fit_service import compute_career_fit

W = {"core_weight": 1.0, "supporting_weight": 0.5, "claim_only_multiplier": 0.5,
     "confidence_multiplier": {"high": 1.0, "medium": 0.85, "low": 0.7}, "proficiency_modifier": 0.1}


def test_proficiency_bonus_is_inert_for_linked_skill():
    # w=1.0, linked -> c0=1.0; min(1.0*1.1, 1.0)=1.0 (not 1.1)
    r = compute_career_fit([R("S1", "CORE", "high")], [U("S1", "linked", "advanced")], W)
    assert r.total_contribution == pytest.approx(1.0) and r.fit_score == pytest.approx(1.0)


def test_proficiency_bonus_applies_to_claim_only():
    # c0 = 1.0*0.5 = 0.5; with bonus min(0.5*1.1, 1.0) = 0.55
    r = compute_career_fit([R("S1", "CORE", "high")], [U("S1", "none", "intermediate")], W)
    assert r.total_contribution == pytest.approx(0.55)


@pytest.mark.parametrize("proficiency", [None, "", "unspecified", "none", "  NONE "])
def test_non_informative_proficiency_gets_no_bonus(proficiency):
    r = compute_career_fit([R("S1", "CORE", "high")], [U("S1", "none", proficiency)], W)
    assert r.total_contribution == pytest.approx(0.5)


@pytest.mark.parametrize("proficiency", ["unknown", "N/A", "not specified"])
def test_placeholder_proficiency_still_gets_bonus_current_behaviour(proficiency):
    r = compute_career_fit([R("S1", "CORE", "high")], [U("S1", "none", proficiency)], W)
    assert r.total_contribution == pytest.approx(0.55)


def test_lowercase_core_label_is_core_weighted():
    # "core" -> core_weight 1.0 x medium 0.85 = 0.85 (would be 0.425 if treated as supporting)
    r = compute_career_fit([R("S1", "core", "medium")], [U("S1", "linked", None)], W)
    assert r.total_weight == pytest.approx(0.85) and r.fit_score == pytest.approx(1.0)


def test_duplicate_requirements_are_counted_twice_current_behaviour():
    # required [S1, S1, S2], all CORE/high, user linked S1 only: sum_c = 2, sum_w = 3 -> 2/3
    req = [R("S1", "CORE", "high"), R("S1", "CORE", "high"), R("S2", "CORE", "high")]
    r = compute_career_fit(req, [U("S1", "linked", None)], W)
    assert r.total_weight == pytest.approx(3.0) and r.fit_score == pytest.approx(2 / 3)


def test_unknown_evidence_status_is_treated_as_claim_only_current_behaviour():
    r = compute_career_fit([R("S1", "CORE", "high")], [U("S1", "weird", None)], W)
    assert r.total_contribution == pytest.approx(0.5)


def test_non_default_weights_are_actually_used():
    w = {"core_weight": 2.0, "supporting_weight": 0.25, "claim_only_multiplier": 0.4,
         "confidence_multiplier": {"high": 1.0, "medium": 0.5, "low": 0.1}, "proficiency_modifier": 0.25}
    req = [R("S1", "CORE", "medium"), R("S2", "SUPPORTING", "high"), R("S3", "CORE", "low")]
    usr = [U("S1", "none", "beginner"), U("S2", "linked", None)]
    # w = 2.0*0.5=1.0 | 0.25*1.0=0.25 | 2.0*0.1=0.2          sum_w = 1.45
    # c = min(1.0*0.4*1.25, 1.0)=0.5 | 0.25 | 0 (missing)     sum_c = 0.75  -> 0.75/1.45
    r = compute_career_fit(req, usr, w)
    assert r.total_weight == pytest.approx(1.45) and r.total_contribution == pytest.approx(0.75)
    assert r.fit_score == pytest.approx(0.75 / 1.45)