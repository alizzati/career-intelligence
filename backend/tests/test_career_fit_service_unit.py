"""
Pure unit tests for career_fit_service.py. No DB connection, no LLM, no
network, no Pydantic schemas -- hand-built dataclass inputs only.

Run: python -m tests.test_career_fit_service_unit
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.career_fit_service import (
    compute_career_fit, RequiredSkillInput, UserSkillInput, DEFAULT_WEIGHTS,
)

W = DEFAULT_WEIGHTS  # explicit, documented defaults -- same values as scoring_weights.yaml


def main():
    print("=== 1 & 8. Deterministic: same input -> same output, called twice ===")
    required = [
        RequiredSkillInput("S001", "CORE", "high"),
        RequiredSkillInput("S002", "SUPPORTING", "medium"),
    ]
    user = [UserSkillInput("S001", "linked", "intermediate")]
    r1 = compute_career_fit(required, user, W)
    r2 = compute_career_fit(required, user, W)
    assert r1.fit_score == r2.fit_score, "REGRESSION: non-deterministic output"
    print(f"  run1={r1.fit_score}, run2={r2.fit_score} -- identical")

    print("\n=== 2. fit_score always in [0.0, 1.0] ===")
    for req_set, user_set in [
        ([RequiredSkillInput("S001", "CORE", "high")], []),  # nothing matched
        ([RequiredSkillInput("S001", "CORE", "high")], [UserSkillInput("S001", "linked", "advanced")]),  # full match + bonus
        ([], []),  # no requirements at all
    ]:
        r = compute_career_fit(req_set, user_set, W)
        print(f"  requirements={len(req_set)}, user_skills={len(user_set)} -> fit_score={r.fit_score}")
        assert 0.0 <= r.fit_score <= 1.0, f"REGRESSION: fit_score out of bounds: {r.fit_score}"

    print("\n=== 3. linked evidence contributes MORE than claim-only, all else equal ===")
    required = [RequiredSkillInput("S001", "CORE", "high")]
    r_linked = compute_career_fit(required, [UserSkillInput("S001", "linked", None)], W)
    r_claim_only = compute_career_fit(required, [UserSkillInput("S001", "none", None)], W)
    print(f"  linked contribution={r_linked.total_contribution}, claim-only={r_claim_only.total_contribution}")
    assert r_linked.total_contribution > r_claim_only.total_contribution

    print("\n=== 4. claim-only contributes MORE than missing (zero), and is NEVER zero ===")
    r_missing = compute_career_fit(required, [], W)
    print(f"  claim-only={r_claim_only.total_contribution}, missing={r_missing.total_contribution}")
    assert r_claim_only.total_contribution > r_missing.total_contribution == 0.0
    assert r_claim_only.total_contribution > 0.0, \
        "REGRESSION: claim-only (Section 4: claim != missing) must never be zero"

    print("\n=== 5. CORE weight > SUPPORTING weight, per config, same confidence ===")
    core_req = [RequiredSkillInput("S001", "CORE", "high")]
    supp_req = [RequiredSkillInput("S001", "SUPPORTING", "high")]
    user_linked = [UserSkillInput("S001", "linked", None)]
    r_core = compute_career_fit(core_req, user_linked, W)
    r_supp = compute_career_fit(supp_req, user_linked, W)
    print(f"  CORE weight={r_core.total_weight}, SUPPORTING weight={r_supp.total_weight}")
    assert r_core.total_weight > r_supp.total_weight
    assert W["core_weight"] > W["supporting_weight"]

    print("\n=== 6. KB confidence multiplier is applied (high != medium) ===")
    high_req = [RequiredSkillInput("S001", "CORE", "high")]
    med_req = [RequiredSkillInput("S001", "CORE", "medium")]
    r_high = compute_career_fit(high_req, user_linked, W)
    r_med = compute_career_fit(med_req, user_linked, W)
    print(f"  high-confidence weight={r_high.total_weight}, medium-confidence weight={r_med.total_weight}")
    assert r_high.total_weight > r_med.total_weight, "REGRESSION: confidence multiplier not applied"

    print("\n=== 7. user skill with skill_id=None NEVER matches a requirement ===")
    required = [RequiredSkillInput("S001", "CORE", "high")]
    unnormalized_user = [UserSkillInput(None, "linked", "advanced")]  # claimed but unnormalized
    r = compute_career_fit(required, unnormalized_user, W)
    print(f"  fit_score={r.fit_score}, status={r.skill_details[0].status}")
    assert r.skill_details[0].status == "missing", \
        "REGRESSION: an unnormalized (skill_id=None) user skill was incorrectly treated as a match"
    assert r.fit_score == 0.0

    print("\n=== Extra: tie-break when user has 2 claims normalizing to the same skill_id ===")
    required = [RequiredSkillInput("S001", "CORE", "high")]
    dual_claims = [UserSkillInput("S001", "none", None), UserSkillInput("S001", "linked", None)]
    r = compute_career_fit(required, dual_claims, W)
    assert r.skill_details[0].status == "matched-linked", \
        "tie-break should prefer the 'linked' claim over the 'none' claim"
    print(f"  resolved status={r.skill_details[0].status} (linked claim correctly preferred)")

    print("\n=== Extra: unknown confidence string defaults to neutral multiplier (1.0), does not crash ===")
    weird_req = [RequiredSkillInput("S001", "CORE", "some-unexpected-value")]
    r = compute_career_fit(weird_req, user_linked, W)
    print(f"  weight with unknown confidence = {r.total_weight} (expected = core_weight * 1.0 = {W['core_weight']})")
    assert r.total_weight == W["core_weight"]

    print("\nALL CAREER FIT SERVICE UNIT TESTS PASSED.")


if __name__ == "__main__":
    main()