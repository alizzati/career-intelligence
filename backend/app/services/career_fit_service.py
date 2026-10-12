"""
Career Fit Service -- the SINGLE deterministic calculator for comparing a
user's normalized skills against a career's required skills.

CRITICAL ARCHITECTURAL RULE (per the Step 8 design checkpoint, addressing
the thesis's circularity risk): this module is the ONE place skill-vs-
requirement matching math happens. Step 8 (Career Recommendation Agent)
calls compute_career_fit() once per candidate career to build a ranking.
Step 9 (Skill Gap Agent, not yet implemented) MUST call this exact same
function for one selected career and expose its full SkillFitDetail list
-- never a second, independently-written matching implementation. This is
what guarantees a recommended career's score and its later gap breakdown
can never mathematically disagree with each other.

No DB, no LLM, no Pydantic dependency in this module -- pure dataclasses
and arithmetic only, so it is fully unit-testable in isolation. Callers
(career_recommendation_agent.py) are responsible for converting real KB/
user data (Pydantic schema objects) into the plain input dataclasses
defined here.
"""
import os
from dataclasses import dataclass, field

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


# ---------------------------------------------------------------------
# These defaults MIRROR config/scoring_weights.yaml exactly (see that
# file for the full rationale of every value). They exist here so the
# calculator still works -- deterministically, with the same documented
# values -- even if PyYAML is not installed or the config file is
# missing, rather than silently falling back to different numbers.
# Still an "initial/default configuration", not scientifically validated.
# ---------------------------------------------------------------------
DEFAULT_WEIGHTS = {
    "core_weight": 1.0,
    "supporting_weight": 0.5,
    "claim_only_multiplier": 0.5,
    "confidence_multiplier": {"high": 1.0, "medium": 0.85, "low": 0.7},
    "proficiency_modifier": 0.1,
}

CORE_LABEL = "CORE"


def load_scoring_weights(config_path: str | None = None) -> dict:
    """
    Loads weights from config/scoring_weights.yaml. Falls back to
    DEFAULT_WEIGHTS (same documented values, just inline) if PyYAML is
    unavailable or the file cannot be read -- never silently falls back
    to DIFFERENT numbers, and never raises for a missing optional file.
    """
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "config", "scoring_weights.yaml",
        )
    if not _HAS_YAML or not os.path.exists(config_path):
        return dict(DEFAULT_WEIGHTS)
    try:
        with open(config_path, "r") as f:
            loaded = yaml.safe_load(f)
        if not loaded:
            return dict(DEFAULT_WEIGHTS)
        merged = dict(DEFAULT_WEIGHTS)
        merged.update(loaded)
        return merged
    except Exception:
        return dict(DEFAULT_WEIGHTS)


# ---------------------------------------------------------------------
# Plain input/output types. Deliberately NOT the Pydantic schemas from
# retrieval_service/user_service -- keeps this module dependency-free
# and trivially unit-testable with hand-built lists.
# ---------------------------------------------------------------------

@dataclass
class RequiredSkillInput:
    skill_id: str
    evidence_class: str          # 'CORE' | anything else is treated as supporting
    kb_confidence: str           # 'high' | 'medium' | 'low' | unknown values default to neutral 1.0


@dataclass
class UserSkillInput:
    skill_id: str | None         # None = unnormalized claim -- NEVER matches any requirement
    evidence_status: str         # 'linked' | 'none'
    proficiency: str | None = None


@dataclass
class SkillFitDetail:
    skill_id: str
    evidence_class: str
    weight: float
    status: str                  # 'matched-linked' | 'matched-claimed-only' | 'missing'
    contribution: float


@dataclass
class CareerFitResult:
    fit_score: float             # always in [0.0, 1.0]
    total_weight: float
    total_contribution: float
    skill_details: list[SkillFitDetail] = field(default_factory=list)

    @property
    def matched_linked_skill_ids(self) -> list[str]:
        return [d.skill_id for d in self.skill_details if d.status == "matched-linked"]

    @property
    def matched_claimed_only_skill_ids(self) -> list[str]:
        return [d.skill_id for d in self.skill_details if d.status == "matched-claimed-only"]

    @property
    def missing_skill_ids(self) -> list[str]:
        return [d.skill_id for d in self.skill_details if d.status == "missing"]


def _best_user_match(skill_id: str, user_skills: list[UserSkillInput]) -> UserSkillInput | None:
    """
    A user may have more than one claimed_skill string normalize to the
    same canonical skill_id (e.g. "DB mgmt" and "Database Management" both
    -> S035). Deterministic tie-break: prefer evidence_status='linked'
    over 'none'; among equals, keep input order (first one wins).
    Skills with skill_id=None are never candidates here by construction
    (filtered by the caller / never match on identity below).
    """
    candidates = [u for u in user_skills if u.skill_id == skill_id]
    if not candidates:
        return None
    linked = [u for u in candidates if u.evidence_status == "linked"]
    return linked[0] if linked else candidates[0]


def compute_career_fit(
    required_skills: list[RequiredSkillInput],
    user_skills: list[UserSkillInput],
    weights: dict | None = None,
) -> CareerFitResult:
    """
    Pure, deterministic. Same inputs ALWAYS produce the same
    CareerFitResult -- no randomness, no LLM, no I/O.

    required_skills: the full set of career_skills rows for ONE career
                      (from retrieval_service.get_career_skills, converted
                      by the caller).
    user_skills:      the user's normalized skills (from
                       user_service.get_user_full_profile, converted by
                       the caller). Entries with skill_id=None are simply
                       never matched -- they cannot contribute, by
                       construction of the matching key (identity on
                       skill_id), not by any special-case branch.
    """
    w = weights if weights is not None else DEFAULT_WEIGHTS
    conf_mult_table = w.get("confidence_multiplier", DEFAULT_WEIGHTS["confidence_multiplier"])

    details: list[SkillFitDetail] = []
    total_weight = 0.0
    total_contribution = 0.0

    for req in required_skills:
        base = w["core_weight"] if req.evidence_class.upper() == CORE_LABEL else w["supporting_weight"]
        conf_mult = conf_mult_table.get(req.kb_confidence, 1.0)  # unknown confidence value -> neutral 1.0
        weight = base * conf_mult

        match = _best_user_match(req.skill_id, user_skills)

        if match is None:
            contribution = 0.0
            status = "missing"
        else:
            if match.evidence_status == "linked":
                base_contribution = weight * 1.0
                status = "matched-linked"
            else:
                base_contribution = weight * w["claim_only_multiplier"]
                status = "matched-claimed-only"

            # Self-reported proficiency modifier -- see module docstring
            # and scoring_weights.yaml: this is NOT a comparison against a
            # KB-required proficiency level (no such field exists in the
            # KB). It is a weak secondary bonus for having self-reported
            # ANY proficiency at all, capped so it can never push this
            # skill's contribution above its own full weight.
            has_proficiency = bool(match.proficiency) and match.proficiency.strip().lower() not in ("", "unspecified", "none")
            if has_proficiency:
                contribution = min(base_contribution * (1 + w["proficiency_modifier"]), weight)
            else:
                contribution = base_contribution

        details.append(SkillFitDetail(
            skill_id=req.skill_id, evidence_class=req.evidence_class,
            weight=weight, status=status, contribution=contribution,
        ))
        total_weight += weight
        total_contribution += contribution

    fit_score = (total_contribution / total_weight) if total_weight > 0 else 0.0
    fit_score = max(0.0, min(1.0, fit_score))  # clamp against float rounding

    return CareerFitResult(
        fit_score=fit_score, total_weight=total_weight,
        total_contribution=total_contribution, skill_details=details,
    )