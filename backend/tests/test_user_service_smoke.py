"""
End-to-end smoke test for the user domain (STEP 6).

Key behavior under test: a claimed skill with NO evidence must show
evidence_status == 'none', NOT be dropped or silently marked 'missing'.
A second claimed skill WITH evidence must show evidence_status == 'linked'.

Run: python -m tests.test_user_service_smoke   (from backend/)
"""
import sys, os, uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import user_service as us
from app.services import retrieval_service as rs


def main():
    test_email = f"smoke_test_{uuid.uuid4().hex[:8]}@example.com"

    print("=== create_user() ===")
    user = us.create_user(test_email, "Smoke Test User")
    print(f"  {user}")

    print("\n=== set_profile() ===")
    us.set_profile(user.user_id, headline="Fresh IT Graduate",
                    summary="Aspiring backend engineer", target_domain="Backend Engineering")

    print("\n=== add_user_skill('Python') -- NO evidence provided ===")
    py_skill = us.add_user_skill(user.user_id, claimed_skill="Python")
    print(f"  {py_skill}")
    assert py_skill.evidence_status == "none", \
        f"REGRESSION: expected evidence_status='none', got {py_skill.evidence_status!r}"
    assert py_skill.skill_id is None, "unnormalized skill should have skill_id=None"
    print("  OK: claimed-without-evidence is 'none', not dropped, not 'missing'.")

    print("\n=== add_user_skill('Database Management') -- will attach KB-normalized skill_id + evidence ===")
    # look up the real KB skill_id via the retrieval service (no guessing/hardcoding the ID)
    target_name = "Database Management"
    candidates = [cs.skill for cs in rs.get_career_skills("C01") if cs.skill.canonical_name == target_name]
    assert candidates, f"expected {target_name!r} to exist among C01 career_skills in the KB"
    sql_skill_id = candidates[0].skill_id
    sql_us = us.add_user_skill(user.user_id, claimed_skill="Database Management", skill_id=sql_skill_id,
                                normalized_skill=target_name, proficiency="intermediate")
    print(f"  {sql_us}")

    print("\n=== add_skill_evidence() for SQL, sourced from a project ===")
    proj_ev = us.add_skill_evidence(
        sql_us.user_skill_id, evidence_type="project", source_table="user_projects",
        source_id=None, description="Built a normalized schema for a course project",
    )
    print(f"  {proj_ev}")

    print("\n=== get_user_full_profile() ===")
    full = us.get_user_full_profile(user.user_id)
    assert full is not None
    print(f"  user: {full.user.full_name} <{full.user.email}>")
    print(f"  profile.target_domain: {full.profile.target_domain}")
    for s in full.skills:
        print(f"  skill: {s.claimed_skill!r} skill_id={s.skill_id} "
              f"status={s.evidence_status} evidence_count={len(s.evidence)}")

    python_in_profile = next(s for s in full.skills if s.claimed_skill == "Python")
    sql_in_profile = next(s for s in full.skills if s.claimed_skill == "Database Management")
    assert python_in_profile.evidence_status == "none" and len(python_in_profile.evidence) == 0
    assert sql_in_profile.evidence_status == "linked" and len(sql_in_profile.evidence) == 1
    assert sql_in_profile.skill_id == sql_skill_id, "Database Management should be normalized to the real KB skill_id"

    print("\n=== get_user_full_profile() for nonexistent user -> None ===")
    print(f"  {us.get_user_full_profile(999999)}")

    print("\nALL USER-DOMAIN SMOKE TESTS PASSED.")
    print(f"(test user left in DB: user_id={user.user_id}, email={test_email} -- harmless, isolated test row)")


if __name__ == "__main__":
    main()