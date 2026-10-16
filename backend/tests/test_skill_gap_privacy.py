"""Privacy-boundary regression tests for persisted Step 9 user text."""
from app.agents.skill_gap_agent import SkillGapAgent
from app.schemas.skill_gap import MatchedUserClaim
from app.services.profile_privacy_service import redact_skill_gap_result
from tests.test_skill_gap_agent_unit import GAP, VOCAB, ScriptedLLM, good_response


EMAIL = "synthetic.person@example.test"
PHONE = "0812-5555-0199"


def _gap_with_synthetic_pii():
    item = GAP.matched_claimed_only[0].model_copy(update={
        "matched_user_claim": MatchedUserClaim(
            claimed_skill=EMAIL,
            proficiency=PHONE,
            evidence_status="none",
            evidence_count=0,
        ),
    })
    return GAP.model_copy(update={"matched_claimed_only": [item]})


def test_skill_gap_prompt_and_narrative_redact_user_text_without_changing_step9():
    gap = _gap_with_synthetic_pii()
    original = gap.model_dump()
    response = good_response(gap)
    response["conclusion"] += f" Contact: {EMAIL} or {PHONE}."
    llm = ScriptedLLM(response)

    result = SkillGapAgent(llm_client=llm, vocabulary=VOCAB).explain(gap)

    assert EMAIL not in llm.calls[0]["user"]
    assert PHONE not in llm.calls[0]["user"]
    assert "[REDACTED_EMAIL]" in llm.calls[0]["user"]
    assert "[REDACTED_PHONE]" in llm.calls[0]["user"]
    assert "Skill Three" in llm.calls[0]["user"]
    assert result.skill_gap is gap
    assert gap.model_dump() == original
    assert EMAIL not in result.narrative.model_dump_json()
    assert PHONE not in result.narrative.model_dump_json()
    assert "[REDACTED_EMAIL]" in result.narrative.conclusion
    assert "[REDACTED_PHONE]" in result.narrative.conclusion


def test_verification_copy_redacts_user_claims_but_preserves_deterministic_fields():
    gap = _gap_with_synthetic_pii()

    safe = redact_skill_gap_result(gap)

    assert safe is not gap
    assert safe.matched_claimed_only[0].skill_id == gap.matched_claimed_only[0].skill_id
    assert safe.matched_claimed_only[0].status == gap.matched_claimed_only[0].status
    assert safe.fit_score == gap.fit_score
    assert safe.matched_claimed_only[0].matched_user_claim.claimed_skill == "[REDACTED_EMAIL]"
    assert safe.matched_claimed_only[0].matched_user_claim.proficiency == "[REDACTED_PHONE]"
    assert gap.matched_claimed_only[0].matched_user_claim.claimed_skill == EMAIL
    assert gap.matched_claimed_only[0].matched_user_claim.proficiency == PHONE
