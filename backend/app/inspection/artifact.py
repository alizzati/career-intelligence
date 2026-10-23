"""Builds the manual-validation artifact from a Recorder, plus cross-stage checks.

Each check states WHERE its reference comes from. A reference is never the same object/value as the
thing being checked (e.g. an agent output is compared against a fresh KB/DB read or an independent
calculator call recorded during the run). Missing evidence is reported as UNAVAILABLE/NOT_APPLICABLE,
never as PASS. Checks are explanatory aids; they are NOT part of the system's verification.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from importlib import metadata

from app.inspection.recorder import Recorder, clean_str, sha256_text, to_jsonable

SCHEMA_VERSION = "manual_validation/0.2"
PRIVACY_NOTICE = (
    "Contains structured data derived from the submitted CV (skills, education, experience, ...). "
    "CV text, full prompts, raw LLM responses, API keys, account e-mail and file names are NOT stored; "
    "all strings pass the best-effort PII redactor (names/addresses without labels can still be missed). "
    "Do not share or commit this file.")
LEGEND = {
    "output_agent": "object returned by the agent's run()",
    "database_reads": "app user-data reads (user_service.get_user_full_profile) made during the agent run",
    "database_writes": "user-data writes (user_service.add_*) made during the agent run",
    "knowledge_base_reads": "occupational KB reads (retrieval_service.*) made during the agent run",
    "deterministic_computations": "calls to compute_career_fit() with its inputs' ids and its result",
    "llm_calls": "sizes/hashes/keys/errors only; never prompt or response text",
    "nested": "true = the call was made inside another recorded call (e.g. get_occupational_context -> get_career)",
}
AGENT_SECTIONS = {"profile": "profile_agent", "career_recommendation": "career_recommendation_agent",
                  "skill_gap": "skill_gap_agent", "roadmap": "roadmap_agent",
                  "verification": "verification_agent"}
_LINEAR_NEXT = {"profile_analysis": "career_recommendation", "career_recommendation": "skill_gap_analysis",
                "skill_gap_analysis": "learning_roadmap", "learning_roadmap": "verification",
                "verification": "verification_decision"}
_ROUTE = {"career_recommendation": "career_recommendation", "skill_gap": "skill_gap_analysis",
          "roadmap": "learning_roadmap"}


def _g(obj, name, default=None):
    return getattr(obj, name, default)


def _ids(items):
    return [_g(i, "skill_id") for i in (items or [])]


def _gap_of(x):
    return _g(x, "skill_gap", x)


def _text_fingerprint(value):
    if not isinstance(value, str):
        return "unavailable"
    return {"chars": len(value), "sha256": sha256_text(value)}


def _safe_errors(errors):
    safe = []
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
            elif key == "status" and isinstance(value, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", value):
                item[key] = value
        safe.append(item)
    return safe


def _text_collection(values):
    return [
        _text_fingerprint(value) if isinstance(value, str)
        else value if value is None or isinstance(value, (bool, int))
        else {"value_type": type(value).__name__}
        for value in values or []
    ]


def _unsupported_claims(values):
    return [
        {
            "component": clean_str(_g(value, "component", ""), 100),
            "claim_fingerprint": _text_fingerprint(_g(value, "claim")),
            "source_ids": [
                clean_str(source_id, 100)
                if isinstance(source_id, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", source_id)
                else _text_fingerprint(str(source_id))
                for source_id in list(_g(value, "source_ids", []) or [])[:20]
            ],
        }
        for value in values or []
    ]


def _safe_context_values(value, allowed_keys):
    if not isinstance(value, dict):
        return {}
    return {
        key: clean_str(value[key], 160) if isinstance(value[key], str) else value[key]
        for key in allowed_keys
        if isinstance(value.get(key), (str, int, float, bool)) or value.get(key) is None
    }


def _safe_document(value):
    data = _safe_context_values(value, ("format", "size_bytes", "sha256"))
    if "sha256" in data and not re.fullmatch(r"[A-Fa-f0-9]{64}", str(data["sha256"])):
        data.pop("sha256")
    return data or "unavailable"


def _llm_runtime(client):
    inner = client
    seen = set()
    while inner is not None and id(inner) not in seen and hasattr(inner, "_inner"):
        seen.add(id(inner))
        inner = inner._inner
    if inner is None:
        return {"provider": "unavailable", "model": "unavailable", "sdk": "unavailable"}

    class_name = type(inner).__name__
    module_name = type(inner).__module__
    if class_name == "GeminiClient" and module_name.endswith(".llm_client"):
        try:
            sdk_version = metadata.version("google-genai")
        except metadata.PackageNotFoundError:
            sdk_version = "unavailable (google-genai package metadata not installed)"
        return {
            "provider": "google_genai",
            "model": clean_str(str(getattr(inner, "model", "unavailable")), 120),
            "sdk": {"package": "google-genai", "version": sdk_version, "used_by_run": True},
            "generation_settings": {
                "response_mime_type": {"value": "application/json", "source": "explicit"},
                "system_instruction": {"value": "per-call prompt", "source": "explicit"},
                "max_output_tokens": {"value": "per-call max_tokens", "source": "explicit"},
                "temperature": {
                    "value": "unavailable",
                    "source": "SDK default; not pinned by GeminiClient",
                },
                "other_generation_parameters": {
                    "value": "unavailable",
                    "source": "SDK defaults; not pinned by GeminiClient",
                },
            },
            "application_retries": "No provider-call retry is implemented in GeminiClient.",
            "sdk_retries": "unavailable (SDK-internal retry policy is not exposed or pinned by this client)",
        }
    model = getattr(inner, "model_name", getattr(inner, "model", class_name))
    try:
        sdk_version = metadata.version("google-genai")
    except metadata.PackageNotFoundError:
        sdk_version = "unavailable (google-genai package metadata not installed)"
    return {
        "provider": "test_double" if class_name.lower().startswith(("fake", "recordingfake")) else "unknown",
        "model": clean_str(str(model), 120),
        "sdk": {"package": "google-genai", "version": sdk_version, "used_by_run": False},
        "generation_settings": {
            "value": "unavailable (test double does not establish provider generation settings)",
        },
        "application_retries": "unavailable (test double)",
        "sdk_retries": "not applicable (test double)",
    }


def _runs(rec, agent):
    return [r for r in rec.agent_runs if r["agent"] == agent]


def _last(rec, agent):
    runs = _runs(rec, agent)
    return runs[-1] if runs else None


def _safe(fn):
    try:
        return fn()
    except Exception as exc:
        return {"summary_error": type(exc).__name__}


# ----------------------------------------------------------------------------- per-agent summaries
def _in_profile(rec, run):
    a, kw = run["raw_args"], run["raw_kwargs"]
    text = a[1] if len(a) > 1 else kw.get("raw_profile_text")
    return {"user_id": a[0] if a else kw.get("user_id"),
            "redacted_text": _text_fingerprint(text)}


def _out_profile(rec, run):
    o = run["raw_output"]
    ex = _g(o, "extracted")
    extracted_summary = "unavailable"
    if isinstance(ex, dict):
        allowed_fields = {"skills", "evidence", "education", "experience", "projects", "certifications"}
        extracted_summary = {
            "field_names": sorted(allowed_fields.intersection(ex)),
            "unknown_field_count": len(set(ex) - allowed_fields),
            "item_counts": {
                key: len(ex[key]) for key in allowed_fields
                if isinstance(ex.get(key), list)
            },
            "skill_claims": [
                {"claim_fingerprint": _text_fingerprint(item.get("claimed_skill")),
                 "candidate_skill_id": (
                     item.get("candidate_skill_id")
                     if isinstance(item.get("candidate_skill_id"), str)
                     and re.fullmatch(r"S[0-9]+", item["candidate_skill_id"])
                     else "unavailable"
                 )}
                for item in ex.get("skills", []) if isinstance(item, dict)
            ],
        }
    return {"extracted_summary": extracted_summary,
            "normalizations": [{"claim_fingerprint": _text_fingerprint(n.claimed_skill),
                                "skill_id": n.result.skill_id,
                                "normalized_name": n.result.normalized_name, "method": n.result.method,
                                "score": n.result.score} for n in _g(o, "normalizations", [])],
            "skills_persisted": _g(o, "skills_persisted"), "evidence_persisted": _g(o, "evidence_persisted")}


def _handoff_profile(rec, run):
    writes = Counter(rec.io[i]["function"] for i in run["io_idx"] if rec.io[i]["category"] == "db_write")
    ex = _g(run["raw_output"], "extracted")
    lens = ({k: len(v) for k, v in ex.items() if isinstance(v, list)} if isinstance(ex, dict) else "unavailable")
    return {"mechanism": "persisted to the database; downstream agents re-read the profile from the DB "
                         "(state['profile_result'] is not consumed by them)",
            "db_write_calls": dict(writes), "extracted_list_lengths": lens,
            "note": "extracted list length minus write calls = entries not written; the agent does not report this"}


def _in_user_only(rec, run):
    a, kw = run["raw_args"], run["raw_kwargs"]
    return {"user_id": a[0] if a else kw.get("user_id")}


def _out_rec(rec, run):
    ranked, weights = [], None
    for i, r in enumerate(run["raw_output"] or [], 1):
        sb = to_jsonable(_g(r, "score_breakdown"))
        if isinstance(sb, dict):
            weights = weights or sb.pop("weights_used", None)
        ranked.append({"rank": i, "career_id": _g(r, "career_id"), "canonical_name": _g(r, "canonical_name"),
                       "fit_score": _g(r, "fit_score"), "reasoning_source": _g(r, "reasoning_source"),
                       "reasoning": _text_fingerprint(_g(r, "reasoning")),
                       "matched_skill_ids": _ids(_g(r, "matched_skills")),
                       "claimed_only_skill_ids": _ids(_g(r, "claimed_only_skills")),
                       "missing_skill_ids": _ids(_g(r, "missing_skills_preview")), "score_breakdown": sb})
    return {"ranked": ranked, "weights_used": weights}


def _node_event(rec, node, after_seq=None, run_seq=None):
    for ev in rec.node_events:
        if ev["node"] != node:
            continue
        if run_seq is not None and run_seq in ev["agent_run_seqs"]:
            return ev
        if after_seq is not None and ev["seq"] > after_seq:
            return ev
    return None


def _handoff_rec(rec, run):
    ev = _node_event(rec, "career_recommendation", run_seq=run["seq"])
    return {"state_target_career_id": ev["target_career_id"] if ev else "unavailable (observer not attached)",
            "rule": "explicit target if given, else top-ranked (CareerWorkflow._career_recommendation)"}


def _cat_item(i):
    claim = _g(i, "matched_user_claim")
    return {"skill_id": _g(i, "skill_id"), "canonical_name": _g(i, "canonical_name"), "status": _g(i, "status"),
            "evidence_class": _g(i, "evidence_class"), "kb_confidence": _g(i, "kb_confidence"),
            "weight": _g(i, "weight"), "contribution": _g(i, "contribution"),
            "matched_user_claim": (
                {"claim_fingerprint": _text_fingerprint(_g(claim, "claimed_skill")),
                 "evidence_status": _g(claim, "evidence_status"),
                 "evidence_count": _g(claim, "evidence_count")}
                if claim is not None else None
            )}


def _out_gap(rec, run):
    a = run["raw_output"]
    g = _gap_of(a)
    return {"career_id": _g(g, "career_id"), "fit_score": _g(g, "fit_score"),
            "total_weight": _g(g, "total_weight"), "total_contribution": _g(g, "total_contribution"),
            "categories": {"matched_evidenced": [_cat_item(i) for i in _g(g, "matched_evidenced", [])],
                           "matched_claimed_only": [_cat_item(i) for i in _g(g, "matched_claimed_only", [])],
                           "missing": [_cat_item(i) for i in _g(g, "missing", [])],
                           "unmatched_user_claims": [
                               {"user_skill_id": _g(item, "user_skill_id"),
                                "claim_fingerprint": _text_fingerprint(_g(item, "claimed_skill")),
                                "evidence_status": _g(item, "evidence_status")}
                               for item in _g(g, "unmatched_user_claims", [])
                           ]},
            "narrative_source": _g(a, "narrative_source"),
            "llm_error": _g(a, "llm_error") is not None,
            "validation_notes": _text_collection(_g(a, "validation_notes", [])),
            "narrative": _text_fingerprint(_g(a, "narrative"))}


def _handoff_gap(rec, run):
    same = [r["raw_args"] and r["raw_args"][0] is run["raw_output"] for r in _runs(rec, "roadmap")]
    return {"consumed_by": "learning_roadmap", "roadmap_received_same_object": (same[-1] if same else "unavailable (roadmap did not run)")}


def _in_roadmap(rec, run):
    a = run["raw_args"][0] if run["raw_args"] else run["raw_kwargs"].get("result")
    g = _gap_of(a)
    gr = _last(rec, "skill_gap")
    return {"received_type": type(a).__name__, "career_id": _g(g, "career_id"),
            "outstanding_skill_ids": {"matched_claimed_only": _ids(_g(g, "matched_claimed_only")),
                                      "missing": _ids(_g(g, "missing"))},
            "same_object_as_skill_gap_output": (a is gr["raw_output"]) if gr else "unavailable"}


def _out_roadmap(rec, run):
    o = run["raw_output"]
    gr = _last(rec, "skill_gap")
    unchanged = "unavailable"
    if gr is not None and hasattr(_g(o, "skill_gap"), "model_dump"):
        unchanged = _g(o, "skill_gap").model_dump() == _gap_of(gr["raw_output"]).model_dump()
    return {"items": to_jsonable(_g(o, "items", []), str_limit=300),
            "summary": _text_fingerprint(_g(o, "summary")),
            "narrative_source": _g(o, "narrative_source"),             "llm_error": _g(o, "llm_error") is not None,
            "embedded_skill_gap_equals_skill_gap_output": unchanged}


def _handoff_roadmap(rec, run):
    return {"consumed_by": "verification", "roadmap_item_ids": _ids(_g(run["raw_output"], "items"))}


def _in_verification(rec, run):
    a = run["raw_args"]
    recs, gap, road = (list(a) + [None, None, None])[:3]
    rr, gr, roadr = _last(rec, "career_recommendation"), _last(rec, "skill_gap"), _last(rec, "roadmap")
    g = _gap_of(gap)
    return {"recommendation_ids_in_order": [_g(r, "career_id") for r in (recs or [])],
            "skill_gap_category_ids": {"matched_evidenced": _ids(_g(g, "matched_evidenced")),
                                       "matched_claimed_only": _ids(_g(g, "matched_claimed_only")),
                                       "missing": _ids(_g(g, "missing"))},
            "roadmap_item_ids": _ids(_g(road, "items")),
            "same_object_as_agent_output": {
                "recommendations": (recs is rr["raw_output"]) if rr else "unavailable",
                "skill_gap": (gap is gr["raw_output"]) if gr else "unavailable",
                "roadmap": (road is roadr["raw_output"]) if roadr else "unavailable"},
            "note": "the node passes redacted copies; they are the same objects unless redaction changed text"}


def _out_verification(rec, run):
    v = run["raw_output"]
    checks = [{"check": c.check, "status": c.status, "reason": _text_fingerprint(c.reason),
               "source_ids_count": len(c.source_ids), "source_ids": list(c.source_ids)[:20]}
              for c in _g(v, "checks", [])]
    prov = next((c["source_ids"] for c in checks if c["check"] == "evidence.provenance_references"), [])
    return {"status": _g(v, "status"), "checks": checks,
            "unsupported_claims": _unsupported_claims(_g(v, "unsupported_claims", [])),
            "required_revision": _text_collection(_g(v, "required_revision", [])),
            "llm_error": to_jsonable(_g(v, "llm_error"), str_limit=200), "provenance_ids_resolved": prov}


def _handoff_verification(rec, run):
    ev = _node_event(rec, "verification_decision", after_seq=run["seq"])
    return ({"consumed_by": "verification_decision", "final_status": ev["final_status"],
             "revision_target": ev["revision_target"], "revision_count": ev["revision_count"]}
            if ev else {"consumed_by": "verification_decision", "decision": "unavailable (observer not attached)"})


SUMMARIES = {
    "profile": (_in_profile, _out_profile, _handoff_profile,
                ["ids of rows written are in database_writes (recorder), not in the agent output",
                 "skipped/merged entries are not reported by the agent"]),
    "career_recommendation": (_in_user_only, _out_rec, _handoff_rec,
                              ["evidence/source/provenance per recommendation (not in CareerRecommendationOut)",
                               "per-skill weight/contribution (only in skill-gap items and calculator records)"]),
    "skill_gap": (_in_user_only, _out_gap, _handoff_gap, ["priority / required proficiency (excluded by design)"]),
    "roadmap": (_in_roadmap, _out_roadmap, _handoff_roadmap,
                ["stages, learning objectives, resources (excluded by frozen decisions)"]),
    "verification": (_in_verification, _out_verification, _handoff_verification,
                     ["content of provenance records (only ids are reported by the agent)"]),
}


def _group(entries, cap=8):
    out: dict = {}
    for e in entries:
        slot = out.setdefault(e["function"], {"calls": 0, "nested_calls": 0, "entries": []})
        slot["calls"] += 1
        slot["nested_calls"] += 1 if e["nested"] else 0
        if len(slot["entries"]) < cap:
            slot["entries"].append({k: e[k] for k in ("seq", "nested", "args", "result", "error")})
    for slot in out.values():
        slot["entries_omitted"] = slot["calls"] - len(slot["entries"])
    return out


def _execution(rec, run, key):
    f_in, f_out, f_hand, unavailable = SUMMARIES[key]
    io = [rec.io[i] for i in run["io_idx"]]
    ok = run["raw_output"] is not None
    return {"seq": run["seq"], "attempt": run["attempt"], "t_start_ms": run["t_start_ms"],
            "duration_ms": run["duration_ms"],
            "input_actual": _safe(lambda: f_in(rec, run)),
            "output_agent": _safe(lambda: f_out(rec, run)) if ok else None,
            "handoff": _safe(lambda: f_hand(rec, run)) if ok else None,
            "llm_calls": [rec.llm[i] for i in run["llm_idx"]],
            "database_reads": _group([e for e in io if e["category"] == "db_read"]),
            "database_writes": _group([e for e in io if e["category"] == "db_write"]),
            "knowledge_base_reads": _group([e for e in io if e["category"] == "kb_read"]),
            "deterministic_computations": [
                {k: v for k, v in rec.computations[i].items() if k != "skill_details"}
                | {"skill_details": rec.computations[i]["skill_details"]} for i in run["comp_idx"]],
            "error": run["error"], "unavailable": unavailable}


def _agent_section(rec, key, ctx):
    runs = _runs(rec, key)
    if runs:
        return {"executed": True, "executions": [_execution(rec, r, key) for r in runs]}
    errors = ctx["final_state"].get("errors") or []
    if key == "profile":
        reason = ("not executed: no raw profile text supplied" if not ctx.get("input_source")
                  else "not executed (see final_output.errors)")
    else:
        reason = ("not reached: an earlier stage ended with ERROR" if errors else "not executed")
    return {"executed": False, "reason": reason}


def _safe_agent_output(rec, key, run):
    if key == "career_recommendation":
        return _out_rec(rec, run)
    if key == "skill_gap":
        return _out_gap(rec, run)
    if key == "roadmap":
        return _out_roadmap(rec, run)
    return None


def _revision_transitions(rec, trace):
    agent_for_target = {
        "career_recommendation": "career_recommendation",
        "skill_gap": "skill_gap",
        "roadmap": "roadmap",
    }
    decisions = [event for event in trace if event["node"] == "verification_decision"]
    verification_runs = _runs(rec, "verification")
    transitions = []
    for index, event in enumerate(decisions):
        verification = verification_runs[index]["raw_output"] if index < len(verification_runs) else None
        failed_checks = [
            {"check": check.check, "status": check.status}
            for check in _g(verification, "checks", [])
            if check.status != "PASS"
        ]
        target = event.get("revision_target")
        agent = agent_for_target.get(target)
        changed_fields = "unavailable (the revision output has not been observed)"
        if agent:
            prior = next(
                (run for run in reversed(_runs(rec, agent)) if run["seq"] < event["seq"]),
                None,
            )
            revised = next(
                (run for run in _runs(rec, agent) if run["seq"] > event["seq"]),
                None,
            )
            if prior and revised and prior["raw_output"] is not None and revised["raw_output"] is not None:
                before = _safe_agent_output(rec, agent, prior) or {}
                after = _safe_agent_output(rec, agent, revised) or {}
                changed_fields = sorted(
                    key for key in set(before) | set(after) if before.get(key) != after.get(key)
                )
        transitions.append({
            "revision_count": event.get("revision_count"),
            "revision_target": target,
            "outcome": event.get("final_status"),
            "verification_checks_requiring_revision": failed_checks,
            "changed_output_fields": changed_fields,
        })
    return transitions


# ----------------------------------------------------------------------------- cross-stage checks
def _res(cid, name, result, reference, compared, detail=None):
    return {"id": cid, "name": name, "result": result, "reference": reference, "compared": compared,
            "detail": detail}


def _kb_reads(rec, fn, key=None):
    out = []
    for e in rec.raw_io:
        if e["function"] != fn or e["result"] is None:
            continue
        if key is not None and (e["args"][0] if e["args"] else e["kwargs"].get("career_id")) != key:
            continue
        out.append(e)
    return out


def _sig(profile):
    return sorted((s.user_skill_id, s.skill_id, s.evidence_status, s.proficiency, len(s.evidence))
                  for s in profile.skills)


def c_profile_vs_db(rec, ctx):
    name = "profile_agent_output_vs_persisted_db_rows"
    ref = "DB profile read by the harness AFTER the run (independent of the agent's return value)"
    run = _last(rec, "profile")
    if run is None or run["error"] or run["raw_output"] is None:
        return _res("X1", name, "NOT_APPLICABLE", ref, "-", "Profile Agent did not run or failed")
    db = ctx.get("post_run_profile")
    if db is None:
        return _res("X1", name, "UNAVAILABLE", ref, "-", "post-run DB profile not available")
    out, problems = run["raw_output"], []
    by_claim = {s.claimed_skill: s for s in db.skills}
    for i, n in enumerate(_g(out, "normalizations", [])):
        row = by_claim.get(n.claimed_skill)
        if row is None:
            problems.append(f"normalization #{i} has no user_skills row")
        elif row.skill_id != n.result.skill_id:
            problems.append(f"normalization #{i}: DB skill_id {row.skill_id} != agent {n.result.skill_id}")
    writes = [e for e in rec.raw_io if e["function"] == "add_user_skill" and e["stage"] == "profile"]
    if len(writes) != _g(out, "skills_persisted"):
        problems.append(f"add_user_skill calls {len(writes)} != skills_persisted {_g(out, 'skills_persisted')}")
    return _res("X1", name, "FAIL" if problems else "PASS", ref,
                f"{len(_g(out, 'normalizations', []))} normalizations, {len(db.skills)} DB skill rows", problems)


def c_profile_views(rec, ctx):
    name = "profile_seen_by_downstream_agents_is_consistent"
    ref = "independent get_user_full_profile reads in each stage + post-run DB read"
    reads = [e for e in rec.raw_io if e["function"] == "get_user_full_profile" and not e["nested"]]
    if len(reads) < 2:
        return _res("X2", name, "UNAVAILABLE", ref, "-", "fewer than two profile reads recorded")
    sigs = {e["seq"]: (e["stage"], _sig(e["result"])) for e in reads if e["result"] is not None}
    if ctx.get("post_run_profile") is not None:
        sigs[-1] = ("post_run", _sig(ctx["post_run_profile"]))
    distinct = {repr(v[1]) for v in sigs.values()}
    return _res("X2", name, "PASS" if len(distinct) == 1 else "FAIL", ref,
                {"reads_by_stage": dict(Counter(v[0] for v in sigs.values()))},
                None if len(distinct) == 1 else "profile signature differs between reads")


def c_career_universe(rec, ctx):
    name = "recommendations_cover_kb_careers_and_target_is_valid"
    ref = "KB read retrieval_service.get_all_careers during the run"
    run, kb = _last(rec, "career_recommendation"), _kb_reads(rec, "get_all_careers")
    if run is None or run["raw_output"] is None:
        return _res("X3", name, "NOT_APPLICABLE", ref, "-", "recommendation agent did not produce output")
    if not kb:
        return _res("X3", name, "UNAVAILABLE", ref, "-", "no get_all_careers read recorded")
    kb_ids = {c.career_id for c in kb[-1]["result"]}
    rec_ids = [r.career_id for r in run["raw_output"]]
    target, requested = ctx["final_state"].get("target_career_id"), ctx.get("target_requested")
    problems = []
    if set(rec_ids) != kb_ids or len(rec_ids) != len(set(rec_ids)):
        problems.append("recommended career ids differ from KB careers (or contain duplicates)")
    if target not in kb_ids:
        problems.append("target career is not a KB career")
    if requested is None and rec_ids and target != rec_ids[0]:
        problems.append("no explicit target but target != top-ranked recommendation")
    return _res("X3", name, "FAIL" if problems else "PASS", ref,
                {"kb_careers": len(kb_ids), "recommended": len(rec_ids), "target": target}, problems)


def c_scores(rec, ctx):
    name = "recommendation_and_gap_fit_scores_vs_calculator_calls"
    ref = "compute_career_fit() calls recorded in each stage, matched to the target career by its KB skill-id list"
    target = ctx["final_state"].get("target_career_id")
    rr, gr = _last(rec, "career_recommendation"), _last(rec, "skill_gap")
    if not (rr and gr and rr["raw_output"] and gr["raw_output"] and target):
        return _res("X4", name, "NOT_APPLICABLE", ref, "-", "recommendation or skill-gap output missing")
    kb = _kb_reads(rec, "get_career_skills", target)
    if not kb:
        return _res("X4", name, "UNAVAILABLE", ref, "-", "no KB read of the target's career_skills recorded")
    kb_ids = [c.skill.skill_id for c in kb[-1]["result"]]
    by = {}
    for c in rec.computations:
        if c["required_ids"] == kb_ids:
            by[c["stage"]] = c
    rec_out = next((r for r in rr["raw_output"] if r.career_id == target), None)
    gap = _gap_of(gr["raw_output"])
    problems, missing = [], [s for s in ("career_recommendation", "skill_gap", "verification") if s not in by]
    if "career_recommendation" in by and rec_out is not None and rec_out.fit_score != round(by["career_recommendation"]["fit_score"], 4):
        problems.append("recommendation fit_score != its calculator call")
    if "skill_gap" in by and gap.fit_score != round(by["skill_gap"]["fit_score"], 4):
        problems.append("skill-gap fit_score != its calculator call")
    vals = [c["fit_score"] for c in by.values()]
    if vals and max(vals) - min(vals) > 1e-9:
        problems.append("calculator calls for the same career disagree across stages")
    result = "FAIL" if problems else ("UNAVAILABLE" if missing else "PASS")
    return _res("X4", name, result, ref,
                {"calculator_fit_by_stage": {k: v["fit_score"] for k, v in by.items()},
                 "recommendation_fit": _g(rec_out, "fit_score"), "gap_fit": gap.fit_score},
                problems or ([f"no calculator record for: {missing}"] if missing else None))


def c_gap_vs_kb(rec, ctx):
    name = "gap_items_cover_kb_requirements_with_kb_metadata"
    ref = "KB read retrieval_service.get_career_skills(target)"
    target, gr = ctx["final_state"].get("target_career_id"), _last(rec, "skill_gap")
    if not (gr and gr["raw_output"] and target):
        return _res("X5", name, "NOT_APPLICABLE", ref, "-", "no skill-gap output")
    kb = _kb_reads(rec, "get_career_skills", target)
    if not kb:
        return _res("X5", name, "UNAVAILABLE", ref, "-", "no KB read recorded")
    rows = {c.skill.skill_id: c for c in kb[-1]["result"]}
    gap = _gap_of(gr["raw_output"])
    items = list(gap.matched_evidenced) + list(gap.matched_claimed_only) + list(gap.missing)
    ids, problems = [i.skill_id for i in items], []
    if sorted(ids) != sorted(rows) or len(ids) != len(set(ids)):
        problems.append("gap items are not exactly the KB requirements (missing, extra or duplicate ids)")
    for i in items:
        r = rows.get(i.skill_id)
        if r and (i.canonical_name, i.evidence_class, i.kb_confidence) != (r.skill.canonical_name, r.evidence_class, r.confidence):
            problems.append(f"{i.skill_id}: name/class/confidence differ from KB")
    return _res("X5", name, "FAIL" if problems else "PASS", ref,
                {"kb_requirements": len(rows), "gap_items": len(ids)}, problems)


def c_gap_vs_profile(rec, ctx):
    name = "gap_category_of_each_requirement_vs_db_profile"
    ref = ("DB profile read inside the skill-gap stage + KB requirements; presence/evidence rule from AGENTS.md "
           "(a category check, not a score)")
    target, gr = ctx["final_state"].get("target_career_id"), _last(rec, "skill_gap")
    if not (gr and gr["raw_output"] and target):
        return _res("X6", name, "NOT_APPLICABLE", ref, "-", "no skill-gap output")
    prof = [e for e in rec.raw_io if e["function"] == "get_user_full_profile" and e["stage"] == "skill_gap" and e["result"] is not None]
    kb = _kb_reads(rec, "get_career_skills", target)
    if not prof or not kb:
        return _res("X6", name, "UNAVAILABLE", ref, "-", "profile or KB read missing")
    skills, gap, problems = prof[-1]["result"].skills, _gap_of(gr["raw_output"]), []
    actual = {i.skill_id: c for c, items in (("matched_evidenced", gap.matched_evidenced),
              ("matched_claimed_only", gap.matched_claimed_only), ("missing", gap.missing)) for i in items}
    for c in kb[-1]["result"]:
        sid = c.skill.skill_id
        rows = [s for s in skills if s.skill_id == sid]
        expected = "missing" if not rows else ("matched_evidenced" if any(s.evidence_status == "linked" for s in rows) else "matched_claimed_only")
        if actual.get(sid) != expected:
            problems.append(f"{sid}: expected {expected}, gap says {actual.get(sid)}")
    want = sorted(s.user_skill_id for s in skills if s.skill_id is None)
    if sorted(u.user_skill_id for u in gap.unmatched_user_claims) != want:
        problems.append("unmatched_user_claims differ from DB claims without skill_id")
    return _res("X6", name, "FAIL" if problems else "PASS", ref,
                {"requirements": len(kb[-1]["result"]), "user_skill_rows": len(skills)}, problems)


def c_roadmap(rec, ctx):
    name = "roadmap_items_vs_gap_and_kb_basis"
    ref = "skill-gap agent output (the roadmap's actual input) + KB get_career_skills evidence text"
    rr, gr = _last(rec, "roadmap"), _last(rec, "skill_gap")
    if not (rr and rr["raw_output"] and gr and gr["raw_output"]):
        return _res("X7", name, "NOT_APPLICABLE", ref, "-", "roadmap or skill-gap output missing")
    gap, road, problems = _gap_of(gr["raw_output"]), rr["raw_output"], []
    arg = rr["raw_args"][0] if rr["raw_args"] else None
    if arg is not gr["raw_output"]:
        problems.append("roadmap input is not the object returned by the skill-gap agent")
    want = {i.skill_id: i.status for i in list(gap.matched_claimed_only) + list(gap.missing)}
    got = {i.skill_id: i.gap_status for i in road.items}
    if got != want or len(road.items) != len(got):
        problems.append("roadmap item ids/statuses differ from matched_claimed_only + missing")
    kb = _kb_reads(rec, "get_career_skills", gap.career_id)
    if not kb:
        return _res("X7", name, "UNAVAILABLE" if not problems else "FAIL", ref, "-",
                    problems or ["no KB read recorded; knowledge_base_basis not checked"])
    basis = {c.skill.skill_id: c.evidence_source_text for c in kb[-1]["result"]}
    for i in road.items:
        if basis.get(i.skill_id) != i.knowledge_base_basis:
            problems.append(f"{i.skill_id}: knowledge_base_basis differs from KB evidence text")
    return _res("X7", name, "FAIL" if problems else "PASS", ref, {"roadmap_items": len(road.items)}, problems)


def c_verifier_inputs(rec, ctx):
    name = "verifier_inputs_match_earlier_agent_outputs"
    ref = "structured outputs of the recommendation, skill-gap and roadmap agents recorded earlier"
    vr = _runs(rec, "verification")
    if not vr or len(vr[-1]["raw_args"]) < 3:
        return _res("X8", name, "NOT_APPLICABLE", ref, "-", "verification did not run")
    recs, gap, road = vr[-1]["raw_args"][:3]
    rr, gr, roadr = _last(rec, "career_recommendation"), _last(rec, "skill_gap"), _last(rec, "roadmap")
    if not (rr and gr and roadr):
        return _res("X8", name, "UNAVAILABLE", ref, "-", "an earlier agent output is missing")
    problems = []
    if [(r.career_id, r.fit_score) for r in recs] != [(r.career_id, r.fit_score) for r in rr["raw_output"]]:
        problems.append("recommendation ids/scores differ")
    a, b = _gap_of(gap), _gap_of(gr["raw_output"])
    for cat in ("matched_evidenced", "matched_claimed_only", "missing"):
        if _ids(_g(a, cat)) != _ids(_g(b, cat)):
            problems.append(f"skill-gap {cat} ids differ")
    if _ids(road.items) != _ids(roadr["raw_output"].items):
        problems.append("roadmap item ids differ")
    return _res("X8", name, "FAIL" if problems else "PASS", ref, "ids/scores", problems)


def c_order(rec, ctx):
    name = "node_execution_order_matches_workflow_routing"
    ref = "routing rules in CareerWorkflow (edges + _after_decision) applied to the observed node updates"
    events = rec.node_events
    if not events:
        return _res("X9", name, "UNAVAILABLE", ref, "-", "observer recorded no node updates")
    problems, prev, loops = [], None, 0
    for ev in events:
        if prev is None:
            allowed = {"profile_analysis"}
        elif prev["node"] == "final_result":
            allowed = set()
        elif prev["final_status"] == "ERROR":
            allowed = {"final_result"}
        elif prev["node"] == "verification_decision":
            allowed = ({"final_result"} if prev["final_status"] != "RUNNING"
                       else {_ROUTE.get(prev["revision_target"], "final_result")})
            loops += 1 if prev["final_status"] == "RUNNING" else 0
        else:
            allowed = {_LINEAR_NEXT.get(prev["node"], "final_result")}
        if ev["node"] not in allowed:
            problems.append(f"seq {ev['seq']}: '{ev['node']}' after '{prev['node'] if prev else 'START'}', allowed {sorted(allowed)}")
        prev = ev
    fs = ctx["final_state"]
    if loops != fs.get("revision_count"):
        problems.append(f"observed {loops} revision loops, final revision_count={fs.get('revision_count')}")
    if ctx.get("max_revisions") is not None and loops > ctx["max_revisions"]:
        problems.append("revision loops exceed max_revisions")
    return _res("X9", name, "FAIL" if problems else "PASS", ref,
                {"nodes": [e["node"] for e in events], "revision_loops": loops}, problems)


def c_final(rec, ctx):
    name = "final_status_consistent_with_final_verification"
    ref = "rule in CareerWorkflow._verification_decision, applied to the verification agent's last output"
    fs, run = ctx["final_state"], _last(rec, "verification")
    if run is None or run["raw_output"] is None:
        ok = fs.get("final_status") != "VERIFIED"
        return _res("X10", name, "NOT_APPLICABLE" if ok else "FAIL", ref, "-",
                    "no verification output; status must not be VERIFIED" if ok else "VERIFIED without verification")
    v = run["raw_output"]
    expect = (v.status == "PASS" and all(c.status == "PASS" for c in v.checks)
              and not v.unsupported_claims and not v.required_revision)
    ok = (fs.get("final_status") == "VERIFIED") == expect
    return _res("X10", name, "PASS" if ok else "FAIL", ref,
                {"final_status": fs.get("final_status"), "verification_status": v.status,
                 "all_checks_pass": all(c.status == "PASS" for c in v.checks)})


def c_llm_labels(rec, ctx):
    name = "narrative_source_labels_vs_recorded_llm_calls"
    ref = "LLM call log recorded by RecordingLLMClient, per stage"
    problems, seen = [], {}
    def ok_calls(stage):
        return sum(1 for e in rec.llm if e["stage"] == stage and e["error"] is None)
    rr, gr, roadr = _last(rec, "career_recommendation"), _last(rec, "skill_gap"), _last(rec, "roadmap")
    if rr and rr["raw_output"]:
        n = sum(1 for r in rr["raw_output"] if _g(r, "reasoning_source") == "llm")
        seen["career_recommendation"] = {"llm_labelled": n, "ok_llm_calls": ok_calls("career_recommendation")}
        if n > ok_calls("career_recommendation"):
            problems.append("more 'llm' reasoning labels than successful LLM calls")
    if gr and gr["raw_output"]:
        src = _g(gr["raw_output"], "narrative_source")
        seen["skill_gap"] = {"source": src, "ok_llm_calls": ok_calls("skill_gap")}
        if src in ("llm", "llm-partial") and ok_calls("skill_gap") == 0:
            problems.append("skill-gap narrative labelled LLM without a successful LLM call")
    if roadr and roadr["raw_output"]:
        src = _g(roadr["raw_output"], "narrative_source")
        seen["roadmap"] = {"source": src, "ok_llm_calls": ok_calls("roadmap")}
        if src == "llm" and ok_calls("roadmap") == 0:
            problems.append("roadmap summary labelled 'llm' without a successful LLM call")
    if not seen:
        return _res("X11", name, "NOT_APPLICABLE", ref, "-", "no narrative-producing agent output")
    return _res("X11", name, "FAIL" if problems else "PASS", ref, seen, problems)


CHECKS = (c_profile_vs_db, c_profile_views, c_career_universe, c_scores, c_gap_vs_kb, c_gap_vs_profile,
          c_roadmap, c_verifier_inputs, c_order, c_final, c_llm_labels)


def run_checks(rec, ctx):
    results = []
    for fn in CHECKS:
        try:
            results.append(fn(rec, ctx))
        except Exception as exc:  # a bug in the inspection tool, reported as such
            results.append(_res(fn.__name__, fn.__name__, "ERROR", "inspection tool", "-", type(exc).__name__))
    return {"summary": dict(Counter(r["result"] for r in results)), "checks": results}


# ----------------------------------------------------------------------------- artifact
def build_artifact(rec: Recorder, ctx: dict) -> dict:
    fs = ctx["final_state"]
    trace = [{k: v for k, v in ev.items()} for ev in rec.node_events]
    llm_runtime = _llm_runtime(ctx.get("llm_client"))
    executed_agents = [
        {"agent": section, "attempts": len(_runs(rec, key))}
        for key, section in AGENT_SECTIONS.items()
    ]
    artifact = {
        "schema_version": SCHEMA_VERSION, "privacy_notice": PRIVACY_NOTICE, "data_source_legend": LEGEND,
        "run_metadata": {
            "run_id": clean_str(ctx["run_id"], 80), "started_at": clean_str(ctx["started_at"], 80),
            "duration_ms": rec.now_ms(),
            "mode": clean_str(ctx["mode"], 80), "mode_label": clean_str(ctx["mode_label"], 120),
            "input_source": clean_str(ctx["input_source"], 80) if ctx.get("input_source") else "unavailable",
            "user": ctx.get("user") if isinstance(ctx.get("user"), int) else "unavailable",
            "target_career_requested": ctx.get("target_requested"),
            "target_career_final": fs.get("target_career_id"), "final_status": fs.get("final_status"),
            "verified": fs.get("final_status") == "VERIFIED", "revision_count": fs.get("revision_count"),
            "max_revisions": ctx.get("max_revisions"), "input_document": _safe_document(
                ctx.get("input_document", ctx.get("document"))),
            "redaction": _safe_context_values(ctx.get("redaction"), ("types", "counts", "total")),
            "llm": {**_safe_context_values(
                ctx.get("llm"), ("client_type", "provider", "model", "test_double")),
                    "calls_total": len(rec.llm),
                    "calls_failed": sum(1 for e in rec.llm if e["error"])},
            "llm_runtime": llm_runtime,
            "prompt_identities": [
                {"stage": call["stage"], "prompt_id": call["prompt_id"],
                 "system_prompt_sha256": call["system_prompt_sha256"],
                 "prompt_sha256": call["prompt_sha256"]}
                for call in rec.llm
            ],
            "per_call_token_limits": [
                {"stage": call["stage"], "prompt_id": call["prompt_id"],
                 "max_tokens": call["max_tokens"], "source": call["max_tokens_source"]}
                for call in rec.llm
            ],
            "application_retry_behavior": {
                "provider_calls": llm_runtime.get("application_retries", "unavailable"),
                "workflow_revision_cap": ctx.get("max_revisions"),
                "workflow_revision_count": fs.get("revision_count"),
            },
            "scoring_weights": to_jsonable(ctx.get("scoring_weights")),
            "versions": _safe_context_values(ctx.get("versions"), ("python", "google_genai_sdk")),
            "kb_counts_before": _safe_context_values(ctx.get("kb_counts_before"), (
                "careers", "skills", "career_skills", "occupations", "sources")),
            "kb_counts_after": _safe_context_values(ctx.get("kb_counts_after"), (
                "careers", "skills", "career_skills", "occupations", "sources")),
            "kb_unchanged": ctx.get("kb_counts_before") == ctx.get("kb_counts_after"),
            "kb_version": "unavailable (not exposed by the implementation; Step 16 scope)",
            "git_commit": (
                ctx["git_commit"] if isinstance(ctx.get("git_commit"), str)
                and re.fullmatch(r"[A-Fa-f0-9]{40,64}", ctx["git_commit"])
                else "unavailable"
            ),
            "harness_error": _safe_errors(ctx.get("harness_error")) if ctx.get("harness_error") else []},
        "workflow_execution": {
            "nodes_in_order": [event["node"] for event in trace],
            "agents": executed_agents,
            "revision_transitions": _revision_transitions(rec, trace),
            "node_start_observability": (
                "Agent start times are recorded by the agent proxies; graph-only node start times are "
                "unavailable because LangGraph update streaming exposes completed node updates."
            ),
        },
        "execution_trace": trace,
        **{section: _agent_section(rec, key, ctx) for key, section in AGENT_SECTIONS.items()},
        "cross_stage_checks": run_checks(rec, ctx),
        "final_output": {"final_status": fs.get("final_status"), "verified": fs.get("final_status") == "VERIFIED",
                         "revision_count": fs.get("revision_count"), "target_career_id": fs.get("target_career_id"),
                         "errors": _safe_errors(fs.get("errors", [])),
                         "state_keys": sorted(k for k in fs if k != "redacted_profile_text"),
                         "api_response": "not recorded (inspection runs the workflow, not the HTTP layer)"},
        "instrumentation_warnings": rec.warnings,
    }
    clean = to_jsonable(artifact, str_limit=10 ** 9)   # idempotent final scrub; keeps earlier truncation
    return json.loads(json.dumps(clean, ensure_ascii=False))