"""Adapters from real system output to the Step 17 evaluation contracts.

The adapters are read-only projections. They do not change workflow state, API
responses, analysis logs, or any agent output. They accept either the plain
dicts produced by ``to_jsonable()`` (as persisted by Step 16) or the Pydantic
objects returned by the agents.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

from app.evaluation.schemas import (
    EvaluationCase,
    EvaluationReferences,
    RecommendationPrediction,
    RoadmapItemPrediction,
    RoadmapPrediction,
    SkillGapPrediction,
    VerificationCheckPrediction,
    VerificationPrediction,
)


def _as_dict(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump()
    raise TypeError(f"expected a mapping or Pydantic model, got {type(value).__name__}")


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _skill_ids(rows: Any) -> list[str]:
    return [
        str(row["skill_id"])
        for row in _list(rows)
        if isinstance(row, dict) and isinstance(row.get("skill_id"), str)
    ]


def recommendation_prediction_from_outputs(outputs: Any) -> RecommendationPrediction:
    """Project ``CareerRecommendationOut`` rows into an evaluation prediction.

    The ranking is the order already produced by the system; it is not re-sorted
    here. ``matched_skills`` means the KB/user evidence status is ``linked``, so
    each such skill is counted as one evidence reference.
    """
    ranking: list[str] = []
    referenced: dict[str, list[str]] = {}
    evidenced: dict[str, list[str]] = {}
    evidence_counts: dict[str, dict[str, int]] = {}
    fit_scores: dict[str, float] = {}
    for row in _list(outputs):
        if not isinstance(row, dict) or not isinstance(row.get("career_id"), str):
            continue
        career_id = row["career_id"]
        if career_id in referenced:
            continue
        matched = _skill_ids(row.get("matched_skills"))
        claimed = _skill_ids(row.get("claimed_only_skills"))
        missing = _skill_ids(row.get("missing_skills_preview"))
        ranking.append(career_id)
        referenced[career_id] = matched + claimed + missing
        evidenced[career_id] = matched
        evidence_counts[career_id] = {skill_id: 1 for skill_id in matched}
        score = row.get("fit_score")
        if isinstance(score, (int, float)) and not isinstance(score, bool):
            fit_scores[career_id] = float(score)
    return RecommendationPrediction(
        ranking=ranking,
        fit_scores=fit_scores,
        referenced_skill_ids=referenced,
        evidenced_skill_ids=evidenced,
        evidence_reference_counts=evidence_counts,
    )


def skill_gap_prediction_from_outputs(output: Any) -> SkillGapPrediction | None:
    """Project a ``SkillGapAnalysisOut``/``SkillGapResult`` into a prediction."""
    data = _as_dict(output)
    if isinstance(data.get("skill_gap"), dict):
        data = data["skill_gap"]
    career_id = data.get("career_id")
    if not isinstance(career_id, str) or not career_id:
        return None
    statuses: dict[str, str] = {}
    for status in ("matched_evidenced", "matched_claimed_only", "missing"):
        for row in _list(data.get(status)):
            if isinstance(row, dict) and isinstance(row.get("skill_id"), str):
                statuses.setdefault(row["skill_id"], status)
    unmatched = [
        f"user_skill_id:{row['user_skill_id']}"
        for row in _list(data.get("unmatched_user_claims"))
        if isinstance(row, dict) and isinstance(row.get("user_skill_id"), int)
    ]
    return SkillGapPrediction(
        career_id=career_id,
        required_skill_status=statuses,
        unmatched_user_claim_keys=unmatched,
    )


def roadmap_prediction_from_outputs(output: Any) -> RoadmapPrediction | None:
    data = _as_dict(output)
    items: list[RoadmapItemPrediction] = []
    for row in _list(data.get("items")):
        if not isinstance(row, dict):
            continue
        skill_id = row.get("skill_id")
        gap_status = row.get("gap_status")
        action = row.get("learning_action")
        if (
            isinstance(skill_id, str)
            and gap_status in ("matched_claimed_only", "missing")
            and action in ("develop_skill", "add_linked_evidence")
        ):
            items.append(RoadmapItemPrediction(
                skill_id=skill_id,
                gap_status=gap_status,
                learning_action=action,
                knowledge_base_basis=(
                    row.get("knowledge_base_basis")
                    if isinstance(row.get("knowledge_base_basis"), str) else ""
                ),
            ))
    return RoadmapPrediction(items=items)


def default_claim_key(claim: Mapping[str, Any]) -> str | None:
    """Stable, non-PII identity for a verification claim.

    The key is only used in memory to match reported claims against injected
    fault IDs. It is never written to a metric value or report.
    """
    component = claim.get("component")
    text = claim.get("claim")
    if not isinstance(component, str) or not isinstance(text, str):
        return None
    return f"{component}::{text.strip()}"


def verification_prediction_from_outputs(
    output: Any,
    *,
    first_pass_status: str | None = None,
    revision_count: int = 0,
    claim_key: Callable[[Mapping[str, Any]], str | None] = default_claim_key,
) -> VerificationPrediction:
    data = _as_dict(output)
    status = data.get("status")
    if status not in ("PASS", "FAIL", "REVISE"):
        status = "unavailable"
    checks = [
        VerificationCheckPrediction(
            check=str(row.get("check")),
            status=row.get("status"),
        )
        for row in _list(data.get("checks"))
        if isinstance(row, dict)
        and isinstance(row.get("check"), str)
        and row.get("status") in ("PASS", "FAIL", "REVISE")
    ]
    reported = [
        key
        for key in (claim_key(row) for row in _list(data.get("unsupported_claims")))
        if isinstance(key, str) and key
    ]
    first = first_pass_status if first_pass_status in ("PASS", "FAIL", "REVISE") else None
    return VerificationPrediction(
        status=status,
        checks=checks,
        reported_claim_ids=list(dict.fromkeys(reported)),
        first_pass_status=first,
        revision_count=max(0, revision_count),
    )


def case_from_analysis_record(
    record: Mapping[str, Any],
    *,
    config_id: str,
    references: EvaluationReferences | None = None,
    first_pass_status: str | None = None,
    revision_count: int | None = None,
    claim_key: Callable[[Mapping[str, Any]], str | None] = default_claim_key,
    dataset_type: str | None = None,
    split: str | None = None,
) -> EvaluationCase:
    """Build one evaluation case from a Step 16 ``analysis_log/1.0`` record.

    The record does not store the experimental configuration, latency, or token
    usage, so ``config_id`` is required and runtime metrics remain ``None``
    rather than being inferred.
    """
    outputs = record.get("agent_outputs") if isinstance(record.get("agent_outputs"), dict) else {}
    final = record.get("final_result") if isinstance(record.get("final_result"), dict) else {}
    final_status = final.get("final_status")
    run_status = "failed" if final_status == "ERROR" else "completed"

    recommendation = None
    if outputs.get("career_recommendation") is not None:
        recommendation = recommendation_prediction_from_outputs(outputs["career_recommendation"])

    skill_gap = None
    if outputs.get("skill_gap") is not None:
        skill_gap = skill_gap_prediction_from_outputs(outputs["skill_gap"])

    roadmap = None
    if outputs.get("roadmap") is not None:
        roadmap = roadmap_prediction_from_outputs(outputs["roadmap"])

    recorded_revision = record.get("revision_count")
    revisions = (
        revision_count
        if isinstance(revision_count, int) and not isinstance(revision_count, bool)
        else recorded_revision if isinstance(recorded_revision, int) else 0
    )
    verification = verification_prediction_from_outputs(
        record.get("verification_result"),
        first_pass_status=first_pass_status,
        revision_count=revisions,
        claim_key=claim_key,
    )

    user_id = record.get("user_profile_id")
    profile_id = str(user_id) if user_id is not None else "unavailable"

    return EvaluationCase(
        profile_id=profile_id,
        config_id=config_id,  # type: ignore[arg-type]
        dataset_type=dataset_type,  # type: ignore[arg-type]
        split=split,  # type: ignore[arg-type]
        run_status=run_status,
        references=references,
        recommendation=recommendation,
        skill_gap=skill_gap,
        roadmap=roadmap,
        verification=verification,
        operational={"revision_count": revisions},
    )


def reference_skill_status(reference: Any) -> dict[str, str]:
    """Return ``skill_id -> status`` from a ``SkillGapReference`` or mapping."""
    if reference is None:
        return {}
    labels = getattr(reference, "required_skill_status", None)
    if labels is None and isinstance(reference, Mapping):
        labels = reference.get("required_skill_status", [])
    result: dict[str, str] = {}
    for label in labels or []:
        if isinstance(label, Mapping):
            skill_id, status = label.get("skill_id"), label.get("status")
        else:
            skill_id, status = getattr(label, "skill_id", None), getattr(label, "status", None)
        if isinstance(skill_id, str) and isinstance(status, str):
            result[skill_id] = status
    return result


def reference_status_from_keys(keys: Iterable[str]) -> dict[str, str]:
    """Compatibility helper for harness-supplied status mappings."""
    return {str(key): "missing" for key in keys}
