"""Stage 2C experiment runner: one frozen bundle, four configurations, isolated records.

The runner is deliberately small.  It does not preprocess a CV, choose a career
for the user, calculate career fit, or recompute skill gaps.  It hands the same
``FrozenProfileBundle`` to the existing ``CareerWorkflow`` paths and records what
happened.  Persistence is file-based and separate from ``analysis_log/1.0`` and
the application database.
"""
from __future__ import annotations

import concurrent.futures as _futures
import datetime as _dt
import json
import os
import threading
import time as _time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.evaluation.adapters import case_from_analysis_record
from app.evaluation.baseline_inference import (
    BaselineInferenceAgent,
    CareerOutputLabel,
    FrozenProfileBundle,
)
from app.evaluation.configurations import get_configuration
from app.evaluation.experiment_store import (
    ExperimentManifest,
    ExperimentRunRecord,
    ExperimentStore,
    FailureKind,
    RunSummary,
)
from app.evaluation.schemas import ConfigId
from app.inspection.recorder import clean_str, sha256_text, to_jsonable
from app.services.analysis_log_service import _model_metadata, _prompt_identifiers
from app.workflows.career_workflow import CareerWorkflow


ALL_CONFIGURATIONS: tuple[ConfigId, ...] = ("B0", "B2", "B3", "F")
BUNDLE_SCHEMA_VERSION = "frozen_profile_bundle/1.0"
TECHNOLOGY_NOTE = (
    "UNRESOLVED_RESEARCH_DECISION: the 120 Lightcast TECHNOLOGY records remain "
    "in the OKB; their contribution to the career-recommendation percentage is "
    "unresolved and no weight or scoring formula is applied here."
)
_FORBIDDEN_METADATA_KEYS = frozenset({
    "ground_truth",
    "ground_truth_career_ids",
    "ground_truth_labels",
    "groundtruth",
    "label",
    "labels",
    "relevance",
    "relevance_labels",
    "expected_career",
    "expected_career_id",
    "expected_skills",
    "gold_label",
    "gold_labels",
    "target_career",
    "target_career_id",
    "annotation",
    "annotations",
})


class LLMCallProvenance:
    """Capture request identity without retaining prompt text or model output."""
    def __init__(self, case_id: str, run_id: str, configuration_id: str):
        self.case_id = case_id
        self.run_id = run_id
        self.configuration_id = configuration_id
        self._calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def wrap(self, client: Any):
        return _ProvenanceLLMClient(client, self)

    def record(self, client: Any, system: Any, user: Any, max_tokens: Any,
               started: float, error: BaseException | None) -> None:
        row = {
            "case_id": self.case_id,
            "run_id": self.run_id,
            "configuration_id": self.configuration_id,
            "call_index": 0,
            "system_prompt_sha256": sha256_text(system) if isinstance(system, str) else None,
            "user_prompt_sha256": sha256_text(user) if isinstance(user, str) else None,
            "max_tokens": max_tokens if isinstance(max_tokens, (int, float, str, type(None))) else None,
            "model": str(getattr(client, "model", getattr(client, "model_name", "unavailable"))),
            "temperature": getattr(client, "temperature", None),
            "top_p": getattr(client, "top_p", None),
            "top_k": getattr(client, "top_k", None),
            "duration_ms": round((_time.perf_counter() - started) * 1000, 2),
            "retry_count": max(0, int(getattr(client, "last_call_retry_count", 0) or 0)),
            "outcome": "failure" if error else "success",
            "failure_type": type(error).__name__ if error else None,
        }
        with self._lock:
            row["call_index"] = len(self._calls) + 1
            self._calls.append(row)

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(row) for row in self._calls]


class _ProvenanceLLMClient:
    def __init__(self, client: Any, recorder: LLMCallProvenance):
        self._client = client
        self._recorder = recorder

    def __getattr__(self, name: str):
        return getattr(self._client, name)

    def complete_json(self, *args, **kwargs):
        system = kwargs.get("system", args[0] if args else None)
        user = kwargs.get("user", args[1] if len(args) > 1 else None)
        max_tokens = kwargs.get("max_tokens", args[2] if len(args) > 2 else None)
        started = _time.perf_counter()
        error = None
        try:
            return self._client.complete_json(*args, **kwargs)
        except BaseException as exc:
            error = exc
            raise
        finally:
            self._recorder.record(self._client, system, user, max_tokens, started, error)
_VERIFICATION_VALUES = frozenset({"PASS", "FAIL", "REVISE"})
_ISOLATED_DB_SUFFIXES = ("_eval", "_test")
_FORBIDDEN_DATABASES = frozenset({
    "career_intelligence",
    "career_intelligence_main",
    "postgres",
    "template0",
    "template1",
})


class SharedInputError(ValueError):
    """The case/run/bundle/metadata input is invalid, so no configuration runs."""


class RetrievalFailure(RuntimeError):
    """The OKB snapshot could not be read or validated."""


class IsolationError(RuntimeError):
    """Real execution was pointed at a database that is not an isolated target."""


class ExperimentTimeoutError(TimeoutError):
    """A workflow exceeded its configured wall-clock timeout."""


class OkbSnapshot(BaseModel):
    model_config = {"extra": "forbid"}

    fingerprint: str
    counts: dict[str, int] = Field(default_factory=dict)
    components: list[str] = Field(default_factory=list)

    @field_validator("fingerprint")
    @classmethod
    def _fingerprint(cls, value: str) -> str:
        if not isinstance(value, str) or len(value) != 64 or any(
            char not in "0123456789abcdef" for char in value
        ):
            raise ValueError("OKB fingerprint must be a 64-character lowercase sha256")
        return value


@dataclass(frozen=True)
class PreparedExperiment:
    case_id: str
    run_id: str
    bundle: FrozenProfileBundle
    bundle_fingerprint: str
    metadata: dict[str, Any]
    git_provenance: dict[str, Any]


@dataclass
class PairedExperimentResult:
    manifest: ExperimentManifest
    records: list[ExperimentRunRecord]


def fingerprint_bundle(bundle: FrozenProfileBundle) -> str:
    """Deterministic sha256 of the validated frozen bundle (no per-config input)."""
    payload = {
        "schema": BUNDLE_SCHEMA_VERSION,
        "bundle": bundle.model_dump(mode="json"),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_text(canonical)


def _load_okb_snapshot_rows() -> dict[str, list[dict[str, Any]]]:
    """Load every OKB component through the deterministic repository reader."""
    from app.core.db import engine
    from app.repositories import okb_repository

    with engine.connect() as conn:
        return okb_repository.fetch_okb_snapshot_rows(conn)


def compute_okb_snapshot() -> OkbSnapshot:
    """Fingerprint the complete OKB state used by B2/B3/F and the agents.

    Coverage includes careers, occupations, career-occupation mappings,
    skills, skill groups, career-skill relationships, SKKNI standards,
    competency units/skills, occupation competencies, technologies, tasks,
    provenance records, occupational source mappings, and skill source
    evidence. Any content or relationship change in these components changes
    the fingerprint.
    """
    components = _load_okb_snapshot_rows()
    payload = {
        "schema": "okb_snapshot/2.0",
        "components": components,
    }
    fingerprint = sha256_text(
        json.dumps(
            payload, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, default=str,
        )
    )
    return OkbSnapshot(
        fingerprint=fingerprint,
        counts={name: len(rows) for name, rows in components.items()},
        components=list(components),
    )


def database_name() -> str:
    """Return the configured database name without exposing credentials."""
    url = os.environ.get("CAREER_DB_URL", "").strip()
    configured = os.environ.get("CAREER_DB_NAME", "").strip()
    if url:
        try:
            from sqlalchemy.engine import make_url

            url_database = make_url(url).database or "unavailable"
        except Exception:
            parsed = urllib.parse.urlparse(url)
            url_database = parsed.path.lstrip("/") or "unavailable"
        if configured and configured != url_database:
            return "configuration_mismatch"
        return url_database
    return configured or "unavailable"


def assert_isolated_database(name: str | None = None) -> str:
    """Fail closed unless the target is an explicitly isolated evaluation DB."""
    target = name if name is not None else database_name()
    if target == "configuration_mismatch":
        raise IsolationError(
            "CAREER_DB_NAME disagrees with the database named by CAREER_DB_URL; refusing real execution"
        )
    configured_url = os.environ.get("CAREER_DB_URL", "").strip()
    if configured_url:
        url_target = database_name()
        if url_target == "configuration_mismatch" or target != url_target:
            raise IsolationError(
                "the requested isolated target does not match the database named by CAREER_DB_URL"
            )
    if target in _FORBIDDEN_DATABASES:
        raise IsolationError(
            f"refusing to run against protected database {target!r}; use an isolated "
            "evaluation database such as career_intelligence_eval"
        )
    if target == "unavailable":
        raise IsolationError(
            "database name is unavailable; refusing real execution because isolation "
            "cannot be verified"
        )
    if not target.endswith(_ISOLATED_DB_SUFFIXES):
        raise IsolationError(
            f"database {target!r} is not an isolated evaluation target; expected a name "
            "ending in _eval or _test"
        )
    return target


def _default_git_provenance() -> dict[str, Any]:
    try:
        from scripts.manual_validation import _git_provenance

        return _git_provenance()
    except Exception:
        return {"git_commit": "unavailable", "git_dirty": "unavailable", "git_diff_sha256": None}


def _source_state_fingerprint(provenance: dict[str, Any]) -> str | None:
    identity = {
        "git_commit": provenance.get("git_commit"),
        "git_dirty": provenance.get("git_dirty"),
        "git_diff_sha256": provenance.get("git_diff_sha256"),
    }
    if identity["git_commit"] in (None, "unavailable"):
        return None
    return sha256_text(json.dumps(identity, sort_keys=True, separators=(",", ":")))


def _mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return dump()
    return {}


def _reject_ground_truth_keys(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).strip().lower()
            if lowered in _FORBIDDEN_METADATA_KEYS or lowered.startswith("ground_truth"):
                raise SharedInputError(
                    f"experiment metadata must not contain ground-truth key {path}{key!r}"
                )
            _reject_ground_truth_keys(item, f"{path}{key}.")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_ground_truth_keys(item, f"{path}[{index}].")


def _classify_exception(exc: BaseException) -> tuple[FailureKind, str, str, str | None]:
    name = type(exc).__name__
    message = clean_str(str(exc), 500) or name
    lowered = f"{name} {message}".lower()
    if isinstance(exc, ExperimentTimeoutError) or "timeout" in name.lower() or "timed out" in lowered:
        return "timeout", name, message, None
    if isinstance(exc, IsolationError):
        return "validation_failure", name, message, "database_isolation"
    if "retrieval" in name.lower() or "retriev" in lowered or "okb" in lowered:
        return "retrieval_failure", name, message, "okb_retrieval"
    if "operationalerror" in name.lower() or "sqlalchemy" in lowered or "database" in lowered:
        return "retrieval_failure", name, message, "okb_retrieval"
    if "incomplete" in name.lower() or "incomplete output" in lowered:
        return "incomplete_output", name, message, "output_validation"
    if isinstance(exc, (ValidationError, ValueError, TypeError)) or "validation" in lowered:
        return "validation_failure", name, message, None
    if "llm" in lowered or "api" in lowered or "provider" in lowered or "quota" in lowered:
        return "model_api_failure", name, message, None
    return "model_api_failure", name, message, None


def _classify_workflow_error(state: dict[str, Any]) -> tuple[FailureKind, str, str, str | None]:
    errors = state.get("errors") if isinstance(state.get("errors"), list) else []
    first = errors[0] if errors and isinstance(errors[0], dict) else {}
    stage = first.get("stage") if isinstance(first.get("stage"), str) else state.get("stage")
    error_type = first.get("error_type") if isinstance(first.get("error_type"), str) else "WorkflowError"
    message = first.get("message") if isinstance(first.get("message"), str) else "workflow reported ERROR"
    lowered = f"{error_type} {message}".lower()
    if "timeout" in lowered:
        return "timeout", error_type, message, stage
    if "retriev" in lowered or "okb" in lowered or "database" in lowered or "sqlalchemy" in lowered:
        return "retrieval_failure", error_type, message, stage
    if "incomplete" in lowered or ("missing" in lowered and "output" in lowered):
        return "incomplete_output", error_type, message, stage
    if stage == "input_validation" or "validation" in lowered:
        return "validation_failure", error_type, message, stage
    if error_type in {"ValueError", "ValidationError", "InvalidVerificationState"}:
        return "validation_failure", error_type, message, stage
    return "model_api_failure", error_type, message, stage


def _capabilities(configuration_id: ConfigId) -> dict[str, str]:
    if configuration_id == "B0":
        return {
            "skill_gap": "NOT_APPLICABLE",
            "roadmap": "NOT_APPLICABLE",
            "verification": "NOT_APPLICABLE",
        }
    if configuration_id == "B2":
        return {
            "skill_gap": "AVAILABLE",
            "roadmap": "NOT_APPLICABLE",
            "verification": "NOT_APPLICABLE",
        }
    if configuration_id == "B3":
        return {
            "skill_gap": "AVAILABLE",
            "roadmap": "AVAILABLE",
            "verification": "NOT_APPLICABLE",
        }
    return {
        "skill_gap": "AVAILABLE",
        "roadmap": "AVAILABLE",
        "verification": "AVAILABLE",
    }


class ExperimentRunner:
    """Execute a frozen bundle under B0/B2/B3/F and persist isolated records."""

    def __init__(
        self,
        *,
        store: ExperimentStore | None = None,
        llm_client: Any | None = None,
        career_labels: list[CareerOutputLabel] | None = None,
        max_revisions: int = 2,
        workflow_factory: Callable[[str], Any] | None = None,
        okb_fingerprint_provider: Callable[[], OkbSnapshot | dict[str, Any]] | None = None,
        git_provenance_provider: Callable[[], dict[str, Any]] | None = None,
        enforce_database_isolation: bool = True,
        timeout_seconds: float | None = None,
    ):
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive when supplied")
        self.store = store if store is not None else ExperimentStore()
        self.llm_client = llm_client
        self.career_labels = career_labels
        self.max_revisions = max_revisions
        self.workflow_factory = workflow_factory
        self.okb_fingerprint_provider = okb_fingerprint_provider
        self.git_provenance_provider = git_provenance_provider
        self.enforce_database_isolation = enforce_database_isolation
        self.timeout_seconds = timeout_seconds

    # ------------------------------------------------------------------ input
    def _prepare(
        self,
        *,
        case_id: str,
        run_id: str,
        bundle: FrozenProfileBundle | dict[str, Any],
        metadata: dict[str, Any] | None,
    ) -> PreparedExperiment:
        if not isinstance(case_id, str) or not case_id.strip():
            raise SharedInputError("case_id must be a non-empty string")
        if not isinstance(run_id, str) or not run_id.strip():
            raise SharedInputError("run_id must be a non-empty string")
        if metadata is not None and not isinstance(metadata, dict):
            raise SharedInputError("experiment metadata must be a mapping")
        safe_metadata = dict(metadata or {})
        _reject_ground_truth_keys(safe_metadata)
        try:
            validated = FrozenProfileBundle.model_validate(bundle)
        except Exception as exc:
            raise SharedInputError(f"invalid frozen profile bundle: {exc}") from exc
        provenance = (
            self.git_provenance_provider()
            if self.git_provenance_provider is not None
            else _default_git_provenance()
        )
        return PreparedExperiment(
            case_id=case_id.strip(),
            run_id=run_id.strip(),
            bundle=validated,
            bundle_fingerprint=fingerprint_bundle(validated),
            metadata=to_jsonable(safe_metadata, str_limit=4000),
            git_provenance=provenance,
        )

    # ------------------------------------------------------------------ OKB
    def _resolve_okb(
        self, configurations: Iterable[ConfigId]
    ) -> tuple[OkbSnapshot | None, BaseException | None]:
        if not any(configuration_id != "B0" for configuration_id in configurations):
            return None, None
        try:
            snapshot = (
                self.okb_fingerprint_provider()
                if self.okb_fingerprint_provider is not None
                else self._default_okb_snapshot()
            )
            return OkbSnapshot.model_validate(snapshot), None
        except Exception as exc:
            return None, RetrievalFailure(
                f"OKB snapshot retrieval failed: {type(exc).__name__}: {clean_str(str(exc), 300)}"
            )

    def _default_okb_snapshot(self) -> OkbSnapshot:
        if self.enforce_database_isolation:
            target = assert_isolated_database()
            from app.core.db import get_engine
            from sqlalchemy import text

            engine = get_engine()
            engine_database = engine.url.database
            engine_host = (engine.url.host or "").lower()
            if engine_database != target:
                raise IsolationError(
                    "effective engine database does not match the explicitly selected isolated target"
                )
            if engine_host not in {"localhost", "127.0.0.1", "::1"}:
                raise IsolationError("effective engine host is not loopback")
            with engine.connect() as connection:
                server_database = connection.execute(
                    text("SELECT current_database()")
                ).scalar_one()
            if server_database != target:
                raise IsolationError(
                    "server-confirmed database does not match the explicitly selected isolated target"
                )
        return compute_okb_snapshot()

    # --------------------------------------------------------------- workflow
    def _default_workflow_factory(self, configuration_id: str):
        if configuration_id != "B0" and self.enforce_database_isolation:
            assert_isolated_database()
        if self.llm_client is None:
            raise ValueError("real experiment execution requires an LLM client")
        if configuration_id == "B0" and not self.career_labels:
            raise ValueError("B0 requires the fixed 10-career output label list")
        return CareerWorkflow(
            llm_client=self.llm_client,
            configuration_id=configuration_id,
            career_labels=self.career_labels,
            max_revisions=self.max_revisions,
        )

    def _reusable_record(
        self,
        *,
        prepared: PreparedExperiment,
        configuration_id: ConfigId,
        timeout_seconds: float | None,
        okb_snapshot: OkbSnapshot | None,
    ) -> ExperimentRunRecord | None:
        """Return a successful prior record only when all run inputs still match."""
        try:
            record = ExperimentRunRecord.model_validate(
                self.store.read_run(prepared.case_id, prepared.run_id, configuration_id)
            )
        except (OSError, ValueError, ValidationError):
            return None

        client_metadata = self._model_metadata(self.llm_client)
        expected_snapshot = (
            okb_snapshot.fingerprint if configuration_id != "B0" and okb_snapshot else None
        )
        expected_settings = {
            **self._inference_settings(configuration_id, self.llm_client, timeout_seconds),
            "sdk_version": client_metadata.get("sdk_version"),
        }
        if (
            record.case_id != prepared.case_id
            or record.run_id != prepared.run_id
            or record.configuration_id != configuration_id
            or record.execution_status != "success"
            or not record.persisted
            or record.normalized_evaluation_output is None
            or record.normalization_error_type is not None
            or record.input_bundle_fingerprint != prepared.bundle_fingerprint
            or record.metadata != prepared.metadata
            or record.okb_snapshot_fingerprint != expected_snapshot
            or record.prompt_identifiers != self._prompt_identifiers(configuration_id)
            or record.llm_model != client_metadata.get("model")
            or record.llm_provider != client_metadata.get("provider")
            or record.inference_settings != expected_settings
            or record.database_target != database_name()
            or record.git_commit != prepared.git_provenance.get("git_commit")
            or record.git_dirty != prepared.git_provenance.get("git_dirty")
            or record.git_diff_sha256 != prepared.git_provenance.get("git_diff_sha256")
        ):
            return None
        return record

    def _factory(self, configuration_id: str):
        if self.workflow_factory is not None:
            return self.workflow_factory(configuration_id)
        return self._default_workflow_factory(configuration_id)

    def _invoke(
        self,
        workflow: Any,
        *,
        configuration_id: ConfigId,
        prepared: PreparedExperiment,
        user_id: int,
        timeout_seconds: float | None,
    ) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "user_id": user_id,
            "profile_bundle": prepared.bundle,
        }
        if configuration_id in {"B0", "B2"}:
            kwargs["career_labels"] = self.career_labels
        effective_timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        if effective_timeout is None:
            return workflow.run(**kwargs)
        executor = _futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(workflow.run, **kwargs)
        try:
            return future.result(timeout=effective_timeout)
        except _futures.TimeoutError as exc:
            future.cancel()
            raise ExperimentTimeoutError(
                f"workflow exceeded {effective_timeout} seconds"
            ) from exc
        finally:
            executor.shutdown(wait=False)

    def _interpret_state(
        self, configuration_id: ConfigId, state: Any
    ) -> tuple[FailureKind, str | None, str | None, str | None]:
        if not isinstance(state, dict):
            return (
                "incomplete_output",
                "IncompleteOutput",
                "workflow did not return a structured state",
                "output_validation",
            )
        if state.get("final_status") == "ERROR":
            return _classify_workflow_error(state)
        missing = self._missing_outputs(configuration_id, state)
        if missing:
            return (
                "incomplete_output",
                "IncompleteOutput",
                "missing required outputs: " + ", ".join(missing),
                "output_validation",
            )
        violation = self._contract_violation(configuration_id, state)
        if violation:
            return "validation_failure", "ContractViolation", violation, "output_validation"
        return "success", None, None, None

    @staticmethod
    def _missing_outputs(configuration_id: ConfigId, state: dict[str, Any]) -> list[str]:
        missing: list[str] = []
        if configuration_id == "B0":
            baseline = _mapping(state.get("baseline_result"))
            if not baseline:
                missing.append("baseline_result")
            elif not baseline.get("recommendations"):
                missing.append("baseline_result.recommendations")
        elif configuration_id == "B2":
            baseline = _mapping(state.get("baseline_result"))
            if not baseline:
                missing.append("baseline_result")
            else:
                if not baseline.get("recommendations"):
                    missing.append("baseline_result.recommendations")
                gap = _mapping(baseline.get("skill_gap"))
                if not gap or gap.get("status") == "NOT_APPLICABLE":
                    missing.append("baseline_result.skill_gap")
                elif not all(
                    key in gap
                    for key in (
                        "matched_evidenced",
                        "matched_claimed_only",
                        "missing",
                        "unmatched_user_claims",
                    )
                ):
                    missing.append("baseline_result.skill_gap.categories")
        else:
            if not state.get("recommendations"):
                missing.append("recommendations")
            if state.get("skill_gap") is None:
                missing.append("skill_gap")
            if state.get("roadmap") is None:
                missing.append("roadmap")
            if configuration_id == "F" and state.get("verification") is None:
                missing.append("verification")
        return missing

    @staticmethod
    def _contract_violation(configuration_id: ConfigId, state: dict[str, Any]) -> str | None:
        if configuration_id in {"B0", "B2"}:
            baseline = _mapping(state.get("baseline_result"))
            if configuration_id == "B0":
                for key in ("skill_gap", "roadmap", "verification"):
                    if _mapping(baseline.get(key)).get("status") != "NOT_APPLICABLE":
                        return f"B0 {key} must be explicitly NOT_APPLICABLE"
            else:
                for key in ("roadmap", "verification"):
                    if _mapping(baseline.get(key)).get("status") != "NOT_APPLICABLE":
                        return f"B2 {key} must be explicitly NOT_APPLICABLE"
        if configuration_id == "B3" and state.get("verification") is not None:
            return "B3 must not run the Verification Agent"
        return None

    # --------------------------------------------------------------- metadata
    def _resolve_llm_client(self, workflow: Any) -> Any | None:
        if self.llm_client is not None:
            return self.llm_client
        for attribute in (
            "profile_agent",
            "career_recommendation_agent",
            "skill_gap_agent",
            "learning_roadmap_agent",
            "verification_agent",
        ):
            client = getattr(getattr(workflow, attribute, None), "llm_client", None)
            if client is not None:
                return client
        return None

    def _instrument_workflow_llm_calls(
        self, workflow: Any, recorder: LLMCallProvenance,
    ) -> None:
        owners = [workflow]
        owners.extend(
            getattr(workflow, attribute, None)
            for attribute in (
                "baseline_agent", "profile_agent", "career_recommendation_agent",
                "skill_gap_agent", "learning_roadmap_agent", "verification_agent",
            )
        )
        wrappers: dict[int, Any] = {}
        for owner in owners:
            if owner is None:
                continue
            client = getattr(owner, "llm_client", None)
            if client is None or isinstance(client, _ProvenanceLLMClient):
                continue
            wrapper = wrappers.setdefault(id(client), recorder.wrap(client))
            try:
                setattr(owner, "llm_client", wrapper)
            except (AttributeError, TypeError):
                continue

    @staticmethod
    def _model_metadata(client: Any | None) -> dict[str, Any]:
        if client is None:
            return {
                "model": "unavailable (no LLM client configured)",
                "model_version": "unavailable (no LLM client configured)",
                "provider": "unavailable",
                "sdk_version": "unavailable",
            }
        holder = SimpleNamespace(profile_agent=SimpleNamespace(llm_client=client))
        return _model_metadata(holder)

    @staticmethod
    def _prompt_identifiers(configuration_id: ConfigId) -> dict[str, Any]:
        if configuration_id in {"B0", "B2"}:
            identifiers = _prompt_identifiers([{"agent": "baseline_inference"}])
            prompt_sha = sha256_text(BaselineInferenceAgent.system_prompt(configuration_id))
            identifiers.setdefault("prompts", {})["baseline_inference"] = {
                "agent": "baseline_inference",
                "version": f"sha256:{prompt_sha}",
                "sha256": prompt_sha,
            }
            return identifiers
        agents = [
            {"agent": "career_recommendation"},
            {"agent": "skill_gap"},
            {"agent": "roadmap"},
        ]
        if configuration_id == "F":
            agents.append({"agent": "verification"})
        return _prompt_identifiers(agents)

    def _inference_settings(
        self,
        configuration_id: ConfigId,
        client: Any | None,
        timeout_seconds: float | None,
    ) -> dict[str, Any]:
        effective_timeout = timeout_seconds if timeout_seconds is not None else self.timeout_seconds
        settings: dict[str, Any] = {
            "response_format": "json",
            "max_tokens": "per-agent (existing agent contracts)",
            "max_revisions": self.max_revisions if configuration_id == "F" else 0,
            "timeout_seconds": effective_timeout,
        }
        if client is not None:
            for attribute in ("temperature", "top_p", "top_k"):
                value = getattr(client, attribute, None)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    settings[attribute] = value
        return settings

    # ---------------------------------------------------------------- records
    @staticmethod
    def _verification_values(
        configuration_id: ConfigId, state: dict[str, Any] | None
    ) -> tuple[str, str]:
        if configuration_id in {"B0", "B2", "B3"}:
            return "NOT_APPLICABLE", "NOT_APPLICABLE"
        verification = _mapping(state.get("verification")) if state else {}
        final = verification.get("status")
        if final not in _VERIFICATION_VALUES:
            final = "unavailable"
        first = state.get("first_pass_verification_status") if state else None
        if first not in _VERIFICATION_VALUES:
            first = final if final in _VERIFICATION_VALUES else "unavailable"
        return first, final

    @staticmethod
    def _revision_count(state: dict[str, Any] | None) -> int:
        value = state.get("revision_count") if state else 0
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            return 0
        return value

    @staticmethod
    def _raw_output(state: dict[str, Any] | None) -> dict[str, Any] | None:
        if state is None:
            return None
        raw = {
            key: value
            for key, value in state.items()
            if key not in {"profile_result", "redacted_profile_text", "input_profile_bundle"}
        }
        profile_result = state.get("profile_result")
        if profile_result is not None:
            diagnostics = []
            for report in getattr(profile_result, "normalizations", []) or []:
                result = getattr(report, "result", None)
                if result is None:
                    continue
                diagnostics.append({
                    "mention_id": getattr(report, "mention_id", None),
                    "claim_sha256": sha256_text(report.claimed_skill)
                    if isinstance(getattr(report, "claimed_skill", None), str) else None,
                    "candidate_skill_id": result.skill_id,
                    "normalized_name": result.normalized_name,
                    "method": result.method,
                    "outcome": result.outcome,
                    "exact_match": result.exact_match,
                    "similarity": result.score,
                    "fuzzy_candidates": [
                        {
                            "skill_id": candidate.skill_id,
                            "canonical_name": candidate.canonical_name,
                            "similarity": candidate.similarity,
                            "meets_threshold": candidate.meets_threshold,
                        }
                        for candidate in result.fuzzy_candidates
                    ],
                })
            raw["normalization_diagnostics"] = diagnostics
        return to_jsonable(raw, str_limit=4000)

    def _normalized_output(
        self,
        *,
        configuration_id: ConfigId,
        state: dict[str, Any] | None,
        user_id: int,
        first_pass: str,
        revision_count: int,
    ) -> tuple[dict[str, Any] | None, str | None, str | None]:
        if state is None:
            return None, None, None
        try:
            if configuration_id in {"B0", "B2"}:
                baseline = state.get("baseline_result")
                if baseline is None:
                    return None, "IncompleteOutput", "baseline_result is missing"
                baseline_data = (
                    baseline.model_dump(mode="json")
                    if hasattr(baseline, "model_dump")
                    else baseline
                )
                evaluation_record = {
                    "user_profile_id": user_id,
                    "baseline_result": baseline_data,
                    "final_result": {"final_status": state.get("final_status")},
                    "revision_count": revision_count,
                }
            else:
                evaluation_record = {
                    "user_profile_id": user_id,
                    "agent_outputs": {
                        "career_recommendation": to_jsonable(state.get("recommendations")),
                        "skill_gap": to_jsonable(state.get("skill_gap")),
                        "roadmap": to_jsonable(state.get("roadmap")),
                        "verification": to_jsonable(state.get("verification")),
                    },
                    "verification_result": to_jsonable(state.get("verification")),
                    "final_result": {"final_status": state.get("final_status")},
                    "revision_count": revision_count,
                }
            first_pass_for_case = first_pass if first_pass in _VERIFICATION_VALUES else None
            case = case_from_analysis_record(
                evaluation_record,
                config_id=configuration_id,
                first_pass_status=first_pass_for_case,
                revision_count=revision_count,
            )
            return case.model_dump(mode="json"), None, None
        except Exception as exc:
            return None, type(exc).__name__, clean_str(str(exc), 500)

    def _build_record(
        self,
        *,
        prepared: PreparedExperiment,
        configuration_id: ConfigId,
        user_id: int,
        timeout_seconds: float | None,
        state: dict[str, Any] | None,
        execution_status: FailureKind,
        error_type: str | None,
        error_message: str | None,
        error_stage: str | None,
        okb_snapshot: OkbSnapshot | None,
        okb_error: BaseException | None,
        workflow: Any,
        llm_calls: list[dict[str, Any]],
        started_at: str,
        completed_at: str,
        duration_ms: float,
    ) -> ExperimentRunRecord:
        configuration = get_configuration(configuration_id)
        client = self._resolve_llm_client(workflow)
        model_metadata = self._model_metadata(client)
        first_pass, final = self._verification_values(configuration_id, state)
        revision_count = self._revision_count(state)
        normalized, normalization_error_type, normalization_error_message = self._normalized_output(
            configuration_id=configuration_id,
            state=state,
            user_id=user_id,
            first_pass=first_pass,
            revision_count=revision_count,
        )

        if configuration_id == "B0":
            okb_usage = "NOT_APPLICABLE"
        elif okb_error is not None:
            okb_usage = "RETRIEVAL_FAILED"
        else:
            okb_usage = "USED"

        if configuration_id == "B0":
            database_write_guard = "NOT_APPLICABLE"
        elif self.workflow_factory is not None:
            database_write_guard = "BYPASSED_INJECTED_EXECUTOR"
        elif self.enforce_database_isolation:
            database_write_guard = "ENFORCED"
        else:
            database_write_guard = "DISABLED"

        notes = [TECHNOLOGY_NOTE]
        if configuration_id == "B0":
            notes.append(
                "B0 does not use the OKB; okb_usage is NOT_APPLICABLE and no OKB snapshot "
                "fingerprint was computed."
            )
        if configuration_id in {"B0", "B2"}:
            notes.append("Roadmap and verification are NOT_APPLICABLE for this configuration.")
        if configuration_id == "B3":
            notes.append(
                "B3 verification is NOT_APPLICABLE; no Verification Agent or revision loop ran."
            )
        if configuration_id == "F":
            notes.append("F ran the Verification Agent and the bounded revision loop.")
        if state is not None and state.get("profile_result") is not None:
            notes.append(
                "The intermediate profile_result was omitted from raw_structured_output to "
                "avoid duplicating CV-derived personal data."
            )

        shared_calls = prepared.metadata.get("shared_input_llm_calls", [])
        if not isinstance(shared_calls, list):
            shared_calls = []
        return ExperimentRunRecord(
            case_id=prepared.case_id,
            run_id=prepared.run_id,
            configuration_id=configuration_id,
            configuration_label=configuration.label,
            input_bundle_fingerprint=prepared.bundle_fingerprint,
            start_timestamp_utc=started_at,
            completion_timestamp_utc=completed_at,
            duration_ms=duration_ms,
            execution_status=execution_status,
            raw_structured_output=self._raw_output(state),
            normalized_evaluation_output=normalized,
            normalization_error_type=normalization_error_type,
            normalization_error_message=normalization_error_message,
            first_pass_verification_status=first_pass,
            final_verification_status=final,
            revision_count=revision_count,
            error_type=error_type,
            error_message=error_message,
            error_stage=error_stage,
            llm_provider=model_metadata.get("provider"),
            llm_model=model_metadata.get("model"),
            prompt_identifiers=self._prompt_identifiers(configuration_id),
            llm_call_provenance=[*shared_calls, *llm_calls],
            inference_settings={
                **self._inference_settings(configuration_id, client, timeout_seconds),
                "sdk_version": model_metadata.get("sdk_version"),
            },
            okb_usage=okb_usage,
            okb_snapshot_fingerprint=(
                okb_snapshot.fingerprint if okb_snapshot is not None and configuration_id != "B0" else None
            ),
            okb_counts=(
                dict(okb_snapshot.counts)
                if okb_snapshot is not None and configuration_id != "B0"
                else None
            ),
            capabilities=_capabilities(configuration_id),
            database_target=database_name(),
            database_write_guard=database_write_guard,
            git_commit=prepared.git_provenance.get("git_commit"),
            git_dirty=prepared.git_provenance.get("git_dirty"),
            git_diff_sha256=prepared.git_provenance.get("git_diff_sha256"),
            source_state_fingerprint=_source_state_fingerprint(prepared.git_provenance),
            metadata=prepared.metadata,
            notes=notes,
        )

    def _run_prepared(
        self,
        *,
        prepared: PreparedExperiment,
        configuration_id: ConfigId,
        user_id: int,
        timeout_seconds: float | None,
        okb_snapshot: OkbSnapshot | None,
        okb_error: BaseException | None,
    ) -> ExperimentRunRecord:
        started_at = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
        started_monotonic = _time.monotonic()
        state: dict[str, Any] | None = None
        workflow: Any = None
        call_recorder = LLMCallProvenance(prepared.case_id, prepared.run_id, configuration_id)
        execution_status: FailureKind
        error_type: str | None = None
        error_message: str | None = None
        error_stage: str | None = None

        if configuration_id != "B0" and okb_error is not None:
            execution_status, error_type, error_message, error_stage = _classify_exception(okb_error)
            if execution_status == "success":
                execution_status = "retrieval_failure"
        else:
            try:
                workflow = self._factory(configuration_id)
                self._instrument_workflow_llm_calls(workflow, call_recorder)
                state = self._invoke(
                    workflow,
                    configuration_id=configuration_id,
                    prepared=prepared,
                    user_id=user_id,
                    timeout_seconds=timeout_seconds,
                )
                execution_status, error_type, error_message, error_stage = self._interpret_state(
                    configuration_id, state
                )
            except Exception as exc:
                execution_status, error_type, error_message, error_stage = _classify_exception(exc)

        completed_at = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
        duration_ms = max(0.0, (_time.monotonic() - started_monotonic) * 1000.0)
        record = self._build_record(
            prepared=prepared,
            configuration_id=configuration_id,
            user_id=user_id,
            timeout_seconds=timeout_seconds,
            state=state,
            execution_status=execution_status,
            error_type=error_type,
            error_message=error_message,
            error_stage=error_stage,
            okb_snapshot=okb_snapshot,
            okb_error=okb_error,
            workflow=workflow,
            llm_calls=call_recorder.snapshot(),
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
        )
        record.record_path = str(
            self.store.run_path(prepared.case_id, prepared.run_id, configuration_id)
        )
        record.persisted = True
        try:
            self.store.write_run(record)
        except Exception as exc:
            record.pre_persistence_status = record.execution_status
            record.execution_status = "persistence_failure"
            record.persisted = False
            record.persistence_error_type = type(exc).__name__
            record.persistence_error_message = clean_str(str(exc), 500)
        return record

    # ------------------------------------------------------------- public API
    def run_configuration(
        self,
        *,
        case_id: str,
        run_id: str,
        configuration_id: str,
        bundle: FrozenProfileBundle | dict[str, Any],
        user_id: int,
        metadata: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> ExperimentRunRecord:
        """Execute one configuration and persist its isolated record."""
        get_configuration(configuration_id)
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise SharedInputError("user_id must be a positive integer")
        prepared = self._prepare(
            case_id=case_id, run_id=run_id, bundle=bundle, metadata=metadata
        )
        okb_snapshot, okb_error = self._resolve_okb((configuration_id,))  # type: ignore[arg-type]
        return self._run_prepared(
            prepared=prepared,
            configuration_id=configuration_id,  # type: ignore[arg-type]
            user_id=user_id,
            timeout_seconds=timeout_seconds,
            okb_snapshot=okb_snapshot,
            okb_error=okb_error,
        )

    def run_case(
        self,
        *,
        case_id: str,
        run_id: str,
        bundle: FrozenProfileBundle | dict[str, Any],
        user_id: int,
        metadata: dict[str, Any] | None = None,
        configurations: Iterable[str] | None = None,
        timeout_seconds: float | None = None,
        resume: bool = True,
    ) -> PairedExperimentResult:
        """Execute one frozen bundle under all four configurations sequentially."""
        selected = list(configurations or ALL_CONFIGURATIONS)
        if not selected:
            raise SharedInputError("at least one configuration must be requested")
        if len(set(selected)) != len(selected):
            raise SharedInputError("configurations must not repeat a configuration ID")
        for configuration_id in selected:
            get_configuration(configuration_id)
        if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise SharedInputError("user_id must be a positive integer")

        prepared = self._prepare(
            case_id=case_id, run_id=run_id, bundle=bundle, metadata=metadata
        )
        started_at = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
        started_monotonic = _time.monotonic()
        okb_snapshot, okb_error = self._resolve_okb(selected)  # type: ignore[arg-type]

        records: list[ExperimentRunRecord] = []
        for configuration_id in selected:
            reused = (
                self._reusable_record(
                    prepared=prepared,
                    configuration_id=configuration_id,  # type: ignore[arg-type]
                    timeout_seconds=timeout_seconds,
                    okb_snapshot=okb_snapshot,
                )
                if resume and okb_error is None
                else None
            )
            records.append(reused or self._run_prepared(
                prepared=prepared,
                configuration_id=configuration_id,  # type: ignore[arg-type]
                user_id=user_id,
                timeout_seconds=timeout_seconds,
                okb_snapshot=okb_snapshot,
                okb_error=okb_error,
            ))

        completed_at = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
        duration_ms = max(0.0, (_time.monotonic() - started_monotonic) * 1000.0)
        successful = [
            record.configuration_id
            for record in records
            if record.execution_status == "success" and record.persisted
        ]
        failed = [
            record.configuration_id
            for record in records
            if record.configuration_id not in successful
        ]
        manifest = ExperimentManifest(
            case_id=prepared.case_id,
            run_id=prepared.run_id,
            input_bundle_fingerprint=prepared.bundle_fingerprint,
            start_timestamp_utc=started_at,
            completion_timestamp_utc=completed_at,
            duration_ms=duration_ms,
            configurations=selected,  # type: ignore[arg-type]
            records=[
                RunSummary(
                    configuration_id=record.configuration_id,
                    execution_status=record.execution_status,
                    first_pass_verification_status=record.first_pass_verification_status,
                    final_verification_status=record.final_verification_status,
                    revision_count=record.revision_count,
                    error_type=record.error_type,
                    record_path=record.record_path,
                    persisted=record.persisted,
                )
                for record in records
            ],
            partial=bool(failed),
            successful_configurations=successful,  # type: ignore[arg-type]
            failed_configurations=failed,  # type: ignore[arg-type]
            git_commit=prepared.git_provenance.get("git_commit"),
            git_dirty=prepared.git_provenance.get("git_dirty"),
            git_diff_sha256=prepared.git_provenance.get("git_diff_sha256"),
            source_state_fingerprint=_source_state_fingerprint(prepared.git_provenance),
            metadata=prepared.metadata,
            notes=[
                TECHNOLOGY_NOTE,
                "Partial execution is explicit: a failed configuration is recorded as failed "
                "and does not erase successful records from other configurations.",
            ],
        )
        manifest.manifest_path = str(
            self.store.manifest_path(prepared.case_id, prepared.run_id)
        )
        manifest.persisted = True
        try:
            self.store.write_manifest(manifest)
        except Exception as exc:
            manifest.persisted = False
            manifest.persistence_error_type = type(exc).__name__
            manifest.persistence_error_message = clean_str(str(exc), 500)
        return PairedExperimentResult(manifest=manifest, records=records)
