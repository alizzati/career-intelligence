"""Profile-level and run-level evaluation orchestration for Step 17.

The evaluator is deliberately small: it maps an :class:`EvaluationCase` to the
applicable metrics, and averages profile values into a machine-readable report.
It never runs the workflow, never calls an LLM, and never writes to the
database. Step 18 owns experiment execution and manifest persistence.
"""
from __future__ import annotations

import datetime as _dt
from statistics import fmean
from typing import Iterable, Mapping

from app.evaluation.adapters import reference_skill_status
from app.evaluation.configurations import get_configuration
from app.evaluation.metrics import (
    classification_metrics,
    detection_metrics,
    gap_set_metrics,
    hit_at_k,
    mean_pairwise_top_k_stability,
    ndcg_at_k,
    over_credit_rate,
    reciprocal_rank,
    relevance_map,
    roadmap_metrics,
    tie_at_cutoff,
    traceability_metrics,
    unmatched_claim_metrics,
)
from app.evaluation.schemas import (
    EvaluationCase,
    EvaluationReport,
    MetricResult,
    ProfileEvaluation,
)

PROFILE_EVALUATION_SCHEMA_VERSION = "evaluation/1.0"
HIT_K_VALUES: tuple[int, ...] = (1, 3)
NDCG_K = 3


def _result(
    name: str,
    value: float | None,
    *,
    unit: str = "ratio",
    reason: str | None = None,
) -> MetricResult:
    if value is None:
        return MetricResult(
            name=name,
            status="unavailable",
            value=None,
            unit=unit,  # type: ignore[arg-type]
            reason=reason or "metric is undefined for this case",
        )
    return MetricResult(name=name, status="computed", value=float(value), unit=unit)  # type: ignore[arg-type]


def _add_unavailable(metrics: dict[str, MetricResult], names: Iterable[str], reason: str) -> None:
    for name in names:
        metrics[name] = MetricResult(name=name, status="unavailable", reason=reason)


def _evaluate_recommendation(case: EvaluationCase, metrics: dict, warnings: list[str]) -> None:
    reference = case.references.recommendation if case.references else None
    if reference is None:
        warnings.append("recommendation reference labels were not supplied")
        return
    relevance = relevance_map(reference.labels)
    names = [f"career.hit_at_{k}" for k in HIT_K_VALUES] + [
        f"career.ndcg_at_{NDCG_K}",
        "career.mrr",
    ]
    if not relevance:
        _add_unavailable(metrics, names, "recommendation reference labels are empty")
        return
    if case.recommendation is None:
        _add_unavailable(metrics, names, "recommendation prediction is unavailable")
        return
    ranking = case.recommendation.ranking
    for k in HIT_K_VALUES:
        metrics[f"career.hit_at_{k}"] = _result(
            f"career.hit_at_{k}",
            hit_at_k(ranking, relevance, k),
            reason=f"no relevant career is labeled for Hit@{k}",
        )
    metrics[f"career.ndcg_at_{NDCG_K}"] = _result(
        f"career.ndcg_at_{NDCG_K}",
        ndcg_at_k(ranking, relevance, NDCG_K),
        reason="ideal DCG is zero (no positive relevance label)",
    )
    metrics["career.mrr"] = _result(
        "career.mrr",
        reciprocal_rank(ranking, relevance),
        reason="no relevant career is labeled",
    )
    tie = tie_at_cutoff(ranking, case.recommendation.fit_scores, NDCG_K)
    metrics["career.tie_at_3"] = _result(
        "career.tie_at_3",
        None if tie is None else (1.0 if tie else 0.0),
        reason="fewer than four ranked careers carry a fit score",
    )


def _evaluate_skill_gap(case: EvaluationCase, metrics: dict, warnings: list[str]) -> None:
    reference = case.references.skill_gap if case.references else None
    if reference is None:
        warnings.append("skill-gap reference labels were not supplied")
        return
    reference_status = {
        label.skill_id: label.status for label in reference.required_skill_status
    }
    names = (
        ["skill_gap.status_macro_f1", "skill_gap.status_accuracy"]
        + [
            f"skill_gap.{status}.{metric}"
            for status in ("matched_evidenced", "matched_claimed_only", "missing")
            for metric in ("precision", "recall", "f1")
        ]
        + [
            f"skill_gap.{status}_set.{metric}"
            for status in ("matched_claimed_only", "missing")
            for metric in ("precision", "recall", "f1")
        ]
        + ["skill_gap.over_credit_rate", "skill_gap.unmatched_claim_recall"]
    )
    if not reference_status:
        _add_unavailable(metrics, names, "skill-gap reference labels are empty")
        return
    prediction = case.skill_gap
    if prediction is None:
        _add_unavailable(metrics, names, "skill-gap prediction is unavailable")
        return
    if prediction.career_id != reference.career_id:
        _add_unavailable(
            metrics,
            names,
            "skill-gap prediction career_id does not match the reference",
        )
        return

    scores = classification_metrics(reference_status, prediction.required_skill_status)
    metrics["skill_gap.status_macro_f1"] = _result(
        "skill_gap.status_macro_f1",
        scores["status_macro_f1"],
        reason="no status has reference support",
    )
    metrics["skill_gap.status_accuracy"] = _result(
        "skill_gap.status_accuracy",
        scores["status_accuracy"],
        reason="no reference statuses",
    )
    for status, values in scores["per_status"].items():
        for metric in ("precision", "recall", "f1"):
            metrics[f"skill_gap.{status}.{metric}"] = _result(
                f"skill_gap.{status}.{metric}",
                values[metric],
                reason=f"status {status!r} is not defined for this reference",
            )

    gap_sets = gap_set_metrics(reference_status, prediction.required_skill_status)
    for status, values in gap_sets.items():
        for metric in ("precision", "recall", "f1"):
            metrics[f"skill_gap.{status}_set.{metric}"] = _result(
                f"skill_gap.{status}_set.{metric}",
                values[metric],
                reason=f"the {status!r} set is empty on one side",
            )

    credit = over_credit_rate(reference_status, prediction.required_skill_status)
    metrics["skill_gap.over_credit_rate"] = _result(
        "skill_gap.over_credit_rate",
        credit["rate"],
        reason="the reference has no missing skill",
    )

    unmatched = unmatched_claim_metrics(
        reference.unmatched_user_claim_keys,
        prediction.unmatched_user_claim_keys,
    )
    metrics["skill_gap.unmatched_claim_recall"] = _result(
        "skill_gap.unmatched_claim_recall",
        unmatched["recall"],
        reason="the reference has no unmatched user claim",
    )


def _evaluate_verification(case: EvaluationCase, metrics: dict, warnings: list[str]) -> None:
    reference = case.references.verification if case.references else None
    prediction = case.verification
    if prediction is None and reference is None:
        return
    if prediction is not None and prediction.status != "unavailable":
        metrics["verification.outcome_pass"] = _result(
            "verification.outcome_pass",
            1.0 if prediction.status == "PASS" else 0.0,
        )
        metrics["verification.revision_triggered"] = _result(
            "verification.revision_triggered",
            1.0 if prediction.revision_count > 0 else 0.0,
        )
        metrics["verification.revision_count"] = _result(
            "verification.revision_count",
            float(prediction.revision_count),
            unit="count",
        )
        if prediction.first_pass_status is not None:
            if prediction.first_pass_status == "PASS":
                metrics["verification.resolution"] = MetricResult(
                    name="verification.resolution",
                    status="unavailable",
                    reason="the first pass already passed; no revision was resolvable",
                )
            else:
                metrics["verification.resolution"] = _result(
                    "verification.resolution",
                    1.0 if prediction.status == "PASS" else 0.0,
                )

    if reference is None:
        warnings.append("verification fault labels were not supplied")
        return
    detection_names = [
        "verification.detection_recall",
        "verification.detection_precision",
        "verification.false_positive_rate",
    ]
    if prediction is None:
        _add_unavailable(metrics, detection_names, "verification prediction is unavailable")
        return
    detection = detection_metrics(
        reference.injected_fault_ids,
        prediction.reported_claim_ids,
        reference.audited_claim_ids or None,
    )
    metrics["verification.detection_recall"] = _result(
        "verification.detection_recall",
        detection["detection_recall"],
        reason="no injected fault label was supplied",
    )
    metrics["verification.detection_precision"] = _result(
        "verification.detection_precision",
        detection["detection_precision"],
        reason="no claim was reported",
    )
    metrics["verification.false_positive_rate"] = _result(
        "verification.false_positive_rate",
        detection["false_positive_rate"],
        reason="no audited clean claim was supplied",
    )


def _evaluate_traceability(case: EvaluationCase, metrics: dict, warnings: list[str]) -> None:
    reference = case.references.kb if case.references else None
    if reference is None:
        warnings.append("knowledge-base reference was not supplied")
        return
    names = [
        "traceability.recommendation_l1_rate",
        "traceability.recommendation_l2_rate",
        "traceability.recommendation_l3_rate",
        "traceability.evidence_lineage_rate",
        "traceability.gap_item_lineage_rate",
    ]
    if case.recommendation is None:
        _add_unavailable(metrics, names, "recommendation prediction is unavailable")
        return
    values = traceability_metrics(case.recommendation, reference, case.skill_gap)
    labels = {
        "traceability.recommendation_l1_rate": ("recommendation_l1_rate", "no ranked career"),
        "traceability.recommendation_l2_rate": ("recommendation_l2_rate", "no ranked career"),
        "traceability.recommendation_l3_rate": ("recommendation_l3_rate", "no ranked career"),
        "traceability.evidence_lineage_rate": ("evidence_lineage_rate", "no evidenced skill"),
        "traceability.gap_item_lineage_rate": ("gap_item_lineage_rate", "no skill-gap item"),
    }
    for name, (key, reason) in labels.items():
        metrics[name] = _result(name, values.get(key), reason=reason)


def _evaluate_roadmap(case: EvaluationCase, metrics: dict, warnings: list[str]) -> None:
    prediction = case.roadmap
    if prediction is None:
        if case.references and case.references.skill_gap is not None:
            warnings.append("roadmap prediction is unavailable")
        return
    reference_status = reference_skill_status(
        case.references.skill_gap if case.references else None
    )
    gap_status = reference_status or (
        case.skill_gap.required_skill_status if case.skill_gap is not None else {}
    )
    if not gap_status:
        warnings.append("no skill-gap status is available for roadmap grounding")
        return
    values = roadmap_metrics(prediction, gap_status)
    labels = {
        "roadmap.coverage": ("coverage", "the deterministic gap has no missing or claimed-only skill"),
        "roadmap.unsupported_item_rate": ("unsupported_item_rate", "no roadmap item"),
        "roadmap.grounding_rate": ("grounding_rate", "no roadmap item"),
        "roadmap.status_consistency": ("status_consistency", "no actionable roadmap item"),
        "roadmap.action_consistency": ("action_consistency", "no actionable roadmap item"),
    }
    for name, (key, reason) in labels.items():
        metrics[name] = _result(name, values.get(key), reason=reason)


def _evaluate_operational(case: EvaluationCase, metrics: dict) -> None:
    metrics["operational.failure"] = _result(
        "operational.failure",
        1.0 if case.run_status == "failed" else 0.0,
    )
    operational = case.operational
    if operational is not None:
        for name, value, unit in (
            ("operational.latency_ms", operational.latency_ms, "ms"),
            ("operational.token_usage", operational.token_usage, "tokens"),
            ("operational.api_call_count", operational.api_call_count, "calls"),
            ("operational.retry_count", operational.retry_count, "count"),
            ("operational.revision_count", operational.revision_count, "count"),
        ):
            if value is not None:
                metrics[name] = _result(name, float(value), unit=unit)


def evaluate_case(case: EvaluationCase) -> ProfileEvaluation:
    """Compute every applicable metric for one profile/configuration case."""
    get_configuration(case.config_id)  # defensive: reject non-agreed config IDs
    metrics: dict[str, MetricResult] = {}
    warnings: list[str] = []
    if case.references is None:
        warnings.append("no reference labels were supplied for this profile")
    _evaluate_recommendation(case, metrics, warnings)
    _evaluate_skill_gap(case, metrics, warnings)
    _evaluate_verification(case, metrics, warnings)
    _evaluate_traceability(case, metrics, warnings)
    _evaluate_roadmap(case, metrics, warnings)
    _evaluate_operational(case, metrics)
    return ProfileEvaluation(
        profile_id=case.profile_id,
        config_id=case.config_id,
        metrics=dict(sorted(metrics.items())),
        warnings=warnings,
    )


def _aggregate(profiles: list[ProfileEvaluation]) -> dict[str, MetricResult]:
    """Average within profile first, then across profiles (protocol unit)."""
    grouped: dict[str, list[ProfileEvaluation]] = {}
    for profile in profiles:
        grouped.setdefault(profile.profile_id, []).append(profile)

    metric_names = sorted({name for profile in profiles for name in profile.metrics})
    summary: dict[str, MetricResult] = {}
    for name in metric_names:
        results = [
            metric
            for profile in profiles
            for metric in [profile.metrics.get(name)]
            if metric is not None
        ]
        unit = results[0].unit
        profile_means: list[float] = []
        skipped_profiles = 0
        for group in grouped.values():
            values = [
                profile.metrics[name].value
                for profile in group
                if name in profile.metrics
                and profile.metrics[name].status == "computed"
                and profile.metrics[name].value is not None
            ]
            if values:
                profile_means.append(fmean(values))
            else:
                skipped_profiles += 1
        if not profile_means:
            reasons = sorted({item.reason for item in results if item.reason})
            summary[name] = MetricResult(
                name=name,
                status="unavailable",
                unit=unit,
                n=0,
                skipped=sum(
                    1 for group in grouped.values()
                    if all(
                        name not in profile.metrics
                        or profile.metrics[name].status != "computed"
                        for profile in group
                    )
                ),
                reason="; ".join(reasons) or "no profile produced a value",
            )
            continue
        summary[name] = MetricResult(
            name=name,
            status="computed",
            value=fmean(profile_means),
            unit=unit,
            n=len(profile_means),
            skipped=skipped_profiles,
        )
    return summary


def _stability_metric(cases: list[EvaluationCase]) -> MetricResult:
    """Report-level pairwise top-3 stability over repeated runs per profile.

    A profile contributes one averaged value across its pairwise run
    comparisons. Profiles with fewer than two usable rankings are counted as
    skipped rather than silently dropped.
    """
    grouped: dict[str, list[list[str]]] = {case.profile_id: [] for case in cases}
    for case in cases:
        if case.recommendation is not None:
            grouped[case.profile_id].append(case.recommendation.ranking)
    values = [
        value
        for value in (
            mean_pairwise_top_k_stability(rankings, NDCG_K)
            for rankings in grouped.values()
        )
        if value is not None
    ]
    if not values:
        return MetricResult(
            name="career.stability_at_3",
            status="unavailable",
            reason="no profile has at least two usable recommendation runs",
            n=0,
            skipped=len(grouped),
        )
    return MetricResult(
        name="career.stability_at_3",
        status="computed",
        value=fmean(values),
        n=len(values),
        skipped=len(grouped) - len(values),
    )


def evaluate_report(cases: Iterable[EvaluationCase]) -> EvaluationReport:
    """Evaluate a non-empty batch of cases belonging to one configuration.

    The unit of analysis is the profile. Each metric is computed per profile and
    then averaged across profiles that produced a value. ``n`` and ``skipped``
    make coverage explicit.
    """
    case_list = list(cases)
    if not case_list:
        raise ValueError("at least one evaluation case is required")
    config_ids = sorted({case.config_id for case in case_list})
    if len(config_ids) != 1:
        raise ValueError(
            "all cases in one report must share a configuration; got " + ", ".join(config_ids)
        )
    config_id = case_list[0].config_id
    get_configuration(config_id)

    profiles = [evaluate_case(case) for case in case_list]
    failures = sum(1 for case in case_list if case.run_status == "failed")
    warnings: list[str] = []
    for profile in profiles:
        for warning in profile.warnings:
            warnings.append(f"{profile.profile_id}: {warning}")

    metrics = _aggregate(profiles)
    metrics["career.stability_at_3"] = _stability_metric(case_list)

    return EvaluationReport(
        schema_version=PROFILE_EVALUATION_SCHEMA_VERSION,  # type: ignore[arg-type]
        generated_at=_dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        config_id=config_id,
        case_count=len(case_list),
        profile_count=len({case.profile_id for case in case_list}),
        failed_case_count=failures,
        metrics=dict(sorted(metrics.items())),
        profiles=profiles,
        warnings=warnings,
    )
