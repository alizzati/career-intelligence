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
from dataclasses import dataclass
from difflib import SequenceMatcher

FUZZY_THRESHOLD = 0.88


@dataclass
class NormalizationResult:
    skill_id: str | None
    normalized_name: str | None
    method: str   # 'exact-deterministic' | 'fuzzy-deterministic' | 'llm-assisted' | 'unmatched'
    score: float | None = None


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
            return NormalizationResult(s["skill_id"], s["canonical_name"], "exact-deterministic", 1.0)

    # 2. fuzzy match, require a clear unique winner
    scored = sorted(
        ((SequenceMatcher(None, claimed_norm, _norm(s["canonical_name"])).ratio(), s) for s in skill_catalog),
        key=lambda x: x[0], reverse=True,
    )
    if scored and scored[0][0] >= FUZZY_THRESHOLD:
        if len(scored) == 1 or scored[0][0] - scored[1][0] > 1e-6 or scored[0][1]["skill_id"] == scored[1][1]["skill_id"]:
            best_score, best = scored[0]
            return NormalizationResult(best["skill_id"], best["canonical_name"], "fuzzy-deterministic", best_score)

    # 3. LLM suggestion, but ONLY if it is a real entry in the catalog --
    #    this is what prevents a hallucinated skill_id from being persisted.
    if llm_suggested_skill_id:
        catalog_ids = {s["skill_id"]: s["canonical_name"] for s in skill_catalog}
        if llm_suggested_skill_id in catalog_ids:
            return NormalizationResult(
                llm_suggested_skill_id, catalog_ids[llm_suggested_skill_id], "llm-assisted", None,
            )
        # LLM suggested an ID that doesn't exist in the KB -- discard it, do not persist.

    # 4. unmatched
    return NormalizationResult(None, None, "unmatched", None)