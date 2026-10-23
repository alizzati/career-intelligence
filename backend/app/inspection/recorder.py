"""Manual-validation instrumentation (inspection only; never used by normal API runs).

Observes the REAL CareerWorkflow. It never changes what an agent receives or returns:
proxies forward the original arguments and hand back the original object.
Every recording step is fail-open: a recording problem becomes a warning, never an exception
inside the workflow. No CV text, full prompt, raw LLM response, API key or account e-mail is stored.
"""
from __future__ import annotations

import dataclasses
import datetime as _dt
import hashlib
import json
import os
import re
import threading
import time
import traceback
from collections import Counter
from contextlib import contextmanager
from typing import Any

from app.services.pii_redaction_service import redact_pii

STR_LIMIT = 600
_SECRET = re.compile(
    r"(AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9_\-]{20,}|(?i:api[_-]?key|secret|password)\s*[:=]\s*\S+)"
)
# Hex digests (sha256, git SHA) are identifiers, not PII. Without this exemption a digest that
# contains exactly 16 consecutive decimal digits is rewritten by the Indonesian-ID redaction pattern.
# The lookahead requires at least one a-f letter so an all-digit number is still redacted.
_DIGEST = re.compile(r"(?=[0-9]*[a-fA-F])[0-9a-fA-F]{32,128}")
# Identifier-like dictionary keys are structure, not content: keep them byte-for-byte.
_SAFE_KEY = re.compile(r"[A-Za-z0-9_.:\-]{1,120}")
_LONG_DIGITS = re.compile(r"\d{9,}")

KB_READS = ("get_all_skills", "get_all_careers", "get_career", "get_career_skills",
            "get_occupations_for_career", "get_occupation_competencies",
            "get_skill_evidence", "get_occupational_context")
DB_READS = ("get_user_full_profile",)
DB_WRITES = ("add_education", "add_experience", "add_project", "add_certification",
             "add_user_skill", "add_skill_evidence")

_PROMPT_LABELS = (
    ("information-extraction component", "profile_extraction"),
    ("narrative-explanation component", "career_reasoning"),
    ("narrative layer of a skill-gap report", "skill_gap_narrative"),
    ("learning-focus list", "roadmap_summary"),
    ("semantic grounding checker", "verification_semantic"),
)
_UNSET = object()


# ----------------------------------------------------------------------------- sanitizing
def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()


def clean_str(value: str, limit: int = STR_LIMIT) -> str:
    """PII/secret-redacted, length-capped copy. ALWAYS returns a str (never None)."""
    if not isinstance(value, str):
        value = str(value)
    if _DIGEST.fullmatch(value):
        return value
    text = _SECRET.sub("[REDACTED_SECRET]", redact_pii(value).redacted_text)
    if len(text) > limit:
        return f"{text[:limit]}...[truncated; {len(text)} chars; sha256:{sha256_text(text)[:12]}]"
    return text


def _clean_key(key: Any) -> str:
    text = str(key)
    if _SAFE_KEY.fullmatch(text) and not _LONG_DIGITS.search(text):
        return text
    return clean_str(text, 120)


def to_jsonable(obj: Any, *, str_limit: int = STR_LIMIT, _depth: int = 0) -> Any:
    """JSON-safe copy; every string is PII/secret-redacted and length-capped."""
    if _depth > 12:
        return "[max depth]"
    kw = {"str_limit": str_limit, "_depth": _depth + 1}
    if obj is None or isinstance(obj, (bool, int)):
        return obj
    if isinstance(obj, float):
        return obj if obj == obj and abs(obj) != float("inf") else str(obj)
    if isinstance(obj, str):
        return clean_str(obj, str_limit)
    if isinstance(obj, (_dt.datetime, _dt.date)):
        return obj.isoformat()
    if hasattr(obj, "model_dump"):
        return to_jsonable(obj.model_dump(), **kw)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return to_jsonable(dataclasses.asdict(obj), **kw)
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            name = _clean_key(k)
            if name in out:                      # never silently overwrite a colliding key
                n = 2
                while f"{name}#{n}" in out:
                    n += 1
                name = f"{name}#{n}"
            out[name] = to_jsonable(v, **kw)
        return out
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_jsonable(v, **kw) for v in obj]
    return {"unserializable_type": type(obj).__name__}


def describe_exception(exc: BaseException) -> dict:
    """Return exception metadata without retaining potentially sensitive messages."""
    info: dict[str, Any] = {
        "type": type(exc).__name__,
        "module": type(exc).__module__,
    }
    code = getattr(exc, "code", None)
    if isinstance(code, int) and not isinstance(code, bool):
        info["code"] = code
    status = getattr(exc, "status", None)
    if isinstance(status, int) and not isinstance(status, bool):
        info["status"] = status
    elif isinstance(status, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", status):
        info["status"] = status
    frames = traceback.extract_tb(exc.__traceback__)
    if frames:
        f = frames[-1]
        info["origin"] = f"{os.path.basename(f.filename)}:{f.lineno} in {f.name}"
    if isinstance(exc, json.JSONDecodeError):
        info["json_error_position"] = {"char": exc.pos, "line": exc.lineno, "column": exc.colno}
    return info


def _safe_workflow_errors(errors: Any) -> list[dict]:
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


def describe_args(args, kwargs, limit: int = 80) -> dict:
    return {"args": [to_jsonable(a, str_limit=limit) for a in args],
            "kwargs": {k: to_jsonable(v, str_limit=limit) for k, v in kwargs.items()}}


def _item_id(x):
    for attr in ("user_skill_id", "education_id", "experience_id", "project_id", "certification_id",
                 "evidence_id", "career_id", "relationship_id", "occupation_id", "skill_id"):
        v = getattr(x, attr, None)
        if v is not None:
            return v
    return None


def summarize_result(name: str, result) -> Any:
    """Compact, id-level summary of a read/write result (raw object is kept in memory for checks)."""
    if result is None:
        return None
    if name == "get_user_full_profile":
        return {"skills": [{"user_skill_id": s.user_skill_id, "skill_id": s.skill_id,
                            "claim_sha256": sha256_text(s.claimed_skill)[:16],
                            "evidence_status": s.evidence_status, "evidence_count": len(s.evidence)}
                           for s in result.skills],
                "counts": {k: len(getattr(result, k)) for k in
                           ("education", "experience", "projects", "certifications")}}
    if name == "get_career_skills":
        return {"count": len(result), "skill_ids": [c.skill.skill_id for c in result]}
    if name == "get_skill_evidence":
        return {"count": len(result), "granularity": dict(Counter(e.granularity for e in result)),
                "provenance_ids": sorted({e.provenance.provenance_id for e in result if e.provenance})}
    if name == "get_occupations_for_career":
        return {"count": len(result), "occupation_ids": [o.occupation.occupation_id for o in result]}
    if name == "get_occupation_competencies":
        return {"count": len(result), "standard_ids": [c.standard_id for c in result]}
    if name == "get_occupational_context":
        return {"career_id": result.career.career_id, "occupations": len(result.occupations),
                "career_skills": len(result.career_skills), "competency_standards": len(result.competencies),
                "tasks": {k: len(v) for k, v in result.tasks.items()},
                "technologies": {k: len(v) for k, v in result.technologies.items()},
                "source_mappings": {k: len(v) for k, v in result.source_mappings.items()}}
    if isinstance(result, list):
        return {"count": len(result), "ids": [_item_id(x) for x in result]}
    return {"id": _item_id(result)}


# ----------------------------------------------------------------------------- recorder
class Recorder:
    def __init__(self) -> None:
        self._t0 = time.perf_counter()
        self._lock = threading.Lock()
        self._seq = 0
        self._depth = 0
        self._stack: list[dict] = []
        self._pending_runs: list[int] = []
        self._node_attempts: dict[str, int] = {}
        self.agent_runs: list[dict] = []      # raw objects kept in memory for cross-stage checks
        self.node_events: list[dict] = []
        self.raw_updates: list[dict] = []
        self.llm: list[dict] = []
        self.io: list[dict] = []
        self.raw_io: list[dict] = []
        self.computations: list[dict] = []
        self.warnings: list[str] = []

    # -- helpers
    def _next_seq(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq

    def now_ms(self) -> float:
        return round((time.perf_counter() - self._t0) * 1000, 1)

    def current_stage(self) -> str:
        return self._stack[-1]["agent"] if self._stack else "workflow"

    def _safe(self, fn):
        try:
            return fn()
        except Exception as exc:  # recording must never break the run
            return {"recording_error": type(exc).__name__}

    def _link(self, key: str, idx: int) -> None:
        if self._stack:
            self._stack[-1][key].append(idx)

    # -- agents
    def call_agent(self, name: str, target, args, kwargs):
        attempt = 1 + sum(1 for r in self.agent_runs if r["agent"] == name)
        run = {"seq": self._next_seq(), "agent": name, "attempt": attempt, "t_start_ms": self.now_ms(),
               "duration_ms": None, "raw_args": args, "raw_kwargs": kwargs, "raw_output": None,
               "error": None, "llm_idx": [], "io_idx": [], "comp_idx": []}
        self.agent_runs.append(run)
        self._pending_runs.append(run["seq"])
        self._stack.append(run)
        started = time.perf_counter()
        try:
            output = target.run(*args, **kwargs)
            run["raw_output"] = output
            return output
        except BaseException as exc:
            run["error"] = describe_exception(exc)
            raise
        finally:
            run["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
            self._stack.pop()

    # -- workflow observer (called by CareerWorkflow.run(observer=...))
    def observer(self, event: str, payload: dict) -> None:
        try:
            if event != "node_update":
                return
            node, update = payload["node"], payload.get("update") or {}
            attempt = self._node_attempts[node] = self._node_attempts.get(node, 0) + 1
            self.node_events.append({
                "seq": self._next_seq(), "node": node, "attempt": attempt, "t_ms": self.now_ms(),
                "event": "node_completed",
                "update_keys": sorted(update), "stage": update.get("stage"),
                "final_status": update.get("final_status"), "revision_count": update.get("revision_count"),
                "revision_target": update.get("revision_target"),
                "target_career_id": update.get("target_career_id"),
                "errors": _safe_workflow_errors(update.get("errors")),
                "agent_run_seqs": list(self._pending_runs)})
            self.raw_updates.append(update)
            self._pending_runs.clear()
        except Exception as exc:
            self.warnings.append(f"observer recording failed: {type(exc).__name__}")

    # -- KB / DB / calculator instrumentation
    def _io_wrapper(self, module, name, original, category):
        label = f"{module.__name__.rsplit('.', 1)[-1]}.{name}"

        def wrapper(*args, **kwargs):
            nested = self._depth > 0
            self._depth += 1
            entry = {"seq": self._next_seq(), "stage": self.current_stage(), "category": category,
                     "function": label, "nested": nested, "args": None, "result": None, "error": None}
            raw = {"seq": entry["seq"], "function": name, "stage": entry["stage"], "nested": nested,
                   "args": args, "kwargs": kwargs, "result": None}
            if category == "db_write":
                entry["args"] = {
                    "positional_count": len(args),
                    "positional_types": [type(value).__name__ for value in args],
                    "keyword_names": sorted(kwargs),
                }
            else:
                entry["args"] = self._safe(lambda: describe_args(args, kwargs))
            try:
                result = original(*args, **kwargs)
            except BaseException as exc:
                entry["error"] = describe_exception(exc)
                self._add_io(entry, raw)
                raise
            finally:
                self._depth -= 1
            entry["result"] = self._safe(lambda: summarize_result(name, result))
            raw["result"] = result
            self._add_io(entry, raw)
            return result
        return wrapper

    def _add_io(self, entry, raw) -> None:
        self.io.append(entry)
        self.raw_io.append(raw)
        self._link("io_idx", len(self.io) - 1)

    def _fit_wrapper(self, module_label, original):
        def wrapper(*args, **kwargs):
            result = original(*args, **kwargs)
            try:
                required = args[0] if args else kwargs["required_skills"]
                users = args[1] if len(args) > 1 else kwargs["user_skills"]
                weights = args[2] if len(args) > 2 else kwargs.get("weights")
                self.computations.append({
                    "seq": self._next_seq(), "stage": self.current_stage(), "called_from": module_label,
                    "required_ids": [r.skill_id for r in required], "n_user_skills": len(users),
                    "fit_score": result.fit_score, "total_weight": result.total_weight,
                    "total_contribution": result.total_contribution,
                    "skill_details": [{"skill_id": d.skill_id, "status": d.status, "weight": d.weight,
                                       "contribution": d.contribution} for d in result.skill_details],
                    "weights_used": to_jsonable(weights)})
                self._link("comp_idx", len(self.computations) - 1)
            except Exception as exc:
                self.warnings.append(f"computation record failed: {type(exc).__name__}")
            return result
        return wrapper

    @contextmanager
    def instrument(self, *, rs, us, fit_modules=()):
        """Temporarily wrap read/write functions of the retrieval/user services and the career-fit
        calculator references held by agent modules. Originals are always restored."""
        restore: list[tuple[Any, str, Any]] = []

        def patch(module, name, factory):
            try:
                original = getattr(module, name)
                setattr(module, name, factory(original))
                restore.append((module, name, original))
            except Exception as exc:
                self.warnings.append(f"could not instrument {getattr(module, '__name__', '?')}.{name}: "
                                     f"{type(exc).__name__}")

        for n in KB_READS:
            patch(rs, n, lambda o, n=n: self._io_wrapper(rs, n, o, "kb_read"))
        for n in DB_READS:
            patch(us, n, lambda o, n=n: self._io_wrapper(us, n, o, "db_read"))
        for n in DB_WRITES:
            patch(us, n, lambda o, n=n: self._io_wrapper(us, n, o, "db_write"))
        for module in fit_modules:
            label = module.__name__.rsplit(".", 1)[-1]
            patch(module, "compute_career_fit", lambda o, label=label: self._fit_wrapper(label, o))
        try:
            yield self
        finally:
            for module, name, original in reversed(restore):
                setattr(module, name, original)


class AgentProxy:
    """Forwards .run() to the real agent through the recorder; every other attribute passes through."""

    def __init__(self, recorder: Recorder, name: str, target) -> None:
        self._recorder, self._name, self._target = recorder, name, target

    def run(self, *args, **kwargs):
        return self._recorder.call_agent(self._name, self._target, args, kwargs)

    def __getattr__(self, item):
        return getattr(self._target, item)


class RecordingLLMClient:
    """Wraps an LLMClient. Adds NO calls. Stores sizes, hashes, keys and error info only."""

    def __init__(self, inner, recorder: Recorder) -> None:
        self._inner, self._rec = inner, recorder

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def complete_json(self, system: str, user: str, max_tokens=_UNSET):
        rec = self._rec
        label = next((lbl for key, lbl in _PROMPT_LABELS if key in system), "unknown")
        entry = {"seq": rec._next_seq(), "stage": rec.current_stage(), "prompt_id": label,
                 "system_prompt_sha256": sha256_text(system), "prompt_chars": len(user),
                 "prompt_sha256": sha256_text(user),
                 "max_tokens": None if max_tokens is _UNSET else max_tokens,
                 "max_tokens_source": ("client default (agent passed none)" if max_tokens is _UNSET
                                       else "passed by agent"),
                 "duration_ms": None, "response": None, "error": None}
        started = time.perf_counter()
        try:
            if max_tokens is _UNSET:
                out = self._inner.complete_json(system=system, user=user)
            else:
                out = self._inner.complete_json(system=system, user=user, max_tokens=max_tokens)
        except BaseException as exc:
            entry["error"] = describe_exception(exc)
            raise
        else:
            entry["response"] = rec._safe(lambda: {
                "python_type": type(out).__name__,
                "top_level_keys": sorted(map(str, out)) if isinstance(out, dict) else None,
                "json_chars": len(json.dumps(out, default=str))})
            return out
        finally:
            entry["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
            rec.llm.append(entry)
            rec._link("llm_idx", len(rec.llm) - 1)