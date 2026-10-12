"""
Career Recommendation Agent (master prompt Section 5, Agent 2 / Step 8
design checkpoint).

Responsibilities (and ONLY these):
  - enumerate every career in the KB (get_all_careers() -- never an LLM
    choice, never a subset)
  - for each career, build its required-skill set from get_career_skills()
    and the user's normalized skills from get_user_full_profile()
  - score EVERY career with the shared deterministic calculator
    (career_fit_service.compute_career_fit) -- the SAME function Step 9
    will later call for detailed gap analysis on one chosen career
  - ask the LLM for a short natural-language `reasoning` string per
    career, strictly from the already-computed facts -- the LLM never
    computes a score, never adds/removes a skill, never picks or invents
    a career

This agent does NOT do skill-gap analysis (Step 9) or learning-roadmap
generation (Step 10) -- `missing_skills_preview` here is a preview list
only, not a prioritized/classified gap breakdown.

Provider-agnostic: depends only on the LLMClient Protocol from
llm_client.py (works with any implementation -- Gemini, etc. -- that
satisfies complete_json(system, user, max_tokens) -> dict).
"""
from dataclasses import dataclass

from app.agents.llm_client import LLMClient
from app.services import retrieval_service as rs
from app.services import user_service as us
from app.services.career_fit_service import (
    compute_career_fit, load_scoring_weights,
    RequiredSkillInput, UserSkillInput, CareerFitResult,
)
from app.schemas.career_fit import (
    CareerRecommendationOut, SkillRefOut, ScoreBreakdownOut,
)


REASONING_SYSTEM_PROMPT = """You are a narrative-explanation component in a career intelligence \
system. You are given a career name, domain, a pre-computed numeric fit score, and three lists of \
skill names that were already determined by a separate deterministic calculator: matched skills \
(the user has these, with evidence), claimed-only skills (the user claims these but has not yet \
provided evidence), and a preview of missing skills (required skills the user does not currently have).

Your ONLY job is to write a short (2-4 sentence) natural-language explanation of why this career \
received this fit score, using ONLY the skill names and the score given to you. You are NOT allowed \
to: invent any skill name not in the three lists given; invent any career name other than the one \
given; change, recompute, or contradict the given fit score; claim a missing skill is actually \
present, or vice versa. If you are unsure how to phrase something, stay generic rather than inventing \
a fact.

Return ONLY a single JSON object, no prose outside it, with exactly this shape:
{"reasoning": "<your 2-4 sentence explanation>"}"""


def _fallback_reasoning(canonical_name: str, fit_score: float, matched_n: int,
                         claimed_only_n: int, missing_n: int) -> str:
    """Deterministic, template-based reasoning used when no LLM client is
    supplied, or when the LLM response cannot be parsed as expected. Never
    blocks the pipeline on an LLM failure."""
    pct = round(fit_score * 100)
    return (
        f"{canonical_name} shows a {pct}% skill-coverage fit based on {matched_n} evidenced "
        f"skill(s), {claimed_only_n} claimed-but-unverified skill(s), and {missing_n} skill(s) "
        f"not yet present in the user's profile."
    )


@dataclass
class _CareerScratch:
    career_id: str
    canonical_name: str
    domain: str
    fit: CareerFitResult
    skill_lookup: dict  # skill_id -> (canonical_name, evidence_class)


class CareerRecommendationAgent:
    def __init__(self, llm_client: LLMClient | None = None, weights: dict | None = None):
        self.llm_client = llm_client
        self.weights = weights if weights is not None else load_scoring_weights()

    def _build_reasoning(self, scratch: _CareerScratch) -> tuple[str, str]:
        matched_names = [scratch.skill_lookup[sid][0] for sid in scratch.fit.matched_linked_skill_ids]
        claimed_names = [scratch.skill_lookup[sid][0] for sid in scratch.fit.matched_claimed_only_skill_ids]
        missing_names = [scratch.skill_lookup[sid][0] for sid in scratch.fit.missing_skill_ids]

        fallback = _fallback_reasoning(
            scratch.canonical_name, scratch.fit.fit_score,
            len(matched_names), len(claimed_names), len(missing_names),
        )
        if self.llm_client is None:
            return fallback, "fallback-template"

        user_prompt = (
            f"Career: {scratch.canonical_name} (domain: {scratch.domain})\n"
            f"Pre-computed fit_score: {round(scratch.fit.fit_score, 3)}\n"
            f"Matched skills (evidenced): {matched_names}\n"
            f"Claimed-only skills (no evidence yet): {claimed_names}\n"
            f"Missing skills (preview, not full gap analysis): {missing_names}"
        )
        try:
            response = self.llm_client.complete_json(
                system=REASONING_SYSTEM_PROMPT, user=user_prompt, max_tokens=300,
            )
            # *** Anti-hallucination guard ***
            # The LLM response is parsed STRICTLY for the "reasoning" string
            # only. Any other key it might return is ignored outright --
            # there is no code path anywhere that lets LLM output modify
            # fit_score, matched/claimed/missing lists, or career_id. Those
            # were all already finalized before this method was even called.
            reasoning_text = response.get("reasoning") if isinstance(response, dict) else None
            if not reasoning_text or not isinstance(reasoning_text, str):
                return fallback, "fallback-template"
            return reasoning_text, "llm"
        except Exception:
            # Any LLM failure (network, parsing, provider error) degrades
            # to the deterministic template -- never blocks or corrupts output.
            return fallback, "fallback-template"

    def run(self, user_id: int) -> list[CareerRecommendationOut]:
        full_profile = us.get_user_full_profile(user_id)
        if full_profile is None:
            raise ValueError(f"user_id={user_id} does not exist")

        # Build the user's normalized-skill input set ONCE. Skills with
        # skill_id=None (never normalized) are included here for
        # completeness but can never match any requirement -- the
        # calculator enforces that by identity on skill_id, not a special
        # case written here.
        user_skill_inputs = [
            UserSkillInput(skill_id=s.skill_id, evidence_status=s.evidence_status, proficiency=s.proficiency)
            for s in full_profile.skills
        ]

        # Career candidates: EVERY career in the KB, enumerated directly
        # from the database. The LLM has no say in this set whatsoever.
        all_careers = rs.get_all_careers()

        scratches: list[_CareerScratch] = []
        for career in all_careers:
            career_skills = rs.get_career_skills(career.career_id)
            required_inputs = [
                RequiredSkillInput(
                    skill_id=cs.skill.skill_id, evidence_class=cs.evidence_class, kb_confidence=cs.confidence,
                ) for cs in career_skills
            ]
            skill_lookup = {cs.skill.skill_id: (cs.skill.canonical_name, cs.evidence_class) for cs in career_skills}

            fit = compute_career_fit(required_inputs, user_skill_inputs, self.weights)
            scratches.append(_CareerScratch(
                career_id=career.career_id, canonical_name=career.canonical_name,
                domain=career.domain, fit=fit, skill_lookup=skill_lookup,
            ))

        results: list[CareerRecommendationOut] = []
        for scratch in scratches:
            reasoning_text, reasoning_source = self._build_reasoning(scratch)

            matched = [
                SkillRefOut(skill_id=sid, canonical_name=scratch.skill_lookup[sid][0],
                            evidence_class=scratch.skill_lookup[sid][1])
                for sid in scratch.fit.matched_linked_skill_ids
            ]
            claimed_only = [
                SkillRefOut(skill_id=sid, canonical_name=scratch.skill_lookup[sid][0],
                            evidence_class=scratch.skill_lookup[sid][1])
                for sid in scratch.fit.matched_claimed_only_skill_ids
            ]
            missing_preview = [
                SkillRefOut(skill_id=sid, canonical_name=scratch.skill_lookup[sid][0],
                            evidence_class=scratch.skill_lookup[sid][1])
                for sid in scratch.fit.missing_skill_ids
            ]

            core_count = sum(1 for d in scratch.fit.skill_details if d.evidence_class.upper() == "CORE")
            supporting_count = len(scratch.fit.skill_details) - core_count

            results.append(CareerRecommendationOut(
                career_id=scratch.career_id, canonical_name=scratch.canonical_name, domain=scratch.domain,
                fit_score=round(scratch.fit.fit_score, 4),
                score_breakdown=ScoreBreakdownOut(
                    total_weight=scratch.fit.total_weight, total_contribution=scratch.fit.total_contribution,
                    core_required_count=core_count, supporting_required_count=supporting_count,
                    matched_linked_count=len(matched), matched_claimed_only_count=len(claimed_only),
                    missing_count=len(missing_preview), weights_used=self.weights,
                ),
                matched_skills=matched, claimed_only_skills=claimed_only,
                missing_skills_preview=missing_preview,
                reasoning=reasoning_text, reasoning_source=reasoning_source,
            ))

        # Deterministic ranking: sort by fit_score desc, tie-broken by
        # career_id asc so ordering is 100% reproducible, never dependent
        # on dict/set iteration order or LLM timing.
        results.sort(key=lambda r: (-r.fit_score, r.career_id))
        return results