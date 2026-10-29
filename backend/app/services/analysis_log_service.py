"""Privacy-safe per-analysis logging for MASTER_SPEC section 19.

Every analysis that reaches the workflow through the normal API endpoints writes
one JSON record containing the required reproducibility metadata. The record is
derived from the final workflow state and the observed node trace; raw CV text,
raw prompts, raw LLM responses, and exception messages are never stored.

Logging is best-effort: an I/O or serialization problem is reported as a warning
and can never change the analysis response.
"""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import uuid
from importlib import metadata
from pathlib import Path
from typing import Any

from app.agents.career_recommendation_agent import REASONING_SYSTEM_PROMPT
from app.agents.learning_roadmap_agent import ROADMAP_SYSTEM_PROMPT
from app.agents.profile_agent import EXTRACTION_SYSTEM_PROMPT, ProfileAgentResult
from app.agents.skill_gap_agent import NARRATIVE_SYSTEM_PROMPT
from app.agents.verification_agent import SEMANTIC_SYSTEM_PROMPT
from app.inspection.recorder import clean_str, sha256_text, to_jsonable
from app.services.profile_privacy_service import (
    redact_recommendations,
    redact_roadmap,
    redact_skill_gap_analysis,
    redact_verification,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "analysis_log/1.0"
STR_LIMIT = 2000
KB_VERSION = "unavailable (Knowledge Base exposes no version identifier)"
MODEL_VERSION_UNAVAILABLE = (
    "unavailable (LLM client exposes no separate model version; "
    "the model identifier is recorded instead)"
)
DEFAULT_LOG_DIRECTORY = Path(__file__).resolve().parents[2] / "artifacts" / "analysis_logs"
LOG_DIRECTORY_ENV = "CAREER_ANALYSIS_LOG_DIR"

# Workflow nodes that execute one of the five analysis agents.
_AGENT_NODES = {
    "profile_analysis": "profile",
    "career_recommendation": "career_recommendation",
    "skill_gap_analysis": "skill_gap",
    "learning_roadmap": "roadmap",
    "verification": "verification",
}
_AGENT_ATTRIBUTES = (
    "profile_agent",
    "career_recommendation_agent",
    "skill_gap_agent",
    "learning_roadmap_agent",
    "verification_agent",
)
_PROMPT_CATALOG = {
    "profile_extraction": ("profile", EXTRACTION_SYSTEM_PROMPT),
    "career_reasoning": ("career_recommendation", REASONING_SYSTEM_PROMPT),
    "skill_gap_narrative": ("skill_gap", NARRATIVE_SYSTEM_PROMPT),
    "roadmap_summary": ("roadmap", ROADMAP_SYSTEM_PROMPT),
    "verification_semantic": ("verification", SEMANTIC_SYSTEM_PROMPT),
}


# ------------------------------------------------------------------------- helpers
def _timestamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _log_directory() -> Path:
    configured = os.environ.get(LOG_DIRECTORY_ENV, "").strip()
    return Path(configured) if configured else DEFAULT_LOG_DIRECTORY


def _safe_errors(errors: Any) -> list[dict]:
    """Workflow error metadata only: exception messages are never persisted."""
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
            elif (
                key == "status"
                and isinstance(value, str)
                and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", value)
            ):
                item[key] = value
        safe.append(item)
    return safe


def _safe_document(document: Any) -> dict | None:
    """Document metadata only: the uploaded file name is deliberately omitted."""
    if document is None:
        return None
    size = getattr(document, "size_bytes", None)
    pages = getattr(document, "page_count", None)
    characters = getattr(document, "character_count", None)
    fmt = getattr(document, "format", None)
    return {
        "format": clean_str(fmt, 40) if isinstance(fmt, str) else None,
        "size_bytes": size if isinstance(size, int) and not isinstance(size, bool) else None,
        "page_count": pages if isinstance(pages, int) and not isinstance(pages, bool) else None,
        "character_count": (
            characters if isinstance(characters, int) and not isinstance(characters, bool) else None
        ),
    }


def _safe_redaction(redaction: Any) -> dict | None:
    if redaction is None:
        return None
    types = getattr(redaction, "detected_types", ())
    replacements = getattr(redaction, "replacement_count", None)
    return {
        "detected_types": [clean_str(value, 40) for value in types if isinstance(value, str)],
        "replacement_count": (
            replacements
            if isinstance(replacements, int) and not isinstance(replacements, bool)
            else None
        ),
    }


def _llm_client(workflow: Any) -> Any:
    for attribute in _AGENT_ATTRIBUTES:
        agent = getattr(workflow, attribute, None)
        client = getattr(agent, "llm_client", None)
        if client is not None:
            return client
    return None


def _sdk_version() -> str:
    try:
        return metadata.version("google-genai")
    except metadata.PackageNotFoundError:
        return "unavailable (google-genai package metadata not installed)"


def _model_metadata(workflow: Any) -> dict:
    client = _llm_client(workflow)
    if client is None:
        return {
            "model": "unavailable (no LLM client configured)",
            "model_version": "unavailable (no LLM client configured)",
            "provider": "unavailable",
            "sdk_version": "unavailable",
        }

    inner, seen = client, set()
    while inner is not None and id(inner) not in seen and hasattr(inner, "_inner"):
        seen.add(id(inner))
        inner = inner._inner

    name = getattr(inner, "model", None) or getattr(inner, "model_name", None)
    model = (
        clean_str(name, 120)
        if isinstance(name, str) and name.strip()
        else "unavailable (LLM client exposes no model identifier)"
    )
    version = getattr(inner, "model_version", None)
    provider = type(inner).__name__
    return {
        "model": model,
        "model_version": (
            clean_str(version, 120)
            if isinstance(version, str) and version.strip()
            else MODEL_VERSION_UNAVAILABLE
        ),
        "provider": provider,
        "sdk_version": _sdk_version() if provider == "GeminiClient" else "not applicable",
    }


def _prompt_identifiers(agents: list[dict]) -> dict:
    executed = {item["agent"] for item in agents}
    prompts = {
        prompt_id: {"agent": agent, "sha256": sha256_text(prompt)}
        for prompt_id, (agent, prompt) in _PROMPT_CATALOG.items()
        if agent in executed
    }
    return {
        "catalog": "career-intelligence/system-prompts",
        "hash_algorithm": "sha256",
        "prompts": prompts,
    }


def _agents_executed(nodes: list[str], state: dict, source: str) -> list[dict]:
    """One entry per agent, with the number of workflow attempts (revisions)."""
    order: list[str] = []
    attempts: dict[str, int] = {}
    node_for: dict[str, str] = {}
    for node in nodes:
        agent = _AGENT_NODES.get(node)
        if agent is None:
            continue
        # The existing-profile path reuses persisted data in the
        # profile_analysis node; the Profile Agent itself does not run.
        if agent == "profile" and source != "cv_upload":
            continue
        if agent not in attempts:
            order.append(agent)
            node_for[agent] = node
        attempts[agent] = attempts.get(agent, 0) + 1

    if not order:
        # Defensive fallback for callers that do not supply an observer trace.
        if source == "cv_upload" and state.get("profile_result") is not None:
            order.append("profile")
            node_for["profile"] = "profile_analysis"
        for agent, key in (
            ("career_recommendation", "recommendations"),
            ("skill_gap", "skill_gap"),
            ("roadmap", "roadmap"),
            ("verification", "verification"),
        ):
            if state.get(key) is not None:
                order.append(agent)
                node_for[agent] = next(
                    node for node, mapped in _AGENT_NODES.items() if mapped == agent
                )
        attempts = {agent: 1 for agent in order}

    return [
        {"agent": agent, "node": node_for[agent], "attempts": attempts[agent]}
        for agent in order
    ]


def _profile_output(state: dict, source: str, executed: bool) -> dict:
    if source != "cv_upload":
        return {
            "executed": False,
            "reason": "existing profile reused; the Profile Agent was not run",
        }
    result = state.get("profile_result")
    if isinstance(result, ProfileAgentResult) or hasattr(result, "skills_persisted"):
        normalizations = []
        for normalization in getattr(result, "normalizations", []) or []:
            claim = getattr(normalization, "claimed_skill", None)
            outcome = getattr(normalization, "result", None)
            normalizations.append({
                "claim_sha256": sha256_text(claim) if isinstance(claim, str) else None,
                "skill_id": getattr(outcome, "skill_id", None),
                "method": getattr(outcome, "method", None),
                "score": getattr(outcome, "score", None),
            })
        return {
            "executed": True,
            "skills_persisted": getattr(result, "skills_persisted", None),
            "evidence_persisted": getattr(result, "evidence_persisted", None),
            "normalizations": normalizations,
        }
    return {
        "executed": bool(executed),
        "output": "unavailable (Profile Agent produced no result)",
    }


def _agent_outputs(state: dict, source: str, agents: list[dict]) -> dict:
    executed = {item["agent"] for item in agents}
    recommendations = state.get("recommendations")
    skill_gap = state.get("skill_gap")
    roadmap = state.get("roadmap")
    verification = state.get("verification")
    outputs = {
        "profile": _profile_output(state, source, "profile" in executed),
        "career_recommendation": (
            to_jsonable(redact_recommendations(list(recommendations)), str_limit=STR_LIMIT)
            if recommendations is not None else None
        ),
        "skill_gap": (
            to_jsonable(redact_skill_gap_analysis(skill_gap), str_limit=STR_LIMIT)
            if skill_gap is not None else None
        ),
        "roadmap": (
            to_jsonable(redact_roadmap(roadmap), str_limit=STR_LIMIT)
            if roadmap is not None else None
        ),
        "verification": (
            to_jsonable(redact_verification(verification), str_limit=STR_LIMIT)
            if verification is not None else None
        ),
    }
    return outputs


def build_analysis_record(
    *,
    state: dict,
    workflow: Any,
    user_id: int,
    source: str,
    target_career_id: str | None = None,
    nodes_executed: list[str] | None = None,
    document: Any = None,
    redaction: Any = None,
) -> dict:
    """Build the section-19 record. Pure apart from timestamp/UUID generation."""
    nodes = [node for node in (nodes_executed or []) if isinstance(node, str)]
    agents = _agents_executed(nodes, state, source)
    model = _model_metadata(workflow)
    verification = state.get("verification")
    if verification is None:
        verification_result: Any = {
            "status": "unavailable",
            "reason": "verification did not execute",
        }
    else:
        verification_result = to_jsonable(redact_verification(verification), str_limit=STR_LIMIT)

    final_status = state.get("final_status")
    target = state.get("target_career_id", target_career_id)
    record = {
        "schema_version": SCHEMA_VERSION,
        "analysis_id": uuid.uuid4().hex,
        "timestamp": _timestamp(),
        "user_profile_id": user_id,
        "source": source,
        "model": model["model"],
        "model_version": model["model_version"],
        "model_details": {
            "provider": model["provider"],
            "sdk_version": model["sdk_version"],
        },
        "prompt_version_identifier": _prompt_identifiers(agents),
        "kb_version": KB_VERSION,
        "agents_executed": agents,
        "workflow_trace": {"nodes": [clean_str(node, 80) for node in nodes]},
        "agent_outputs": _agent_outputs(state, source, agents),
        "verification_result": verification_result,
        "revision_count": (
            state.get("revision_count")
            if isinstance(state.get("revision_count"), int)
            and not isinstance(state.get("revision_count"), bool)
            else 0
        ),
        "final_result": {
            "final_status": clean_str(final_status, 40) if isinstance(final_status, str) else "unavailable",
            "verified": final_status == "VERIFIED",
            "target_career_id": clean_str(target, 64) if isinstance(target, str) else None,
            "last_stage": (
                clean_str(state.get("stage"), 80)
                if isinstance(state.get("stage"), str) else "unavailable"
            ),
            "errors": _safe_errors(state.get("errors")),
        },
        "input": {
            "source": source,
            "document": _safe_document(document),
            "redaction": _safe_redaction(redaction),
        },
    }
    # Final scrub is idempotent and guarantees every persisted string passes
    # the existing best-effort PII/secret redactor.
    return to_jsonable(record, str_limit=STR_LIMIT)


def _atomic_write(record: dict, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{record['analysis_id']}.json"
    temporary = directory / f".{record['analysis_id']}.{uuid.uuid4().hex}.tmp"
    try:
        temporary.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
    return target


def record_analysis(
    *,
    state: dict,
    workflow: Any,
    user_id: int,
    source: str,
    target_career_id: str | None = None,
    nodes_executed: list[str] | None = None,
    document: Any = None,
    redaction: Any = None,
) -> dict | None:
    """Write one log record. Any failure is reported and swallowed."""
    try:
        record = build_analysis_record(
            state=state,
            workflow=workflow,
            user_id=user_id,
            source=source,
            target_career_id=target_career_id,
            nodes_executed=nodes_executed,
            document=document,
            redaction=redaction,
        )
        _atomic_write(record, _log_directory())
        return record
    except Exception as exc:  # logging must never change the analysis result
        logger.warning("Analysis log was not written (%s).", type(exc).__name__)
        return None
