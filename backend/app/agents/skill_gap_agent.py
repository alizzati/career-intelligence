"""
Skill-Gap Agent (Step 10).

The deterministic Step 9 engine decides which required skills are
matched_evidenced / matched_claimed_only / missing and which user claims are
unmatched. THIS agent never recomputes any of that: it calls the engine,
hands the result to the LLM as authoritative context, asks for a narrative,
and validates the narrative against the engine's result before returning it.

    Gemini explains the deterministic result. It does not recompute it.

Dependency direction:  SkillGapAgent -> Step 9 engine, SkillGapAgent -> LLM.
Step 9 knows nothing about this module or about any LLM.

Provider-agnostic: only the LLMClient Protocol (complete_json(system, user,
max_tokens) -> dict) is used -- the same one Steps 7 and 8 use.

Failure behaviour (follows the Step 8 convention, with the failure made visible):
  * unknown user / career      -> UserNotFoundError / CareerNotFoundError from Step 9 (propagated)
  * LLM exception or unusable output
        default                -> the deterministic result is returned with a template narrative,
                                  narrative_source='fallback-template' and llm_error set
        strict_llm=True        -> NarrativeGenerationError is raised instead
  * parts of an otherwise usable narrative that fail validation are dropped and replaced by the
    deterministic template (narrative_source='llm-partial'), each recorded in validation_notes.
"""
import json

from app.agents.llm_client import LLMClient
from app.agents.skill_gap_grounding import (
    NarrativeFormatError, Vocabulary, build_fallback_narrative, validate_narrative,
)
from app.schemas.skill_gap import SkillGapResult
from app.schemas.skill_gap_agent import SkillGapAnalysisOut
from app.services import retrieval_service as rs
from app.services.skill_gap_service import analyze_skill_gap

LLM_MAX_TOKENS = 1500

NARRATIVE_SYSTEM_PROMPT = """You write the narrative layer of a skill-gap report for an IT graduate. A deterministic \
engine has ALREADY classified every skill. Its result (section DETERMINISTIC RESULTS) is authoritative: you explain it, \
you never recompute, modify, add or remove any classification, skill, id or number.

RULES
1. Mention only skills, the career, and user claims that appear in DETERMINISTIC RESULTS. Do not name any other skill, \
tool, technology, framework, certification or career, even as an example or a suggestion.
2. Categories are fixed. matched_evidenced = the user has the required skill with linked evidence. matched_claimed_only \
= the user claims the required skill but has no linked evidence: say "claimed", "reported by the user" or "not yet \
supported by linked evidence", and never call it demonstrated, proven or verified. missing = required by the career, no \
corresponding canonical skill in the profile. unmatched_user_claims = claims that could not be mapped to the knowledge \
base: they are NOT missing requirements and NOT evidence that the user lacks the skill; do not relate them to any \
required skill.
3. Do not introduce priorities, rankings, severity, tiers or urgency. evidence_class and kb_confidence are descriptive \
knowledge-base metadata only.
4. The knowledge base has no required proficiency level. Never state or imply one. A user's proficiency is self-reported \
profile information only.
5. Do not compute or quote any score except the career-fit percentage given to you.
6. Every observation must list in "skill_ids" (or "user_skill_ids") exactly the ids it is about, taken ONLY from the \
matching category. If a category is empty, return an empty list for it and do not invent strengths or gaps.
7. Be cautious and factual. Write 1-3 sentences per observation.

Return ONLY one JSON object, with no text outside it, in exactly this shape:
{
  "summary": "<2-4 sentences>",
  "strengths": [{"skill_ids": ["<matched_evidenced ids>"], "text": "<sentence>"}],
  "claimed_only_observations": [{"skill_ids": ["<matched_claimed_only ids>"], "text": "<sentence>"}],
  "missing_skill_observations": [{"skill_ids": ["<missing ids>"], "text": "<sentence>"}],
  "unmatched_claim_observations": [{"user_skill_ids": [<unmatched user_skill_id integers>], "text": "<sentence>"}],
  "conclusion": "<1-2 cautious sentences about the current readiness>"
}"""


class NarrativeGenerationError(RuntimeError):
    """Raised only when strict_llm=True and the LLM call or its output is unusable."""


def build_user_prompt(gap: SkillGapResult) -> str:
    def required(item):
        d = {"skill_id": item.skill_id, "name": item.canonical_name,
             "evidence_class": item.evidence_class, "kb_confidence": item.kb_confidence}
        if item.matched_user_claim:
            c = item.matched_user_claim
            d["user_claim"] = {"claimed_as": c.claimed_skill, "self_reported_proficiency": c.proficiency,
                               "linked_evidence_count": c.evidence_count}
        return d

    results = {
        "fit_score_percent": round(gap.fit_score * 100, 1),
        "required_skill_count": len(gap.matched_evidenced) + len(gap.matched_claimed_only) + len(gap.missing),
        "matched_evidenced": [required(i) for i in gap.matched_evidenced],
        "matched_claimed_only": [required(i) for i in gap.matched_claimed_only],
        "missing": [required(i) for i in gap.missing],
        "unmatched_user_claims": [
            {"user_skill_id": u.user_skill_id, "claimed_as": u.claimed_skill,
             "self_reported_proficiency": u.proficiency, "linked_evidence_count": u.evidence_count}
            for u in gap.unmatched_user_claims],
    }
    return (
        "=== USER PROFILE / SKILL-GAP CONTEXT ===\n"
        f"Selected career: {gap.canonical_name} (career_id {gap.career_id}), domain: {gap.domain}\n\n"
        "=== DETERMINISTIC RESULTS (authoritative; do not change) ===\n"
        f"{json.dumps(results, indent=2, ensure_ascii=False)}\n\n"
        "=== INSTRUCTIONS ===\n"
        "Explain this result following the RULES. Use only the names and ids above.\n\n"
        "=== OUTPUT REQUIREMENTS ===\n"
        "One JSON object exactly as specified in the system message."
    )


def load_kb_vocabulary() -> Vocabulary:
    """KB names used only to RECOGNIZE ungrounded mentions in LLM text (read-only,
    via the existing retrieval_service). Technologies are not canonical skills and
    are never sent to the LLM; they are only used to detect when it brings one up."""
    skills = tuple(s.canonical_name for s in rs.get_all_skills())
    careers = rs.get_all_careers()
    technologies: dict[str, None] = {}
    for c in careers:
        context = rs.get_occupational_context(c.career_id)
        if context is None:
            continue
        for tech_list in context.technologies.values():
            for t in tech_list:
                technologies[t.technology_name] = None
    return Vocabulary(skill_names=skills, technology_names=tuple(technologies),
                      career_names=tuple(c.canonical_name for c in careers))


class SkillGapAgent:
    def __init__(self, llm_client: LLMClient | None = None, weights: dict | None = None,
                 strict_llm: bool = False, vocabulary: Vocabulary | None = None):
        self.llm_client = llm_client
        self.weights = weights
        self.strict_llm = strict_llm
        self._vocabulary = vocabulary

    def run(self, user_id: int, career_id: str) -> SkillGapAnalysisOut:
        # The only place classification happens. Unknown user/career raise here.
        gap = analyze_skill_gap(user_id, career_id, self.weights)
        return self.explain(gap)

    def explain(self, gap: SkillGapResult) -> SkillGapAnalysisOut:
        """Narrative for an existing Step 9 result. `gap` is read, never modified."""
        if self.llm_client is None:
            return SkillGapAnalysisOut(
                skill_gap=gap, narrative=build_fallback_narrative(gap), narrative_source="fallback-template",
            )

        try:
            raw = self.llm_client.complete_json(
                system=NARRATIVE_SYSTEM_PROMPT, user=build_user_prompt(gap), max_tokens=LLM_MAX_TOKENS,
            )
        except Exception as exc:
            return self._failed(gap, f"LLM call failed: {type(exc).__name__}: {str(exc)[:200]}", exc)

        if self._vocabulary is None:
            self._vocabulary = load_kb_vocabulary()
        try:
            outcome = validate_narrative(raw, gap, self._vocabulary)
        except NarrativeFormatError as exc:
            return self._failed(gap, f"invalid structured LLM output: {exc}", exc)

        return SkillGapAnalysisOut(
            skill_gap=gap, narrative=outcome.narrative,
            narrative_source="llm-partial" if outcome.degraded else "llm",
            validation_notes=outcome.notes,
        )

    def _failed(self, gap: SkillGapResult, message: str, cause: Exception) -> SkillGapAnalysisOut:
        if self.strict_llm:
            raise NarrativeGenerationError(message) from cause
        return SkillGapAnalysisOut(
            skill_gap=gap, narrative=build_fallback_narrative(gap),
            narrative_source="fallback-template", llm_error=message,
        )