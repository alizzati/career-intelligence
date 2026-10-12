"""
Smoke test: exercises every retrieval function required by STEP 5 against
the live, already-populated career_intelligence database. Read-only.

Run: python -m tests.test_retrieval_service_smoke   (from backend/)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import retrieval_service as rs


def main():
    print("=== get_all_careers() ===")
    careers = rs.get_all_careers()
    assert len(careers) == 10, f"expected 10 careers, got {len(careers)}"
    for c in careers:
        print(f"  {c.career_id}  {c.canonical_name}  ({c.domain})")

    print("\n=== get_career('C01') ===")
    c01 = rs.get_career("C01")
    assert c01 is not None
    print(f"  {c01}")

    print("\n=== get_career('C99') [nonexistent -> should be None] ===")
    print(f"  {rs.get_career('C99')}")

    print("\n=== get_career_skills('C01') ===")
    cs = rs.get_career_skills("C01")
    assert len(cs) == 15, f"expected 15 career_skills for C01, got {len(cs)}"
    print(f"  {len(cs)} skills, sample: {cs[0].skill.canonical_name} "
          f"[{cs[0].evidence_class}/{cs[0].confidence}]")

    print("\n=== get_occupations_for_career('C01') ===")
    occs = rs.get_occupations_for_career("C01")
    for o in occs:
        print(f"  {o.occupation.occupation_id}  {o.occupation.canonical_name}  conf={o.confidence}")

    print("\n=== get_occupation_competencies(<first occupation of C01>) ===")
    comps = rs.get_occupation_competencies(occs[0].occupation.occupation_id)
    for comp in comps:
        print(f"  {comp.standard_id} ({comp.standard_title}) - {len(comp.units)} units")

    print("\n=== get_skill_evidence() -- one skill WITH structured evidence ===")
    ev1 = rs.get_skill_evidence(cs[0].skill.skill_id)
    for e in ev1:
        print(f"  [{e.granularity}] {e.source_name}: {e.reference}")

    print("\n=== get_skill_evidence('S009') -- CI/CD, known to lack skill_source_evidence"
          " (STEP 4 Check 9) but MUST still return career-skill-level evidence ===")
    ev2 = rs.get_skill_evidence("S009")
    assert len(ev2) > 0, "REGRESSION: S009 returned zero evidence items -- Check 9 fix broken"
    assert all(e.granularity == "career-skill-level" for e in ev2), \
        "S009 should have ONLY career-skill-level evidence"
    for e in ev2:
        print(f"  [{e.granularity}] {e.source_name}: {e.reference}")

    print("\n=== get_occupational_context('C01') -- full bundle ===")
    ctx = rs.get_occupational_context("C01")
    assert ctx is not None
    print(f"  career: {ctx.career.canonical_name}")
    print(f"  occupations: {[o.occupation_id for o in ctx.occupations]}")
    print(f"  career_skills: {len(ctx.career_skills)}")
    print(f"  competencies (standards): {[c.standard_id for c in ctx.competencies]}")
    for oid, tl in ctx.tasks.items():
        print(f"  tasks[{oid}]: {len(tl)}")
    for oid, tel in ctx.technologies.items():
        print(f"  technologies[{oid}]: {len(tel)}")
    for oid, sml in ctx.source_mappings.items():
        print(f"  source_mappings[{oid}]: {len(sml)} "
              f"(with provenance: {sum(1 for m in sml if m.provenance)})")

    print("\n=== get_occupational_context('C99') [nonexistent -> should be None] ===")
    print(f"  {rs.get_occupational_context('C99')}")

    print("\nALL SMOKE TESTS PASSED.")


if __name__ == "__main__":
    main()