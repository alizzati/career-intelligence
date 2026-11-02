"""Per-CV diagnostic trace (``diagnostic_trace/1.0``).

Design rules
------------
* Derive only. Every value comes from an object the real pipeline already produced
  (workflow state, agent results, the Step 16 log, recorder entries, API response).
  Nothing is recomputed, re-ranked, or "improved".
* Never store raw CV text, prompt text, LLM response text, uploaded file names, or
  evidence URLs. Every string goes through the existing inspection sanitizer
  (``app.inspection.recorder.clean_str``), which applies the project PII/secret
  redactor and a length cap.
* Absent information is reported as ``unavailable (...)`` or ``None`` with an
  explicit entry in ``unavailable_fields``. It is never estimated.
* The four frozen skill-gap categories are copied verbatim; no priority, tier, or
  target-proficiency field is introduced anywhere in this module.
"""
from __future__ import annotations

import dataclasses
from collections import Counter
from typing import Any

from app.inspection.recorder import clean_str, to_jsonable
from app.services.analysis_log_service import KB_VERSION, PROMPT_CATALOG_VERSION

TRACE_SCHEMA_VERSION = "diagnostic_trace/1.0"
MANIFEST_SCHEMA_VERSION = "diagnostic_manifest/1.0"

STAGE_ORDER = (
    "extraction",
    "profile",
    "okb_retrieval",
    "career_fit",
    "skill_gap",
    "roadmap",
    "verification",
    "final",
)
STAGE_STATUSES = ("ok", "failed", "skipped", "not_reached")

# The frozen skill-gap contract (AGENTS.md 6.1). Copied, never extended.
SKILL_GAP_CATEGORIES = (
    "matched_evidenced",
    "matched_claimed_only",
    "missing",
    "unmatched_user_claims",
)

GAP_COUNTER_COLUMNS = {
    "matched_evidenced": "gap_matched_evidenced_count",
    "matched_claimed_only": "gap_matched_claimed_only_count",
    "missing": "gap_missing_count",
    "unmatched_user_claims": "gap_unmatched_user_claims_count",
}

UNAVAILABLE_TOKENS = "unavailable (the LLM client interface exposes no token usage)"
UNAVAILABLE_COST = "unavailable (the LLM client interface performs no cost accounting)"
UNAVAILABLE_MODEL_VERSION = (
    "unavailable (the LLM client exposes no separate model version; "
    "the model identifier is recorded instead)"
)
UNAVAILABLE_SAMPLING = (
    "unavailable (temperature/top_p/top_k/seed are not passed through the "
    "LLM client interface)"
)
UNAVAILABLE_KB_VERSION = KB_VERSION

UNAVAILABLE_FIELDS = (
    {"field": "llm_calls[].prompt_tokens", "reason": UNAVAILABLE_TOKENS},
    {"field": "llm_calls[].completion_tokens", "reason": UNAVAILABLE_TOKENS},
    {"field": "llm_calls[].total_tokens", "reason": UNAVAILABLE_TOKENS},
    {"field": "llm_calls[].cost_usd", "reason": UNAVAILABLE_COST},
    {"field": "run.model_version", "reason": UNAVAILABLE_MODEL_VERSION},
    {"field": "run.generation_settings", "reason": UNAVAILABLE_SAMPLING},
    {"field": "run.kb_version", "reason": UNAVAILABLE_KB_VERSION},
    {
        "field": "cv.original_filename",
        "reason": "deliberately not recorded: the upload uses a neutral <cv_id>.<ext> name",
    },
    {
        "field": "stages.extraction.raw_text",
        "reason": "deliberately not recorded: only counts, format and hashes are persisted",
    },
)

CSV_COLUMNS = (
    "run_id",
    "cv_id",
    "cv_sha256",
    "file_format",
    "file_size_bytes",
    "pdf_page_count",
    "extraction_status",
    "extraction_error_code",
    "http_status",
    "final_status",
    "verified",
    "target_career_id",
    "revision_count",
    "revision_limit",
    "profile_agent_executed",
    "profile_skills_persisted",
    "profile_evidence_persisted",
    "skills_extracted_count",
    "skills_normalized_count",
    "skills_unmatched_count",
    "recommendations_count",
    "top1_career_id",
    "top1_fit_score",
    "top2_career_id",
    "top2_fit_score",
    "target_fit_score",
    "target_rank",
    "gap_matched_evidenced_count",
    "gap_matched_claimed_only_count",
    "gap_missing_count",
    "gap_unmatched_user_claims_count",
    "gap_narrative_source",
    "roadmap_items_count",
    "roadmap_narrative_source",
    "verification_status",
    "verification_checks_total",
    "verification_checks_failed",
    "verification_unsupported_claims_count",
    "verification_required_revision_count",
    "analysis_id",
    "model",
    "model_version",
    "sdk_version",
    "prompt_catalog_version",
    "kb_version",
    "llm_mode",
    "total_llm_calls",
    "total_duration_ms",
    "stage_errors",
    "trace_path",
    "analysis_log_path",
)


# --------------------------------------------------------------------------- helpers
def _dump(value: Any) -> Any:
    """Best-effort plain-data copy of a pydantic model / dataclass / container."""
    if value is None:
        return None
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_dump(item) for item in value]
    if isinstance(value, dict):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return model_dump()
        except Exception:  # pragma: no cover - defensive only
            return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        try:
            return dataclasses.asdict(value)
        except Exception:  # pragma: no cover - defensive only
            return value
    return value


def _text(value: Any, limit: int = 300) -> str | None:
    if value is None:
        return None
    return clean_str(value if isinstance(value, str) else str(value), limit)


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float(value: Any) -> float | None:
    return value if isinstance(value, float) and value == value else None


def _rows(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _dig(obj: Any, *path: str, default: Any = None) -> Any:
    current = obj
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def stage(
    status: str,
    *,
    payload: Any = None,
    error: dict | None = None,
    started_at: str | None = None,
    duration_ms: float | None = None,
    notes: list[str] | None = None,
) -> dict:
    if status not in STAGE_STATUSES:
        raise ValueError(f"unknown stage status: {status!r}")
    return {
        "status": status,
        "started_at": started_at,
        "duration_ms": duration_ms,
        "error": error,
        "notes": notes or [],
        "payload": payload,
    }


def safe_errors(errors: Any) -> list[dict]:
    """Metadata only: never persists an exception message (mirrors the recorder)."""
    safe: list[dict] = []
    for error in errors if isinstance(errors, list) else []:
        if not isinstance(error, dict):
            continue
        item = {
            key: clean_str(error[key], 80)
            for key in ("stage", "error_type")
            if isinstance(error.get(key), str)
        }
        for key in ("code", "status"):
            value = error.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                item[key] = value
        safe.append(item)
    return safe


# --------------------------------------------------------------------------- stages
def build_extraction_stage(
    *,
    document: Any,
    redaction: Any,
    http_status: int | None,
    error_code: str | None = None,
    error_message: str | None = None,
    duration_ms: float | None = None,
) -> dict:
    if document is None:
        return stage(
            "failed" if http_status is not None and http_status != 200 else "skipped",
            error={"http_status": http_status, "code": error_code, "message": _text(error_message)},
            duration_ms=duration_ms,
            notes=["No document metadata was produced, so text extraction did not complete."],
        )
    data = _dump(document) or {}
    redaction_data = _dump(redaction) or {}
    return stage(
        "ok",
        duration_ms=duration_ms,
        payload={
            "format": _text(data.get("format"), 20),
            "size_bytes": _int(data.get("size_bytes")),
            "page_count": _int(data.get("page_count")),
            "character_count": _int(data.get("character_count")),
            "replacement_count": _int(redaction_data.get("replacement_count")),
            "detected_types": [
                item for item in (redaction_data.get("detected_types") or []) if isinstance(item, str)
            ],
            "raw_text_persisted": False,
        },
    )


def build_profile_stage(profile_result: Any, *, duration_ms: float | None = None) -> dict:
    data = _dump(profile_result)
    if not isinstance(data, dict):
        return stage(
            "not_reached",
            notes=["The Profile Agent did not return a result (it did not run, or it failed)."],
        )
    extracted = data.get("extracted") if isinstance(data.get("extracted"), dict) else {}

    skills = _rows(extracted.get("skills"))
    evidence = _rows(extracted.get("evidence"))

    normalizations: list[dict] = []
    for item in data.get("normalizations") or []:
        if not isinstance(item, dict):
            continue
        result = item.get("result") if isinstance(item.get("result"), dict) else {}
        normalizations.append(
            {
                "claimed_skill": _text(item.get("claimed_skill")),
                "skill_id": result.get("skill_id"),
                "normalized_name": _text(result.get("normalized_name"), 120),
                "method": _text(result.get("method"), 40),
                "score": result.get("score"),
                "matched": result.get("skill_id") is not None,
            }
        )

    skill_rows = []
    for index, claim in enumerate(skills):
        # profile_agent appends one normalization per skill, in list order.
        match = normalizations[index] if index < len(normalizations) else None
        skill_rows.append(
            {
                "claimed_skill": _text(claim.get("claimed_skill")),
                "proficiency": _text(claim.get("proficiency"), 60),
                "llm_candidate_skill_id": claim.get("candidate_skill_id"),
                "matched_skill_id": match["skill_id"] if match else None,
                "normalized_name": match["normalized_name"] if match else None,
                "match_method": match["method"] if match else None,
                "match_score": match["score"] if match else None,
                "matched": match["matched"] if match else None,
            }
        )

    payload = {
        "counts": {
            "skills_extracted": len(skills),
            "evidence_extracted": len(evidence),
            "education_extracted": len(_rows(extracted.get("education"))),
            "experience_extracted": len(_rows(extracted.get("experience"))),
            "projects_extracted": len(_rows(extracted.get("projects"))),
            "certifications_extracted": len(_rows(extracted.get("certifications"))),
            "skills_persisted": _int(data.get("skills_persisted")),
            "evidence_persisted": _int(data.get("evidence_persisted")),
            "skills_normalized": sum(1 for item in normalizations if item["matched"]),
            "skills_unmatched": sum(1 for item in normalizations if not item["matched"]),
        },
        "match_methods": dict(Counter(item["method"] for item in normalizations if item["method"])),
        "skills": skill_rows,
        "normalizations": normalizations,
        "evidence": [
            {
                "claimed_skill": _text(item.get("claimed_skill")),
                "evidence_type": _text(item.get("evidence_type"), 40),
                "description": _text(item.get("description")),
                # A URL can carry an account handle; only its presence is recorded.
                "url_present": bool(item.get("url")),
            }
            for item in evidence
        ],
        "education": [
            {
                "institution": _text(item.get("institution"), 160),
                "degree": _text(item.get("degree"), 120),
                "field_of_study": _text(item.get("field_of_study"), 120),
                "start_date": _text(item.get("start_date"), 40),
                "end_date": _text(item.get("end_date"), 40),
                "description": _text(item.get("description")),
            }
            for item in _rows(extracted.get("education"))
        ],
        "experience": [
            {
                "company": _text(item.get("company"), 160),
                "role_title": _text(item.get("role_title"), 160),
                "employment_type": _text(item.get("employment_type"), 60),
                "start_date": _text(item.get("start_date"), 40),
                "end_date": _text(item.get("end_date"), 40),
                "description": _text(item.get("description")),
            }
            for item in _rows(extracted.get("experience"))
        ],
        "projects": [
            {
                "title": _text(item.get("title"), 160),
                "role": _text(item.get("role"), 120),
                "description": _text(item.get("description")),
                "url_present": bool(item.get("url")),
            }
            for item in _rows(extracted.get("projects"))
        ],
        "certifications": [
            {
                "name": _text(item.get("name"), 160),
                "issuer": _text(item.get("issuer"), 160),
                "issue_date": _text(item.get("issue_date"), 40),
                "expiry_date": _text(item.get("expiry_date"), 40),
                "credential_url_present": bool(item.get("credential_url")),
            }
            for item in _rows(extracted.get("certifications"))
        ],
    }
    return stage("ok", duration_ms=duration_ms, payload=payload)


def _requirement_row(item: Any) -> dict:
    skill = getattr(item, "skill", None)
    return {
        "skill_id": getattr(skill, "skill_id", None),
        "canonical_name": _text(getattr(skill, "canonical_name", None), 120),
        "relationship_id": getattr(item, "relationship_id", None),
        "evidence_class": _text(getattr(item, "evidence_class", None), 40),
        "confidence": _text(getattr(item, "confidence", None), 40),
        "mapping_method": _text(getattr(item, "mapping_method", None), 60),
        "evidence_source_text": _text(getattr(item, "evidence_source_text", None), 240),
    }


def build_okb_retrieval_stage(raw_io: Any, *, duration_ms: float | None = None) -> dict:
    """Rebuild the OKB requirements from the agent's OWN retrieval calls.

    ``raw_io`` is the recorder's untouched copy of every service read, so the
    requirements below are exactly what the agents consulted -- not a fresh read.
    """
    by_career: dict[str, dict] = {}
    careers_seen: list[str] = []
    for entry in raw_io if isinstance(raw_io, list) else []:
        if not isinstance(entry, dict) or entry.get("nested"):
            continue
        function = entry.get("function")
        result = entry.get("result")
        if function == "get_all_careers" and isinstance(result, list):
            for career in result:
                career_id = getattr(career, "career_id", None)
                if isinstance(career_id, str) and career_id not in careers_seen:
                    careers_seen.append(career_id)
        elif function == "get_career_skills":
            args = entry.get("args") or ()
            career_id = args[0] if args else None
            if not isinstance(career_id, str):
                continue
            record = by_career.setdefault(
                career_id, {"career_id": career_id, "read_count": 0, "requirements": []}
            )
            record["read_count"] += 1
            record["requirements"] = [
                _requirement_row(item) for item in (result or []) if item is not None
            ]

    if not by_career:
        return stage(
            "not_reached",
            duration_ms=duration_ms,
            notes=["No get_career_skills read was observed, so no OKB requirements were captured."],
        )

    careers = [by_career[key] for key in sorted(by_career)]
    return stage(
        "ok",
        duration_ms=duration_ms,
        payload={
            "source": "workflow_instrumentation (the agents' own retrieval calls)",
            "careers_read": careers_seen,
            "career_count": len(careers),
            "requirement_count": sum(len(item["requirements"]) for item in careers),
            "careers": careers,
        },
    )


def build_career_fit_stage(
    recommendations: Any,
    *,
    computations: Any = None,
    duration_ms: float | None = None,
) -> dict:
    items = _rows(_dump(recommendations) or [])
    if not items:
        return stage(
            "not_reached",
            duration_ms=duration_ms,
            notes=["The Career Recommendation Agent returned no canonical careers."],
        )
    ranked = []
    for index, item in enumerate(items, start=1):
        ranked.append(
            {
                "rank": index,
                "career_id": item.get("career_id"),
                "canonical_name": _text(item.get("canonical_name"), 160),
                "domain": _text(item.get("domain"), 80),
                "fit_score": item.get("fit_score"),
                "score_breakdown": item.get("score_breakdown"),
                "matched_skills": item.get("matched_skills"),
                "claimed_only_skills": item.get("claimed_only_skills"),
                "missing_skills_preview": item.get("missing_skills_preview"),
                "reasoning": _text(item.get("reasoning")),
                "reasoning_source": _text(item.get("reasoning_source"), 40),
            }
        )
    calls = [
        {
            "seq": entry.get("seq"),
            "stage": entry.get("stage"),
            "called_from": entry.get("called_from"),
            "fit_score": entry.get("fit_score"),
            "total_weight": entry.get("total_weight"),
            "total_contribution": entry.get("total_contribution"),
            "required_skill_count": len(entry.get("required_ids") or []),
        }
        for entry in (computations if isinstance(computations, list) else [])
        if isinstance(entry, dict)
    ]
    return stage(
        "ok",
        duration_ms=duration_ms,
        payload={
            "career_count": len(ranked),
            "ranked": ranked,
            "compute_career_fit_calls": calls,
            "compute_career_fit_call_count": len(calls),
            "note": (
                "Scores are the existing compute_career_fit() output, copied as produced. "
                "This trace never recomputes career fit."
            ),
        },
    )


def build_skill_gap_stage(skill_gap: Any, *, duration_ms: float | None = None) -> dict:
    data = _dump(skill_gap)
    if not isinstance(data, dict):
        return stage(
            "not_reached",
            duration_ms=duration_ms,
            notes=["No Skill-Gap Agent result exists (the stage did not run, or it failed)."],
        )
    deterministic = data.get("skill_gap") if isinstance(data.get("skill_gap"), dict) else {}
    categories = {}
    for name in SKILL_GAP_CATEGORIES:
        rows = _rows(deterministic.get(name))
        if name == "unmatched_user_claims":
            categories[name] = [
                {
                    "user_skill_id": row.get("user_skill_id"),
                    "claimed_skill": _text(row.get("claimed_skill")),
                    "proficiency": _text(row.get("proficiency"), 60),
                    "evidence_status": _text(row.get("evidence_status"), 40),
                    "evidence_count": _int(row.get("evidence_count")),
                }
                for row in rows
            ]
        else:
            categories[name] = [
                {
                    "skill_id": row.get("skill_id"),
                    "canonical_name": _text(row.get("canonical_name"), 120),
                    "status": row.get("status"),
                    "evidence_class": _text(row.get("evidence_class"), 40),
                    "kb_confidence": _text(row.get("kb_confidence"), 40),
                    "weight": row.get("weight"),
                    "contribution": row.get("contribution"),
                    "matched_user_claim": row.get("matched_user_claim"),
                }
                for row in rows
            ]
    return stage(
        "ok",
        duration_ms=duration_ms,
        payload={
            "career_id": deterministic.get("career_id"),
            "canonical_name": _text(deterministic.get("canonical_name"), 160),
            "fit_score": deterministic.get("fit_score"),
            "total_weight": deterministic.get("total_weight"),
            "total_contribution": deterministic.get("total_contribution"),
            "score_breakdown": deterministic.get("score_breakdown"),
            "categories": categories,
            "counts": {name: len(categories[name]) for name in SKILL_GAP_CATEGORIES},
            "narrative": data.get("narrative"),
            "narrative_source": _text(data.get("narrative_source"), 40),
            "validation_notes": data.get("validation_notes") or [],
            "llm_error_present": bool(data.get("llm_error")),
            "note": (
                "The four categories are copied verbatim from the deterministic engine. "
                "No priority, tier, or target proficiency is added."
            ),
        },
    )


def build_roadmap_stage(roadmap: Any, *, duration_ms: float | None = None) -> dict:
    data = _dump(roadmap)
    if not isinstance(data, dict):
        return stage(
            "not_reached",
            duration_ms=duration_ms,
            notes=["No roadmap result exists (the stage did not run, or it failed)."],
        )
    items = _rows(data.get("items"))
    return stage(
        "ok",
        duration_ms=duration_ms,
        payload={
            "items": [
                {
                    "skill_id": item.get("skill_id"),
                    "canonical_name": _text(item.get("canonical_name"), 120),
                    "gap_status": item.get("gap_status"),
                    "evidence_class": _text(item.get("evidence_class"), 40),
                    "kb_confidence": _text(item.get("kb_confidence"), 40),
                    "knowledge_base_basis": _text(item.get("knowledge_base_basis"), 240),
                    "learning_action": item.get("learning_action"),
                }
                for item in items
            ],
            "item_count": len(items),
            "covered_skill_ids": [item.get("skill_id") for item in items],
            "summary": _text(data.get("summary"), 600),
            "narrative_source": _text(data.get("narrative_source"), 40),
            "llm_error_present": bool(data.get("llm_error")),
        },
    )


def build_verification_stage(
    verification: Any,
    *,
    revision_count: int | None = None,
    revision_limit: int | None = None,
    duration_ms: float | None = None,
) -> dict:
    data = _dump(verification)
    if not isinstance(data, dict):
        return stage(
            "not_reached",
            duration_ms=duration_ms,
            notes=["The Verification Agent did not produce a result."],
        )
    checks = _rows(data.get("checks"))
    claims = _rows(data.get("unsupported_claims"))
    revisions = data.get("required_revision") or []
    return stage(
        "ok",
        duration_ms=duration_ms,
        payload={
            "status": data.get("status"),
            "checks": checks,
            "unsupported_claims": claims,
            "required_revision": revisions,
            "counts": {
                "checks_total": len(checks),
                "checks_passed": sum(1 for item in checks if item.get("status") == "PASS"),
                "checks_failed": sum(1 for item in checks if item.get("status") == "FAIL"),
                "checks_revise": sum(1 for item in checks if item.get("status") == "REVISE"),
                "unsupported_claims": len(claims),
                "required_revision": len(revisions),
            },
            "llm_error_present": bool(data.get("llm_error")),
            "revision_count": revision_count,
            "revision_limit": revision_limit,
            "note": "Findings are copied as reported; no output was rewritten by this trace.",
        },
    )


def build_final_stage(
    *,
    final_status: str | None,
    verified: Any,
    target_career_id: str | None,
    revision_count: int | None,
    revision_limit: int | None,
    revision_target: str | None,
    last_stage: str | None,
    errors: Any,
    ranked: Any,
    duration_ms: float | None = None,
) -> dict:
    ranking = _rows(_dump(ranked) or [])
    target_rank = target_fit = None
    for index, item in enumerate(ranking, start=1):
        if item.get("career_id") == target_career_id:
            target_rank, target_fit = index, item.get("fit_score")
            break
    return stage(
        "ok" if final_status else "not_reached",
        duration_ms=duration_ms,
        payload={
            "final_status": final_status,
            "verified": verified,
            "target_career_id": target_career_id,
            "revision_count": revision_count,
            "revision_limit": revision_limit,
            "revision_target": revision_target,
            "last_stage": last_stage,
            "errors": safe_errors(errors),
            "target_rank": target_rank,
            "target_fit_score": target_fit,
            "top1_career_id": ranking[0].get("career_id") if len(ranking) >= 1 else None,
            "top1_fit_score": ranking[0].get("fit_score") if len(ranking) >= 1 else None,
            "top2_career_id": ranking[1].get("career_id") if len(ranking) >= 2 else None,
            "top2_fit_score": ranking[1].get("fit_score") if len(ranking) >= 2 else None,
        },
    )


# --------------------------------------------------------------------------- recorder
def build_llm_calls(recorder: Any) -> dict:
    entries = getattr(recorder, "llm", []) or []
    calls = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        calls.append(
            {
                "seq": entry.get("seq"),
                "stage": entry.get("stage"),
                "prompt_id": entry.get("prompt_id"),
                "system_prompt_sha256": entry.get("system_prompt_sha256"),
                "prompt_sha256": entry.get("prompt_sha256"),
                "prompt_chars": entry.get("prompt_chars"),
                "max_tokens": entry.get("max_tokens"),
                "max_tokens_source": entry.get("max_tokens_source"),
                "duration_ms": entry.get("duration_ms"),
                "response": entry.get("response"),
                "error": entry.get("error"),
                "prompt_tokens": UNAVAILABLE_TOKENS,
                "completion_tokens": UNAVAILABLE_TOKENS,
                "total_tokens": UNAVAILABLE_TOKENS,
                "cost_usd": UNAVAILABLE_COST,
            }
        )
    durations = [item["duration_ms"] for item in calls if isinstance(item["duration_ms"], (int, float))]
    return {
        "call_count": len(calls),
        "total_duration_ms": round(sum(durations), 1) if durations else None,
        "by_prompt": dict(Counter(item["prompt_id"] for item in calls if item["prompt_id"])),
        "calls": calls,
        "tokens": UNAVAILABLE_TOKENS,
        "cost_usd": UNAVAILABLE_COST,
    }


def build_agent_runs(recorder: Any) -> list[dict]:
    runs = []
    for entry in getattr(recorder, "agent_runs", []) or []:
        if not isinstance(entry, dict):
            continue
        output = entry.get("raw_output")
        runs.append(
            {
                "seq": entry.get("seq"),
                "agent": entry.get("agent"),
                "attempt": entry.get("attempt"),
                "duration_ms": entry.get("duration_ms"),
                "error": entry.get("error"),
                "produced_output": output is not None,
                "output_type": type(output).__name__ if output is not None else None,
            }
        )
    return runs


# --------------------------------------------------------------------------- assemble
def build_trace(
    *,
    run: dict,
    cv: dict,
    analysis: dict,
    stages: dict,
    recorder: Any,
    warnings: list[str] | None = None,
    privacy: dict | None = None,
    consistency_observations: list[dict] | None = None,
) -> dict:
    """Assemble the diagnostic document. Nothing is recomputed here."""
    ordered_stages = {name: stages.get(name) for name in STAGE_ORDER}
    for name, value in stages.items():
        ordered_stages.setdefault(name, value)
    for name, value in ordered_stages.items():
        if value is None:
            ordered_stages[name] = stage("not_reached")

    privacy_block = {
        "raw_cv_text_persisted": False,
        "raw_prompt_persisted": False,
        "raw_llm_response_persisted": False,
        "original_filename_persisted": False,
        "evidence_urls_persisted": False,
        "pii_redaction_applied": True,
        "redaction_helper": "app.inspection.recorder.clean_str",
        "artifact_location": "diagnostic results directory (never the formal experiment results)",
    }
    if privacy:
        privacy_block.update(privacy)

    trace = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "run": run,
        "cv": cv,
        "analysis": analysis,
        "stages": ordered_stages,
        "llm_calls": build_llm_calls(recorder),
        "node_events": list(getattr(recorder, "node_events", []) or []),
        "agent_runs": build_agent_runs(recorder),
        "warnings": [
            clean_str(item, 200) for item in (warnings or []) + list(getattr(recorder, "warnings", []) or [])
            if isinstance(item, str)
        ],
        "privacy": privacy_block,
        "unavailable_fields": [dict(item) for item in UNAVAILABLE_FIELDS],
        "consistency_note": (
            "consistency_observations is a diagnostic cross-check only. It is NOT the Step 12 "
            "verification result and never changes any stage output."
        ),
        "consistency_observations": consistency_observations or [],
    }
    return to_jsonable(trace, str_limit=600)


def observe_consistency(*, analysis: dict, stages: dict) -> list[dict]:
    """Read-only cross-checks between stages. Observations never modify anything."""
    observations: list[dict] = []

    def add(check: str, result: str, detail: Any) -> None:
        observations.append(
            {"check": check, "result": result, "detail": detail, "observation_only": True}
        )

    response_status = (analysis or {}).get("response_final_status")
    final_payload = _dig(stages, "final", "payload", default={}) or {}
    state_status = final_payload.get("final_status")
    if response_status and state_status:
        add(
            "api_response_matches_workflow_state",
            "PASS" if response_status == state_status else "WARN",
            {"api_response": response_status, "workflow_state": state_status},
        )

    okb = _dig(stages, "okb_retrieval", "payload", default={}) or {}
    fit = _dig(stages, "career_fit", "payload", default={}) or {}
    okb_count, fit_count = okb.get("career_count"), fit.get("career_count")
    if isinstance(okb_count, int) and isinstance(fit_count, int):
        add(
            "every_okb_career_was_scored",
            "PASS" if okb_count == fit_count else "WARN",
            {"okb_careers": okb_count, "scored_careers": fit_count},
        )

    gap = _dig(stages, "skill_gap", "payload", default={}) or {}
    counts = gap.get("counts") or {}
    if counts and isinstance(okb_count, int):
        classified = sum(
            counts.get(name, 0) for name in ("matched_evidenced", "matched_claimed_only", "missing")
        )
        target_id = gap.get("career_id")
        requirements = None
        for career in okb.get("careers") or []:
            if isinstance(career, dict) and career.get("career_id") == target_id:
                requirements = len(career.get("requirements") or [])
                break
        if requirements is not None:
            add(
                "skill_gap_covers_every_required_skill",
                "PASS" if classified == requirements else "WARN",
                {"classified": classified, "required": requirements, "career_id": target_id},
            )

    roadmap = _dig(stages, "roadmap", "payload", default={}) or {}
    if counts and roadmap.get("covered_skill_ids") is not None:
        allowed = set()
        for name in ("matched_claimed_only", "missing"):
            for row in (gap.get("categories") or {}).get(name) or []:
                if isinstance(row, dict) and row.get("skill_id"):
                    allowed.add(row["skill_id"])
        covered = {sid for sid in roadmap.get("covered_skill_ids") or [] if sid}
        add(
            "roadmap_covers_only_outstanding_skills",
            "PASS" if covered <= allowed else "WARN",
            {"outside_expected_set": sorted(covered - allowed), "items": len(covered)},
        )

    verification = _dig(stages, "verification", "payload", default={}) or {}
    if state_status and verification.get("status"):
        if state_status == "VERIFIED" and verification.get("status") != "PASS":
            add(
                "verified_status_requires_pass_verification",
                "WARN",
                {"final_status": state_status, "verification_status": verification.get("status")},
            )

    return observations


# --------------------------------------------------------------------------- CSV
def build_csv_row(trace: dict) -> dict:
    """One flat row per CV. Missing stages produce None, never a guessed value."""
    run = trace.get("run") or {}
    cv = trace.get("cv") or {}
    analysis = trace.get("analysis") or {}
    stages = trace.get("stages") or {}

    extraction = stages.get("extraction") or {}
    extraction_payload = extraction.get("payload") or {}
    profile = stages.get("profile") or {}
    profile_counts = _dig(profile, "payload", "counts", default={}) or {}
    fit = _dig(stages, "career_fit", "payload", default={}) or {}
    gap = _dig(stages, "skill_gap", "payload", default={}) or {}
    gap_counts = gap.get("counts") or {}
    roadmap = _dig(stages, "roadmap", "payload", default={}) or {}
    verification = _dig(stages, "verification", "payload", default={}) or {}
    verification_counts = verification.get("counts") or {}
    final = _dig(stages, "final", "payload", default={}) or {}

    stage_errors = []
    for name in STAGE_ORDER:
        entry = stages.get(name) or {}
        if entry.get("status") == "failed":
            error = entry.get("error") or {}
            stage_errors.append(f"{name}:{error.get('code') or error.get('error_type') or 'failed'}")

    row = {
        "run_id": run.get("run_id"),
        "cv_id": cv.get("cv_id"),
        "cv_sha256": cv.get("sha256"),
        "file_format": cv.get("format"),
        "file_size_bytes": cv.get("size_bytes"),
        "pdf_page_count": extraction_payload.get("page_count"),
        "extraction_status": extraction.get("status"),
        "extraction_error_code": _dig(extraction, "error", "code"),
        "http_status": analysis.get("http_status"),
        "final_status": final.get("final_status"),
        "verified": final.get("verified"),
        "target_career_id": final.get("target_career_id"),
        "revision_count": final.get("revision_count"),
        "revision_limit": final.get("revision_limit"),
        "profile_agent_executed": profile.get("status") == "ok",
        "profile_skills_persisted": profile_counts.get("skills_persisted"),
        "profile_evidence_persisted": profile_counts.get("evidence_persisted"),
        "skills_extracted_count": profile_counts.get("skills_extracted"),
        "skills_normalized_count": profile_counts.get("skills_normalized"),
        "skills_unmatched_count": profile_counts.get("skills_unmatched"),
        "recommendations_count": fit.get("career_count"),
        "top1_career_id": final.get("top1_career_id"),
        "top1_fit_score": final.get("top1_fit_score"),
        "top2_career_id": final.get("top2_career_id"),
        "top2_fit_score": final.get("top2_fit_score"),
        "target_fit_score": final.get("target_fit_score"),
        "target_rank": final.get("target_rank"),
        "gap_narrative_source": gap.get("narrative_source"),
        "roadmap_items_count": roadmap.get("item_count"),
        "roadmap_narrative_source": roadmap.get("narrative_source"),
        "verification_status": verification.get("status"),
        "verification_checks_total": verification_counts.get("checks_total"),
        "verification_checks_failed": verification_counts.get("checks_failed"),
        "verification_unsupported_claims_count": verification_counts.get("unsupported_claims"),
        "verification_required_revision_count": verification_counts.get("required_revision"),
        "analysis_id": analysis.get("analysis_id"),
        "model": run.get("model"),
        "model_version": run.get("model_version"),
        "sdk_version": run.get("sdk_version"),
        "prompt_catalog_version": run.get("prompt_catalog_version"),
        "kb_version": run.get("kb_version"),
        "llm_mode": run.get("llm_mode"),
        "total_llm_calls": _dig(trace, "llm_calls", "call_count"),
        "total_duration_ms": analysis.get("duration_ms"),
        "stage_errors": ";".join(stage_errors) or None,
        "trace_path": cv.get("trace_path"),
        "analysis_log_path": analysis.get("analysis_log_path"),
    }
    for name, column in GAP_COUNTER_COLUMNS.items():
        row[column] = gap_counts.get(name) if gap_counts else None
    return {column: row.get(column) for column in CSV_COLUMNS}


def prompt_catalog_version() -> str:
    return PROMPT_CATALOG_VERSION


__all__ = [
    "CSV_COLUMNS",
    "GAP_COUNTER_COLUMNS",
    "MANIFEST_SCHEMA_VERSION",
    "SKILL_GAP_CATEGORIES",
    "STAGE_ORDER",
    "STAGE_STATUSES",
    "TRACE_SCHEMA_VERSION",
    "UNAVAILABLE_COST",
    "UNAVAILABLE_FIELDS",
    "UNAVAILABLE_KB_VERSION",
    "UNAVAILABLE_MODEL_VERSION",
    "UNAVAILABLE_SAMPLING",
    "UNAVAILABLE_TOKENS",
    "build_agent_runs",
    "build_career_fit_stage",
    "build_csv_row",
    "build_extraction_stage",
    "build_final_stage",
    "build_llm_calls",
    "build_okb_retrieval_stage",
    "build_profile_stage",
    "build_roadmap_stage",
    "build_skill_gap_stage",
    "build_trace",
    "build_verification_stage",
    "observe_consistency",
    "prompt_catalog_version",
    "safe_errors",
    "stage",
]
