"""
Step 9 smoke / integration tests: the deterministic Skill-Gap Engine
against the REAL database. No LLM is involved anywhere in this test.

Test users are created through user_service and removed in a `finally`
block by exact user_id (targeted DELETE; no TRUNCATE).

Run: python -m tests.test_skill_gap_service_smoke
"""
import json
import os
import subprocess
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.agents.career_recommendation_agent import CareerRecommendationAgent
from app.core.db import engine
from app.services import retrieval_service as rs
from app.services import skill_gap_service as sgs
from app.services import user_service as us
from app.services.career_fit_service import (
    RequiredSkillInput, UserSkillInput, compute_career_fit, load_scoring_weights,
)

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_BASELINE = {"careers": 10, "skills": 87, "career_skills": 155, "competency_units": 146}
created_user_ids: list[int] = []

# --- What counts as "an LLM / agent dependency" in sys.modules ---------------
# The bare top-level namespace package `google` is deliberately NOT in this
# list: it contains no code (it is a PEP 420 namespace shared by many unrelated
# Google libraries) and can be present for reasons unrelated to any LLM (an
# interpreter-startup .pth file, or a failed optional `import google.x` probe).
# A real Gemini SDK dependency always loads its own submodules, e.g.
# `google.genai.*` or `google.generativeai.*`, which ARE listed.
LLM_PACKAGES = ("google.genai", "google.generativeai", "google.ai", "genai", "anthropic", "openai")
AGENT_PACKAGE = "app.agents"
LLM_CLIENT_MODULE_NAME = "llm_client"


def _is_or_under(name: str, package: str) -> bool:
    return name == package or name.startswith(package + ".")


def find_llm_or_agent_modules(module_names) -> list[str]:
    """Return the module names that indicate an agent or LLM-provider dependency."""
    offending = []
    for name in module_names:
        if (_is_or_under(name, AGENT_PACKAGE)
                or name.split(".")[-1] == LLM_CLIENT_MODULE_NAME
                or any(_is_or_under(name, p) for p in LLM_PACKAGES)):
            offending.append(name)
    return sorted(offending)


def loaded_modules_after_import(module: str) -> list[str]:
    """Import `module` in a FRESH interpreter (no pollution from this test
    runner) and return every module name present in sys.modules afterwards."""
    code = f"import sys, json; import {module}; print(json.dumps(sorted(sys.modules)))"
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def kb_counts() -> dict:
    with engine.connect() as conn:
        return {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in KB_BASELINE}


def new_user(label: str) -> int:
    user = us.create_user(f"skill_gap_engine_test_{label}_{uuid.uuid4().hex[:8]}@example.com", f"Skill Gap Test {label}")
    created_user_ids.append(user.user_id)
    return user.user_id


def ids(items):
    return [i.skill_id for i in items]


def run_tests():
    print("=== KB baseline (before) ===")
    before = kb_counts()
    print(f"  {before}")
    assert before == KB_BASELINE, f"KB does not match the documented baseline {KB_BASELINE}"

    careers = rs.get_all_careers()
    career = careers[0]
    required = rs.get_career_skills(career.career_id)
    assert len(required) >= 3, "test needs a career with at least 3 required skills"
    evidenced_skill, claimed_only_skill = required[0].skill, required[1].skill

    print(f"\n=== Seed a user against career {career.career_id} ({career.canonical_name}) ===")
    user_id = new_user("mixed")
    a = us.add_user_skill(user_id, claimed_skill=evidenced_skill.canonical_name,
                          skill_id=evidenced_skill.skill_id, normalized_skill=evidenced_skill.canonical_name,
                          proficiency="intermediate")
    us.add_skill_evidence(a.user_skill_id, evidence_type="project", description="seed evidence")
    us.add_user_skill(user_id, claimed_skill=claimed_only_skill.canonical_name,
                      skill_id=claimed_only_skill.skill_id, normalized_skill=claimed_only_skill.canonical_name,
                      proficiency="beginner")
    us.add_user_skill(user_id, claimed_skill="Some Totally Unnormalizable Claim", skill_id=None)
    print(f"  evidenced={evidenced_skill.skill_id}, claimed-only={claimed_only_skill.skill_id}, 1 unmatched claim")

    print("\n=== 1. valid user + valid career ===")
    result = sgs.analyze_skill_gap(user_id, career.career_id)
    print(f"  evidenced={len(result.matched_evidenced)}, claimed_only={len(result.matched_claimed_only)}, "
          f"missing={len(result.missing)}, unmatched_claims={len(result.unmatched_user_claims)}, "
          f"fit_score={result.fit_score}")
    assert ids(result.matched_evidenced) == [evidenced_skill.skill_id]
    assert ids(result.matched_claimed_only) == [claimed_only_skill.skill_id]
    assert len(result.missing) == len(required) - 2
    assert [u.claimed_skill for u in result.unmatched_user_claims] == ["Some Totally Unnormalizable Claim"]

    print("\n=== 2 & 3. invalid user / invalid career raise controlled errors ===")
    for call, exc in ((lambda: sgs.analyze_skill_gap(999999999, career.career_id), sgs.UserNotFoundError),
                      (lambda: sgs.analyze_skill_gap(user_id, "C_DOES_NOT_EXIST"), sgs.CareerNotFoundError)):
        try:
            call()
            raise AssertionError(f"expected {exc.__name__}")
        except exc as e:
            print(f"  {exc.__name__}: {e}")

    print("\n=== 4. requirements come from the KB: every KB requirement appears exactly once, nothing extra ===")
    all_items = result.matched_evidenced + result.matched_claimed_only + result.missing
    assert sorted(ids(all_items)) == sorted(c.skill.skill_id for c in required)
    assert len(all_items) == len(required)

    print("\n=== 5. CORE/SUPPORTING + confidence + names preserved from the KB; original order kept (ALL careers) ===")
    classes_seen, confidences_seen = set(), set()
    for c in careers:
        req_c = rs.get_career_skills(c.career_id)
        gap_c = sgs.analyze_skill_gap(user_id, c.career_id)
        items_c = gap_c.matched_evidenced + gap_c.matched_claimed_only + gap_c.missing
        assert len(items_c) == len(req_c)
        kb_by_id = {r.skill.skill_id: r for r in req_c}
        for item in items_c:
            kb = kb_by_id[item.skill_id]
            assert (item.evidence_class, item.kb_confidence, item.canonical_name) == \
                   (kb.evidence_class, kb.confidence, kb.skill.canonical_name), (c.career_id, item.skill_id)
            classes_seen.add(item.evidence_class)
            confidences_seen.add(item.kb_confidence)
        order_c = [r.skill.skill_id for r in req_c]
        for category in (gap_c.matched_evidenced, gap_c.matched_claimed_only, gap_c.missing):
            pos = [order_c.index(s) for s in ids(category)]
            assert pos == sorted(pos), f"{c.career_id}: category reordered"
    print(f"  classes seen across all careers: {sorted(classes_seen)}; confidences: {sorted(confidences_seen)}")
    assert len(classes_seen) >= 2 and len(confidences_seen) >= 2, \
        "check would be vacuous: the KB should contain more than one evidence_class and confidence value"

    print("\n=== 6. unmatched claim never appears as a requirement outcome ===")
    assert all("Unnormalizable" not in (i.matched_user_claim.claimed_skill if i.matched_user_claim else "") for i in all_items)

    print("\n=== 7. Step 8 <-> Step 9 consistency, ALL careers, default AND custom weights ===")
    custom = dict(load_scoring_weights(), claim_only_multiplier=0.3, supporting_weight=0.4)
    profile = us.get_user_full_profile(user_id)
    for label, weights in (("default weights", None), ("custom weights", custom)):
        recs = {r.career_id: r for r in CareerRecommendationAgent(llm_client=None, weights=weights).run(user_id)}
        assert set(recs) == {c.career_id for c in careers}
        for c in careers:
            gap = sgs.analyze_skill_gap(user_id, c.career_id, weights)
            rec = recs[c.career_id]
            assert gap.fit_score == rec.fit_score, (c.career_id, gap.fit_score, rec.fit_score)
            assert gap.total_weight == rec.score_breakdown.total_weight
            assert gap.total_contribution == rec.score_breakdown.total_contribution
            assert gap.score_breakdown.model_dump() == rec.score_breakdown.model_dump(), c.career_id
            assert ids(gap.matched_evidenced) == [s.skill_id for s in rec.matched_skills]
            assert ids(gap.matched_claimed_only) == [s.skill_id for s in rec.claimed_only_skills]
            assert ids(gap.missing) == [s.skill_id for s in rec.missing_skills_preview]
            # independent third computation, built in this test from the services' raw output
            req = rs.get_career_skills(c.career_id)
            direct = compute_career_fit(
                [RequiredSkillInput(r.skill.skill_id, r.evidence_class, r.confidence) for r in req],
                [UserSkillInput(s.skill_id, s.evidence_status, s.proficiency) for s in profile.skills],
                weights if weights is not None else load_scoring_weights())
            assert gap.total_weight == direct.total_weight and gap.total_contribution == direct.total_contribution
            assert gap.fit_score == round(direct.fit_score, 4)
        print(f"  {label}: Step 9 == Step 8 == direct compute_career_fit() for all {len(careers)} careers "
              f"(fit_score, total_weight, total_contribution, score_breakdown, matched/claimed/missing ids)")

    print("\n=== 8. deterministic: repeated runs are identical ===")
    assert sgs.analyze_skill_gap(user_id, career.career_id).model_dump() == result.model_dump()

    print("\n=== 9. user with no skills -> every requirement missing; only-unmatched user -> same ===")
    empty_id = new_user("empty")
    r_empty = sgs.analyze_skill_gap(empty_id, career.career_id)
    assert len(r_empty.missing) == len(required) and r_empty.fit_score == 0.0 and not r_empty.unmatched_user_claims
    unmatched_id = new_user("unmatched_only")
    us.add_user_skill(unmatched_id, claimed_skill="Totally Unknown Thing A", skill_id=None)
    us.add_user_skill(unmatched_id, claimed_skill="Totally Unknown Thing B", skill_id=None)
    r_un = sgs.analyze_skill_gap(unmatched_id, career.career_id)
    assert len(r_un.missing) == len(required) and len(r_un.unmatched_user_claims) == 2

    print("\n=== 10. Step 9 involves no LLM / agent dependency ===")

    # 10a. The detector itself is checked first, so the real check below cannot pass vacuously
    #      and cannot fail on the harmless bare `google` namespace package.
    assert find_llm_or_agent_modules(["google"]) == []                                   # bare namespace: harmless
    assert find_llm_or_agent_modules(["google", "google.protobuf", "googlemaps", "googleapiclient"]) == []
    assert find_llm_or_agent_modules(["google", "google.genai", "google.genai.types"]) == ["google.genai", "google.genai.types"]
    assert find_llm_or_agent_modules(["google.generativeai.types"]) == ["google.generativeai.types"]
    assert find_llm_or_agent_modules(["google.ai.generativelanguage"]) == ["google.ai.generativelanguage"]
    assert find_llm_or_agent_modules(["genai", "anthropic.types", "openai"]) == ["anthropic.types", "genai", "openai"]
    assert find_llm_or_agent_modules(["genai_utils", "app.agentsx", "my_llm_client_helper"]) == []   # no loose substring matching
    assert find_llm_or_agent_modules(["app.agents", "app.agents.llm_client", "x.llm_client", "llm_client"]) == \
           ["app.agents", "app.agents.llm_client", "llm_client", "x.llm_client"]
    print("  detector self-check OK: bare 'google' is not an offender; google.genai / google.generativeai / "
          "google.ai / genai / anthropic / openai / app.agents / *llm_client are")

    # 10b. The real check: a fresh interpreter importing ONLY the engine.
    engine_modules = loaded_modules_after_import("app.services.skill_gap_service")
    offending = find_llm_or_agent_modules(engine_modules)
    google_loaded = sorted(m for m in engine_modules if m == "google" or m.startswith("google."))
    assert not offending, f"importing the engine pulled in agent/LLM modules: {offending}"
    print(f"  importing skill_gap_service loads no agent/LLM module ({len(engine_modules)} modules inspected)")
    print(f"  informational: google* modules present in that interpreter: {google_loaded or 'none'}"
          + ("  (bare namespace only; no SDK submodule)" if google_loaded == ["google"] else ""))

    # 10c. Positive control: importing a real agent IS detected, so the check above is not vacuous.
    agent_modules = loaded_modules_after_import("app.agents.career_recommendation_agent")
    agent_offending = find_llm_or_agent_modules(agent_modules)
    assert "app.agents.career_recommendation_agent" in agent_offending, agent_offending
    print(f"  positive control OK: importing the Step 8 agent is flagged ({len(agent_offending)} module(s), "
          f"e.g. {agent_offending[:2]})")

    class HallucinatingLLM:   # cannot even be handed to the engine
        def complete_json(self, *a, **k):
            return {"missing": [], "fit_score": 0.999, "matched_evidenced": ["Quantum Blockchain"]}
    try:
        sgs.analyze_skill_gap(user_id, career.career_id, llm_client=HallucinatingLLM())
        raise AssertionError("the engine must not accept an LLM client")
    except TypeError:
        print("  the engine has no LLM entry point: passing an LLM client raises TypeError")
    assert sgs.analyze_skill_gap(user_id, career.career_id).model_dump() == result.model_dump()

    print("\n=== 11. KB unchanged after all runs ===")
    after = kb_counts()
    print(f"  {after}")
    assert after == before == KB_BASELINE

    print("\nALL STEP 9 SMOKE TESTS PASSED.")


def main():
    try:
        run_tests()
    finally:
        if created_user_ids:
            with engine.begin() as conn:
                deleted = conn.execute(text("DELETE FROM users WHERE user_id = ANY(:ids)"),
                                       {"ids": created_user_ids}).rowcount
            print(f"(cleanup: deleted {deleted} test users by exact user_id {created_user_ids})")


if __name__ == "__main__":
    main()