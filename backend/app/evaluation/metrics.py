"""Deterministic metric implementations for Step 17.

Every function here is a pure calculation over explicit inputs. There is no
database access, no LLM call, and no hidden default reference. Metric formulas
and their missing-value policies are documented in
``docs/evaluation/METRICS_IMPLEMENTATION.md``.

Evaluation unit: one profile under one configuration. The evaluator averages
these per-profile values across profiles; the functions below operate on one
profile at a time (or on one career's skill set).
"""
from __future__ import annotations

import math
from itertools import combinations
from statistics import fmean
from typing import Iterable, Mapping

from app.evaluation.schemas import (
    CareerRelevanceLabel,
    KbReference,
    RecommendationPrediction,
    RoadmapPrediction,
    SkillGapPrediction,
)

REQUIRED_STATUSES: tuple[str, ...] = (
    "matched_evidenced",
    "matched_claimed_only",
    "missing",
)
GAP_STATUSES: tuple[str, ...] = ("matched_claimed_only", "missing")

_ACTION_FOR_STATUS = {
    "missing": "develop_skill",
    "matched_claimed_only": "add_linked_evidence",
}


# --------------------------------------------------------------------- ranking
def relevance_map(labels: Iterable[CareerRelevanceLabel]) -> dict[str, float]:
    """Convert reference labels into ``career_id -> relevance``."""
    return {label.career_id: float(label.relevance) for label in labels}


def hit_at_k(
    ranking: Iterable[str],
    relevance: Mapping[str, float],
    k: int,
) -> float | None:
    """Binary Hit@k: 1.0 if at least one top-k career has relevance >= 1.

    Returns ``None`` when the reference contains no relevant career (the metric
    is undefined, not zero). An empty or short ranking is scored against the
    careers it actually contains.
    """
    if k <= 0:
        raise ValueError("k must be a positive integer")
    relevant = {career_id for career_id, value in relevance.items() if value >= 1.0}
    if not relevant:
        return None
    return 1.0 if any(career_id in relevant for career_id in list(ranking)[:k]) else 0.0


def reciprocal_rank(
    ranking: Iterable[str],
    relevance: Mapping[str, float],
) -> float | None:
    """Mean reciprocal-rank input: 1/rank of the first relevant career, else 0."""
    relevant = {career_id for career_id, value in relevance.items() if value >= 1.0}
    if not relevant:
        return None
    for rank, career_id in enumerate(ranking, start=1):
        if career_id in relevant:
            return 1.0 / rank
    return 0.0


def dcg_at_k(ranking: Iterable[str], relevance: Mapping[str, float], k: int) -> float:
    total = 0.0
    for rank, career_id in enumerate(list(ranking)[:k], start=1):
        value = relevance.get(career_id, 0.0)
        if value > 0:
            total += (math.pow(2.0, value) - 1.0) / math.log2(rank + 1)
    return total


def ndcg_at_k(
    ranking: Iterable[str],
    relevance: Mapping[str, float],
    k: int,
) -> float | None:
    """nDCG@k with graded relevance using ``(2^rel - 1) / log2(rank + 1)``.

    The ideal DCG is built from the reference relevance values sorted
    descending. Returns ``None`` when all reference labels are zero (IDCG = 0).
    """
    if k <= 0:
        raise ValueError("k must be a positive integer")
    ideal_values = sorted((value for value in relevance.values() if value > 0), reverse=True)[:k]
    if not ideal_values:
        return None
    idcg = sum(
        (math.pow(2.0, value) - 1.0) / math.log2(rank + 1)
        for rank, value in enumerate(ideal_values, start=1)
    )
    if idcg <= 0:
        return None
    return dcg_at_k(ranking, relevance, k) / idcg


def tie_at_cutoff(ranking: Iterable[str], scores: Mapping[str, float], k: int) -> bool | None:
    """Whether a score tie crosses the top-k boundary.

    Returns ``None`` when fewer than ``k + 1`` ranked careers have scores, so the
    question is not applicable. Ties are a known property of the deterministic
    system (career_id is the arbitrary tie-break), which is why this is reported
    separately instead of hidden inside Hit@k.
    """
    if k <= 0:
        raise ValueError("k must be a positive integer")
    ranked = list(ranking)
    if len(ranked) <= k:
        return None
    above = [scores.get(career_id) for career_id in ranked[:k]]
    below = [scores.get(career_id) for career_id in ranked[k:]]
    if any(value is None for value in above + below):
        return None
    return bool(set(above) & set(below))


def top_k_overlap(ranking_a: Iterable[str], ranking_b: Iterable[str], k: int) -> float | None:
    """Jaccard overlap of two top-k sets (pairwise stability input)."""
    if k <= 0:
        raise ValueError("k must be a positive integer")
    first = set(list(ranking_a)[:k])
    second = set(list(ranking_b)[:k])
    union = first | second
    return len(first & second) / len(union) if union else None


def mean_pairwise_top_k_stability(rankings: Iterable[Iterable[str]], k: int) -> float | None:
    """Mean pairwise top-k overlap across repeated runs of one profile.

    This is the operational definition of recommendation stability. It is not
    part of a single-run report because it requires repeated runs; Step 18 owns
    the repetition schedule.
    """
    materialized = [list(ranking) for ranking in rankings]
    values = [
        top_k_overlap(first, second, k)
        for first, second in combinations(materialized, 2)
    ]
    defined = [value for value in values if value is not None]
    return fmean(defined) if defined else None


# -------------------------------------------------------------- classification
def _safe_ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _f1(precision: float | None, recall: float | None) -> float | None:
    if precision is None or recall is None:
        return None
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def classification_metrics(
    reference: Mapping[str, str],
    prediction: Mapping[str, str],
) -> dict:
    """Per-status and macro-averaged classification metrics.

    Only required skills present in ``reference`` are evaluated. A skill absent
    from ``prediction`` contributes a false negative for its reference class but
    no false positive for any class. Macro-F1 is averaged over statuses that
    have reference support. ``None`` means the metric is undefined.
    """
    valid_prediction = {
        skill_id: status
        for skill_id, status in prediction.items()
        if status in REQUIRED_STATUSES
    }
    per_status: dict[str, dict] = {}
    for status in REQUIRED_STATUSES:
        true_ids = {skill_id for skill_id, value in reference.items() if value == status}
        predicted_ids = {
            skill_id for skill_id, value in valid_prediction.items() if value == status
        }
        true_positive = len(true_ids & predicted_ids)
        # A supported class with no predicted members has precision 0 by
        # convention (not undefined), so macro-F1 stays defined for every
        # class that appears in the reference.
        precision = (
            _safe_ratio(true_positive, len(predicted_ids))
            if predicted_ids else (0.0 if true_ids else None)
        )
        recall = _safe_ratio(true_positive, len(true_ids))
        per_status[status] = {
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
            "support": len(true_ids),
            "predicted": len(predicted_ids),
        }

    supported = [item["f1"] for item in per_status.values() if item["support"] > 0]
    macro_f1 = sum(supported) / len(supported) if supported and all(
        value is not None for value in supported
    ) else None

    total = len(reference)
    correct = sum(
        1
        for skill_id, status in reference.items()
        if valid_prediction.get(skill_id) == status
    )
    return {
        "status_macro_f1": macro_f1,
        "status_accuracy": _safe_ratio(correct, total),
        "per_status": per_status,
        "n": total,
    }


# ------------------------------------------------------------------ gap sets
def set_metrics(reference: set[str], predicted: set[str]) -> dict:
    """Precision/recall/F1 for a set-valued gap category.

    ``None`` is returned when a denominator is empty, so an empty reference set
    is never silently reported as perfect agreement. The caller decides whether
    to treat an empty category as not applicable.
    """
    true_positive = len(reference & predicted)
    precision = _safe_ratio(true_positive, len(predicted))
    recall = _safe_ratio(true_positive, len(reference))
    return {
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
        "tp": true_positive,
        "fp": len(predicted - reference),
        "fn": len(reference - predicted),
    }


def gap_set_metrics(
    reference: Mapping[str, str],
    prediction: Mapping[str, str],
) -> dict:
    """Gap-set metrics for the ``missing`` and ``matched_claimed_only`` sets."""
    result: dict[str, dict] = {}
    for status in GAP_STATUSES:
        reference_ids = {skill_id for skill_id, value in reference.items() if value == status}
        predicted_ids = {skill_id for skill_id, value in prediction.items() if value == status}
        result[status] = set_metrics(reference_ids, predicted_ids)
    return result


def over_credit_rate(reference: Mapping[str, str], prediction: Mapping[str, str]) -> dict:
    """Fraction of reference-``missing`` skills that the system credited.

    A credited skill is one predicted as ``matched_evidenced`` or
    ``matched_claimed_only`` while the reference says it is missing. Returns
    ``None`` when the reference has no missing skills.
    """
    reference_missing = {skill_id for skill_id, value in reference.items() if value == "missing"}
    credited = {
        skill_id
        for skill_id in reference_missing
        if prediction.get(skill_id) in ("matched_evidenced", "matched_claimed_only")
    }
    return {
        "rate": _safe_ratio(len(credited), len(reference_missing)),
        "credited": len(credited),
        "reference_missing": len(reference_missing),
    }


def unmatched_claim_metrics(reference_keys: Iterable[str], predicted_keys: Iterable[str]) -> dict:
    """Set metrics for user claims outside the canonical skill catalog.

    These claims are *not* required career skills, so they are never merged into
    the three-status classification. They are scored only as a claim set.
    """
    return set_metrics(set(reference_keys), set(predicted_keys))


# ---------------------------------------------------------------- verification
def detection_metrics(
    injected_fault_ids: Iterable[str],
    reported_claim_ids: Iterable[str],
    audited_claim_ids: Iterable[str] | None = None,
) -> dict:
    """Detection recall/precision/FPR for controlled fault injection.

    * recall = detected injected faults / all injected faults
    * precision = correct reported faults / all reported faults
    * false-positive rate = non-injected reported claims / audited clean claims

    FPR is ``None`` when no audited clean claims are supplied.
    """
    injected = set(injected_fault_ids)
    reported = set(reported_claim_ids)
    true_positive = injected & reported
    false_positive = reported - injected
    false_negative = injected - reported
    result = {
        "detection_recall": _safe_ratio(len(true_positive), len(injected)),
        "detection_precision": _safe_ratio(len(true_positive), len(reported)),
        "false_positive_rate": None,
        "tp": len(true_positive),
        "fp": len(false_positive),
        "fn": len(false_negative),
    }
    if audited_claim_ids is not None:
        clean = set(audited_claim_ids) - injected
        clean_reported = false_positive & set(audited_claim_ids)
        result["false_positive_rate"] = _safe_ratio(len(clean_reported), len(clean))
        result["clean_claims"] = len(clean)
    return result


# ---------------------------------------------------------------- traceability
def _career_level(
    career_id: str,
    kb: KbReference,
    prediction: RecommendationPrediction,
) -> tuple[int, bool]:
    """Return ``(level, has_evidence_gap)`` for one ranked career.

    Level 1: the career ID exists in the canonical KB and has requirements.
    Level 2: every referenced skill is a canonical requirement of that career
             and exists in the known skill set.
    Level 3: every evidenced skill additionally carries at least one evidence
             reference. A career with no evidenced skill caps at level 2.
    """
    required = kb.required_skill_ids_by_career.get(career_id)
    if career_id not in kb.canonical_career_ids or not required:
        return 0, False
    required_set = set(required)
    known = set(kb.known_skill_ids)
    referenced = prediction.referenced_skill_ids.get(career_id, [])
    if not referenced or not all(
        skill_id in required_set and skill_id in known for skill_id in referenced
    ):
        return 1, False
    evidenced = prediction.evidenced_skill_ids.get(career_id, [])
    if not evidenced:
        return 2, False
    counts = prediction.evidence_reference_counts.get(career_id, {})
    if all(
        skill_id in referenced and counts.get(skill_id, 0) >= 1
        for skill_id in evidenced
    ):
        return 3, False
    return 2, True


def traceability_metrics(
    prediction: RecommendationPrediction,
    kb: KbReference,
    skill_gap: SkillGapPrediction | None = None,
) -> dict:
    """Lineage rates for recommendations, gap items, and user evidence.

    All rates are over the items actually present in the prediction. ``None``
    means there was nothing to trace (for example an empty ranking), not that
    lineage failed.
    """
    levels = [_career_level(career_id, kb, prediction)[0] for career_id in prediction.ranking]
    total = len(levels)
    result: dict = {
        "recommendation_l1_rate": _safe_ratio(sum(level >= 1 for level in levels), total),
        "recommendation_l2_rate": _safe_ratio(sum(level >= 2 for level in levels), total),
        "recommendation_l3_rate": _safe_ratio(sum(level >= 3 for level in levels), total),
        "career_levels": dict(zip(prediction.ranking, levels)),
        "recommendation_count": total,
    }

    evidenced: list[tuple[str, str, int]] = []
    for career_id, skill_ids in prediction.evidenced_skill_ids.items():
        counts = prediction.evidence_reference_counts.get(career_id, {})
        evidenced.extend((career_id, skill_id, counts.get(skill_id, 0)) for skill_id in skill_ids)
    result["evidence_lineage_rate"] = _safe_ratio(
        sum(1 for _, _, count in evidenced if count >= 1),
        len(evidenced),
    )
    result["evidenced_skill_count"] = len(evidenced)

    if skill_gap is not None:
        required = set(kb.required_skill_ids_by_career.get(skill_gap.career_id, []))
        known = set(kb.known_skill_ids)
        skill_ids = list(skill_gap.required_skill_status)
        result["gap_item_lineage_rate"] = _safe_ratio(
            sum(1 for skill_id in skill_ids if skill_id in required and skill_id in known),
            len(skill_ids),
        )
        result["gap_item_count"] = len(skill_ids)
    return result


# -------------------------------------------------------------------- roadmap
def roadmap_metrics(
    prediction: RoadmapPrediction,
    gap_status_by_skill: Mapping[str, str],
) -> dict:
    """Coverage and grounding against the deterministic skill-gap result.

    ``gap_status_by_skill`` is the authoritative gap classification for the
    evaluated career (reference labels when available, otherwise the
    deterministic system result). Only ``missing`` and
    ``matched_claimed_only`` skills are expected roadmap targets.
    """
    expected = {
        skill_id for skill_id, status in gap_status_by_skill.items() if status in GAP_STATUSES
    }
    item_ids = {item.skill_id for item in prediction.items}
    unsupported = item_ids - expected
    actionable = [item for item in prediction.items if item.skill_id in expected]

    def consistency(field: str, expected_value) -> float | None:
        if not actionable:
            return None
        return _safe_ratio(
            sum(
                1
                for item in actionable
                if expected_value(item) == getattr(item, field)
            ),
            len(actionable),
        )

    return {
        "coverage": _safe_ratio(len(expected & item_ids), len(expected)),
        "unsupported_item_rate": _safe_ratio(len(unsupported), len(item_ids)),
        "grounding_rate": _safe_ratio(
            sum(1 for item in prediction.items if item.knowledge_base_basis.strip()),
            len(prediction.items),
        ),
        "status_consistency": consistency(
            "gap_status",
            lambda item: gap_status_by_skill.get(item.skill_id),
        ),
        "action_consistency": consistency(
            "learning_action",
            lambda item: _ACTION_FOR_STATUS.get(gap_status_by_skill.get(item.skill_id, "")),
        ),
        "expected_count": len(expected),
        "item_count": len(item_ids),
        "unsupported_count": len(unsupported),
    }
