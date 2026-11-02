"""Diagnostic CV runner: real endpoint, real workflow, per-CV traces.

What is real
------------
``POST /analysis/cv`` through a FastAPI ``TestClient``, the production route, the
production ``CareerWorkflow`` graph, and the production agents. The only substitution
is the ``get_workflow`` dependency, which is overridden with an instrumented instance of
the SAME ``CareerWorkflow`` class and the SAME agent classes. Request/response schemas,
validation, persistence, and the Step 16 analysis log all execute unchanged.

What is added
-------------
``Recorder`` / ``AgentProxy`` / ``RecordingLLMClient`` / ``Recorder.instrument`` observe
the run. They forward original arguments and return the original objects.

Privacy and safety
------------------
* Every CV is uploaded as ``<cv_id>.<ext>``; the original file name is never stored.
* Artifacts are written only below the configured output directory.
* A synthetic user is created per CV and deleted by exact id afterwards.
* The database must be the isolated test database (same rules as the manual-validation
  gate). Live LLM mode requires ``approve_live_llm=True``.
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Callable

from fastapi.testclient import TestClient

from app.agents import career_recommendation_agent as career_agent_module
from app.agents import verification_agent as verification_agent_module
from app.agents.career_recommendation_agent import CareerRecommendationAgent
from app.agents.learning_roadmap_agent import LearningRoadmapAgent
from app.agents.profile_agent import ProfileAgent
from app.agents.skill_gap_agent import SkillGapAgent
from app.agents.verification_agent import VerificationAgent
from app.api.dependencies import get_workflow
from app.core.config import ApiSettings
from app.diagnostics import trace as trace_mod
from app.inspection.recorder import AgentProxy, Recorder, RecordingLLMClient
from app.main import create_app
from app.services import retrieval_service as rs
from app.services import skill_gap_service
from app.services import user_service as us
from app.workflows.career_workflow import CareerWorkflow

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent

SUPPORTED_SUFFIXES = {".pdf": "application/pdf", ".docx": (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
), ".txt": "text/plain"}

TRACE_SUBDIR = "traces"
LOG_SUBDIR = "analysis_logs"
ERROR_SUBDIR = "errors"

RUN_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")

LIMITATIONS = [
    "Token usage and cost are not exposed by the project LLM client and are recorded as unavailable.",
    "model_version is not exposed separately by the active LLM client; the model identifier is recorded instead.",
    "The Knowledge Base exposes no version identifier, so kb_version cannot be independently verified.",
    "temperature/top_p/top_k/seed are not passed through the LLM client interface and cannot be confirmed.",
    "Pre-workflow failures (unreadable or oversized documents) have no downstream stage data by construction.",
    "Fake-LLM mode exercises the plumbing only and never establishes diagnostic validity.",
    "A process crash between user creation and cleanup can leave one synthetic user row behind.",
]


class DiagnosticSafetyError(RuntimeError):
    """Fail-closed safety violation for diagnostic runs."""


# --------------------------------------------------------------------------- options
@dataclass(frozen=True)
class DiagnosticOptions:
    run_id: str
    input_dir: Path
    output_dir: Path
    approve_live_llm: bool = False
    fake_llm: bool = False
    target_career_id: str | None = None
    selected: tuple[str, ...] = ()
    max_cvs: int | None = None


@dataclass
class _RunState:
    options: DiagnosticOptions
    run_dir: Path
    client: TestClient
    llm_mode: str
    llm_mode_label: str
    llm_client: Any
    database_identity: dict
    cleanup_user: Callable[[int], tuple[bool, dict]]
    started_at: str = field(default_factory=lambda: _now())
    rows: list[dict] = field(default_factory=list)
    cv_records: list[dict] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_run_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}_{uuid.uuid4().hex[:6]}"


def _label_path(path: Path) -> str:
    """Repository-relative when possible, otherwise the bare directory name."""
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except (ValueError, OSError):
        return path.name


# --------------------------------------------------------------------------- inputs
def discover_cvs(input_dir: Path) -> list[Path]:
    if not input_dir.is_dir():
        raise DiagnosticSafetyError(f"Input directory does not exist: {input_dir}")
    files = [
        path
        for path in sorted(input_dir.iterdir(), key=lambda item: item.name.lower())
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES
    ]
    if not files:
        raise DiagnosticSafetyError(
            f"No supported CV files ({', '.join(sorted(SUPPORTED_SUFFIXES))}) found in {input_dir}."
        )
    return files


def select_cvs(files: list[Path], selected: tuple[str, ...]) -> list[Path]:
    if not selected:
        return files
    wanted = {item.strip().lower() for item in selected if item.strip()}
    chosen = [path for path in files if path.name.lower() in wanted or path.stem.lower() in wanted]
    missing = wanted - {path.name.lower() for path in chosen} - {path.stem.lower() for path in chosen}
    if missing:
        raise DiagnosticSafetyError(f"Requested CVs not found in the input directory: {sorted(missing)}")
    return chosen


def cv_identity(payload: bytes, suffix: str, index: int) -> dict:
    """Content identity only. The original file name is deliberately not used or stored."""
    digest = hashlib.sha256(payload).hexdigest()
    cv_id = f"cv{index:02d}_{digest[:8]}"
    fmt = suffix.lstrip(".").lower()
    return {
        "cv_id": cv_id,
        "sha256": digest,
        "format": fmt,
        "size_bytes": len(payload),
        "upload_name": f"{cv_id}.{fmt}",
    }


# --------------------------------------------------------------------------- workflow
class DiagnosticWorkflow(CareerWorkflow):
    """The production workflow, with the recorder composed into its observer."""

    def __init__(self, *, recorder: Recorder, **kwargs: Any) -> None:
        self.recorder = recorder
        self.final_state: dict | None = None
        super().__init__(**kwargs)

    def run(self, user_id, target_career_id=None, raw_profile_text=None, observer=None):
        def compose(event: str, payload: dict) -> None:
            if observer is not None:
                try:
                    observer(event, payload)
                except Exception:  # observation must never break the run
                    pass
            self.recorder.observer(event, payload)

        state = super().run(
            user_id=user_id,
            target_career_id=target_career_id,
            raw_profile_text=raw_profile_text,
            observer=compose,
        )
        self.final_state = state
        return state


def build_instrumented_workflow(recorder: Recorder, llm_client: Any, *, max_revisions: int) -> DiagnosticWorkflow:
    recorded_llm = RecordingLLMClient(llm_client, recorder)
    return DiagnosticWorkflow(
        recorder=recorder,
        llm_client=recorded_llm,
        max_revisions=max_revisions,
        profile_agent=AgentProxy(recorder, "profile", ProfileAgent(recorded_llm)),
        career_recommendation_agent=AgentProxy(
            recorder, "career_recommendation", CareerRecommendationAgent(llm_client=recorded_llm)
        ),
        skill_gap_agent=AgentProxy(recorder, "skill_gap", SkillGapAgent(llm_client=recorded_llm)),
        learning_roadmap_agent=AgentProxy(
            recorder, "roadmap", LearningRoadmapAgent(llm_client=recorded_llm)
        ),
        verification_agent=AgentProxy(
            recorder, "verification", VerificationAgent(llm_client=recorded_llm)
        ),
    )


def _override_for(workflow: CareerWorkflow) -> Callable[[], CareerWorkflow]:
    """A zero-argument dependency override.

    The workflow must NOT be a default argument: FastAPI would inspect it as a
    dependency parameter and deep-copy the default, which fails on live clients.
    """

    def override() -> CareerWorkflow:
        return workflow

    return override


class PlumbingFakeLLM:
    """Deterministic test double for runner plumbing tests ONLY.

    It proves the runner, trace, and artifact writing work. It says nothing about
    real-model behaviour and must never be used for a diagnostic result.
    """

    model_name = "DiagnosticPlumbingFakeLLM"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete_json(self, system: str, user: str, max_tokens: int = 2000):
        if "information-extraction component" in system:
            self.calls.append("profile_extraction")
            return {"skills": [], "evidence": [], "education": [], "experience": [],
                    "projects": [], "certifications": []}
        if "semantic grounding checker" in system:
            self.calls.append("verification_semantic")
            return {"unsupported_claims": []}
        if "Your ONLY job" in system:
            self.calls.append("career_reasoning")
            return {"reasoning": "Plumbing test double; no model was consulted."}
        if "narrative layer of a skill-gap report" in system:
            self.calls.append("skill_gap_narrative")
            return {}
        if "short overview of a learning-focus list" in system:
            self.calls.append("roadmap_summary")
            return {"summary": "Plumbing test double; no model was consulted."}
        raise AssertionError("Unexpected LLM request in the diagnostic plumbing double.")


def resolve_llm_client(options: DiagnosticOptions, injected: Any = None) -> tuple[Any, str, str]:
    if injected is not None:
        return injected, "injected", "Injected client (tests only; not a real provider call)"
    if options.fake_llm and options.approve_live_llm:
        raise DiagnosticSafetyError("Choose exactly one LLM mode: --fake-llm or --approve-live-llm.")
    if options.fake_llm:
        return (
            PlumbingFakeLLM(),
            "fake_llm",
            "Plumbing test double: validates the runner only, never diagnostic validity",
        )
    if not options.approve_live_llm:
        raise DiagnosticSafetyError(
            "Live LLM calls are disabled. Re-run with --approve-live-llm to send the CVs to the "
            "configured provider, or --fake-llm for a plumbing check only."
        )
    from app.api.dependencies import get_llm_client

    client = get_llm_client()
    if client is None:
        raise DiagnosticSafetyError(
            "No LLM client could be constructed (check the provider configuration in backend/.env)."
        )
    return client, "live_llm", "Live provider calls (explicitly approved with --approve-live-llm)"


# --------------------------------------------------------------------------- database
def default_database_seam() -> tuple[dict, Callable[[int], tuple[bool, dict]]]:
    """Reuse the tested manual-validation gate and cleanup, unchanged.

    Both live in ``scripts.manual_validation`` so the delete order and the isolation
    rules have exactly ONE definition.
    """
    from app.core.db import get_engine
    from scripts.manual_validation import (
        ManualValidationSafetyError, _cleanup_synthetic_user, _validate_isolated_db_safety,
    )

    engine = get_engine()
    try:
        identity = _validate_isolated_db_safety(engine)
    except ManualValidationSafetyError as exc:
        raise DiagnosticSafetyError(
            f"Diagnostic runs require the isolated test database. {exc}"
        ) from None

    def cleanup(user_id: int) -> tuple[bool, dict]:
        return _cleanup_synthetic_user(engine, user_id)

    return identity, cleanup


def _git_provenance() -> dict:
    try:
        from scripts.manual_validation import _git_provenance as provenance

        return provenance()
    except Exception:  # pragma: no cover - git may be unavailable
        return {"git_commit": "unavailable", "git_dirty": "unavailable", "git_diff_sha256": None}


# --------------------------------------------------------------------------- LLM metadata
def _unwrap_client(client: Any) -> Any:
    inner, seen = client, set()
    while inner is not None and id(inner) not in seen and hasattr(inner, "_inner"):
        seen.add(id(inner))
        inner = inner._inner
    return inner


def _sdk_version(provider: str) -> str:
    if provider != "GeminiClient":
        return "not applicable"
    try:
        return metadata.version("google-genai")
    except metadata.PackageNotFoundError:
        return "unavailable (google-genai package metadata not installed)"


def model_metadata(llm_client: Any, log_record: dict | None = None) -> dict:
    """Probe the client that actually ran, then let the Step 16 log have the last word."""
    inner = _unwrap_client(llm_client)
    name = getattr(inner, "model", None) or getattr(inner, "model_name", None)
    provider = type(inner).__name__
    result = {
        "model": name if isinstance(name, str) and name.strip() else "unavailable (no model identifier)",
        "model_version": trace_mod.UNAVAILABLE_MODEL_VERSION,
        "provider": provider,
        "sdk_version": _sdk_version(provider),
        "prompt_catalog_version": trace_mod.prompt_catalog_version(),
        "kb_version": trace_mod.UNAVAILABLE_KB_VERSION,
    }
    if isinstance(log_record, dict):
        details = log_record.get("model_details") if isinstance(log_record.get("model_details"), dict) else {}
        result["model"] = log_record.get("model") or result["model"]
        result["model_version"] = log_record.get("model_version") or result["model_version"]
        result["provider"] = details.get("provider") or result["provider"]
        result["sdk_version"] = details.get("sdk_version") or result["sdk_version"]
        identifiers = log_record.get("prompt_version_identifier")
        if isinstance(identifiers, dict) and isinstance(identifiers.get("catalog_version"), str):
            result["prompt_catalog_version"] = identifiers["catalog_version"]
        result["kb_version"] = log_record.get("kb_version") or result["kb_version"]
    return result


# --------------------------------------------------------------------------- environment
_ENV_KEYS = (
    "CAREER_API_ACKNOWLEDGE_NO_AUTH",
    "CAREER_API_ALLOW_REMOTE_CLIENTS",
    "CAREER_ANALYSIS_LOG_DIR",
)


@contextmanager
def _diagnostic_environment(run_dir: Path):
    previous = {key: os.environ.get(key) for key in _ENV_KEYS}
    os.environ["CAREER_API_ACKNOWLEDGE_NO_AUTH"] = "true"
    os.environ["CAREER_API_ALLOW_REMOTE_CLIENTS"] = "true"
    # Route the existing Step 16 writer into this run; its schema and semantics are unchanged.
    os.environ["CAREER_ANALYSIS_LOG_DIR"] = str(run_dir / LOG_SUBDIR)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


# --------------------------------------------------------------------------- one CV
def _runs_for(recorder: Recorder, agent: str) -> list[dict]:
    return [run for run in recorder.agent_runs if run.get("agent") == agent]


def _stage_from_agent(recorder: Recorder, agent: str, builder, **kwargs) -> dict:
    runs = _runs_for(recorder, agent)
    if not runs:
        return trace_mod.stage(
            "not_reached", notes=[f"The {agent} agent did not execute (an earlier stage ended)."]
        )
    latest = runs[-1]
    duration = latest.get("duration_ms")
    if latest.get("raw_output") is None:
        return trace_mod.stage(
            "failed",
            duration_ms=duration,
            error=latest.get("error"),
            notes=[f"The {agent} agent raised before producing a result."],
        )
    return builder(latest["raw_output"], duration_ms=duration, **kwargs)


def _capture_analysis_log(log_dir: Path, before: set[Path], cv_id: str) -> tuple[dict | None, str | None]:
    created = sorted(set(log_dir.glob("*.json")) - before)
    if not created:
        return None, None
    source = created[0]
    try:
        record = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, None
    target = log_dir / f"{cv_id}.analysis_log.json"
    try:
        if source != target:
            if target.exists():
                target.unlink()
            os.replace(source, target)
    except OSError:
        return record, f"{LOG_SUBDIR}/{source.name}"
    return record, f"{LOG_SUBDIR}/{target.name}"


def _run_one_cv(
    state: _RunState,
    *,
    index: int,
    path: Path,
    run_section_base: dict,
    settings: ApiSettings,
) -> dict:
    payload = path.read_bytes()
    cv = cv_identity(payload, path.suffix, index)
    recorder = Recorder()
    workflow = build_instrumented_workflow(
        recorder, state.llm_client, max_revisions=settings.max_revisions
    )
    state.client.app.dependency_overrides[get_workflow] = _override_for(workflow)

    log_dir = state.run_dir / LOG_SUBDIR
    user_id: int | None = None
    response = None
    duration_ms: float | None = None
    runner_error: dict | None = None
    cleanup_ok: bool | None = None
    cleanup_details: dict | None = None
    warnings: list[str] = []

    try:
        user_id = us.create_user(
            f"diagnostic-{state.options.run_id[:40]}-{cv['cv_id']}@example.invalid",
            "Diagnostic Synthetic Candidate",
        ).user_id
        before = set(log_dir.glob("*.json"))
        started = time.perf_counter()
        with recorder.instrument(
            rs=rs,
            us=us,
            fit_modules=(career_agent_module, skill_gap_service, verification_agent_module),
        ):
            response = state.client.post(
                "/analysis/cv",
                data={
                    "user_id": str(user_id),
                    **({"target_career_id": state.options.target_career_id}
                       if state.options.target_career_id else {}),
                },
                files={"file": (cv["upload_name"], payload, SUPPORTED_SUFFIXES[path.suffix.lower()])},
            )
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        analysis_log, analysis_log_path = _capture_analysis_log(log_dir, before, cv["cv_id"])
    except Exception as exc:  # types only: messages may carry sensitive text
        analysis_log, analysis_log_path = None, None
        runner_error = {"stage": "runner", "error_type": type(exc).__name__}
    finally:
        payload = b""

    if user_id is not None:
        try:
            cleanup_ok, cleanup_details = state.cleanup_user(user_id)
        except Exception as exc:  # pragma: no cover - defensive
            cleanup_ok, cleanup_details = False, {"error_type": type(exc).__name__}
        if not cleanup_ok:
            warnings.append("synthetic_user_cleanup_failed")
            (state.run_dir / ERROR_SUBDIR / f"{cv['cv_id']}.cleanup.txt").write_text(
                json.dumps({"user_id_recorded": False, "details": cleanup_details}, indent=2),
                encoding="utf-8",
            )

    body: dict | None = None
    if response is not None:
        try:
            body = response.json()
        except Exception:
            body = None
    http_status = response.status_code if response is not None else None
    error_body = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else None

    document = body.get("document") if isinstance(body, dict) else None
    redaction = body.get("redaction") if isinstance(body, dict) else None

    stages: dict[str, dict] = {}
    stages["extraction"] = trace_mod.build_extraction_stage(
        document=document,
        redaction=redaction,
        http_status=http_status,
        error_code=error_body.get("code") if error_body else None,
        error_message=error_body.get("message") if error_body else None,
        # The extractor is not separately instrumented; the request duration is
        # recorded once under analysis.duration_ms and stages.final.duration_ms.
        duration_ms=None,
    )
    stages["profile"] = _stage_from_agent(recorder, "profile", trace_mod.build_profile_stage)
    stages["okb_retrieval"] = trace_mod.build_okb_retrieval_stage(recorder.raw_io)
    stages["career_fit"] = _stage_from_agent(
        recorder, "career_recommendation", trace_mod.build_career_fit_stage,
        computations=recorder.computations,
    )
    stages["skill_gap"] = _stage_from_agent(recorder, "skill_gap", trace_mod.build_skill_gap_stage)
    stages["roadmap"] = _stage_from_agent(recorder, "roadmap", trace_mod.build_roadmap_stage)
    stages["verification"] = _stage_from_agent(
        recorder, "verification", trace_mod.build_verification_stage,
        revision_count=(workflow.final_state or {}).get("revision_count"),
        revision_limit=workflow.max_revisions,
    )

    final_state = workflow.final_state or {}
    response_final = body.get("final_status") if isinstance(body, dict) else None
    career_runs = _runs_for(recorder, "career_recommendation")
    ranked = (
        career_runs[-1].get("raw_output")
        if career_runs and career_runs[-1].get("raw_output") is not None
        else (body.get("recommendations") if isinstance(body, dict) else None)
    )
    stages["final"] = trace_mod.build_final_stage(
        final_status=response_final or final_state.get("final_status"),
        verified=body.get("verified") if isinstance(body, dict) else None,
        target_career_id=(
            (body.get("target_career_id") if isinstance(body, dict) else None)
            or final_state.get("target_career_id")
        ),
        revision_count=final_state.get("revision_count"),
        revision_limit=workflow.max_revisions,
        revision_target=final_state.get("revision_target"),
        last_stage=final_state.get("stage"),
        errors=final_state.get("errors"),
        ranked=ranked,
        duration_ms=duration_ms,
    )

    analysis = {
        "source": "cv_upload",
        "http_status": http_status,
        "duration_ms": duration_ms,
        "response_final_status": response_final,
        "analysis_id": (analysis_log or {}).get("analysis_id"),
        "analysis_log_path": analysis_log_path,
        "error": (
            {
                "code": error_body.get("code"),
                "stage": error_body.get("stage"),
                "error_type": error_body.get("error_type"),
                "message": error_body.get("message"),
            }
            if error_body else None
        ),
        "runner_error": runner_error,
    }

    observations = trace_mod.observe_consistency(analysis=analysis, stages=stages)
    cv["trace_path"] = f"{TRACE_SUBDIR}/{cv['cv_id']}.trace.json"

    run_section = dict(run_section_base)
    run_section.update(model_metadata(state.llm_client, analysis_log))

    trace = trace_mod.build_trace(
        run=run_section,
        cv=cv,
        analysis=analysis,
        stages=stages,
        recorder=recorder,
        warnings=warnings,
        privacy={
            "synthetic_user_created": user_id is not None,
            "synthetic_user_deleted": cleanup_ok,
            "cleanup": cleanup_details,
            "database": state.database_identity.get("name"),
        },
        consistency_observations=observations,
    )
    (state.run_dir / TRACE_SUBDIR / f"{cv['cv_id']}.trace.json").write_text(
        json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    state.rows.append(trace_mod.build_csv_row(trace))
    record = {
        "cv_id": cv["cv_id"],
        "cv_sha256": cv["sha256"],
        "file_size_bytes": cv["size_bytes"],
        "file_format": cv["format"],
        "http_status": http_status,
        "final_status": stages["final"]["payload"].get("final_status"),
        "analysis_id": analysis["analysis_id"],
        "trace_path": cv["trace_path"],
        "analysis_log_path": analysis_log_path,
        "cleanup_ok": cleanup_ok,
        "runner_error": runner_error,
        "warnings": warnings,
    }
    state.cv_records.append(record)
    return record


# --------------------------------------------------------------------------- outputs
def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(trace_mod.CSV_COLUMNS), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_manifest(
    state: _RunState,
    *,
    status: str,
    finished_at: str | None,
    config: dict,
    selected_cv_ids: list[str],
) -> dict:
    rows = state.rows
    completed = sum(1 for row in rows if row.get("http_status") == 200)
    errored = sum(1 for record in state.cv_records if record.get("http_status") is None)
    failed = len(rows) - completed
    manifest = {
        "schema_version": trace_mod.MANIFEST_SCHEMA_VERSION,
        "run_id": state.options.run_id,
        "started_at": state.started_at,
        "finished_at": finished_at,
        "status": status,
        "llm_mode": state.llm_mode,
        "llm_mode_label": state.llm_mode_label,
        "database": state.database_identity,
        "config": config,
        "input": {
            "directory_label": _label_path(state.options.input_dir),
            "cv_count": len(rows),
            # Selection is recorded as anonymized cv_ids only: the values passed to
            # --cv are original file names and must never reach an artifact.
            "selection_restricted": bool(state.options.selected),
            "selected_cv_ids": selected_cv_ids,
        },
        "counts": {"total": len(rows), "completed": completed, "failed": failed, "errored": errored},
        "cvs": state.cv_records,
        "privacy": {
            "raw_cv_text_persisted": False,
            "original_filename_persisted": False,
            "synthetic_users_deleted": all(
                record.get("cleanup_ok") is not False for record in state.cv_records
            ),
        },
        "limitations": LIMITATIONS,
    }
    (state.run_dir / "run.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return manifest


def _write_summary(state: _RunState, manifest: dict) -> None:
    lines = [
        f"# Diagnostic CV run {state.options.run_id}",
        "",
        f"- Status: **{manifest['status']}**",
        f"- LLM mode: `{state.llm_mode}` ({state.llm_mode_label})",
        f"- Started: {manifest['started_at']}",
        f"- Finished: {manifest['finished_at'] or 'incomplete'}",
        f"- CVs: total {manifest['counts']['total']}, completed {manifest['counts']['completed']}, "
        f"failed {manifest['counts']['failed']}, errored {manifest['counts']['errored']}",
        f"- Database: `{state.database_identity.get('name')}`",
        "",
        "Diagnostic artifacts only. These are not formal B0/B2/B3/F experiment results.",
        "",
        "| cv_id | HTTP | final_status | top1 | target | gap (E/C/M/U) | verification | trace |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in state.rows:
        gap = "/".join(
            str(row.get(column) if row.get(column) is not None else "-")
            for column in (
                "gap_matched_evidenced_count",
                "gap_matched_claimed_only_count",
                "gap_missing_count",
                "gap_unmatched_user_claims_count",
            )
        )
        lines.append(
            "| {cv} | {http} | {final} | {top1} | {target} | {gap} | {verification} | `{trace}` |".format(
                cv=row.get("cv_id") or "-",
                http=row.get("http_status") if row.get("http_status") is not None else "-",
                final=row.get("final_status") or "-",
                top1=row.get("top1_career_id") or "-",
                target=row.get("target_career_id") or "-",
                gap=gap,
                verification=row.get("verification_status") or "-",
                trace=row.get("trace_path") or "-",
            )
        )
    lines += ["", "## Limitations", ""] + [f"- {item}" for item in manifest["limitations"]] + [""]
    (state.run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------- entry point
def run_diagnostic(
    options: DiagnosticOptions,
    *,
    llm_client: Any = None,
    database: Callable[[], tuple[dict, Callable[[int], tuple[bool, dict]]]] | None = None,
) -> dict:
    """Run every selected CV through the real endpoint and write the artifacts.

    ``llm_client`` and ``database`` are testing seams only; the CLI passes neither.
    """
    if not RUN_ID_PATTERN.fullmatch(options.run_id):
        raise DiagnosticSafetyError(
            "run_id must start alphanumeric and contain only letters, digits, '.', '_' or '-'."
        )
    run_dir = Path(options.output_dir) / options.run_id
    if run_dir.exists():
        raise DiagnosticSafetyError(
            f"Refusing to overwrite an existing diagnostic run directory: {run_dir}"
        )

    files = select_cvs(discover_cvs(Path(options.input_dir)), options.selected)
    if options.max_cvs is not None:
        files = files[: max(1, options.max_cvs)]
    # Anonymized identities of the selected CVs, for the manifest (never the raw names).
    selected_cv_ids = [
        cv_identity(path.read_bytes(), path.suffix, index)["cv_id"]
        for index, path in enumerate(files, start=1)
    ]

    resolved_llm, llm_mode, llm_mode_label = resolve_llm_client(options, llm_client)
    identity, cleanup_user = (database or default_database_seam)()

    settings = ApiSettings.from_env()
    provenance = _git_provenance()
    app = create_app()
    run_dir.mkdir(parents=True, exist_ok=False)
    for sub in (TRACE_SUBDIR, LOG_SUBDIR, ERROR_SUBDIR):
        (run_dir / sub).mkdir(parents=True, exist_ok=True)

    run_section_base = {
        "run_id": options.run_id,
        "started_at": _now(),
        "llm_mode": llm_mode,
        "llm_mode_label": llm_mode_label,
        "git_commit": provenance.get("git_commit"),
        "git_dirty": provenance.get("git_dirty"),
        "git_diff_sha256": provenance.get("git_diff_sha256"),
        "database": identity,
        "versions": {
            "python": sys.version.split()[0],
            "trace_schema": trace_mod.TRACE_SCHEMA_VERSION,
            "manifest_schema": trace_mod.MANIFEST_SCHEMA_VERSION,
        },
        "config": {
            "max_revisions": settings.max_revisions,
            "max_upload_bytes": settings.max_upload_bytes,
            "max_pdf_pages": settings.max_pdf_pages,
            "target_career_id": options.target_career_id,
            "max_cvs": options.max_cvs,
        },
    }
    config = dict(run_section_base["config"])

    with _diagnostic_environment(run_dir):
        with TestClient(app) as client:
            state = _RunState(
                options=options,
                run_dir=run_dir,
                client=client,
                llm_mode=llm_mode,
                llm_mode_label=llm_mode_label,
                llm_client=resolved_llm,
                database_identity=identity,
                cleanup_user=cleanup_user,
                started_at=run_section_base["started_at"],
            )
            for index, path in enumerate(files, start=1):
                try:
                    _run_one_cv(
                        state, index=index, path=path,
                        run_section_base=run_section_base, settings=settings,
                    )
                except Exception as exc:  # keep going: one broken CV must not stop the run
                    cv_id = f"cv{index:02d}_failed"
                    (run_dir / ERROR_SUBDIR / f"{cv_id}.error.txt").write_text(
                        json.dumps({"error_type": type(exc).__name__, "stage": "runner"}, indent=2),
                        encoding="utf-8",
                    )
                    warnings = [f"runner failed for CV index {index}: {type(exc).__name__}"]
                    state.cv_records.append(
                        {"cv_id": cv_id, "http_status": None, "final_status": None,
                         "trace_path": None, "warnings": warnings}
                    )
                _write_csv(run_dir / "manifest.csv", state.rows)
                _write_manifest(
                    state, status="RUNNING", finished_at=None, config=config,
                    selected_cv_ids=selected_cv_ids,
                )

    finished_at = _now()
    errored = any(record.get("http_status") is None for record in state.cv_records)
    status = "PASS" if state.rows and not errored else "FAIL"
    manifest = _write_manifest(
        state, status=status, finished_at=finished_at, config=config,
        selected_cv_ids=selected_cv_ids,
    )
    _write_summary(state, manifest)
    _write_csv(run_dir / "manifest.csv", state.rows)

    return {
        "status": status,
        "run_id": options.run_id,
        "run_dir": str(run_dir),
        "run_manifest": str(run_dir / "run.json"),
        "manifest_csv": str(run_dir / "manifest.csv"),
        "summary": str(run_dir / "summary.md"),
        "llm_mode": llm_mode,
        "counts": manifest["counts"],
    }
