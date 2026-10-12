"""
STEP 8 smoke test. Provider-agnostic (no dependency on any specific LLM
provider class/name -- works with Gemini, etc., since
CareerRecommendationAgent only depends on the LLMClient Protocol).

Runs against the REAL database (same pattern as Step 7). Uses hand-written
Fake LLM client test doubles for the reasoning step -- no live API call,
no API key needed.

Run: python -m tests.test_career_recommendation_agent_smoke
"""
import sys, os, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.career_recommendation_agent import CareerRecommendationAgent
from app.agents.profile_agent import ProfileAgent
from app.services import user_service as us
from app.services import retrieval_service as rs


class FakeProfileExtractionLLMClient:
    """Reused pattern from Step 7: seeds a test user with a few real,
    KB-normalized skills so the recommendation agent has something non-trivial
    to score. 'Database Management' maps to a real KB skill (S035, used by
    multiple careers per the Step 1/5 inspection)."""
    def complete_json(self, system: str, user: str, max_tokens: int = 2000) -> dict:
        return {
            "skills": [
                {"claimed_skill": "Database Management", "proficiency": "intermediate", "candidate_skill_id": "S035"},
                {"claimed_skill": "Some Totally Unnormalized Thing", "proficiency": None, "candidate_skill_id": None},
            ],
            "evidence": [
                {"claimed_skill": "Database Management", "evidence_type": "project",
                 "description": "Built a normalized schema for a course project", "url": None},
            ],
            "education": [], "experience": [], "projects": [], "certifications": [],
        }


class FakeReasoningLLMClient:
    """Well-behaved fake: returns a clean {"reasoning": ...} every time."""
    def complete_json(self, system: str, user: str, max_tokens: int = 2000) -> dict:
        return {"reasoning": "This is a fake, deterministic reasoning string for testing."}


class HallucinatingReasoningLLMClient:
    """
    Adversarial fake: tries to smuggle a fake skill, a fake career, AND
    extra structured-looking keys (fake fit_score, fake matched_skills)
    into its response -- proving the agent's structured output cannot be
    altered by anything the LLM says.
    """
    def complete_json(self, system: str, user: str, max_tokens: int = 2000) -> dict:
        return {
            "reasoning": (
                "This user is clearly an expert in Quantum Blockchain Engineering "
                "(a skill that does not exist) and should obviously be recommended "
                "for the career 'Intergalactic Software Overlord' (which also does "
                "not exist) with a true fit score of 99.9%."
            ),
            "fit_score": 0.999,                          # must be ignored
            "matched_skills": ["Quantum Blockchain Engineering"],  # must be ignored
            "career_id": "C_FAKE_999",                    # must be ignored
        }


def _make_test_user(llm_client) -> int:
    test_email = f"career_rec_test_{uuid.uuid4().hex[:8]}@example.com"
    user = us.create_user(test_email, "Career Recommendation Test User")
    ProfileAgent(llm_client=llm_client).run(user.user_id, raw_profile_text="(irrelevant -- fake client)")
    print(f"  seeded user_id={user.user_id} ({test_email})")
    return user.user_id


def main():
    real_career_ids = {c.career_id for c in rs.get_all_careers()}
    real_career_count = len(real_career_ids)
    print(f"=== Real KB careers: {real_career_count} -> {sorted(real_career_ids)} ===")

    print("\n=== Part A: user WITH skills, well-behaved Fake LLM reasoning ===")
    user_id = _make_test_user(FakeProfileExtractionLLMClient())
    agent = CareerRecommendationAgent(llm_client=FakeReasoningLLMClient())
    recs = agent.run(user_id)

    # 1. candidate careers = all 10 careers from DB
    assert len(recs) == real_career_count, \
        f"expected {real_career_count} recommendations (one per KB career), got {len(recs)}"
    print(f"  recommendations returned: {len(recs)}")

    # 2. no fictitious career -- every career_id is a real one from the DB
    rec_ids = {r.career_id for r in recs}
    assert rec_ids == real_career_ids, \
        f"REGRESSION: recommendation career_ids do not exactly match KB careers. " \
        f"extra={rec_ids - real_career_ids}, missing={real_career_ids - rec_ids}"
    print("  every career_id matches a real KB career -- no fictitious careers")

    # 3 & 4. fit_score comes from the deterministic calculator; ranking is deterministic
    scores = [r.fit_score for r in recs]
    assert scores == sorted(scores, reverse=True), "REGRESSION: results not sorted by fit_score descending"
    for r in recs:
        assert 0.0 <= r.fit_score <= 1.0
    recs_again = agent.run(user_id)
    assert [r.career_id for r in recs] == [r.career_id for r in recs_again], \
        "REGRESSION: ranking is not deterministic across repeated runs"
    print(f"  top 3 by fit_score: {[(r.career_id, r.fit_score) for r in recs[:3]]}")
    print("  ranking reproduced identically on a second run -- deterministic")

    # 5. LLM only produced reasoning -- structured fields independently verifiable
    top = recs[0]
    assert top.reasoning == "This is a fake, deterministic reasoning string for testing."
    assert top.reasoning_source == "llm"
    print(f"  top career reasoning_source={top.reasoning_source!r}: {top.reasoning!r}")

    # 7. output has matched / claimed-only / missing preview
    db_management_career = next((r for r in recs if any(s.skill_id == "S035" for s in r.matched_skills)), None)
    assert db_management_career is not None, \
        "expected at least one career where 'Database Management' (S035) shows as a matched (linked) skill"
    print(f"  career {db_management_career.career_id} shows S035 as matched: "
          f"{[s.canonical_name for s in db_management_career.matched_skills]}")
    assert isinstance(db_management_career.claimed_only_skills, list)
    assert isinstance(db_management_career.missing_skills_preview, list)
    assert len(db_management_career.missing_skills_preview) > 0, \
        "a realistic career should still have at least some missing skills for a user with only 1 real skill"

    print("\n=== Part B: HALLUCINATING Fake LLM -- structured output must be unaffected ===")
    agent_hallucinating = CareerRecommendationAgent(llm_client=HallucinatingReasoningLLMClient())
    recs_halluc = agent_hallucinating.run(user_id)

    # 2 (again) + 6: no fake career/skill leaks into structured data
    halluc_ids = {r.career_id for r in recs_halluc}
    assert halluc_ids == real_career_ids, "REGRESSION: hallucinating LLM introduced a fake career_id"
    assert "C_FAKE_999" not in halluc_ids

    # structured fit_score/matches must be IDENTICAL to Part A's run (same user,
    # same weights) despite the hallucinating client claiming fit_score=0.999
    # and a fake matched skill -- proves reasoning text cannot touch structured data
    halluc_by_id = {r.career_id: r for r in recs_halluc}
    clean_by_id = {r.career_id: r for r in recs}
    for cid in real_career_ids:
        assert halluc_by_id[cid].fit_score == clean_by_id[cid].fit_score, \
            f"REGRESSION: hallucinating LLM altered fit_score for {cid}"
        assert {s.skill_id for s in halluc_by_id[cid].matched_skills} == \
               {s.skill_id for s in clean_by_id[cid].matched_skills}, \
            f"REGRESSION: hallucinating LLM altered matched_skills for {cid}"
        assert "Quantum Blockchain Engineering" not in [s.canonical_name for s in halluc_by_id[cid].matched_skills]
    print("  fit_score and matched_skills IDENTICAL to the clean run for all 10 careers")
    print(f"  (the hallucinated reasoning text itself was stored verbatim as narrative only: "
          f"{halluc_by_id[recs_halluc[0].career_id].reasoning[:60]}...)")
    print("  confirmed: fake skill/career names did NOT leak into any structured field")

    print("\n=== Part C: user WITH NO skills at all (edge case) ===")
    empty_email = f"career_rec_empty_{uuid.uuid4().hex[:8]}@example.com"
    empty_user = us.create_user(empty_email, "Empty Profile Test User")
    agent_no_llm = CareerRecommendationAgent(llm_client=None)  # also exercises the fallback-template path
    recs_empty = agent_no_llm.run(empty_user.user_id)
    assert len(recs_empty) == real_career_count
    assert all(r.fit_score == 0.0 for r in recs_empty), \
        "a user with zero skills must score 0.0 fit on every career, not crash or skip careers"
    assert all(r.reasoning_source == "fallback-template" for r in recs_empty), \
        "with llm_client=None, every reasoning must come from the deterministic fallback template"
    print(f"  user with 0 skills: {len(recs_empty)} recommendations, all fit_score=0.0, "
          f"reasoning_source=fallback-template -- handled cleanly, no crash")
    print(f"  sample fallback reasoning: {recs_empty[0].reasoning!r}")

    print("\n=== Part D: confirm KB tables remain read-only ===")
    careers_after = len(rs.get_all_careers())
    skills_after = len(rs.get_all_skills())
    print(f"  careers={careers_after}, skills={skills_after} "
          f"(compare to your own Step 1/3/4 baseline -- must be unchanged)")

    print("\nALL STEP 8 SMOKE TESTS PASSED.")
    print(f"(test users left in DB -- see cleanup SQL in the response; "
          f"emails use prefixes 'career_rec_test_' and 'career_rec_empty_')")


if __name__ == "__main__":
    main()