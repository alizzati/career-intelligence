"""
Skill Gap Service -- Step 9: the DETERMINISTIC Skill-Gap Engine.

Compares a user's normalized canonical skills against ONE selected
career's required skills and classifies every required skill:

    matched_evidenced      user has the canonical skill, evidence_status='linked'
    matched_claimed_only   user has the canonical skill, evidence_status='none'
    missing                no canonical user skill with that skill_id

and separately reports user claims that could not be normalized
(skill_id IS NULL) as unmatched_user_claims. An unmatched claim is a
KB-mapping limitation; it is NEVER turned into a "missing" requirement.

ARCHITECTURAL INVARIANT: this module contains NO matching or fit formula
of its own. Every status, weight, contribution and the fit numbers come
from career_fit_service.compute_career_fit() -- the same function Step 8
calls -- so a career's recommendation score and its skill-gap breakdown
cannot disagree. This module only reads that result, attaches KB
metadata (evidence_class, kb_confidence), and groups the items.

What this module deliberately does NOT do:
  - no LLM / Gemini call of any kind (narrative belongs to Step 10)
  - no ordering, weighting or scoring of gaps; items keep the original
    career_skills order
  - no target/required proficiency (the KB has none); user proficiency is
    only echoed as profile information
  - no writes to the KB or to user data; all access goes through the
    existing retrieval_service / user_service
"""
from app.schemas.career_fit import ScoreBreakdownOut
from app.schemas.retrieval import CareerOut, CareerSkillOut
from app.schemas.skill_gap import (
    AcceptedEvidenceRef, MatchedUserClaim, SkillGapItem, SkillGapResult, UnmatchedUserClaim,
)
from app.schemas.user import EffectiveSkillOut, UserSkillOut
from app.services import retrieval_service as rs
from app.services import user_service as us
from app.services.career_fit_service import (
    RequiredSkillInput, UserSkillInput,
    compute_career_fit, load_scoring_weights,
    _best_user_match,  # the calculator's own tie-break; reused, never re-implemented
)


class UserNotFoundError(ValueError):
    pass


class CareerNotFoundError(ValueError):
    pass


# One-to-one translation of the calculator's status vocabulary.
_STATUS_MAP = {
    "matched-linked": "matched_evidenced",
    "matched-claimed-only": "matched_claimed_only",
    "missing": "missing",
}


def _claim_info(user_skill: UserSkillOut) -> MatchedUserClaim:
    return MatchedUserClaim(
        claimed_skill=user_skill.claimed_skill,
        proficiency=user_skill.proficiency,
        evidence_status=user_skill.evidence_status,
        evidence_count=len(user_skill.evidence),
    )


def _accepted_refs(accepted_evidence) -> list[AcceptedEvidenceRef]:
    """Copy accepted-evidence provenance without any raw CV span."""
    return [
        AcceptedEvidenceRef(
            accepted_evidence_id=item.accepted_evidence_id,
            cv_id=item.cv_id,
            skill_id=item.skill_id,
            source_type=item.source_type,
            source_table=item.source_table,
            source_id=item.source_id,
            claimed_skill=item.claimed_skill,
        )
        for item in accepted_evidence
    ]


def _claim_info_from_effective(skill: EffectiveSkillOut) -> MatchedUserClaim | None:
    """A claim exists only when a real user_skills row backs this skill.

    Evidence-only skills (D-04/D-17) must NOT fabricate a matched user claim.
    """
    if skill.user_skill_id is None or skill.claimed_skill is None:
        return None
    return MatchedUserClaim(
        claimed_skill=skill.claimed_skill,
        proficiency=skill.proficiency,
        evidence_status=skill.evidence_status,
        evidence_count=len(skill.accepted_evidence),
    )


def classify_skill_gap(
    user_id: int,
    career: CareerOut,
    career_skills: list[CareerSkillOut],
    user_skills: list[UserSkillOut],
    weights: dict | None = None,
    effective_skills: list[EffectiveSkillOut] | None = None,
) -> SkillGapResult:
    """
    Pure classification: no database access, no LLM, no randomness. Given
    the same inputs it always returns the same SkillGapResult.

    ``effective_skills`` is the canonical, de-duplicated view produced by
    ``user_service.get_user_full_profile()``. When supplied, it is the ONLY
    input to the fit calculator, so accepted evidence (including skills with
    no explicit claim) participates. When omitted, the legacy per-claim view
    is derived from ``user_skills`` for backwards compatibility; that path
    still trusts the caller-supplied ``evidence_status`` and is used by
    existing unit tests, never by the live agents.
    """
    w = weights if weights is not None else load_scoring_weights()
    # An empty effective view means the caller did not populate it (legacy
    # unit tests, offline fixtures). Live profiles always carry at least the
    # claim entries, so this fallback never hides accepted evidence.
    use_effective = bool(effective_skills)
    view = effective_skills if use_effective else user_skills

    required_inputs = [
        RequiredSkillInput(
            skill_id=cs.skill.skill_id, evidence_class=cs.evidence_class, kb_confidence=cs.confidence,
        ) for cs in career_skills
    ]
    user_inputs = [
        UserSkillInput(skill_id=s.skill_id, evidence_status=s.evidence_status, proficiency=s.proficiency)
        for s in view
    ]

    # The ONE call that produces every status and every number.
    fit = compute_career_fit(required_inputs, user_inputs, w)

    if len(fit.skill_details) != len(career_skills):
        raise RuntimeError("compute_career_fit() returned a different number of skill details than requirements")

    matched_evidenced: list[SkillGapItem] = []
    matched_claimed_only: list[SkillGapItem] = []
    missing: list[SkillGapItem] = []

    # compute_career_fit() returns one detail per requirement, in input
    # order, so zip pairs each detail with the KB row it came from.
    for cs, detail in zip(career_skills, fit.skill_details):
        if detail.skill_id != cs.skill.skill_id:
            raise RuntimeError("calculator output order does not match career_skills order")
        status = _STATUS_MAP.get(detail.status)
        if status is None:
            raise RuntimeError(f"unexpected status from compute_career_fit(): {detail.status!r}")

        claim = None
        accepted: list[AcceptedEvidenceRef] = []
        if detail.status != "missing":
            matched = _best_user_match(detail.skill_id, user_inputs)
            if matched is not None:
                position = next(i for i, u in enumerate(user_inputs) if u is matched)
                source = view[position]
                accepted = _accepted_refs(getattr(source, "accepted_evidence", []))
                claim = (
                    _claim_info_from_effective(source)
                    if use_effective else _claim_info(source)
                )

        item = SkillGapItem(
            skill_id=cs.skill.skill_id, canonical_name=cs.skill.canonical_name, status=status,
            evidence_class=cs.evidence_class, kb_confidence=cs.confidence,
            weight=detail.weight, contribution=detail.contribution,
            matched_user_claim=claim, accepted_evidence=accepted,
        )
        if status == "matched_evidenced":
            matched_evidenced.append(item)
        elif status == "matched_claimed_only":
            matched_claimed_only.append(item)
        else:
            missing.append(item)

    # Category D: claims with no canonical skill_id. Built independently of
    # the calculator because such claims can never match a requirement.
    unmatched_user_claims = [
        UnmatchedUserClaim(
            user_skill_id=s.user_skill_id, claimed_skill=s.claimed_skill, proficiency=s.proficiency,
            evidence_status=s.evidence_status, evidence_count=len(s.evidence),
        )
        for s in user_skills if s.skill_id is None
    ]

    core_count = sum(1 for d in fit.skill_details if d.evidence_class.upper() == "CORE")
    breakdown = ScoreBreakdownOut(
        total_weight=fit.total_weight, total_contribution=fit.total_contribution,
        core_required_count=core_count, supporting_required_count=len(fit.skill_details) - core_count,
        matched_linked_count=len(matched_evidenced), matched_claimed_only_count=len(matched_claimed_only),
        missing_count=len(missing), weights_used=w,
    )

    return SkillGapResult(
        user_id=user_id, career_id=career.career_id, canonical_name=career.canonical_name, domain=career.domain,
        fit_score=round(fit.fit_score, 4), total_weight=fit.total_weight, total_contribution=fit.total_contribution,
        score_breakdown=breakdown,
        matched_evidenced=matched_evidenced, matched_claimed_only=matched_claimed_only, missing=missing,
        unmatched_user_claims=unmatched_user_claims,
    )


def analyze_skill_gap(user_id: int, career_id: str, weights: dict | None = None) -> SkillGapResult:
    """
    Validates the user and the career, retrieves their data through the
    existing services, and classifies. Read-only.

    Raises UserNotFoundError / CareerNotFoundError for unknown ids.
    """
    profile = us.get_user_full_profile(user_id)
    if profile is None:
        raise UserNotFoundError(f"user_id={user_id} does not exist")

    career = rs.get_career(career_id)
    if career is None:
        raise CareerNotFoundError(f"career_id={career_id!r} does not exist in the Occupational KB")

    career_skills = rs.get_career_skills(career_id)
    return classify_skill_gap(
        user_id, career, career_skills, profile.skills, weights,
        effective_skills=profile.effective_skills,
    )