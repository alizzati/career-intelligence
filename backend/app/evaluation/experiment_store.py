"""Isolated, file-based persistence for Stage 2C experiment runs.

Experiment records are deliberately *not* written to ``analysis_log/1.0`` or to
any application database.  They live under ``backend/artifacts/experiments``
(already Git-ignored) or under the directory named by
``CAREER_EXPERIMENT_DIR``.  Each run gets its own atomic JSON file, and a paired
case gets a separate manifest.  A write failure is reported explicitly; it is
never turned into a successful empty result.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.evaluation.schemas import ConfigId


FailureKind = Literal[
    "success",
    "model_api_failure",
    "retrieval_failure",
    "validation_failure",
    "timeout",
    "incomplete_output",
    "persistence_failure",
]
VerificationStatusValue = Literal["PASS", "FAIL", "REVISE", "NOT_APPLICABLE", "unavailable"]
OkbUsage = Literal["NOT_APPLICABLE", "USED", "RETRIEVAL_FAILED"]

DEFAULT_EXPERIMENT_DIRECTORY = Path(__file__).resolve().parents[2] / "artifacts" / "experiments"
EXPERIMENT_DIRECTORY_ENV = "CAREER_EXPERIMENT_DIR"
RUN_SCHEMA_VERSION = "experiment_run/1.0"
MANIFEST_SCHEMA_VERSION = "experiment_manifest/1.0"
_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9._-]")


class ExperimentPersistenceError(RuntimeError):
    """Raised when an experiment record cannot be written atomically."""


class ExperimentRunRecord(BaseModel):
    """One configuration execution for one case/run pair.

    ``raw_structured_output`` is the workflow state after the privacy-preserving
    ``to_jsonable`` projection (the intermediate profile result is omitted).
    ``normalized_evaluation_output`` is the ``EvaluationCase`` projection when it
    could be produced.  A failed run never carries a fabricated success value.
    """

    model_config = {"extra": "forbid"}

    schema_version: Literal["experiment_run/1.0"] = RUN_SCHEMA_VERSION
    case_id: str
    run_id: str
    configuration_id: ConfigId
    configuration_label: str
    input_bundle_fingerprint: str
    bundle_fingerprint_algorithm: Literal["sha256"] = "sha256"

    start_timestamp_utc: str
    completion_timestamp_utc: str
    duration_ms: float = Field(ge=0)

    execution_status: FailureKind
    pre_persistence_status: FailureKind | None = None
    raw_structured_output: dict[str, Any] | None = None
    normalized_evaluation_output: dict[str, Any] | None = None
    normalization_error_type: str | None = None
    normalization_error_message: str | None = None

    first_pass_verification_status: VerificationStatusValue
    final_verification_status: VerificationStatusValue
    revision_count: int = Field(ge=0)

    error_type: str | None = None
    error_message: str | None = None
    error_stage: str | None = None

    llm_provider: str | None = None
    llm_model: str | None = None
    prompt_identifiers: dict[str, Any] = Field(default_factory=dict)
    inference_settings: dict[str, Any] = Field(default_factory=dict)
    llm_call_provenance: list[dict[str, Any]] = Field(default_factory=list)

    okb_usage: OkbUsage
    okb_snapshot_fingerprint: str | None = None
    okb_counts: dict[str, int] | None = None
    capabilities: dict[str, str] = Field(default_factory=dict)

    database_target: str = "unavailable"
    database_write_guard: str = "NOT_APPLICABLE"
    git_commit: str | None = None
    git_dirty: bool | str | None = None
    git_diff_sha256: str | None = None
    source_state_fingerprint: str | None = None

    metadata: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    record_path: str | None = None
    persisted: bool = False
    persistence_error_type: str | None = None
    persistence_error_message: str | None = None

    @field_validator("case_id", "run_id")
    @classmethod
    def _non_empty_identifier(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("case_id and run_id must be non-empty strings")
        return value.strip()

    @field_validator("input_bundle_fingerprint")
    @classmethod
    def _fingerprint(cls, value: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("input_bundle_fingerprint must be a 64-character lowercase sha256")
        return value

    @field_validator("okb_snapshot_fingerprint")
    @classmethod
    def _okb_fingerprint(cls, value: str | None) -> str | None:
        if value is not None and not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("okb_snapshot_fingerprint must be a 64-character lowercase sha256")
        return value

    @model_validator(mode="after")
    def _failure_has_error(self) -> "ExperimentRunRecord":
        if self.execution_status != "success" and not self.error_type:
            # Persistence failures are the one exception: the original run may
            # have succeeded and only the write failed.
            if self.execution_status != "persistence_failure":
                raise ValueError("a failed run must record an error_type")
        for call in self.llm_call_provenance:
            if call.get("case_id") != self.case_id or call.get("run_id") != self.run_id:
                raise ValueError("LLM call provenance must reference the containing case/run")
            if call.get("configuration_id") not in {self.configuration_id, "SHARED_INPUT"}:
                raise ValueError("LLM call provenance must reference the containing configuration or shared input")
            for field_name in ("system_prompt_sha256", "user_prompt_sha256"):
                digest = call.get(field_name)
                if digest is not None and not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise ValueError(f"{field_name} must be a lowercase sha256 digest")
        return self


class RunSummary(BaseModel):
    model_config = {"extra": "forbid"}

    configuration_id: ConfigId
    execution_status: FailureKind
    first_pass_verification_status: VerificationStatusValue
    final_verification_status: VerificationStatusValue
    revision_count: int = Field(ge=0)
    error_type: str | None = None
    record_path: str | None = None
    persisted: bool = False


class ExperimentManifest(BaseModel):
    """Paired-case manifest.  One entry per configuration, never merged."""

    model_config = {"extra": "forbid"}

    schema_version: Literal["experiment_manifest/1.0"] = MANIFEST_SCHEMA_VERSION
    case_id: str
    run_id: str
    input_bundle_fingerprint: str
    bundle_fingerprint_algorithm: Literal["sha256"] = "sha256"

    start_timestamp_utc: str
    completion_timestamp_utc: str
    duration_ms: float = Field(ge=0)

    configurations: list[ConfigId]
    records: list[RunSummary]
    partial: bool
    successful_configurations: list[ConfigId]
    failed_configurations: list[ConfigId]
    shared_input_valid: bool = True

    git_commit: str | None = None
    git_dirty: bool | str | None = None
    git_diff_sha256: str | None = None
    source_state_fingerprint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    manifest_path: str | None = None
    persisted: bool = False
    persistence_error_type: str | None = None
    persistence_error_message: str | None = None

    @field_validator("case_id", "run_id")
    @classmethod
    def _non_empty_identifier(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("case_id and run_id must be non-empty strings")
        return value.strip()

    @field_validator("input_bundle_fingerprint")
    @classmethod
    def _fingerprint(cls, value: str) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("input_bundle_fingerprint must be a 64-character lowercase sha256")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> "ExperimentManifest":
        if len(set(self.configurations)) != len(self.configurations):
            raise ValueError("configurations must not repeat a configuration ID")
        record_configs = [record.configuration_id for record in self.records]
        if record_configs != self.configurations:
            raise ValueError("records must follow the declared configuration order")
        failed = set(self.failed_configurations)
        successful = set(self.successful_configurations)
        if failed & successful:
            raise ValueError("a configuration cannot be both successful and failed")
        if failed | successful != set(self.configurations):
            raise ValueError("every configuration must be classified as successful or failed")
        if self.partial != bool(failed):
            raise ValueError("partial must be true exactly when a configuration failed")
        return self


class ExperimentStore:
    """Atomic JSON store for experiment runs and paired manifests."""

    def __init__(self, root: str | Path | None = None):
        configured = os.environ.get(EXPERIMENT_DIRECTORY_ENV, "").strip()
        self.root = Path(root) if root is not None else (
            Path(configured) if configured else DEFAULT_EXPERIMENT_DIRECTORY
        )

    @staticmethod
    def _safe_component(value: str, label: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be a non-empty string")
        cleaned = _SAFE_COMPONENT.sub("_", value.strip())
        if not cleaned or cleaned in {".", ".."}:
            raise ValueError(f"{label} is not a safe path component")
        return cleaned[:160]

    def case_directory(self, case_id: str, run_id: str) -> Path:
        return self.root / self._safe_component(case_id, "case_id") / self._safe_component(
            run_id, "run_id"
        )

    def run_path(self, case_id: str, run_id: str, configuration_id: str) -> Path:
        return self.case_directory(case_id, run_id) / f"{configuration_id}.json"

    def manifest_path(self, case_id: str, run_id: str) -> Path:
        return self.case_directory(case_id, run_id) / "manifest.json"

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except Exception as exc:  # pragma: no cover - exercised through a fake store
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise ExperimentPersistenceError(
                f"could not write experiment artifact {path.name}: {type(exc).__name__}"
            ) from exc

    def write_run(self, record: ExperimentRunRecord) -> Path:
        if record.schema_version != RUN_SCHEMA_VERSION:
            raise ValueError(f"unsupported experiment run schema {record.schema_version!r}")
        path = self.run_path(record.case_id, record.run_id, record.configuration_id)
        self._atomic_write(path, record.model_dump(mode="json"))
        return path

    def write_manifest(self, manifest: ExperimentManifest) -> Path:
        if manifest.schema_version != MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"unsupported experiment manifest schema {manifest.schema_version!r}")
        path = self.manifest_path(manifest.case_id, manifest.run_id)
        self._atomic_write(path, manifest.model_dump(mode="json"))
        return path

    def read_run(self, case_id: str, run_id: str, configuration_id: str) -> dict[str, Any]:
        path = self.run_path(case_id, run_id, configuration_id)
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def read_manifest(self, case_id: str, run_id: str) -> dict[str, Any]:
        path = self.manifest_path(case_id, run_id)
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def list_run_records(self, case_id: str, run_id: str) -> list[dict[str, Any]]:
        directory = self.case_directory(case_id, run_id)
        if not directory.is_dir():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json")):
            if path.name == "manifest.json":
                continue
            with path.open("r", encoding="utf-8") as handle:
                records.append(json.load(handle))
        return records
