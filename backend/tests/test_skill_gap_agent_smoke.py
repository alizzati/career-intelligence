"""
Step 10 smoke / integration test: Skill-Gap Agent against the REAL database,
real Step 9 engine, and the real KB vocabulary used by the grounding guard.

The LLM is a hand-written mock (same convention as the Step 7/8 smoke tests).
A live-LLM section exists but is SKIPPED unless explicitly enabled, because
the project's convention is that tests never need a live API:

    set SKILL_GAP_LIVE_LLM_FACTORY=app.agents.llm_client:<ClientClassOrFactory>
    (the callable is invoked with no arguments and must return an LLMClient)

Test users are removed in a `finally` block by exact user_id (no TRUNCATE).

Run: python -m tests.test_skill_gap_agent_smoke
"""
import importlib
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.agents.career_recommendation_agent import CareerRecommendationAgent
from app.agents.skill_gap_agent import NarrativeGenerationError, SkillGapAgent, load_kb_vocabulary
from app.core.db import engine
from app.services import retrieval_service as rs
from app.services import skill_gap_service as sgs
from app.services import user_service as us
from app.services.career_fit_service import load_scoring_weights

KB_BASELINE = {"careers": 10, "skills": 87, "career_skills": 155, "competency_units": 146}
created_user_ids: list[int] = []


def kb_counts() -> dict:
    with engine.connect() as conn:
        return {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar() for t in KB_BASELINE}


def new_user(label: str) -> int:
    user = us.create_user(f"skill_gap_agent_test_{label}_{uuid.uuid4().hex[:8]}@example.com", f"Skill Gap Agent {label}")
    created_user_ids.append(user.user_id)
    return user.user_id


def ids(items):
    return [i.skill_id for i in items]


def faithful_response(gap) -> dict:
    """What an honest model would return: only names/ids from the deterministic result,
    empty lists for empty categories."""
    def names(items):
        return ", ".join(i.canonical_name for i in items)
    n_req = len(gap.matched_evidenced) + len(gap.matched_claimed_only) + len(gap.missing)
    r = {
        "summary": (f"{gap.canonical_name} ({gap.domain}): the profile was compared with {n_req} required skills. "
                    f"Career-fit score: {gap.fit_score * 100:.1f}%."),
        "strengths": [], "claimed_only_observations": [], "missing_skill_observations": [],
        "unmatched_claim_observations": [],
        "conclusion": "The comparison reflects the current profile; claimed skills still need linked evidence.",
    }
    if gap.matched_evidenced:
        r["strengths"].append({"skill_ids": ids(gap.matched_evidenced),
                               "text": f"{names(gap.matched_evidenced)} are supported by linked evidence."})
    if gap.matched_claimed_only:
        r["claimed_only_observations"].append({"skill_ids": ids(gap.matched_claimed_only),
                                               "text": f"{names(gap.matched_claimed_only)} are claimed by the user but not yet supported by linked evidence."})
    if gap.missing:
        r["missing_skill_observations"].append({"skill_ids": ids(gap.missing),
                                                "text": f"{names(gap.missing)} are required but have no corresponding canonical skill in the profile."})
    if gap.unmatched_user_claims:
        r["unmatched_claim_observations"].append({
            "user_skill_ids": [u.user_skill_id for u in gap.unmatched_user_claims],
            "text": ("; ".join(f"'{u.claimed_skill}'" for u in gap.unmatched_user_claims)
                     + " could not be mapped to the knowledge base, so they are not counted as missing requirements."),
        })
    return r


class MockLLM:
    """`respond(gap)` builds the response from the Step 9 result the test supplies via `.gap`."""
    def __init__(self, respond):
        self.respond, self.gap, self.calls = respond, None, 0

    def complete_json(self, system, user, max_tokens=2000):
        self.calls += 1
        return self.respond(self.gap)


class FailingLLM:
    def __init__(self):
        self.calls = 0

    def complete_json(self, system, user, max_tokens=2000):
        self.calls += 1
        raise ConnectionError("simulated provider outage")


def run_tests():
    print("=== KB baseline (before) ===")
    before = kb_counts()
    print(f"  {before}")
    assert before == KB_BASELINE

    careers = rs.get_all_careers()
    career = careers[0]
    required = rs.get_career_skills(career.career_id)
    evidenced_skill, claimed_only_skill = required[0].skill, required[1].skill

    user_id = new_user("mixed")
    a = us.add_user_skill(user_id, claimed_skill=evidenced_skill.canonical_name, skill_id=evidenced_skill.skill_id,
                          normalized_skill=evidenced_skill.canonical_name, proficiency="intermediate")
    us.add_skill_evidence(a.user_skill_id, evidence_type="project", description="seed evidence")
    us.add_user_skill(user_id, claimed_skill=claimed_only_skill.canonical_name, skill_id=claimed_only_skill.skill_id,
                      normalized_skill=claimed_only_skill.canonical_name, proficiency="beginner")
    us.add_user_skill(user_id, claimed_skill="Some Totally Unnormalizable Claim", skill_id=None)

    vocab = load_kb_vocabulary()
    print(f"\n=== Real KB vocabulary for the guard: {len(vocab.skill_names)} skills, "
          f"{len(vocab.career_names)} careers, {len(vocab.technology_names)} technologies ===")
    assert (len(vocab.skill_names), len(vocab.career_names)) == (87, 10) and len(vocab.technology_names) > 0

    print("\n=== 1. valid user + valid career: deterministic result + narrative ===")
    llm = MockLLM(faithful_response)
    llm.gap = sgs.analyze_skill_gap(user_id, career.career_id)
    agent = SkillGapAgent(llm_client=llm, vocabulary=vocab)
    out = agent.run(user_id, career.career_id)
    print(f"  source={out.narrative_source}, notes={out.validation_notes}, fit_score={out.skill_gap.fit_score}")
    assert out.narrative_source == "llm" and out.validation_notes == [] and llm.calls == 1
    assert out.skill_gap.model_dump() == llm.gap.model_dump()
    assert ids(out.skill_gap.matched_evidenced) == [evidenced_skill.skill_id]
    assert ids(out.skill_gap.matched_claimed_only) == [claimed_only_skill.skill_id]
    assert out.narrative.strengths[0].skill_ids == [evidenced_skill.skill_id]
    assert out.narrative.claimed_only_observations[0].skill_ids == [claimed_only_skill.skill_id]
    assert [u.claimed_skill for u in out.skill_gap.unmatched_user_claims] == ["Some Totally Unnormalizable Claim"]

    print("\n=== 2. honest narratives pass the guard for ALL careers (false-positive sweep on real KB names) "
          "and Step 10 == Step 8 fit ===")
    recs = {r.career_id: r for r in CareerRecommendationAgent(llm_client=None).run(user_id)}
    for c in careers:
        llm.gap = sgs.analyze_skill_gap(user_id, c.career_id)
        res = agent.run(user_id, c.career_id)
        assert res.narrative_source == "llm" and not res.validation_notes, (c.career_id, res.validation_notes)
        assert res.skill_gap.fit_score == recs[c.career_id].fit_score
        assert res.skill_gap.score_breakdown.model_dump() == recs[c.career_id].score_breakdown.model_dump()
    print(f"  {len(careers)}/{len(careers)} careers: source=llm, no notes, fit_score and score_breakdown identical to Step 8")

    custom = dict(load_scoring_weights(), claim_only_multiplier=0.3)
    llm.gap = sgs.analyze_skill_gap(user_id, career.career_id, custom)
    res = SkillGapAgent(llm_client=llm, weights=custom, vocabulary=vocab).run(user_id, career.career_id)
    rec = next(r for r in CareerRecommendationAgent(llm_client=None, weights=custom).run(user_id) if r.career_id == career.career_id)
    assert res.skill_gap.fit_score == rec.fit_score and res.narrative_source == "llm"

    print("\n=== 3. hallucinating LLM using REAL KB names cannot alter Step 9 or leak ungrounded content ===")
    grounded = {r.skill.canonical_name.lower() for r in required}
    outsider = next(n for n in vocab.skill_names
                    if not any(n.lower() in g or g in n.lower() for g in grounded))
    tech = next(t for t in vocab.technology_names if len(t) >= 4 and t not in ("Python",))
    other_career = next(n for n in vocab.career_names if n != career.canonical_name
                        and career.canonical_name.lower() not in n.lower() and n.lower() not in career.canonical_name.lower())

    def hallucinate(gap):
        r = faithful_response(gap)
        r.update({"fit_score": 0.999, "career_id": "C_FAKE", "priority_tiers": {"high": ids(gap.missing)}})
        r["summary"] = f"{gap.canonical_name} is the top priority career; it scores 99.9%."
        r["strengths"] = [{"skill_ids": ["S_FAKE_999"], "text": "A fake skill id."},
                          {"skill_ids": ids(gap.matched_evidenced), "text": f"{tech} experience is also strong."}]
        r["missing_skill_observations"] = [
            {"skill_ids": ids(gap.missing)[:1], "text": f"Also learn {outsider}."},
            {"skill_ids": ids(gap.matched_evidenced), "text": "Everything is missing."},
        ]
        r["conclusion"] = f"They should switch to {other_career}."
        return r

    gap_before = sgs.analyze_skill_gap(user_id, career.career_id)
    llm_h = MockLLM(hallucinate)
    llm_h.gap = gap_before
    out = SkillGapAgent(llm_client=llm_h, vocabulary=vocab).run(user_id, career.career_id)
    gap_after = sgs.analyze_skill_gap(user_id, career.career_id)
    assert gap_before.model_dump() == gap_after.model_dump() == out.skill_gap.model_dump(), "Step 9 result changed"
    assert out.narrative_source == "llm-partial"
    notes = " | ".join(out.validation_notes)
    for fragment in ("ignored unexpected key 'fit_score'", "ignored unexpected key 'career_id'", "ignored unexpected key 'priority_tiers'",
                     "S_FAKE_999", f"mentions '{tech}'", f"mentions '{outsider}'", f"mentions '{other_career}'",
                     "priority/prioritization language", "percentage 99.9%"):
        assert fragment in notes, (fragment, out.validation_notes)
    dumped = str(out.narrative.model_dump())
    for bad in ("S_FAKE_999", tech, outsider, other_career, "99.9", "top priority"):
        assert bad not in dumped, bad
    print(f"  dropped: fake id, technology {tech!r}, outsider skill {outsider!r}, other career {other_career!r}, "
          f"priority wording, invented percentage; Step 9 result identical before/after")

    print("\n=== 4. no skills / only-unmatched users ===")
    empty_id = new_user("empty")
    llm.gap = sgs.analyze_skill_gap(empty_id, career.career_id)
    r_empty = agent.run(empty_id, career.career_id)
    assert len(r_empty.skill_gap.missing) == len(required) and r_empty.narrative.strengths == []
    assert r_empty.narrative_source == "llm"
    llm_bad = MockLLM(lambda g: dict(faithful_response(g), strengths=[{"skill_ids": [required[0].skill.skill_id], "text": "A strength."}]))
    llm_bad.gap = llm.gap
    r_bad = SkillGapAgent(llm_client=llm_bad, vocabulary=vocab).run(empty_id, career.career_id)
    assert r_bad.narrative.strengths == [] and r_bad.narrative_source == "llm-partial", "invented strength must be dropped"

    un_id = new_user("unmatched_only")
    us.add_user_skill(un_id, claimed_skill="Unknown Thing A", skill_id=None)
    us.add_user_skill(un_id, claimed_skill="Unknown Thing B", skill_id=None)
    llm.gap = sgs.analyze_skill_gap(un_id, career.career_id)
    r_un = agent.run(un_id, career.career_id)
    assert len(r_un.skill_gap.missing) == len(required) and len(r_un.skill_gap.unmatched_user_claims) == 2
    assert r_un.narrative_source == "llm" and len(r_un.narrative.unmatched_claim_observations) == 1
    assert "Unknown Thing" not in str(r_un.narrative.missing_skill_observations)

    print("\n=== 5. invalid user / invalid career: controlled errors, LLM never called ===")
    guarded = MockLLM(faithful_response)
    for call, exc in ((lambda: SkillGapAgent(llm_client=guarded, vocabulary=vocab).run(999999999, career.career_id), sgs.UserNotFoundError),
                      (lambda: SkillGapAgent(llm_client=guarded, vocabulary=vocab).run(user_id, "C_DOES_NOT_EXIST"), sgs.CareerNotFoundError)):
        try:
            call()
            raise AssertionError(f"expected {exc.__name__}")
        except exc as e:
            print(f"  {exc.__name__}: {e}")
    assert guarded.calls == 0

    print("\n=== 6. LLM failure keeps the deterministic result; strict mode raises ===")
    failing = FailingLLM()
    out = SkillGapAgent(llm_client=failing, vocabulary=vocab).run(user_id, career.career_id)
    assert out.narrative_source == "fallback-template" and out.llm_error.startswith("LLM call failed: ConnectionError")
    assert out.skill_gap.model_dump() == gap_before.model_dump()
    try:
        SkillGapAgent(llm_client=FailingLLM(), vocabulary=vocab, strict_llm=True).run(user_id, career.career_id)
        raise AssertionError("strict_llm must raise")
    except NarrativeGenerationError:
        pass
    out_none = SkillGapAgent(llm_client=None).run(user_id, career.career_id)
    assert out_none.narrative_source == "fallback-template" and out_none.llm_error is None

    print("\n=== 7. Step 9 result identical after all agent runs; KB unchanged ===")
    assert sgs.analyze_skill_gap(user_id, career.career_id).model_dump() == gap_before.model_dump()
    after = kb_counts()
    print(f"  {after}")
    assert after == before == KB_BASELINE

    print("\n=== 8. optional live LLM check ===")
    spec = os.environ.get("SKILL_GAP_LIVE_LLM_FACTORY", "").strip()
    if not spec:
        print("  SKIPPED (set SKILL_GAP_LIVE_LLM_FACTORY=module:callable to enable; project tests default to mocks)")
    else:
        module_name, _, attr = spec.partition(":")
        client = getattr(importlib.import_module(module_name), attr)()
        live = SkillGapAgent(llm_client=client).run(user_id, career.career_id)
        assert live.skill_gap.model_dump() == gap_before.model_dump(), "live LLM must not change the Step 9 result"
        assert live.narrative_source in ("llm", "llm-partial", "fallback-template")
        print(f"  LIVE run: source={live.narrative_source}, llm_error={live.llm_error}, notes={len(live.validation_notes)}")
        for n in live.validation_notes:
            print(f"    note: {n}")
        if live.narrative_source != "fallback-template":
            print(f"    summary: {live.narrative.summary}")

    print("\nALL STEP 10 SMOKE TESTS PASSED.")


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