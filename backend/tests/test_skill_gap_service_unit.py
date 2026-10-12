"""
Unit tests for the deterministic Skill-Gap Engine (Step 9).

No database queries and no LLM are used: inputs are hand-built Pydantic
objects. (Importing the service builds a SQLAlchemy engine object, which
is lazy and opens no connection.)

Run: python -m tests.test_skill_gap_service_unit
"""
import ast
import inspect
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.schemas import skill_gap as skill_gap_schemas
from app.schemas.retrieval import CareerOut, CareerSkillOut, SkillOut
from app.schemas.skill_gap import (
    MatchedUserClaim, SkillGapItem, SkillGapResult, UnmatchedUserClaim,
)
from app.schemas.user import UserSkillEvidenceOut, UserSkillOut
from app.services import career_fit_service
from app.services import skill_gap_service as sgs
from app.services.career_fit_service import (
    DEFAULT_WEIGHTS, CareerFitResult, RequiredSkillInput, SkillFitDetail,
    UserSkillInput, compute_career_fit,
)

W = DEFAULT_WEIGHTS
CAREER = CareerOut(career_id="CX", canonical_name="Test Career", domain="Test Domain")


def req(skill_id, name, evidence_class, confidence):
    return CareerSkillOut(
        relationship_id=f"R_{skill_id}",
        skill=SkillOut(skill_id=skill_id, canonical_name=name, skill_group_id="SG00", status="active"),
        evidence_class=evidence_class, confidence=confidence,
        mapping_method="test", evidence_source_text="test",
    )


def usk(uid, claimed, skill_id, status, proficiency=None, n_evidence=0):
    return UserSkillOut(
        user_skill_id=uid, claimed_skill=claimed, skill_id=skill_id,
        normalized_skill=None, proficiency=proficiency, evidence_status=status, confidence="unknown",
        evidence=[UserSkillEvidenceOut(evidence_id=i, evidence_type="project") for i in range(n_evidence)],
    )


# Deliberately NOT alphabetical and with CORE/SUPPORTING and confidence
# interleaved, so any hidden sorting by id, class or confidence would be
# visible as a reordering.
REQUIRED = [
    req("S900", "Skill Nine", "SUPPORTING", "medium"),
    req("S100", "Skill One", "CORE", "high"),
    req("S500", "Skill Five", "CORE", "medium"),
    req("S300", "Skill Three", "SUPPORTING", "high"),
    req("S700", "Skill Seven", "CORE", "high"),
]


def mixed_user():
    return [
        usk(1, "skill one (evidenced)", "S100", "linked", "advanced", 2),   # -> matched_evidenced
        usk(2, "Skill Three claim", "S300", "none", "beginner", 0),         # -> matched_claimed_only
        usk(3, "Skill Nine", "S900", "linked", None, 1),                    # -> matched_evidenced
        usk(4, "Python", None, "linked", "intermediate", 1),                # -> unmatched (has evidence!)
        usk(5, "Some Framework", None, "none", None, 0),                    # -> unmatched
    ]
    # S500 and S700 are absent -> missing


def ids(items):
    return [i.skill_id for i in items]


def collect_keys(obj, acc):
    if isinstance(obj, dict):
        for k, v in obj.items():
            acc.add(k)
            collect_keys(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            collect_keys(v, acc)
    return acc


def main():
    result = sgs.classify_skill_gap(7, CAREER, REQUIRED, mixed_user(), W)

    print("=== 1. Four categories are classified correctly ===")
    print(f"  matched_evidenced   : {ids(result.matched_evidenced)}")
    print(f"  matched_claimed_only: {ids(result.matched_claimed_only)}")
    print(f"  missing             : {ids(result.missing)}")
    print(f"  unmatched_user_claim: {[u.claimed_skill for u in result.unmatched_user_claims]}")
    assert ids(result.matched_evidenced) == ["S900", "S100"]
    assert ids(result.matched_claimed_only) == ["S300"]
    assert ids(result.missing) == ["S500", "S700"]
    assert [u.claimed_skill for u in result.unmatched_user_claims] == ["Python", "Some Framework"]

    print("\n=== 2. linked evidence is not missing; claim-only is not missing ===")
    missing_ids = set(ids(result.missing))
    assert "S100" not in missing_ids and "S900" not in missing_ids   # linked
    assert "S300" not in missing_ids                                  # claim-only
    assert all(i.status == "matched_evidenced" for i in result.matched_evidenced)
    assert all(i.status == "matched_claimed_only" for i in result.matched_claimed_only)
    assert all(i.status == "missing" and i.matched_user_claim is None for i in result.missing)

    print("\n=== 3. unmatched user claims are NOT classified as missing ===")
    all_items = result.matched_evidenced + result.matched_claimed_only + result.missing
    assert len(all_items) == len(REQUIRED), "every requirement appears exactly once"
    # 'Python' has linked evidence but no canonical id: must not appear as a requirement
    # outcome of any kind, and must not change the missing count.
    assert len(result.missing) == 2
    for item in all_items:
        assert item.canonical_name not in ("Python", "Some Framework")
        assert item.matched_user_claim is None or item.matched_user_claim.claimed_skill not in ("Python", "Some Framework")
    assert all("does NOT mean the user lacks the skill" in u.note for u in result.unmatched_user_claims)
    # the unmatched claim keeps its own evidence information
    python_claim = result.unmatched_user_claims[0]
    assert python_claim.evidence_status == "linked" and python_claim.evidence_count == 1

    print("\n=== 4. CORE/SUPPORTING and KB confidence metadata are preserved ===")
    by_id = {cs.skill.skill_id: cs for cs in REQUIRED}
    for item in all_items:
        assert item.evidence_class == by_id[item.skill_id].evidence_class
        assert item.kb_confidence == by_id[item.skill_id].confidence
        assert item.canonical_name == by_id[item.skill_id].skill.canonical_name
    print("  evidence_class / kb_confidence / canonical_name identical to the KB rows for all items")

    print("\n=== 5. Matched claim details are echoed (profile info only) ===")
    s100 = next(i for i in result.matched_evidenced if i.skill_id == "S100")
    assert s100.matched_user_claim == MatchedUserClaim(
        claimed_skill="skill one (evidenced)", proficiency="advanced", evidence_status="linked", evidence_count=2)

    print("\n=== 6. Original career_skills order is kept (no sorting) ===")
    original = [c.skill.skill_id for c in REQUIRED]
    for category in (result.matched_evidenced, result.matched_claimed_only, result.missing):
        positions = [original.index(s) for s in ids(category)]
        assert positions == sorted(positions), f"category was reordered: {ids(category)}"
    print(f"  requirement order {original}; each category keeps that relative order")

    print("\n=== 7. Two claims normalizing to the same skill: linked claim wins (calculator's tie-break) ===")
    dual = [usk(1, "Skill One (weak)", "S100", "none"), usk(2, "Skill One (strong)", "S100", "linked", None, 1)]
    r = sgs.classify_skill_gap(7, CAREER, [REQUIRED[1]], dual, W)
    assert ids(r.matched_evidenced) == ["S100"] and r.matched_evidenced[0].matched_user_claim.claimed_skill == "Skill One (strong)"

    print("\n=== 8. Edge cases: no skills at all / only unmatched claims ===")
    r_empty = sgs.classify_skill_gap(7, CAREER, REQUIRED, [], W)
    assert len(r_empty.missing) == len(REQUIRED) and r_empty.unmatched_user_claims == [] and r_empty.fit_score == 0.0
    only_unmatched = [usk(1, "Python", None, "linked", None, 1), usk(2, "Docker-ish", None, "none")]
    r_un = sgs.classify_skill_gap(7, CAREER, REQUIRED, only_unmatched, W)
    assert len(r_un.missing) == len(REQUIRED), "unmatched claims must neither reduce nor add to 'missing'"
    assert len(r_un.unmatched_user_claims) == 2 and r_un.fit_score == 0.0

    print("\n=== 9. compute_career_fit() is the same function object Step 8 uses, and is really called ===")
    assert sgs.compute_career_fit is career_fit_service.compute_career_fit
    with mock.patch.object(sgs, "compute_career_fit", wraps=compute_career_fit) as spy:
        sgs.classify_skill_gap(7, CAREER, REQUIRED, mixed_user(), W)
    assert spy.call_count == 1, f"expected exactly one calculator call, got {spy.call_count}"
    called_required, called_user, called_weights = spy.call_args.args
    assert len(called_required) == len(REQUIRED) and len(called_user) == len(mixed_user()) and called_weights == W
    print("  identical function object; exactly 1 call with the expected inputs")

    print("\n=== 10. Numbers equal an independent direct call to the calculator ===")
    direct = compute_career_fit(
        [RequiredSkillInput(c.skill.skill_id, c.evidence_class, c.confidence) for c in REQUIRED],
        [UserSkillInput(s.skill_id, s.evidence_status, s.proficiency) for s in mixed_user()], W)
    assert result.total_weight == direct.total_weight
    assert result.total_contribution == direct.total_contribution
    assert result.fit_score == round(direct.fit_score, 4)
    assert result.score_breakdown.total_weight == direct.total_weight
    assert result.score_breakdown.weights_used == W
    assert result.score_breakdown.matched_linked_count == len(direct.matched_linked_skill_ids)
    assert result.score_breakdown.matched_claimed_only_count == len(direct.matched_claimed_only_skill_ids)
    assert result.score_breakdown.missing_count == len(direct.missing_skill_ids)

    print("\n=== 11. Classification and numbers come FROM the calculator (forged calculator output) ===")
    forged = CareerFitResult(
        fit_score=0.5, total_weight=123.0, total_contribution=7.77,
        skill_details=[SkillFitDetail(c.skill.skill_id, c.evidence_class, 0.123, "missing", 0.0) for c in REQUIRED],
    )
    with mock.patch.object(sgs, "compute_career_fit", return_value=forged):
        r_forged = sgs.classify_skill_gap(7, CAREER, REQUIRED, mixed_user(), W)
    assert len(r_forged.missing) == len(REQUIRED) and not r_forged.matched_evidenced and not r_forged.matched_claimed_only
    assert r_forged.total_weight == 123.0 and r_forged.total_contribution == 7.77 and r_forged.fit_score == 0.5
    assert all(i.weight == 0.123 for i in r_forged.missing)
    print("  forcing the calculator to say 'missing' changes the output accordingly: nothing is recomputed here")
    bad = CareerFitResult(0.1, 1.0, 0.1, [SkillFitDetail("S900", "CORE", 1.0, "some-new-status", 0.0)] * len(REQUIRED))
    with mock.patch.object(sgs, "compute_career_fit", return_value=bad):
        try:
            sgs.classify_skill_gap(7, CAREER, REQUIRED, [], W)
            raise AssertionError("an unknown calculator status must not be silently accepted")
        except RuntimeError:
            pass

    print("\n=== 12. Deterministic: same inputs -> identical output ===")
    a = sgs.classify_skill_gap(7, CAREER, REQUIRED, mixed_user(), W).model_dump()
    b = sgs.classify_skill_gap(7, CAREER, REQUIRED, mixed_user(), W).model_dump()
    assert a == b

    print("\n=== 13. Custom weights are passed through to the calculator ===")
    custom = dict(W, claim_only_multiplier=0.25)
    r_custom = sgs.classify_skill_gap(7, CAREER, REQUIRED, mixed_user(), custom)
    assert r_custom.score_breakdown.weights_used == custom
    assert r_custom.total_contribution < result.total_contribution   # claim-only contributes less

    print("\n=== 14. No priority / ranking / severity / scoring / required-proficiency fields exist ===")
    forbidden_fields = ("priority", "severity", "rank", "tier", "importance", "urgency", "gap_score",
                        "required_proficiency", "proficiency_gap", "proficiency_deficit",
                        "target_proficiency", "required_level", "level_gap")
    models = [MatchedUserClaim, SkillGapItem, UnmatchedUserClaim, SkillGapResult]
    for m in models:
        for field_name in m.model_fields:
            assert not any(f in field_name.lower() for f in forbidden_fields), f"{m.__name__}.{field_name}"
    dumped_keys = collect_keys(result.model_dump(), set())
    for key in dumped_keys:
        assert not any(f in key.lower() for f in forbidden_fields), f"output key {key!r}"
    item = result.missing[0]
    assert not hasattr(item, "priority_score") and not hasattr(item, "priority_tier")
    # the only numeric per-skill values are the calculator's own weight/contribution
    numeric_item_fields = {n for n, f in SkillGapItem.model_fields.items() if f.annotation is float}
    assert numeric_item_fields == {"weight", "contribution"}, numeric_item_fields
    print(f"  checked {len(dumped_keys)} output keys and all model fields; per-item numerics = {sorted(numeric_item_fields)}")

    print("\n=== 15. Engine source: no sorting, no priority/ranking identifiers, no LLM/network imports ===")
    tree = ast.parse(inspect.getsource(sgs))
    identifiers, imported, calls = set(), set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            identifiers.add(node.name)
        elif isinstance(node, ast.keyword) and node.arg:
            identifiers.add(node.arg)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        if isinstance(node, ast.Call):
            f = node.func
            calls.add(f.id if isinstance(f, ast.Name) else getattr(f, "attr", ""))
    bad_identifiers = [i for i in identifiers if any(f in i.lower() for f in forbidden_fields)]
    assert not bad_identifiers, bad_identifiers
    assert "sorted" not in calls and "sort" not in calls and "reverse" not in calls, calls
    llm_markers = ("llm", "gemini", "anthropic", "openai", "google", "genai", "requests", "httpx", "app.agents")
    bad_imports = [m for m in imported if any(x in m.lower() for x in llm_markers)]
    assert not bad_imports, bad_imports
    params = set(inspect.signature(sgs.analyze_skill_gap).parameters) | set(inspect.signature(sgs.classify_skill_gap).parameters)
    assert not any("llm" in p.lower() or "client" in p.lower() for p in params), params
    print("  no sort/sorted call, no priority-like identifier, no LLM/network import, no llm/client parameter")

    print("\nALL SKILL GAP SERVICE UNIT TESTS PASSED.")


if __name__ == "__main__":
    main()