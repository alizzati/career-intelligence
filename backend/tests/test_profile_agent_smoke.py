"""
STEP 7 smoke test -- provider-agnostic (no dependency on any specific
LLM provider class or name; works whether llm_client.py implements
Gemini, Anthropic, or anything else, because ProfileAgent only depends
on the LLMClient Protocol).

This test exercises the FULL pipeline (extraction -> normalization ->
persistence) against the REAL database, using hand-written Fake LLM
client test doubles below instead of a live API call. What IS proven:
  - the orchestration wiring (ProfileAgent.run) is correct end-to-end
  - the deterministic normalizer behaves correctly on real KB data
  - persistence via user_service/user_repository is correct
  - B1 (evidence-to-skill matching) is fixed: evidence with different
    casing/whitespace than its skill claim still attaches correctly
What is NOT proven here: actual LLM extraction quality against a real
model (that requires running the real Gemini client separately).

Run: python -m tests.test_profile_agent_smoke
"""
import sys, os, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.profile_agent import ProfileAgent
from app.services import user_service as us
from app.services import retrieval_service as rs


class FakeExtractionLLMClient:
    """
    Clearly-labeled test double simulating one LLM extraction response.
    Used ONLY to validate the surrounding pipeline, not LLM extraction
    quality.
    """
    def complete_json(self, system: str, user: str, max_tokens: int = 2000) -> dict:
        return {
            "skills": [
                {"claimed_skill": "Python", "proficiency": "intermediate", "candidate_skill_id": None},  # no language-level entry in this KB -> correctly unmatched
                {"claimed_skill": "Programing", "proficiency": "beginner", "candidate_skill_id": None},  # typo -> fuzzy match
                {"claimed_skill": "Database Management", "proficiency": "intermediate", "candidate_skill_id": "S035"},
                {"claimed_skill": "Quantum Error Correction", "proficiency": None, "candidate_skill_id": None},  # should stay unmatched
                {"claimed_skill": "a hallucination attempt", "proficiency": None, "candidate_skill_id": "S999_FAKE"},  # must be discarded
            ],
            "evidence": [
                {"claimed_skill": "Database Management", "evidence_type": "project",
                 "description": "Designed normalized schema for a course project", "url": None},
                {"claimed_skill": "Programing", "evidence_type": "self-report", "description": "Self-reported only", "url": None},
            ],
            "education": [
                {"institution": "Universitas Contoh", "degree": "S.Kom", "field_of_study": "Computer Science",
                 "start_date": "2020-08-01", "end_date": "2024-07-01", "description": "GPA 3.7"},
            ],
            "experience": [
                {"company": "StartupX", "role_title": "Backend Intern", "employment_type": "internship",
                 "start_date": "2023-06-01", "end_date": "2023-09-01", "description": "Built REST APIs"},
            ],
            "projects": [
                {"title": "Campus Course Scheduler", "description": "Normalized relational schema + API",
                 "url": None, "role": "Backend developer"},
            ],
            "certifications": [],
        }


def main():
    print("=== General Profile Agent pipeline test (FakeExtractionLLMClient) ===")
    test_email = f"profile_agent_test_{uuid.uuid4().hex[:8]}@example.com"
    user = us.create_user(test_email, "Profile Agent Test User")
    print(f"  created user_id={user.user_id}")

    agent = ProfileAgent(llm_client=FakeExtractionLLMClient())
    result = agent.run(user.user_id, raw_profile_text="(irrelevant -- fake client ignores this)")

    print(f"\n  skills_persisted={result.skills_persisted}, evidence_persisted={result.evidence_persisted}")
    for rep in result.normalizations:
        print(f"    '{rep.claimed_skill}' -> skill_id={rep.result.skill_id} method={rep.result.method}")

    norm_by_claim = {r.claimed_skill: r.result for r in result.normalizations}
    assert norm_by_claim["Database Management"].method == "exact-deterministic"
    assert norm_by_claim["Database Management"].skill_id == "S035"
    assert norm_by_claim["Programing"].method == "fuzzy-deterministic", \
        f"expected fuzzy match for typo, got {norm_by_claim['Programing'].method}"
    # NOTE: this KB (SKKNI/O*NET-derived) has no language-specific skill entries,
    # only the generic "Programming" skill. "Python" vs "Programming" is NOT a
    # safe fuzzy match (different concepts), so 'unmatched' is the CORRECT outcome.
    assert norm_by_claim["Python"].method == "unmatched" and norm_by_claim["Python"].skill_id is None, \
        "Python has no KB entry in this dataset -- should be unmatched, not force-matched"
    assert norm_by_claim["Quantum Error Correction"].method == "unmatched"
    assert norm_by_claim["Quantum Error Correction"].skill_id is None
    assert norm_by_claim["a hallucination attempt"].skill_id is None, \
        "REGRESSION: hallucinated skill_id (S999_FAKE) was persisted"

    print("\n=== Verify via get_user_full_profile() ===")
    full = us.get_user_full_profile(user.user_id)
    assert len(full.education) == 1 and full.education[0].institution == "Universitas Contoh"
    assert len(full.experience) == 1 and full.experience[0].company == "StartupX"
    assert len(full.projects) == 1

    skills_by_claim = {s.claimed_skill: s for s in full.skills}
    db_skill = skills_by_claim["Database Management"]
    assert db_skill.skill_id == "S035" and db_skill.evidence_status == "linked" and len(db_skill.evidence) == 1
    print(f"  Database Management: skill_id={db_skill.skill_id} status={db_skill.evidence_status} "
          f"evidence={len(db_skill.evidence)}")

    typo_skill = skills_by_claim["Programing"]
    assert typo_skill.skill_id == "S065"  # fuzzy-resolved to 'Programming'
    assert typo_skill.evidence_status == "linked"  # has a self-report evidence row
    print(f"  Programing (typo): skill_id={typo_skill.skill_id} normalized={typo_skill.normalized_skill} "
          f"status={typo_skill.evidence_status}")

    unmatched_skill = skills_by_claim["Quantum Error Correction"]
    assert unmatched_skill.skill_id is None
    assert unmatched_skill.evidence_status == "none", \
        "a claim with no evidence AND no KB match must still be 'none', never 'missing' or dropped"
    print(f"  Quantum Error Correction: skill_id={unmatched_skill.skill_id} "
          f"status={unmatched_skill.evidence_status}  (claim preserved, correctly unmatched, NOT dropped)")

    hallucination_skill = skills_by_claim["a hallucination attempt"]
    assert hallucination_skill.skill_id is None, \
        "REGRESSION: hallucinated skill_id leaked into persisted user_skills row"
    print(f"  'a hallucination attempt': skill_id={hallucination_skill.skill_id} "
          f"(correctly rejected, NOT silently accepted)")

    print("\n=== KB row counts seen by this run (compare to your own Step 1/3/4 baseline) ===")
    print(f"  careers={len(rs.get_all_careers())}, skills={len(rs.get_all_skills())}")

    print("\nALL GENERAL PROFILE AGENT TESTS PASSED.")
    print(f"(test user left in DB: user_id={user.user_id}, email={test_email})")


class B1CasingVariantLLMClient:
    """
    Fake LLM client purpose-built to prove B1 is fixed.

    skills[] claims "Database Management" ONCE.
    evidence[] refers to it with DIFFERENT casing AND extra whitespace:
        "  DATABASE   management  "
    A second skill, "Unclaimed Skill Example", is claimed with NO evidence
    at all, as a control: it must stay evidence_status='none' in the SAME
    run, proving status changes are driven by actual evidence persistence
    per-skill, not some global side effect of the fix.
    """
    def complete_json(self, system: str, user: str, max_tokens: int = 2000) -> dict:
        return {
            "skills": [
                {"claimed_skill": "Database Management", "proficiency": "intermediate", "candidate_skill_id": "S035"},
                {"claimed_skill": "Unclaimed Skill Example", "proficiency": None, "candidate_skill_id": None},
            ],
            "evidence": [
                {"claimed_skill": "  DATABASE   management  ", "evidence_type": "project",
                 "description": "B1 proof: casing+whitespace variant of the skill claim", "url": None},
            ],
            "education": [], "experience": [], "projects": [], "certifications": [],
        }


def test_b1_evidence_matching():
    print("=== B1 FIX VERIFICATION: evidence with different casing/whitespace than its skill claim ===")
    test_email = f"b1_evidence_matching_{uuid.uuid4().hex[:8]}@example.com"
    user = us.create_user(test_email, "B1 Evidence Matching Test User")

    agent = ProfileAgent(llm_client=B1CasingVariantLLMClient())
    result = agent.run(user.user_id, raw_profile_text="(irrelevant -- fake client ignores this)")
    print(f"  skills_persisted={result.skills_persisted}, evidence_persisted={result.evidence_persisted}")

    # (3) evidence actually persisted (not silently skipped)
    assert result.evidence_persisted == 1, \
        f"B1 NOT FIXED: expected evidence to attach despite casing/whitespace difference, " \
        f"got evidence_persisted={result.evidence_persisted}"

    full = us.get_user_full_profile(user.user_id)

    # (1) only ONE user_skill row for "Database Management" -- no duplicate created
    #     by the casing-variant text appearing in evidence[]
    db_rows = [s for s in full.skills if s.claimed_skill == "Database Management"]
    assert len(db_rows) == 1, \
        f"FAIL: expected exactly 1 user_skill row for 'Database Management', found {len(db_rows)}"
    db = db_rows[0]

    # (6) original claimed_skill text preserved EXACTLY as given in skills[] --
    #     NOT overwritten by the evidence's casing-variant string
    assert db.claimed_skill == "Database Management", \
        f"FAIL: claimed_skill was altered, now reads {db.claimed_skill!r}"

    # (5) canonical skill_id untouched by the fix
    assert db.skill_id == "S035", f"FAIL: skill_id changed unexpectedly, got {db.skill_id!r}"

    # (2) + (4): evidence found the correct user_skill AND evidence_status
    # transitioned none -> linked as a direct result of a persisted evidence row
    assert db.evidence_status == "linked", \
        f"B1 NOT FIXED: evidence_status is {db.evidence_status!r}, expected 'linked'"

    # (8) evidence count correct -- not zero (dropped), not duplicated
    assert len(db.evidence) == 1, \
        f"FAIL: expected exactly 1 evidence item, found {len(db.evidence)}"
    assert "B1 proof" in db.evidence[0].description

    print(f"  Database Management: claimed_skill={db.claimed_skill!r} skill_id={db.skill_id} "
          f"status={db.evidence_status} evidence_count={len(db.evidence)}")
    print(f"  evidence[0].description = {db.evidence[0].description!r}")

    # Control: the OTHER skill in the same run, which received no evidence,
    # must remain 'none' -- proves the status change above is evidence-driven,
    # not a side effect of the fix touching every row.
    control_rows = [s for s in full.skills if s.claimed_skill == "Unclaimed Skill Example"]
    assert len(control_rows) == 1
    control = control_rows[0]
    assert control.evidence_status == "none" and len(control.evidence) == 0, \
        "FAIL: control skill (no evidence) unexpectedly changed status"
    print(f"  Unclaimed Skill Example (control): status={control.evidence_status} "
          f"evidence_count={len(control.evidence)}  (correctly stayed 'none')")

    # (7) no duplicate user_skill rows anywhere in this profile as a side effect
    all_claims = [s.claimed_skill for s in full.skills]
    assert len(all_claims) == len(set(all_claims)) == 2, \
        f"FAIL: unexpected duplicate user_skill rows: {all_claims}"

    print("\nB1 FIX VERIFIED -- all 8 required proof points hold.")
    print(f"(test user left in DB: user_id={user.user_id}, email={test_email})")


if __name__ == "__main__":
    main()
    print()
    test_b1_evidence_matching()