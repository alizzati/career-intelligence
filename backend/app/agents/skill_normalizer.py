"""
Deterministic skill normalizer (Section 10: "Skill ID matching" is a
deterministic component). No LLM call happens inside this module --
it is a pure function of (claimed text, KB skill catalog, optional LLM
suggestion already obtained upstream).

Matching priority:
  1. exact match (case/whitespace-insensitive) on canonical_name
  2. fuzzy match (difflib similarity >= FUZZY_THRESHOLD), unique best match
  3. llm_suggested_skill_id, IF it is present in the candidate catalog
     (never trusted blindly -- re-validated against the real catalog here,
     so a hallucinated skill_id from the LLM step can never leak through)
  4. unmatched -> skill_id stays None
"""
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Literal

FUZZY_THRESHOLD = 0.88


@dataclass
class FuzzyMatchCandidate:
    skill_id: str
    canonical_name: str
    similarity: float
    meets_threshold: bool


@dataclass
class NormalizationResult:
    skill_id: str | None
    normalized_name: str | None
    method: str   # exact-deterministic | fuzzy-deterministic | llm-assisted | ambiguous | unmatched
    score: float | None = None
    outcome: Literal["matched", "unmatched", "ambiguous"] = "unmatched"
    exact_match: bool = False
    fuzzy_candidates: list[FuzzyMatchCandidate] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.skill_id is not None and self.outcome == "unmatched":
            self.outcome = "matched"
        if self.method == "exact-deterministic":
            self.exact_match = True


def _norm(s: str) -> str:
    return " ".join(s.strip().lower().split())


def normalize_skill(
    claimed_skill: str,
    skill_catalog: list[dict],          # [{"skill_id":..., "canonical_name":...}, ...]
    llm_suggested_skill_id: str | None = None,
) -> NormalizationResult:
    claimed_norm = _norm(claimed_skill)

    # 1. exact match
    for s in skill_catalog:
        if _norm(s["canonical_name"]) == claimed_norm:
            return NormalizationResult(
                s["skill_id"], s["canonical_name"], "exact-deterministic", 1.0,
                outcome="matched", exact_match=True,
                fuzzy_candidates=[FuzzyMatchCandidate(s["skill_id"], s["canonical_name"], 1.0, True)],
            )

    # 2. fuzzy match, require a clear unique winner
    scored = sorted(
        ((SequenceMatcher(None, claimed_norm, _norm(s["canonical_name"])).ratio(), s) for s in skill_catalog),
        key=lambda x: x[0], reverse=True,
    )
    candidates = [
        FuzzyMatchCandidate(row["skill_id"], row["canonical_name"], score,
                            score >= FUZZY_THRESHOLD)
        for score, row in scored[:5]
    ]
    if scored and scored[0][0] >= FUZZY_THRESHOLD:
        if len(scored) == 1 or scored[0][0] - scored[1][0] > 1e-6 or scored[0][1]["skill_id"] == scored[1][1]["skill_id"]:
            best_score, best = scored[0]
            return NormalizationResult(
                best["skill_id"], best["canonical_name"], "fuzzy-deterministic", best_score,
                outcome="matched", fuzzy_candidates=candidates,
            )

    # 3. LLM suggestion, but ONLY if it is a real entry in the catalog --
    #    this is what prevents a hallucinated skill_id from being persisted.
    if llm_suggested_skill_id:
        catalog_ids = {s["skill_id"]: s["canonical_name"] for s in skill_catalog}
        if llm_suggested_skill_id in catalog_ids:
            return NormalizationResult(
                llm_suggested_skill_id, catalog_ids[llm_suggested_skill_id], "llm-assisted", None,
                outcome="matched", fuzzy_candidates=candidates,
            )
        # LLM suggested an ID that doesn't exist in the KB -- discard it, do not persist.

    # 4. unmatched
    ambiguous = bool(
        scored and scored[0][0] >= FUZZY_THRESHOLD and len(scored) > 1
        and scored[0][0] - scored[1][0] <= 1e-6
        and scored[0][1]["skill_id"] != scored[1][1]["skill_id"]
    )
    return NormalizationResult(
        None, None, "ambiguous" if ambiguous else "unmatched", None,
        outcome="ambiguous" if ambiguous else "unmatched",
        fuzzy_candidates=candidates,
    )
