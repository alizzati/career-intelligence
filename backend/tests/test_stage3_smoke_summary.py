from types import SimpleNamespace

from scripts.stage3_smoke import _skill_gap_summary


def _record(gap):
    return SimpleNamespace(raw_structured_output={"baseline_result": {"skill_gap": gap}})


def test_skill_gap_summary_partitions_required_skills_excluding_unmatched_claims():
    raw_gap = {
        "career_id": "C09",
        "matched_evidenced": ["S001", "S004"],
        "matched_claimed_only": [],
        "missing": ["S045"],
        "unmatched_user_claims": ["m0006", "m0007", "m0008"],
        "claim_matches": {"S001": ["m0001"], "S004": ["m0002"]},
    }
    summary = _skill_gap_summary(_record(raw_gap))
    assert summary["category_counts"] == {
        "matched_evidenced": 2,
        "matched_claimed_only": 0,
        "missing": 1,
        "unmatched_user_claims": 3,
    }
    assert summary["required_skill_total"] == 3
    assert summary["category_sets_disjoint"] is True
    assert summary["unmatched_claims_valid"] is True


def test_skill_gap_summary_reports_required_overlap_and_claim_overlap_separately():
    raw_gap = {
        "career_id": "C09",
        "matched_evidenced": ["S001", "S001"],
        "matched_claimed_only": [],
        "missing": [],
        "unmatched_user_claims": ["m0001"],
        "claim_matches": {"S001": ["m0001"]},
    }
    summary = _skill_gap_summary(_record(raw_gap))
    assert summary["category_sets_disjoint"] is False
    assert summary["unmatched_claims_valid"] is False
