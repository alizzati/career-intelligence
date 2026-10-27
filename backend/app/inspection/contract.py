"""Static contract + privacy validation of a manual-validation artifact.

Pure function: no I/O, no DB, no LLM. Violation messages carry JSON paths and rule names only,
never the offending values (so reporting a violation cannot itself leak data)."""
from __future__ import annotations

import json
import math
import re
from typing import Any, Iterable

from app.inspection.artifact import SCHEMA_VERSION

REQUIRED_TOP = (
    "schema_version", "privacy_notice", "data_source_legend", "run_metadata", "workflow_execution",
    "execution_trace", "profile_agent", "career_recommendation_agent", "skill_gap_agent",
    "roadmap_agent", "verification_agent", "cross_stage_checks", "independent_reference_checks",
    "final_output", "instrumentation_warnings",
)
REQUIRED_RUN_META = (
    "run_id", "started_at", "duration_ms", "mode", "mode_label", "input_source", "user",
    "target_career_requested", "target_career_final", "final_status", "verified", "revision_count",
    "max_revisions", "input_document", "redaction", "llm", "llm_runtime", "prompt_identities",
    "per_call_token_limits", "application_retry_behavior", "scoring_weights", "versions",
    "kb_counts_before", "kb_counts_after", "kb_unchanged", "kb_version", "database",
    "git_commit", "git_dirty", "git_diff_sha256", "harness_error",
)
ALLOWED_MANUAL_DB = "career_intelligence_e2e_test"
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
DATABASE_IDENTITY_KEYS = frozenset({"name", "host", "port", "server_current_database"})
AGENT_SECTIONS = ("profile_agent", "career_recommendation_agent", "skill_gap_agent",
                  "roadmap_agent", "verification_agent")
KNOWN_NODES = frozenset({"profile_analysis", "career_recommendation", "skill_gap_analysis",
                         "learning_roadmap", "verification", "verification_decision", "final_result"})
FINAL_STATUSES = frozenset({"VERIFIED", "VERIFICATION_FAILED", "REVISION_LIMIT_REACHED", "ERROR"})

_KEY = re.compile(r"[A-Za-z0-9_.:#\-]{1,120}")
_LONG_DIGITS = re.compile(r"\d{9,}")
_HEX_TOKEN = re.compile(r"(?=[0-9]*[a-fA-F])[0-9a-fA-F]{32,128}")
_SHA_VALUE = re.compile(r"[0-9a-f]{16}|[0-9a-f]{64}")
_SHA64 = re.compile(r"[0-9a-f]{64}")
_EXC_KEYS = frozenset({"type", "module", "code", "status", "origin", "json_error_position"})
_ERR_KEYS = frozenset({"stage", "error_type", "code", "status"})


def _scan(node: Any, path: str, out: list[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            ok = isinstance(key, str) and bool(_KEY.fullmatch(key)) and not _LONG_DIGITS.search(key)
            here = f"{path}/{key if ok else '<bad-key>'}"
            if not ok:
                out.append(f"{here}: dictionary key is not an identifier-like string")
            elif key.endswith("sha256") and isinstance(value, str) and not _SHA_VALUE.fullmatch(value):
                out.append(f"{here}: malformed digest")
            _scan(value, here, out)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _scan(item, f"{path}[{i}]", out)
    elif isinstance(node, str):
        text = _HEX_TOKEN.sub("", node)
        if "@" in text:
            out.append(f"{path}: string contains '@' (possible e-mail)")
        if _LONG_DIGITS.search(text):
            out.append(f"{path}: string contains a 9+ digit run (possible identifier)")
    elif isinstance(node, float) and not math.isfinite(node):
        out.append(f"{path}: non-finite number")


def _keys_within(value: Any, allowed: frozenset, label: str, out: list[str]) -> None:
    if not isinstance(value, dict):
        out.append(f"{label}: expected an object")
    elif set(value) - allowed:
        out.append(f"{label}: unexpected fields (exception/error details must be structured metadata only)")


def validate_artifact(artifact: Any, forbidden: Iterable[str] = (),
                      allow_failed_checks: bool = False) -> list[str]:
    """Return a list of violations (empty list = contract satisfied)."""
    if not isinstance(artifact, dict):
        return ["artifact is not a JSON object"]
    out: list[str] = []
    if artifact.get("schema_version") != SCHEMA_VERSION:
        out.append(f"schema_version is not {SCHEMA_VERSION}")
    for key in REQUIRED_TOP:
        if key not in artifact:
            out.append(f"missing top-level field: {key}")
    meta, final = artifact.get("run_metadata"), artifact.get("final_output")
    if not isinstance(meta, dict) or not isinstance(final, dict):
        _scan(artifact, "", out)
        return out + ["run_metadata/final_output missing or not objects"]

    for key in REQUIRED_RUN_META:
        if key not in meta:
            out.append(f"run_metadata missing field: {key}")

    status = meta.get("final_status")
    if status not in FINAL_STATUSES:
        out.append("run_metadata.final_status is not a known status")
    if final.get("final_status") != status:
        out.append("final_output.final_status differs from run_metadata.final_status")
    if meta.get("verified") is not (status == "VERIFIED") or final.get("verified") is not (status == "VERIFIED"):
        out.append("verified flag is inconsistent with final_status")
    harness = meta.get("harness_error")
    if not isinstance(harness, list):
        out.append("run_metadata.harness_error must be a list")
    else:
        for item in harness:
            _keys_within(item, _ERR_KEYS, "harness_error entry", out)
        if harness and status == "VERIFIED":
            out.append("artifact reports VERIFIED but carries a harness error")
    if status == "ERROR" and not final.get("errors"):
        out.append("ERROR run has no structured error in final_output.errors")
    for item in final.get("errors") or []:
        _keys_within(item, _ERR_KEYS, "final_output.errors entry", out)

    # provenance: unavailable must be explicit, never silently missing
    if not isinstance(meta.get("kb_version"), str):
        out.append("kb_version must be a string (an explicit 'unavailable...' marker if unknown)")
    if meta.get("kb_unchanged") not in (True, "unavailable"):
        out.append("kb_unchanged is False or malformed (KB counts changed or are not comparable)")

    # effective database identity: engine URL name/host/port plus the server-confirmed name
    database = meta.get("database")
    if not isinstance(database, dict):
        out.append("run_metadata.database must be an object")
    else:
        _keys_within(database, DATABASE_IDENTITY_KEYS, "run_metadata.database", out)
        name = database.get("name")
        host = database.get("host")
        port = database.get("port")
        current = database.get("server_current_database")
        if name != ALLOWED_MANUAL_DB:
            out.append("database.name is not the isolated manual-validation database")
        if current != name:
            out.append("server-confirmed current_database differs from the engine URL database")
        if not isinstance(host, str) or host.lower() not in LOOPBACK_HOSTS:
            out.append("database.host is not a loopback host")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            out.append("database.port must be an integer between 1 and 65535")

    commit = meta.get("git_commit")
    if not (commit == "unavailable" or (isinstance(commit, str) and re.fullmatch(r"[0-9a-fA-F]{40,64}", commit))):
        out.append("git_commit must be 'unavailable' or a 40-64 char hex revision")
    dirty = meta.get("git_dirty")
    digest = meta.get("git_diff_sha256")
    if dirty not in (True, False, "unavailable") or isinstance(dirty, int) and not isinstance(dirty, bool):
        out.append("git_dirty must be true, false, or 'unavailable'")
    elif dirty is True and not (isinstance(digest, str) and _SHA64.fullmatch(digest)):
        out.append("a dirty working tree must record a 64-char lowercase git_diff_sha256")
    elif dirty in (False, "unavailable") and digest is not None:
        out.append("a clean or unavailable tree must not record a git_diff_sha256")
    runtime = meta.get("llm_runtime")
    if not isinstance(runtime, dict) or not isinstance(runtime.get("provider"), str) \
            or not isinstance(runtime.get("model"), str):
        out.append("llm_runtime.provider/model must be strings")
    elif runtime["provider"] == "test_double":
        gen = runtime.get("generation_settings")
        if not (isinstance(gen, dict) and str(gen.get("value", "")).startswith("unavailable")):
            out.append("test-double run must mark generation settings unavailable")
    for call in meta.get("prompt_identities") or []:
        for field in ("system_prompt_sha256", "prompt_sha256"):
            if not (isinstance(call, dict) and isinstance(call.get(field), str) and _SHA64.fullmatch(call[field])):
                out.append(f"prompt_identities.{field} must be a 64-char lowercase hex digest")
    for call in meta.get("per_call_token_limits") or []:
        if not isinstance(call, dict) or not (call.get("max_tokens") is None or isinstance(call.get("max_tokens"), int)):
            out.append("per_call_token_limits entry malformed")

    # node trace
    trace = artifact.get("execution_trace")
    if not isinstance(trace, list):
        out.append("execution_trace must be a list")
        trace = []
    for event in trace:
        if not isinstance(event, dict) or event.get("node") not in KNOWN_NODES \
                or event.get("event") != "node_completed":
            out.append("execution_trace entry has an unknown node or event type")
            continue
        for err in event.get("errors") or []:
            _keys_within(err, _ERR_KEYS, "execution_trace errors entry", out)
    nodes = [e.get("node") for e in trace if isinstance(e, dict)]
    flow = artifact.get("workflow_execution")
    if not isinstance(flow, dict) or flow.get("nodes_in_order") != nodes:
        out.append("workflow_execution.nodes_in_order differs from execution_trace")
    if nodes and (nodes[0] != "profile_analysis" or nodes[-1] != "final_result"):
        out.append("trace must start at profile_analysis and end at final_result")

    # agent sections
    sections: dict[str, dict] = {}
    for name in AGENT_SECTIONS:
        sec = artifact.get(name)
        if not isinstance(sec, dict) or not isinstance(sec.get("executed"), bool):
            out.append(f"{name}: missing 'executed' flag")
            continue
        sections[name] = sec
        if sec["executed"]:
            execs = sec.get("executions")
            if not isinstance(execs, list) or not execs:
                out.append(f"{name}: executed but no executions recorded")
                continue
            for ex in execs:
                if not isinstance(ex, dict) or not isinstance(ex.get("seq"), int) \
                        or not isinstance(ex.get("attempt"), int) or "error" not in ex:
                    out.append(f"{name}: execution entry malformed")
                elif ex["error"] is not None:
                    _keys_within(ex["error"], _EXC_KEYS, f"{name} execution error", out)
        elif not isinstance(sec.get("reason"), str):
            out.append(f"{name}: not executed and no reason given")

    verification = sections.get("verification_agent")
    if status == "VERIFIED":
        execs = (verification or {}).get("executions") or []
        last = execs[-1].get("output_agent") if execs else None
        if not (isinstance(last, dict) and last.get("status") == "PASS"):
            out.append("VERIFIED run lacks a final PASS verification output")
    if status != "ERROR" and verification and verification.get("executed"):
        count, revisions = len(verification["executions"]), meta.get("revision_count")
        if isinstance(revisions, int) and count != revisions + 1:
            out.append("verification executions != revision_count + 1")
    rc, cap = meta.get("revision_count"), meta.get("max_revisions")
    if isinstance(rc, int) and isinstance(cap, int) and rc > cap:
        out.append("revision_count exceeds max_revisions")

    # cross-stage + independent checks
    cross = artifact.get("cross_stage_checks")
    results = [c.get("result") for c in (cross or {}).get("checks", []) if isinstance(c, dict)] \
        if isinstance(cross, dict) else []
    if not isinstance(cross, dict):
        out.append("cross_stage_checks malformed")
    if "ERROR" in results:
        out.append("a cross-stage check reported ERROR (inspection tool defect)")
    if "FAIL" in results and not allow_failed_checks:
        out.append("a cross-stage check reported FAIL")
    indep = artifact.get("independent_reference_checks")
    if isinstance(indep, list) and not allow_failed_checks:
        if any(not isinstance(c, dict) or c.get("result") != "PASS" for c in indep):
            out.append("an independent reference check did not PASS")
    elif indep != "unavailable" and not isinstance(indep, list):
        out.append("independent_reference_checks must be a list or 'unavailable'")

    _scan(artifact, "", out)
    blob = json.dumps(artifact, ensure_ascii=False).lower()
    for item in forbidden:
        if item and item.lower() in blob:
            out.append("a caller-supplied forbidden string appears in the artifact")
    return out