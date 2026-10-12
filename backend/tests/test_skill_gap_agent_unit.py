"""
Unit tests for the Skill-Gap Agent (Step 10) and its grounding guard.

No database queries and no live LLM: the Step 9 result is built in memory with
classify_skill_gap (the pure function inside the frozen Step 9 service), and
the LLM is replaced by the hand-written fake clients below, following the
convention of the Step 7/8 tests.

Run: python -m tests.test_skill_gap_agent_unit
"""
import ast
import inspect
import os
import re
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents import skill_gap_agent as agent_module
from app.agents import skill_gap_grounding as grounding
from app.agents.skill_gap_agent import NarrativeGenerationError, SkillGapAgent, build_user_prompt
from app.agents.skill_gap_grounding import (
    LABEL_EVIDENCED, LABEL_MISSING, Vocabulary, _Context, _affirmative_hits, _text_problems,
    build_fallback_narrative, validate_narrative,
)
from app.schemas import skill_gap_agent as agent_schemas
from app.schemas.retrieval import CareerOut, CareerSkillOut, SkillOut
from app.schemas.skill_gap import SkillGapResult
from app.schemas.skill_gap_agent import SkillGapAnalysisOut
from app.schemas.user import UserSkillEvidenceOut, UserSkillOut
from app.services.career_fit_service import DEFAULT_WEIGHTS
from app.services.skill_gap_service import classify_skill_gap

W = DEFAULT_WEIGHTS
CAREER = CareerOut(career_id="CX", canonical_name="Test Career", domain="Test Domain")


def req(skill_id, name, evidence_class, confidence):
    return CareerSkillOut(
        relationship_id=f"R_{skill_id}",
        skill=SkillOut(skill_id=skill_id, canonical_name=name, skill_group_id="SG00", status="active"),
        evidence_class=evidence_class, confidence=confidence, mapping_method="test", evidence_source_text="test",
    )


def usk(uid, claimed, skill_id, status, proficiency=None, n_evidence=0):
    return UserSkillOut(
        user_skill_id=uid, claimed_skill=claimed, skill_id=skill_id, normalized_skill=None,
        proficiency=proficiency, evidence_status=status, confidence="unknown",
        evidence=[UserSkillEvidenceOut(evidence_id=i, evidence_type="project") for i in range(n_evidence)],
    )


REQUIRED = [
    req("S900", "Skill Nine", "SUPPORTING", "medium"),
    req("S100", "Skill One", "CORE", "high"),
    req("S500", "Skill Five", "CORE", "medium"),
    req("S300", "Skill Three", "SUPPORTING", "high"),
    req("S700", "Skill Seven", "CORE", "high"),
]


def mixed_user():
    return [
        usk(1, "skill one (evidenced)", "S100", "linked", "advanced", 2),
        usk(2, "Skill Three claim", "S300", "none", "beginner", 0),
        usk(3, "Skill Nine", "S900", "linked", None, 1),
        usk(4, "Python", None, "linked", "intermediate", 1),
        usk(5, "Some Framework", None, "none", None, 0),
    ]


GAP = classify_skill_gap(7, CAREER, REQUIRED, mixed_user(), W)
GAP_EMPTY = classify_skill_gap(7, CAREER, REQUIRED, [], W)
GAP_UNMATCHED_ONLY = classify_skill_gap(
    7, CAREER, REQUIRED, [usk(1, "Python", None, "linked", None, 1), usk(2, "Docker-ish", None, "none")], W)
GAP_ALL_EVIDENCED = classify_skill_gap(
    7, CAREER, REQUIRED, [usk(i, f"claim {i}", c.skill.skill_id, "linked", None, 1) for i, c in enumerate(REQUIRED, 1)], W)

# KB-like vocabulary: names the guard must recognize as "known but not in this context"
VOCAB = Vocabulary(
    skill_names=("Skill One", "Skill Three", "Skill Five", "Skill Seven", "Skill Nine", "Debugging", "Networking"),
    technology_names=("Docker", "Kubernetes", "React", "Amazon Web Services AWS", "Python", "Go", "R", "C#"),
    career_names=("Test Career", "Big Test Career", "Other Career"),
)


def pct(gap):
    return f"{gap.fit_score * 100:.1f}%"


def good_response(gap=GAP):
    return {
        "summary": f"Test Career (Test Domain): 2 of 5 required skills are matched with linked evidence, 1 is claimed "
                   f"without linked evidence, and 2 have no corresponding canonical skill in the profile. "
                   f"Career-fit score: {pct(gap)}.",
        "strengths": [{"skill_ids": ["S100", "S900"], "text": "Skill One and Skill Nine are supported by linked evidence in the profile."}],
        "claimed_only_observations": [{"skill_ids": ["S300"], "text": "Skill Three is claimed by the user but not yet supported by linked evidence."}],
        "missing_skill_observations": [{"skill_ids": ["S500", "S700"], "text": "Skill Five and Skill Seven are required by this career but have no corresponding canonical skill in the profile."}],
        "unmatched_claim_observations": [{"user_skill_ids": [4, 5], "text": "'Python' and 'Some Framework' could not be mapped to the knowledge base, so they are not counted as missing requirements."}],
        "conclusion": "The profile shows evidence for part of the requirements; the claimed skill still needs linked evidence and the unmapped claims were outside the comparison.",
    }


class ScriptedLLM:
    def __init__(self, response):
        self.response, self.calls = response, []

    def complete_json(self, system, user, max_tokens=2000):
        self.calls.append({"system": system, "user": user, "max_tokens": max_tokens})
        return self.response


class RaisingLLM:
    def __init__(self, exc):
        self.exc, self.calls = exc, 0

    def complete_json(self, system, user, max_tokens=2000):
        self.calls += 1
        raise self.exc


def run_agent(response, gap=GAP, **kwargs):
    return SkillGapAgent(llm_client=ScriptedLLM(response), vocabulary=VOCAB, **kwargs).explain(gap)


def has_note(out, text):
    return any(text in n for n in out.validation_notes)


def main():
    before = GAP.model_dump()

    print("=== 1. Clean LLM narrative is accepted unchanged; Step 9 result is embedded untouched ===")
    llm = ScriptedLLM(good_response())
    out = SkillGapAgent(llm_client=llm, vocabulary=VOCAB).explain(GAP)
    assert out.narrative_source == "llm" and out.validation_notes == [] and out.llm_error is None
    assert out.narrative.strengths[0].skill_ids == ["S100", "S900"]
    assert out.skill_gap is GAP and out.skill_gap.model_dump() == before
    assert len(llm.calls) == 1 and llm.calls[0]["max_tokens"] == agent_module.LLM_MAX_TOKENS
    print("  source=llm, no validation notes, skill_gap is the very same Step 9 object")

    print("\n=== 2. The prompt carries the authoritative deterministic result and nothing outside it ===")
    system, user = llm.calls[0]["system"], llm.calls[0]["user"]
    for marker in ("=== USER PROFILE / SKILL-GAP CONTEXT ===", "=== DETERMINISTIC RESULTS", "=== INSTRUCTIONS ===", "=== OUTPUT REQUIREMENTS ==="):
        assert marker in user, marker
    assert "authoritative" in system and "never recompute" in system
    for item in GAP.matched_evidenced + GAP.matched_claimed_only + GAP.missing:
        assert item.skill_id in user and item.canonical_name in user
    for u in GAP.unmatched_user_claims:
        assert str(u.user_skill_id) in user and u.claimed_skill in user
    assert "self_reported_proficiency" in user
    for name in VOCAB.technology_names:
        if name != "Python":   # 'Python' appears only because it is the user's own unmatched claim
            # whole-word match: a raw substring test would flag 'R' inside 'RESULTS'
            leaked = re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", user)
            assert not leaked, f"technology {name!r} leaked into the prompt"
    assert user == build_user_prompt(GAP)
    print("  all 4 sections present; every skill id/name and unmatched claim included; no KB technology sent")

    print("\n=== 3. Hallucinating Gemini cannot change the deterministic result or smuggle ungrounded content ===")
    halluc = good_response()
    halluc.update({
        "summary": "Top priority: this user is 87% ready for the role.",
        "fit_score": 0.99, "matched_skills": ["Docker"], "career_id": "C_FAKE", "skill_gap": {"missing": []},
        "priority_tiers": {"high": ["S500"]},
        "strengths": [
            {"skill_ids": ["S999"], "text": "Skill One is strong."},
            {"skill_ids": ["S300"], "text": "Skill Three is a strength."},
            {"skill_ids": ["S100"], "text": "Skill One is solid and the user also knows Docker."},
            {"skill_ids": ["S100"], "text": "Skill One is claimed only."},
            {"skill_ids": ["S100"], "text": "Skill One accounts for 55% of the fit."},
            {"skill_ids": ["S100"], "text": "Skill One is evidenced, and Skill Five is also strong."},
            {"skill_ids": ["S100"], "text": "Skill One is the top priority."},
        ],
    })
    out = run_agent(halluc)
    assert out.skill_gap.model_dump() == before and out.skill_gap is GAP
    assert out.skill_gap.fit_score == GAP.fit_score
    assert out.narrative_source == "llm-partial"
    for key in ("fit_score", "matched_skills", "career_id", "skill_gap", "priority_tiers"):
        assert has_note(out, f"ignored unexpected key '{key}'"), key
    fb = build_fallback_narrative(GAP)
    assert out.narrative.summary == fb.summary and has_note(out, "replaced summary")
    assert out.narrative.strengths == fb.strengths, "all 7 bad strengths must be replaced by the deterministic template"
    for needle in ("S999", "not in the 'matched_evidenced' category", "'Docker', which is not part of the supplied",
                   "describes an evidenced skill as unverified", "percentage 55%", "'Skill Five', which belongs to a different category",
                   "priority/prioritization language"):
        assert has_note(out, needle), needle
    blob = out.narrative.model_dump_json()
    assert "Docker" not in blob and "S999" not in blob and "87%" not in blob and "priority" not in blob.lower()
    print("  7 bad strengths dropped, bad summary replaced, 5 override keys ignored, Step 9 result byte-identical")

    print("\n=== 4. Unmatched claims stay unmatched; never promoted to missing or to a canonical skill ===")
    resp = good_response()
    resp["unmatched_claim_observations"] = [
        {"user_skill_ids": [1], "text": "Skill One was claimed in a different wording."},
        {"user_skill_ids": [4], "text": "'Python' is a missing requirement for this career."},
        {"user_skill_ids": [5], "text": "'Some Framework' maps to Skill One."},
        {"user_skill_ids": [4, 5], "text": "'Python' and 'Some Framework' could not be mapped to the knowledge base, so they are not counted as missing requirements."},
    ]
    resp["missing_skill_observations"] = [
        {"skill_ids": ["S500"], "text": "Skill Five is missing, similar to the user's 'Python' claim."},
        {"skill_ids": ["S500", "S700"], "text": "Skill Five and Skill Seven are required by this career but have no corresponding canonical skill in the profile."},
    ]
    out = run_agent(resp)
    assert [o.user_skill_ids for o in out.narrative.unmatched_claim_observations] == [[4, 5]]
    assert [o.skill_ids for o in out.narrative.missing_skill_observations] == [["S500", "S700"]]
    assert has_note(out, "not unmatched claims in the deterministic result")
    assert has_note(out, "treats an unmapped claim as absent/missing")
    assert has_note(out, "belongs to a different category")
    assert [m.skill_id for m in out.skill_gap.missing] == ["S500", "S700"]
    assert [u.claimed_skill for u in out.skill_gap.unmatched_user_claims] == ["Python", "Some Framework"]
    assert all("Python" not in m.canonical_name for m in out.skill_gap.missing)
    print("  'unmatched' text calling a claim missing, relating it to a canonical skill, or using a wrong id is dropped")

    print("\n=== 5. Claimed-only is kept distinct from evidenced ===")
    resp = good_response()
    resp["claimed_only_observations"] = [
        {"skill_ids": ["S300"], "text": "Skill Three has been demonstrated by the user."},
        {"skill_ids": ["S100"], "text": "Skill One is claimed."},
        {"skill_ids": ["S300"], "text": "Skill Three is reported by the user but has not been verified."},
    ]
    resp["strengths"] = [{"skill_ids": ["S300"], "text": "Skill Three is a strength."}]
    out = run_agent(resp)
    assert [o.text for o in out.narrative.claimed_only_observations] == ["Skill Three is reported by the user but has not been verified."]
    assert has_note(out, "asserts evidence (demonstrated)")
    assert out.narrative.strengths == build_fallback_narrative(GAP).strengths     # claimed-only id cannot be a strength
    assert {i.skill_id for i in out.skill_gap.matched_claimed_only} == {"S300"}
    assert "S300" not in {i.skill_id for i in out.skill_gap.matched_evidenced}
    print("  'demonstrated' for a claimed-only skill rejected; negated wording accepted; claimed-only id cannot be a strength")

    print("\n=== 6. Missing skills are explained without inventing requirements ===")
    resp = good_response()
    resp["missing_skill_observations"] = [
        {"skill_ids": ["S500"], "text": "Skill Five is required, and the career also expects Debugging."},
        {"skill_ids": ["S500"], "text": "The career also requires Kubernetes."},
        {"skill_ids": ["S100"], "text": "Skill One is missing."},
        {"skill_ids": ["S500", "S700"], "text": "Skill Five and Skill Seven are required but not found among the user's canonical skills."},
    ]
    out = run_agent(resp)
    assert [o.skill_ids for o in out.narrative.missing_skill_observations] == [["S500", "S700"]]
    assert has_note(out, "'Debugging', which is not part of the supplied") and has_note(out, "'Kubernetes', which is not part of the supplied")
    assert [m.skill_id for m in out.skill_gap.missing] == ["S500", "S700"]
    print("  invented requirements (Debugging, Kubernetes) and an evidenced id in the missing list are dropped")

    print("\n=== 7. User with no normalized skills: every requirement missing, no invented strengths ===")
    assert GAP_EMPTY.matched_evidenced == [] and len(GAP_EMPTY.missing) == len(REQUIRED)
    resp = good_response(GAP_EMPTY)
    resp["strengths"] = [{"skill_ids": ["S100"], "text": "Skill One is a clear strength."}]
    resp["claimed_only_observations"] = []
    resp["unmatched_claim_observations"] = []
    resp["missing_skill_observations"] = [{"skill_ids": [c.skill.skill_id for c in REQUIRED],
                                           "text": "Skill Nine, Skill One, Skill Five, Skill Three and Skill Seven have no corresponding canonical skill in the profile."}]
    resp["summary"] = f"Test Career (Test Domain): none of the 5 required skills is matched in the profile. Career-fit score: {pct(GAP_EMPTY)}."
    out = run_agent(resp, GAP_EMPTY)
    assert out.narrative.strengths == [] and has_note(out, "not in the 'matched_evidenced' category")
    assert len(out.narrative.missing_skill_observations[0].skill_ids) == len(REQUIRED)
    assert build_fallback_narrative(GAP_EMPTY).strengths == []
    print("  strengths stay empty even though the LLM tried to invent one")

    print("\n=== 8. User whose claims are ALL unmatched: still every requirement missing, claims reported separately ===")
    assert len(GAP_UNMATCHED_ONLY.missing) == len(REQUIRED) and len(GAP_UNMATCHED_ONLY.unmatched_user_claims) == 2
    resp = good_response(GAP_UNMATCHED_ONLY)
    resp["strengths"], resp["claimed_only_observations"] = [], []
    resp["missing_skill_observations"] = [
        {"skill_ids": ["S100"], "text": "Skill One is not matched; the user's 'Python' claim does not count."},
        {"skill_ids": [c.skill.skill_id for c in REQUIRED], "text": "None of Skill Nine, Skill One, Skill Five, Skill Three or Skill Seven has a corresponding canonical skill in the profile."},
    ]
    resp["unmatched_claim_observations"] = [
        {"user_skill_ids": [1, 2], "text": "'Python' and 'Docker-ish' could not be mapped to the knowledge base and are not counted as missing requirements."}]
    resp["summary"] = f"Test Career (Test Domain): no required skill is matched. Career-fit score: {pct(GAP_UNMATCHED_ONLY)}."
    out = run_agent(resp, GAP_UNMATCHED_ONLY)
    assert len(out.narrative.missing_skill_observations) == 1 and has_note(out, "belongs to a different category")
    assert out.narrative.unmatched_claim_observations[0].user_skill_ids == [1, 2]
    assert len(out.skill_gap.missing) == len(REQUIRED) and len(out.skill_gap.unmatched_user_claims) == 2
    print("  unmatched claims never appear inside missing observations; both lists intact")

    print("\n=== 9. LLM failure: deterministic result kept, failure visible; strict mode raises ===")
    failing = RaisingLLM(RuntimeError("quota exceeded"))
    out = SkillGapAgent(llm_client=failing, vocabulary=VOCAB).explain(GAP)
    assert out.narrative_source == "fallback-template" and out.llm_error.startswith("LLM call failed: RuntimeError")
    assert out.narrative == build_fallback_narrative(GAP) and out.skill_gap is GAP and failing.calls == 1
    try:
        SkillGapAgent(llm_client=RaisingLLM(RuntimeError("boom")), vocabulary=VOCAB, strict_llm=True).explain(GAP)
        raise AssertionError("strict_llm=True must raise")
    except NarrativeGenerationError as e:
        assert isinstance(e.__cause__, RuntimeError)

    print("\n=== 10. Unusable structured output: same handling ===")
    for raw in ("plain text", None, [], {}, {"foo": 1}, 42):
        out = run_agent(raw)
        assert out.narrative_source == "fallback-template" and "invalid structured LLM output" in out.llm_error, raw
        assert out.narrative == build_fallback_narrative(GAP) and out.skill_gap is GAP
        try:
            run_agent(raw, strict_llm=True)
            raise AssertionError("strict_llm=True must raise")
        except NarrativeGenerationError:
            pass

    print("\n=== 11. No LLM configured: deterministic narrative, not an error ===")
    out = SkillGapAgent(llm_client=None).explain(GAP)
    assert out.narrative_source == "fallback-template" and out.llm_error is None and out.validation_notes == []

    print("\n=== 12. The deterministic fallback narrative itself passes the guard (for every shape of result) ===")
    for g in (GAP, GAP_EMPTY, GAP_UNMATCHED_ONLY, GAP_ALL_EVIDENCED):
        outcome = validate_narrative(build_fallback_narrative(g).model_dump(), g, VOCAB)
        assert outcome.notes == [] and not outcome.degraded, outcome.notes
        assert outcome.narrative == build_fallback_narrative(g)
    print("  template narratives are accepted with zero notes for 4 different results")

    print("\n=== 13. Step 9 result is identical before/after every agent path ===")
    for scenario in (good_response(), halluc, "garbage"):
        run_agent(scenario)
    SkillGapAgent(llm_client=failing, vocabulary=VOCAB).explain(GAP)
    SkillGapAgent(llm_client=None).explain(GAP)
    assert GAP.model_dump() == before
    assert classify_skill_gap(7, CAREER, REQUIRED, mixed_user(), W).model_dump() == before
    print("  GAP.model_dump() unchanged and equal to a fresh Step 9 computation")

    print("\n=== 14. Vocabulary is loaded lazily and never needed without a successful LLM response ===")
    with mock.patch.object(agent_module, "load_kb_vocabulary", side_effect=AssertionError("must not load")) as loader:
        SkillGapAgent(llm_client=None).explain(GAP)
        SkillGapAgent(llm_client=RaisingLLM(RuntimeError("x"))).explain(GAP)
        assert loader.call_count == 0

    print("\n=== 15. Output schema: Step 9 result embedded as-is; no priority/score/proficiency-requirement fields ===")
    assert SkillGapAnalysisOut.model_fields["skill_gap"].annotation is SkillGapResult
    forbidden = ("priority", "severity", "rank", "tier", "importance", "urgency", "gap_score", "score",
                 "required_proficiency", "proficiency_gap", "proficiency_deficit", "target_proficiency", "required_level")
    for model in (agent_schemas.SkillObservation, agent_schemas.UnmatchedClaimObservation,
                  agent_schemas.SkillGapNarrative, agent_schemas.SkillGapAnalysisOut):
        for field_name in model.model_fields:
            assert not any(f in field_name.lower() for f in forbidden), f"{model.__name__}.{field_name}"
    print("  checked all fields of 4 models")

    print("\n=== 16. Agent source: it never recomputes, never touches SQL ===")
    def identifiers_and_imports(module):
        tree = ast.parse(inspect.getsource(module))
        names, imported = set(), set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
        return names, imported
    names, imported = identifiers_and_imports(agent_module)
    assert not names & {"compute_career_fit", "classify_skill_gap", "_best_user_match", "RequiredSkillInput", "UserSkillInput"}
    assert not any(m.startswith(("sqlalchemy", "psycopg2", "app.repositories", "app.core")) for m in imported), imported
    assert "analyze_skill_gap" in names
    g_names, g_imported = identifiers_and_imports(grounding)
    assert not any(m.startswith(("sqlalchemy", "psycopg2", "requests", "app.repositories", "app.core", "app.services", "app.agents.llm_client"))
                   for m in g_imported), g_imported
    print("  agent only calls analyze_skill_gap(); grounding module is pure (no DB, no services, no LLM client)")

    print("\n=== 17. Guard internals ===")
    ctx = _Context(GAP, VOCAB)
    assert ctx.scan_terms("Python is mentioned by the user", LABEL_MISSING) != []        # unmatched label inside a missing item
    assert ctx.scan_terms("Skill Five is missing", LABEL_MISSING) == []
    assert any("'Kubernetes'" in p for p in ctx.scan_terms("Kubernetes", None))
    assert any("'AWS'" in p for p in ctx.scan_terms("The user works with AWS.", None))                # alias of 'Amazon Web Services AWS'
    assert any("'Amazon Web Services'" in p for p in ctx.scan_terms("Amazon Web Services is used.", None))
    assert ctx.scan_terms("Let us Go ahead and rank R values.", None) == []                          # 1-2 letter names are not scanned
    assert any("'Big Test Career'" in p for p in ctx.scan_terms("This resembles Big Test Career.", None))
    assert ctx.scan_terms("This is a Test Career role.", None) == []                                 # the selected career is allowed
    assert _affirmative_hits("it has not been verified", ("verified",)) == []
    assert _affirmative_hits("it is verified", ("verified",)) == ["verified"]
    assert _text_problems(f"The fit is about {round(GAP.fit_score * 100)}%.", ctx, None) == []
    assert any("percentage" in p for p in _text_problems(f"The fit is {GAP.fit_score * 100 + 5:.0f}%.", ctx, None))
    for phrase in ("The user needs advanced proficiency.", "A proficiency threshold applies.", "This is a severity 3 gap.",
                   "These form tier 1.", "It is urgent."):
        assert _text_problems(phrase, ctx, None), phrase
    nested = Vocabulary(skill_names=("Database",), technology_names=(), career_names=())
    nested_gap = classify_skill_gap(7, CAREER, [req("S1", "Database Management", "CORE", "high")], [], W)
    nctx = _Context(nested_gap, nested)
    assert nctx.scan_terms("Database Management is required.", LABEL_MISSING) == []                 # longest match claims the span
    assert nctx.scan_terms("Database is required.", LABEL_MISSING) != []
    print("  scan, aliasing, negation, percentage and concept checks behave as specified")

    print("\n=== 18. Replaced free-text fields are recorded ===")
    resp = good_response()
    resp["conclusion"] = "The user needs advanced proficiency in Skill One."
    out = run_agent(resp)
    assert out.narrative.conclusion == build_fallback_narrative(GAP).conclusion and has_note(out, "replaced conclusion")
    assert out.narrative_source == "llm-partial"

    print("\nALL SKILL GAP AGENT UNIT TESTS PASSED.")


if __name__ == "__main__":
    main()