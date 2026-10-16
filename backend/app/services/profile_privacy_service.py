"""Privacy-safe copies of user-derived text in analysis outputs.

These helpers preserve deterministic identifiers and classifications while
redacting only free text derived from the user's persisted profile.
"""
from copy import copy

from app.schemas.career_fit import CareerRecommendationOut
from app.schemas.learning_roadmap import LearningRoadmapOut
from app.schemas.skill_gap import SkillGapResult
from app.schemas.skill_gap_agent import SkillGapAnalysisOut, SkillGapNarrative
from app.schemas.verification import VerificationResult
from app.services.pii_redaction_service import redact_pii


def _redact_text(value: str | None) -> str | None:
    return redact_pii(value).redacted_text if value is not None else None


def redact_skill_gap_result(gap: SkillGapResult) -> SkillGapResult:
    original = gap.model_dump()
    data = gap.model_dump()
    for category in ("matched_evidenced", "matched_claimed_only"):
        for item in data[category]:
            claim = item.get("matched_user_claim")
            if claim is not None:
                claim["claimed_skill"] = _redact_text(claim["claimed_skill"])
                claim["proficiency"] = _redact_text(claim["proficiency"])
    for claim in data["unmatched_user_claims"]:
        claim["claimed_skill"] = _redact_text(claim["claimed_skill"])
        claim["proficiency"] = _redact_text(claim["proficiency"])
    return gap if data == original else SkillGapResult.model_validate(data)


def redact_skill_gap_analysis(
    result: SkillGapAnalysisOut, *, redact_claims: bool = True,
) -> SkillGapAnalysisOut:
    if not isinstance(result, SkillGapAnalysisOut):
        return result
    data = result.model_dump()
    if redact_claims:
        data["skill_gap"] = redact_skill_gap_result(result.skill_gap).model_dump()
    for field in ("summary", "conclusion"):
        data["narrative"][field] = _redact_text(data["narrative"][field])
    for field in (
        "strengths", "claimed_only_observations",
        "missing_skill_observations", "unmatched_claim_observations",
    ):
        for observation in data["narrative"][field]:
            observation["text"] = _redact_text(observation["text"])
    data["llm_error"] = _redact_text(data["llm_error"])
    data["validation_notes"] = [_redact_text(note) for note in data["validation_notes"]]
    if not redact_claims:
        if (
            data["narrative"] == result.narrative.model_dump()
            and data["llm_error"] == result.llm_error
            and data["validation_notes"] == result.validation_notes
        ):
            return result
        data["narrative"] = SkillGapNarrative.model_validate(data["narrative"])
        return result.model_copy(update={
            "narrative": data["narrative"],
            "llm_error": data["llm_error"],
            "validation_notes": data["validation_notes"],
        })
    return result if data == result.model_dump() else SkillGapAnalysisOut.model_validate(data)


def redact_recommendations(
    recommendations: list[CareerRecommendationOut],
) -> list[CareerRecommendationOut]:
    safe = []
    for item in recommendations:
        if hasattr(item, "model_copy") and hasattr(item, "reasoning"):
            reasoning = _redact_text(item.reasoning)
            safe.append(
                item if reasoning == item.reasoning
                else item.model_copy(update={"reasoning": reasoning})
            )
        elif hasattr(item, "reasoning"):
            reasoning = _redact_text(item.reasoning)
            if reasoning == item.reasoning:
                safe.append(item)
            else:
                duplicate = copy(item)
                duplicate.reasoning = reasoning
                safe.append(duplicate)
        else:
            safe.append(item)
    return recommendations if all(a is b for a, b in zip(safe, recommendations)) else safe


def redact_roadmap(roadmap: LearningRoadmapOut) -> LearningRoadmapOut:
    if not isinstance(roadmap, LearningRoadmapOut):
        return roadmap
    gap = redact_skill_gap_result(roadmap.skill_gap)
    summary = _redact_text(roadmap.summary)
    llm_error = _redact_text(roadmap.llm_error)
    if (
        gap is roadmap.skill_gap
        and summary == roadmap.summary
        and llm_error == roadmap.llm_error
    ):
        return roadmap
    return roadmap.model_copy(update={
        "skill_gap": gap, "summary": summary, "llm_error": llm_error,
    })


def redact_verification(result: VerificationResult) -> VerificationResult:
    data = result.model_dump()
    for check in data["checks"]:
        check["reason"] = _redact_text(check["reason"])
    for claim in data["unsupported_claims"]:
        claim["claim"] = _redact_text(claim["claim"])
    data["required_revision"] = [_redact_text(item) for item in data["required_revision"]]
    data["llm_error"] = _redact_text(data["llm_error"])
    return VerificationResult.model_validate(data)
