"""Manifest-driven CV batch evaluation for the frozen B0/B2/B3/F designs.

Run from ``backend/`` with ``python -m app.evaluation.batch_runner --dry-run``.
Live execution is explicitly opt-in and requires the isolated e2e database.
The redacted frozen bundles used for resume are CV-derived data; live mode
therefore requires an explicit local-cache acknowledgement.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import posixpath
import re
import sys
import tempfile
import threading
import time
import uuid
import zipfile
import xml.etree.ElementTree as ET
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

from app.agents.llm_client import GeminiClient
from app.evaluation.baseline_inference import (
    CareerOutputLabel,
    FrozenProfileBundle,
    FrozenProfileBundleExtractor,
)
from app.evaluation.configurations import get_configuration
from app.evaluation.evaluator import evaluate_case, evaluate_report
from app.evaluation.experiment_store import ExperimentStore
from app.evaluation.runner import (
    ALL_CONFIGURATIONS,
    ExperimentRunner,
    LLMCallProvenance,
)
from app.evaluation.schemas import (
    CareerRelevanceLabel,
    EvaluationCase,
    EvaluationReferences,
    RecommendationPrediction,
    RecommendationReference,
)
from app.evaluation.subset_selection import SUBSET_SIZE
from app.services.cv_text_extraction_service import CVTextExtractor
from app.services.pii_redaction_service import redact_pii
from sqlalchemy import text as sql_text


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CROSSWALK = REPO_ROOT / "docs/experiments/candidate_cv_career_crosswalk_draft.csv"
DEFAULT_WORKBOOK = REPO_ROOT / "data/ground_truth/Candidate_Profiles_Data.xlsx"
DEFAULT_CV_ROOT = REPO_ROOT / "frontend/dignostic_testing/input_cvs"
DEFAULT_OKB_WORKBOOK = REPO_ROOT / "data/occupational_knowledge_base_verified_v1_0.xlsx"
EXPECTED_CANDIDATES = 43
ANNOTATORS = ("annotator_1", "annotator_2")
ALLOWED_DATABASE = "career_intelligence_e2e_test"
ALLOWED_DATABASE_HOST = "localhost"
ALLOWED_DATABASE_PORT = 5433
DATABASE_OPT_IN = "CAREER_E2E_ISOLATED_DB_OK"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
XLSX_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
XLSX_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


class BatchValidationError(ValueError):
    """The crosswalk, input files, or run contract is invalid."""


class BatchSafetyError(RuntimeError):
    """Live execution failed a database or LLM opt-in gate."""


@dataclass(frozen=True)
class CandidateInput:
    candidate_id: str
    workbook_file: str
    cv_path: Path
    cv_sha256: str
    annotator_1: str
    annotator_1_career_id: str
    annotator_1_canonical_name: str
    annotator_1_mapping_status: str
    annotator_2: str
    annotator_2_career_id: str
    annotator_2_canonical_name: str
    annotator_2_mapping_status: str

    def reference(self, annotator: str) -> RecommendationReference:
        if annotator not in ANNOTATORS:
            raise ValueError(f"unknown annotator {annotator!r}")
        return RecommendationReference(
            profile_id=self.candidate_id,
            labels=[CareerRelevanceLabel(
                career_id=getattr(self, f"{annotator}_career_id"),
                relevance=1,
            )],
        )


def _column_number(cell_reference: str) -> int:
    match = re.match(r"[A-Z]+", cell_reference)
    if not match:
        raise BatchValidationError("workbook contains an invalid cell reference")
    value = 0
    for character in match.group(0):
        value = value * 26 + ord(character) - ord("A") + 1
    return value


def _xlsx_sheet_rows(
    path: Path,
    sheet_name: str,
    *,
    required_headers: set[str] | None = None,
) -> list[dict[str, str]]:
    """Read workbook cell values only; never opens or extracts a CV document."""
    try:
        with zipfile.ZipFile(path) as archive:
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            targets = {
                relation.attrib["Id"]: relation.attrib["Target"]
                for relation in relationships.findall(PKG_REL + "Relationship")
            }
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                shared = [
                    "".join(text.text or "" for text in item.iter(XLSX_MAIN + "t"))
                    for item in shared_root.findall(XLSX_MAIN + "si")
                ]
            sheets = workbook.find(XLSX_MAIN + "sheets")
            sheet = next(
                item for item in (sheets if sheets is not None else [])
                if item.attrib.get("name") == sheet_name
            )
            target = targets[sheet.attrib[XLSX_REL + "id"]]
            member = posixpath.normpath(
                target.lstrip("/") if target.startswith("/")
                else posixpath.join("xl", target)
            )
            root = ET.fromstring(archive.read(member))
    except (OSError, KeyError, StopIteration, zipfile.BadZipFile, ET.ParseError) as exc:
        raise BatchValidationError(
            f"cannot read workbook sheet {sheet_name!r}: {type(exc).__name__}"
        ) from None

    rows = root.findall(".//" + XLSX_MAIN + "sheetData/" + XLSX_MAIN + "row")

    def cell_text(cell: ET.Element) -> str:
        value = cell.find(XLSX_MAIN + "v")
        if cell.attrib.get("t") == "s" and value is not None:
            try:
                return shared[int(value.text or "")]
            except (ValueError, IndexError):
                raise BatchValidationError("workbook has an invalid shared-string index") from None
        if cell.attrib.get("t") == "inlineStr":
            return "".join(text.text or "" for text in cell.iter(XLSX_MAIN + "t"))
        return value.text if value is not None and value.text else ""

    parsed = [
        { _column_number(cell.attrib["r"]): cell_text(cell) for cell in row.findall(XLSX_MAIN + "c") }
        for row in rows
    ]
    required = required_headers or {"user_id", "file", "annotator_1", "annotator_2"}
    header_index = next(
        (
            index for index, row in enumerate(parsed)
            if required.issubset({value.strip() for value in row.values()})
        ),
        None,
    )
    if header_index is None:
        raise BatchValidationError(f"sheet {sheet_name!r} lacks the required headers")
    header = {column: value.strip() for column, value in parsed[header_index].items()}
    result = []
    for row in parsed[header_index + 1:]:
        record = {
            header[column]: value.strip()
            for column, value in row.items()
            if column in header and header[column]
        }
        if any(record.get(field) for field in required):
            result.append(record)
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_mapping(row: dict[str, str], label_key: str) -> None:
    label = row[label_key]
    career_id = row[f"{label_key}_career_id"]
    canonical_name = row[f"{label_key}_canonical_name"]
    status = row[f"{label_key}_mapping_status"]
    if status not in {"EXACT", "ALIAS"}:
        raise BatchValidationError(f"{label_key} has unresolved mapping for {row['candidate_id']}")
    if not re.fullmatch(r"C(?:0[1-9]|10)", career_id):
        raise BatchValidationError(f"{label_key} maps outside the frozen 10-career IDs")
    if label == "Cybersecurity Analyst":
        if (career_id, canonical_name, status) != (
            "C09", "Cybersecurity Engineer/Analyst", "ALIAS",
        ):
            raise BatchValidationError("Cybersecurity Analyst must remain the C09 evaluation alias")
    elif status != "EXACT" or label != canonical_name:
        raise BatchValidationError(f"{label_key} must retain its exact frozen-name mapping")


def load_candidate_manifest(
    crosswalk_path: str | Path = DEFAULT_CROSSWALK,
    workbook_path: str | Path = DEFAULT_WORKBOOK,
    cv_root: str | Path = DEFAULT_CV_ROOT,
    *,
    expected_count: int = EXPECTED_CANDIDATES,
    allow_subset: bool = False,
) -> list[CandidateInput]:
    """Validate workbook rows, crosswalk labels, unique paths, and content hashes.

    ``allow_subset`` validates a frozen subset crosswalk (for example the 12-CV
    ablation manifest): every subset row must still match its workbook row, but
    the crosswalk need not list all workbook candidates. The default keeps the
    original all-candidates contract.
    """
    crosswalk_path = Path(crosswalk_path)
    workbook_path = Path(workbook_path)
    root = Path(cv_root).resolve()
    workbook_rows = _xlsx_sheet_rows(workbook_path, "Candidates Overview")
    workbook_by_id: dict[str, dict[str, str]] = {}
    for row in workbook_rows:
        candidate_id = row.get("user_id", "").strip()
        if not candidate_id or candidate_id in workbook_by_id:
            raise BatchValidationError("workbook candidate identifiers must be present and unique")
        workbook_by_id[candidate_id] = row

    try:
        with crosswalk_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            required_columns = {
                "candidate_id", "workbook_file", "proposed_cv_path", "cv_match_category",
                "cv_sha256", "annotator_1", "annotator_1_career_id",
                "annotator_1_canonical_name", "annotator_1_mapping_status",
                "annotator_2", "annotator_2_career_id", "annotator_2_canonical_name",
                "annotator_2_mapping_status",
            }
            if not reader.fieldnames or not required_columns.issubset(reader.fieldnames):
                raise BatchValidationError("crosswalk is missing required columns")
            crosswalk_rows = list(reader)
    except OSError as exc:
        raise BatchValidationError(f"cannot read crosswalk: {type(exc).__name__}") from None

    if allow_subset:
        if len(crosswalk_rows) != expected_count:
            raise BatchValidationError(
                f"expected {expected_count} crosswalk rows; found {len(crosswalk_rows)}"
            )
        if len(workbook_rows) < expected_count:
            raise BatchValidationError(
                f"workbook must contain at least {expected_count} candidate rows; "
                f"found {len(workbook_rows)}"
            )
    elif len(workbook_rows) != expected_count or len(crosswalk_rows) != expected_count:
        raise BatchValidationError(
            f"expected {expected_count} workbook and crosswalk rows; found "
            f"{len(workbook_rows)} and {len(crosswalk_rows)}"
        )
    ids = [row.get("candidate_id", "").strip() for row in crosswalk_rows]
    if any(not value for value in ids) or len(set(ids)) != len(ids):
        raise BatchValidationError("crosswalk candidate identifiers must be present and unique")
    if allow_subset:
        if not set(ids).issubset(workbook_by_id):
            raise BatchValidationError("crosswalk candidate IDs are not a subset of the workbook")
    elif set(ids) != set(workbook_by_id):
        raise BatchValidationError("crosswalk candidate IDs do not exactly match the workbook")

    seen_paths: set[Path] = set()
    mapping_by_label: dict[str, tuple[str, str, str]] = {}
    candidates: list[CandidateInput] = []
    for row in crosswalk_rows:
        row = {key: (value or "").strip() for key, value in row.items()}
        candidate_id = row["candidate_id"]
        workbook_row = workbook_by_id[candidate_id]
        if row["workbook_file"] != workbook_row.get("file", "").strip():
            raise BatchValidationError(f"workbook filename mismatch for {candidate_id}")
        for annotator in ANNOTATORS:
            if row[annotator] != workbook_row.get(annotator, "").strip():
                raise BatchValidationError(f"{annotator} label mismatch for {candidate_id}")
            _validate_mapping(row, annotator)
            mapping = (
                row[f"{annotator}_career_id"],
                row[f"{annotator}_canonical_name"],
                row[f"{annotator}_mapping_status"],
            )
            previous = mapping_by_label.setdefault(row[annotator], mapping)
            if previous != mapping:
                raise BatchValidationError(f"inconsistent mapping for label {row[annotator]!r}")

        if row["cv_match_category"] != "EXACT":
            raise BatchValidationError(f"unresolved CV match for {candidate_id}")
        declared_path = Path(row["proposed_cv_path"])
        if declared_path.is_absolute():
            raise BatchValidationError("crosswalk CV paths must be relative to the CV root")
        try:
            repo_relative_root = root.relative_to(REPO_ROOT)
        except ValueError:
            repo_relative_root = None
        if (
            repo_relative_root is not None
            and declared_path.parts[:len(repo_relative_root.parts)] == repo_relative_root.parts
        ):
            path = (REPO_ROOT / declared_path).resolve()
        else:
            path = (root / declared_path).resolve()
        try:
            contained = os.path.commonpath((str(root), str(path))) == str(root)
        except ValueError:
            contained = False
        if not contained:
            raise BatchValidationError(f"CV path escapes the configured root for {candidate_id}")
        if path in seen_paths:
            raise BatchValidationError(f"multiple candidates reference the same CV path: {declared_path}")
        seen_paths.add(path)
        if path.name != row["workbook_file"]:
            raise BatchValidationError(f"explicit workbook filename mismatch for {candidate_id}")
        if path.suffix.lower() not in {".pdf", ".txt", ".docx"} or not path.is_file():
            raise BatchValidationError(f"CV is missing or has an unsupported format for {candidate_id}")
        try:
            actual_hash = _sha256_file(path)
        except OSError as exc:
            raise BatchValidationError(f"CV is unreadable for {candidate_id}: {type(exc).__name__}") from None
        expected_hash = row["cv_sha256"].lower()
        if not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or actual_hash != expected_hash:
            raise BatchValidationError(f"CV SHA-256 mismatch for {candidate_id}")

        candidates.append(CandidateInput(
            candidate_id=candidate_id,
            workbook_file=row["workbook_file"],
            cv_path=path,
            cv_sha256=actual_hash,
            annotator_1=row["annotator_1"],
            annotator_1_career_id=row["annotator_1_career_id"],
            annotator_1_canonical_name=row["annotator_1_canonical_name"],
            annotator_1_mapping_status=row["annotator_1_mapping_status"],
            annotator_2=row["annotator_2"],
            annotator_2_career_id=row["annotator_2_career_id"],
            annotator_2_canonical_name=row["annotator_2_canonical_name"],
            annotator_2_mapping_status=row["annotator_2_mapping_status"],
        ))
    return candidates


def load_career_output_labels(path: str | Path = DEFAULT_OKB_WORKBOOK) -> list[CareerOutputLabel]:
    """Load only the frozen CAREER label space for B0; no relationships are read."""
    rows = _xlsx_sheet_rows(
        Path(path), "CAREER", required_headers={"career_id", "canonical_name"}
    )
    labels = [
        CareerOutputLabel(career_id=row.get("career_id", ""), career_name=row.get("canonical_name", ""))
        for row in rows
    ]
    expected = {f"C{number:02d}" for number in range(1, 11)}
    if len(labels) != 10 or {label.career_id for label in labels} != expected:
        raise BatchValidationError("frozen CAREER sheet must contain exactly canonical IDs C01-C10")
    return labels


def manifest_fingerprint(candidates: Iterable[CandidateInput]) -> str:
    payload = [
        {
            "candidate_id": row.candidate_id,
            "workbook_file": row.workbook_file,
            "cv_sha256": row.cv_sha256,
            "annotator_1": [row.annotator_1, row.annotator_1_career_id],
            "annotator_2": [row.annotator_2, row.annotator_2_career_id],
        }
        for row in candidates
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_dry_run_plan(
    candidates: list[CandidateInput],
    configurations: Iterable[str] = ALL_CONFIGURATIONS,
    *,
    run_id: str = "dry-run",
    manifest_source: str | None = None,
) -> dict[str, Any]:
    selected = list(configurations)
    if not selected or len(selected) != len(set(selected)):
        raise BatchValidationError("select one or more distinct experiment configurations")
    for configuration in selected:
        get_configuration(configuration)
    return {
        "mode": "dry_run",
        "run_id": run_id,
        "manifest_source": manifest_source,
        "candidate_count": len(candidates),
        "configurations": selected,
        "planned_configuration_runs": len(candidates) * len(selected),
        "manifest_sha256": manifest_fingerprint(candidates),
        "database_required": any(configuration != "B0" for configuration in selected),
        "profile_persistence_required": any(configuration in {"B3", "F"} for configuration in selected),
        "shared_frozen_bundle_per_candidate": True,
        "labels_evaluator_only": True,
        "candidate_inputs": [
            {
                "candidate_id": row.candidate_id,
                "cv_filename": row.workbook_file,
                "cv_sha256": row.cv_sha256,
                "category_label": row.annotator_1,
                "references": {
                    "annotator_1": row.annotator_1_career_id,
                    "annotator_2": row.annotator_2_career_id,
                },
            }
            for row in candidates
        ],
        "inference_label_leakage": False,
        "llm_calls": 0,
        "database_operations": 0,
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


class RedactedBundleCache:
    """Cache the frozen PII-redacted input so interrupted runs do not re-extract."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    @staticmethod
    def _key(candidate_id: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]", "_", candidate_id)[:120]

    def load(
        self,
        candidate: CandidateInput,
        *,
        extractor_prompt_sha256: str,
        model: str,
    ) -> tuple[FrozenProfileBundle, list[dict[str, Any]]] | None:
        path = self.root / f"{self._key(candidate.candidate_id)}.json"
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                payload.get("candidate_id") != candidate.candidate_id
                or payload.get("cv_sha256") != candidate.cv_sha256
                or payload.get("extractor_prompt_sha256") != extractor_prompt_sha256
                or payload.get("model") != model
            ):
                raise BatchValidationError(
                    f"frozen bundle cache identity mismatch for {candidate.candidate_id}; use a new run ID"
                )
            bundle = FrozenProfileBundle.model_validate(payload["bundle"])
            calls = payload.get("shared_input_llm_calls", [])
            if not isinstance(calls, list):
                raise BatchValidationError("cached shared LLM provenance must be a list")
            return bundle, calls
        except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, BatchValidationError):
                raise
            raise BatchValidationError(
                f"invalid frozen bundle cache for {candidate.candidate_id}: {type(exc).__name__}"
            ) from None

    def save(
        self,
        candidate: CandidateInput,
        bundle: FrozenProfileBundle,
        *,
        extractor_prompt_sha256: str,
        model: str,
        shared_input_llm_calls: list[dict[str, Any]],
    ) -> Path:
        path = self.root / f"{self._key(candidate.candidate_id)}.json"
        _atomic_json(path, {
            "schema_version": "frozen_profile_cache/1.0",
            "candidate_id": candidate.candidate_id,
            "cv_filename": candidate.workbook_file,
            "cv_sha256": candidate.cv_sha256,
            "extractor_prompt_sha256": extractor_prompt_sha256,
            "model": model,
            "cached_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "bundle": bundle.model_dump(mode="json"),
            "shared_input_llm_calls": shared_input_llm_calls,
            "contains_redacted_cv_derived_data": True,
        })
        return path


class PacedRetryLLMClient:
    """Sequential LLM wrapper with configurable pacing and transient backoff."""

    def __init__(
        self,
        client: Any,
        *,
        minimum_interval_seconds: float = 2.0,
        max_retries: int = 4,
        backoff_base_seconds: float = 2.0,
        backoff_max_seconds: float = 30.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        if minimum_interval_seconds < 0 or max_retries < 0 or backoff_base_seconds < 0:
            raise ValueError("pacing and retry settings must be non-negative")
        if backoff_max_seconds < backoff_base_seconds:
            raise ValueError("backoff_max_seconds must be >= backoff_base_seconds")
        self._client = client
        self._inner = client
        self.minimum_interval_seconds = minimum_interval_seconds
        self.max_retries = max_retries
        self.backoff_base_seconds = backoff_base_seconds
        self.backoff_max_seconds = backoff_max_seconds
        self._sleep = sleep
        self._clock = clock
        self._lock = threading.Lock()
        self._next_call_at = 0.0
        self.last_call_retry_count = 0
        self.total_retries = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._client, name)

    @staticmethod
    def _transient(exc: BaseException) -> bool:
        code = getattr(exc, "code", None)
        if code in {408, 429, 500, 502, 503, 504}:
            return True
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return True
        return type(exc).__name__ in {
            "DeadlineExceeded", "InternalServerError", "LLMQuotaExceededError",
            "RateLimitError", "ResourceExhausted", "ServiceUnavailable",
        }

    def _pace(self) -> None:
        delay = self._next_call_at - self._clock()
        if delay > 0:
            self._sleep(delay)
        self._next_call_at = self._clock() + self.minimum_interval_seconds

    def complete_json(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        with self._lock:
            retries = 0
            while True:
                self._pace()
                try:
                    result = self._client.complete_json(*args, **kwargs)
                    self.last_call_retry_count = retries
                    return result
                except Exception as exc:
                    if retries >= self.max_retries or not self._transient(exc):
                        self.last_call_retry_count = retries
                        raise
                    delay = min(
                        self.backoff_max_seconds,
                        self.backoff_base_seconds * (2 ** retries),
                    )
                    retries += 1
                    self.total_retries += 1
                    if delay:
                        self._sleep(delay)


def _is_isolated_engine(engine: Any) -> dict[str, Any]:
    if os.environ.get("CAREER_DB_URL", "").strip():
        raise BatchSafetyError("CAREER_DB_URL must be unset; it can override the isolated database name")
    if os.environ.get("CAREER_DB_NAME", "").strip() != ALLOWED_DATABASE:
        raise BatchSafetyError(f"CAREER_DB_NAME must be {ALLOWED_DATABASE}")
    if os.environ.get("CAREER_DB_HOST", "").strip().lower() != ALLOWED_DATABASE_HOST:
        raise BatchSafetyError(f"CAREER_DB_HOST must be explicitly set to {ALLOWED_DATABASE_HOST}")
    try:
        configured_port = int(os.environ.get("CAREER_DB_PORT", ""))
    except ValueError:
        configured_port = None
    if configured_port != ALLOWED_DATABASE_PORT:
        raise BatchSafetyError(f"CAREER_DB_PORT must be explicitly set to {ALLOWED_DATABASE_PORT}")
    if os.environ.get(DATABASE_OPT_IN, "") != ALLOWED_DATABASE:
        raise BatchSafetyError(f"explicit opt-in {DATABASE_OPT_IN}={ALLOWED_DATABASE} is required")
    url = engine.url
    host = (url.host or "").lower()
    if (
        host != ALLOWED_DATABASE_HOST
        or url.port != ALLOWED_DATABASE_PORT
        or url.database != ALLOWED_DATABASE
    ):
        raise BatchSafetyError("configured database must be the loopback isolated e2e database")
    with engine.connect() as connection:
        current = connection.execute(sql_text("SELECT current_database()"))
        server_database = current.scalar_one()
    if server_database != ALLOWED_DATABASE or server_database == "career_intelligence_main":
        raise BatchSafetyError("server-confirmed database is not the isolated e2e database")
    return {"name": url.database, "host": host, "port": url.port, "server_current_database": server_database}


def resolve_isolated_engine() -> tuple[Any, dict[str, Any]]:
    """Construct an engine only after requiring explicit isolated-target settings."""
    if os.environ.get("CAREER_DB_URL", "").strip():
        raise BatchSafetyError("CAREER_DB_URL must be unset before live batch execution")
    if os.environ.get("CAREER_DB_NAME", "").strip() != ALLOWED_DATABASE:
        raise BatchSafetyError(f"set CAREER_DB_NAME={ALLOWED_DATABASE} in the execution environment")
    if os.environ.get("CAREER_DB_HOST", "").strip().lower() != ALLOWED_DATABASE_HOST:
        raise BatchSafetyError(f"set CAREER_DB_HOST={ALLOWED_DATABASE_HOST} explicitly in the execution environment")
    try:
        configured_port = int(os.environ.get("CAREER_DB_PORT", ""))
    except ValueError:
        configured_port = None
    if configured_port != ALLOWED_DATABASE_PORT:
        raise BatchSafetyError(f"set CAREER_DB_PORT={ALLOWED_DATABASE_PORT} explicitly in the execution environment")
    if os.environ.get(DATABASE_OPT_IN, "") != ALLOWED_DATABASE:
        raise BatchSafetyError(f"set {DATABASE_OPT_IN}={ALLOWED_DATABASE} for explicit opt-in")
    from app.core import db

    # Mask any URL loaded from backend/.env so it cannot override CAREER_DB_NAME.
    prior_url = os.environ.get("CAREER_DB_URL")
    os.environ["CAREER_DB_URL"] = ""
    try:
        engine = db.get_engine()
    finally:
        if prior_url is None:
            os.environ.pop("CAREER_DB_URL", None)
        else:
            os.environ["CAREER_DB_URL"] = prior_url
    return engine, _is_isolated_engine(engine)


def _recommendation_prediction(record: Any | None) -> RecommendationPrediction | None:
    if record is None or record.execution_status != "success":
        return None
    normalized = record.normalized_evaluation_output
    if not isinstance(normalized, dict) or not isinstance(normalized.get("recommendation"), dict):
        return None
    try:
        prediction = RecommendationPrediction.model_validate(normalized["recommendation"])
    except Exception:
        return None
    canonical_ids = {f"C{number:02d}" for number in range(1, 11)}
    if len(prediction.ranking) != 10 or set(prediction.ranking) != canonical_ids:
        return None
    return prediction


def _make_evaluation_case(
    candidate: CandidateInput,
    configuration_id: str,
    annotator: str,
    record: Any | None,
) -> EvaluationCase:
    recommendation = _recommendation_prediction(record)
    valid = recommendation is not None
    return EvaluationCase(
        profile_id=candidate.candidate_id,
        config_id=configuration_id,  # type: ignore[arg-type]
        run_status="completed" if valid else "failed",
        references=EvaluationReferences(recommendation=candidate.reference(annotator)),
        recommendation=recommendation,
    )


def _metric_value(profile: dict[str, Any], name: str) -> float | None:
    metric = profile.get("metrics", {}).get(name, {})
    return metric.get("value") if metric.get("status") == "computed" else None


def _case_csv_rows(candidate_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    columns = (
        "candidate_id", "cv_filename", "cv_sha256", "configuration_id", "execution_status",
        "annotator", "reference_label", "reference_career_id", "prediction_valid",
        "top1_career_id", "ranking_json", "top1_accuracy", "hit_at_1", "hit_at_3",
        "mrr", "ndcg_at_3", "model", "revision_count", "verification_outcome",
        "error_type", "error_stage",
    )
    output: list[dict[str, Any]] = []
    for case in candidate_results:
        for configuration_id, config_result in case["configurations"].items():
            for annotator in ANNOTATORS:
                profile = config_result["evaluations"][annotator]
                normalized = config_result.get("normalized_evaluation_output") or {}
                prediction = normalized.get("recommendation") if config_result["execution_status"] == "success" else None
                ranking = prediction.get("ranking", []) if isinstance(prediction, dict) else []
                record = config_result.get("record") or {}
                row = {
                    "candidate_id": case["candidate_id"],
                    "cv_filename": case["cv_filename"],
                    "cv_sha256": case["cv_sha256"],
                    "configuration_id": configuration_id,
                    "execution_status": config_result["execution_status"],
                    "annotator": annotator,
                    "reference_label": getattr(case["candidate"], annotator),
                    "reference_career_id": getattr(case["candidate"], f"{annotator}_career_id"),
                    "prediction_valid": bool(prediction and ranking),
                    "top1_career_id": ranking[0] if ranking else "",
                    "ranking_json": json.dumps(ranking, ensure_ascii=False),
                    "top1_accuracy": _metric_value(profile, "career.top1_accuracy"),
                    "hit_at_1": _metric_value(profile, "career.hit_at_1"),
                    "hit_at_3": _metric_value(profile, "career.hit_at_3"),
                    "mrr": _metric_value(profile, "career.mrr"),
                    "ndcg_at_3": _metric_value(profile, "career.ndcg_at_3"),
                    "model": record.get("llm_model"),
                    "revision_count": record.get("revision_count"),
                    "verification_outcome": record.get("final_verification_status"),
                    "error_type": config_result.get("error_type"),
                    "error_stage": config_result.get("error_stage"),
                }
                output.append({key: row.get(key) for key in columns})
    return output


class CandidateBatchRunner:
    """Sequential paired batch orchestration over validated candidate inputs."""

    def __init__(
        self,
        *,
        candidates: list[CandidateInput],
        configurations: Iterable[str],
        run_id: str,
        output_dir: str | Path,
        bundle_cache: RedactedBundleCache,
        experiment_runner: ExperimentRunner,
        bundle_builder: Callable[[CandidateInput], tuple[FrozenProfileBundle, list[dict[str, Any]], dict[str, Any]]],
        user_scope: Callable[[CandidateInput], Any],
        model: str,
        extractor_prompt_sha256: str,
        database_identity: dict[str, Any] | None = None,
        reference_source: str = "docs/experiments/candidate_cv_career_crosswalk_draft.csv",
    ):
        self.candidates = candidates
        self.configurations = list(configurations)
        if not self.configurations or len(set(self.configurations)) != len(self.configurations):
            raise BatchValidationError("configurations must be non-empty and unique")
        for configuration_id in self.configurations:
            get_configuration(configuration_id)
        self.run_id = run_id
        self.output_dir = Path(output_dir)
        self.bundle_cache = bundle_cache
        self.experiment_runner = experiment_runner
        self.bundle_builder = bundle_builder
        self.user_scope = user_scope
        self.model = model
        self.extractor_prompt_sha256 = extractor_prompt_sha256
        self.database_identity = database_identity
        self.reference_source = reference_source
        self._evaluation_cases: dict[tuple[str, str, str], EvaluationCase] = {}

    def _bundle_for(self, candidate: CandidateInput):
        cached = self.bundle_cache.load(
            candidate,
            extractor_prompt_sha256=self.extractor_prompt_sha256,
            model=self.model,
        )
        if cached is not None:
            bundle, shared_calls = cached
            return bundle, shared_calls, {"status": "reused", "llm_calls": 0}
        started = time.monotonic()
        bundle, shared_calls, extraction_metadata = self.bundle_builder(candidate)
        bundle = FrozenProfileBundle.model_validate(bundle)
        path = self.bundle_cache.save(
            candidate,
            bundle,
            extractor_prompt_sha256=self.extractor_prompt_sha256,
            model=self.model,
            shared_input_llm_calls=shared_calls,
        )
        return bundle, shared_calls, {
            **extraction_metadata,
            "status": "success",
            "duration_ms": round((time.monotonic() - started) * 1000, 2),
            "bundle_fingerprint": hashlib.sha256(
                json.dumps(bundle.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
            "cache_path": str(path),
        }

    def _record_case_failure(
        self,
        candidate: CandidateInput,
        extraction: dict[str, Any],
        exc: BaseException,
        stage: str,
    ) -> dict[str, Any]:
        configurations: dict[str, Any] = {}
        for configuration_id in self.configurations:
            evaluations = {}
            for annotator in ANNOTATORS:
                evaluation = evaluate_case(
                    _make_evaluation_case(candidate, configuration_id, annotator, None)
                )
                evaluations[annotator] = evaluation.model_dump(mode="json")
                self._evaluation_cases[(configuration_id, annotator, candidate.candidate_id)] = (
                    _make_evaluation_case(candidate, configuration_id, annotator, None)
                )
            configurations[configuration_id] = {
                "execution_status": "failed",
                "error_type": type(exc).__name__,
                "error_stage": stage,
                "error_message": "Exception details omitted to protect CV-derived data.",
                "record": None,
                "normalized_evaluation_output": None,
                "evaluations": evaluations,
                "capabilities": {
                    "roadmap": "NOT_APPLICABLE" if configuration_id in {"B0", "B2"} else "unavailable",
                    "verification": "NOT_APPLICABLE" if configuration_id in {"B0", "B2", "B3"} else "unavailable",
                },
            }
        return {
            "candidate_id": candidate.candidate_id,
            "cv_filename": candidate.workbook_file,
            "cv_sha256": candidate.cv_sha256,
            "extraction": extraction,
            "configurations": configurations,
            "candidate": candidate,
        }

    def run(self) -> dict[str, Any]:
        checkpoint_path = self.output_dir / "checkpoint.json"
        fingerprint = manifest_fingerprint(self.candidates)
        if checkpoint_path.exists():
            try:
                prior = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raise BatchValidationError("existing batch checkpoint is unreadable") from None
            if (
                prior.get("manifest_sha256") != fingerprint
                or prior.get("run_id") != self.run_id
                or prior.get("configurations") != self.configurations
                or prior.get("model") != self.model
                or prior.get("extractor_prompt_sha256") != self.extractor_prompt_sha256
            ):
                raise BatchValidationError("checkpoint identity changed; choose a new run ID")

        candidate_results: list[dict[str, Any]] = []
        completed: list[str] = []
        for candidate in self.candidates:
            extraction = {"status": "not_started"}
            records: list[Any] = []
            try:
                bundle, shared_calls, extraction = self._bundle_for(candidate)
                needs_user = any(configuration in {"B3", "F"} for configuration in self.configurations)
                scope = self.user_scope(candidate) if needs_user else nullcontext(1)
                with scope as user_id:
                    result = self.experiment_runner.run_case(
                        case_id=f"cv-{candidate.cv_sha256[:16]}",
                        run_id=self.run_id,
                        bundle=bundle,
                        user_id=user_id,
                        configurations=self.configurations,
                        metadata={
                            "cv_sha256": candidate.cv_sha256,
                            "shared_input_llm_calls": shared_calls,
                            "reference_source": "evaluator_only_crosswalk",
                        },
                        resume=True,
                    )
                records = result.records
            except BatchSafetyError:
                raise
            except Exception as exc:
                candidate_results.append(
                    self._record_case_failure(candidate, extraction, exc, "bundle_or_inference")
                )
                self._write_case_artifact(candidate_results[-1])
                self._write_checkpoint(checkpoint_path, fingerprint, completed, candidate_results)
                continue

            by_configuration = {record.configuration_id: record for record in records}
            configuration_results: dict[str, Any] = {}
            for configuration_id in self.configurations:
                record = by_configuration.get(configuration_id)
                prediction = _recommendation_prediction(record)
                record_status = record.execution_status if record else "failed"
                batch_status = record_status if prediction is not None else (
                    record_status if record_status != "success" else "incomplete_output"
                )
                evaluations = {}
                for annotator in ANNOTATORS:
                    evaluation_case = _make_evaluation_case(
                        candidate, configuration_id, annotator, record
                    )
                    self._evaluation_cases[(configuration_id, annotator, candidate.candidate_id)] = evaluation_case
                    evaluations[annotator] = evaluate_case(evaluation_case).model_dump(mode="json")
                normalized = record.normalized_evaluation_output if record else None
                configuration_results[configuration_id] = {
                    "execution_status": batch_status,
                    "source_execution_status": record_status,
                    "error_type": (
                        record.error_type if record and record_status != "success"
                        else None if prediction is not None else "IncompleteRecommendation"
                    ),
                    "error_stage": (
                        record.error_stage if record and record_status != "success"
                        else None if prediction is not None else "output_validation"
                    ),
                    "record": record.model_dump(mode="json") if record else None,
                    "normalized_evaluation_output": normalized if prediction is not None else None,
                    "evaluations": evaluations,
                    "capabilities": record.capabilities if record else {},
                }
            case_result = {
                "candidate_id": candidate.candidate_id,
                "cv_filename": candidate.workbook_file,
                "cv_sha256": candidate.cv_sha256,
                "extraction": extraction,
                "configurations": configuration_results,
                "candidate": candidate,
            }
            candidate_results.append(case_result)
            completed.append(candidate.candidate_id)
            self._write_case_artifact(case_result)
            self._write_checkpoint(checkpoint_path, fingerprint, completed, candidate_results)

        aggregates: dict[str, Any] = {}
        for configuration_id in self.configurations:
            aggregates[configuration_id] = {}
            for annotator in ANNOTATORS:
                cases = [
                    self._evaluation_cases[(configuration_id, annotator, candidate.candidate_id)]
                    for candidate in self.candidates
                ]
                aggregates[configuration_id][annotator] = evaluate_report(cases).to_dict()

        serializable_cases = [self._public_case_result(item) for item in candidate_results]
        report = {
            "schema_version": "candidate_batch_report/1.0",
            "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            "run_id": self.run_id,
            "manifest_sha256": fingerprint,
            "configurations": self.configurations,
            "candidate_count": len(self.candidates),
            "database_identity": self.database_identity,
            "model": self.model,
            "reference_policy": "Annotator 1 and annotator 2 are evaluated independently; no consensus is inferred.",
            "single_label_metric_limit": "Each annotator supplies one positive career label; unlabeled careers are not asserted irrelevant. Precision@K and Recall@K are not reported.",
            "technology_weight": "UNRESOLVED; no wT is applied by the experiment runner.",
            "aggregate_by_configuration_and_annotator": aggregates,
            "cases": serializable_cases,
            "failed_or_incomplete": [
                {
                    "candidate_id": case["candidate_id"],
                    "configuration_id": configuration_id,
                    "execution_status": value["execution_status"],
                    "error_type": value.get("error_type"),
                    "error_stage": value.get("error_stage"),
                }
                for case in candidate_results
                for configuration_id, value in case["configurations"].items()
                if value["execution_status"] != "success"
            ],
        }
        _atomic_json(self.output_dir / "summary.json", report)
        self._write_case_csv(candidate_results)
        self._write_summary_markdown(report)
        return report

    def _public_case_result(self, case: dict[str, Any]) -> dict[str, Any]:
        candidate: CandidateInput = case["candidate"]
        output = {key: value for key, value in case.items() if key != "candidate"}
        references = {
            "source": self.reference_source,
        }
        for annotator in ANNOTATORS:
            references[annotator] = {
                "label": getattr(candidate, annotator),
                "career_id": getattr(candidate, f"{annotator}_career_id"),
                "canonical_name": getattr(candidate, f"{annotator}_canonical_name"),
                "mapping_status": getattr(candidate, f"{annotator}_mapping_status"),
            }
        output["references"] = references
        return output

    def _write_case_artifact(self, case: dict[str, Any]) -> None:
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", case["candidate_id"])[:120]
        _atomic_json(self.output_dir / "cases" / f"{safe}.json", self._public_case_result(case))

    def _write_checkpoint(
        self,
        path: Path,
        fingerprint: str,
        completed: list[str],
        results: list[dict[str, Any]],
    ) -> None:
        _atomic_json(path, {
            "schema_version": "candidate_batch_checkpoint/1.0",
            "run_id": self.run_id,
            "manifest_sha256": fingerprint,
            "configurations": self.configurations,
            "model": self.model,
            "extractor_prompt_sha256": self.extractor_prompt_sha256,
            "completed_candidates": completed,
            "case_count": len(results),
            "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        })

    def _write_case_csv(self, cases: list[dict[str, Any]]) -> None:
        path = self.output_dir / "cases.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        fieldnames = [
            "candidate_id", "cv_filename", "cv_sha256", "configuration_id", "execution_status",
            "annotator", "reference_label", "reference_career_id", "prediction_valid",
            "top1_career_id", "ranking_json", "top1_accuracy", "hit_at_1", "hit_at_3",
            "mrr", "ndcg_at_3", "model", "revision_count", "verification_outcome",
            "error_type", "error_stage",
        ]
        try:
            with temporary.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                for row in _case_csv_rows(cases):
                    writer.writerow(row)
            os.replace(temporary, path)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _write_summary_markdown(self, report: dict[str, Any]) -> None:
        lines = [
            "# Candidate Batch Evaluation Summary",
            "",
            f"- Run: `{report['run_id']}`",
            f"- Candidates: {report['candidate_count']}",
            f"- Configurations: {', '.join(report['configurations'])}",
            "- Labels: annotator reports remain separate; no consensus rule applied.",
            "- Technology weight: unresolved; no `wT` applied.",
            "",
            "| Configuration | Annotator | Top-1 accuracy | Hit@1 | Hit@3 | MRR | nDCG@3 | Failed cases |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        for configuration_id, annotator_reports in report["aggregate_by_configuration_and_annotator"].items():
            for annotator, evaluation in annotator_reports.items():
                metrics = evaluation["metrics"]
                value = lambda key: (
                    f"{metrics[key]['value']:.4f}"
                    if key in metrics and metrics[key]["status"] == "computed" else "unavailable"
                )
                lines.append(
                    f"| {configuration_id} | {annotator} | {value('career.top1_accuracy')} | "
                    f"{value('career.hit_at_1')} | {value('career.hit_at_3')} | "
                    f"{value('career.mrr')} | {value('career.ndcg_at_3')} | "
                    f"{evaluation['failed_case_count']} |"
                )
        lines.extend(["", "Failed or incomplete cases are listed in `summary.json` and `cases.csv`."])
        path = self.output_dir / "summary.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
        os.replace(temporary, path)


def _case_csv_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for case in cases:
        candidate: CandidateInput = case["candidate"]
        for configuration_id, config_result in case["configurations"].items():
            normalized = config_result.get("normalized_evaluation_output") or {}
            prediction = (
                normalized.get("recommendation")
                if config_result["execution_status"] == "success" else None
            )
            ranking = prediction.get("ranking", []) if isinstance(prediction, dict) else []
            record = config_result.get("record") or {}
            for annotator in ANNOTATORS:
                profile = config_result["evaluations"][annotator]
                metrics = profile.get("metrics", {})
                value = lambda name: (
                    metrics[name].get("value")
                    if name in metrics and metrics[name].get("status") == "computed" else ""
                )
                output.append({
                    "candidate_id": candidate.candidate_id,
                    "cv_filename": candidate.workbook_file,
                    "cv_sha256": candidate.cv_sha256,
                    "configuration_id": configuration_id,
                    "execution_status": config_result["execution_status"],
                    "annotator": annotator,
                    "reference_label": getattr(candidate, annotator),
                    "reference_career_id": getattr(candidate, f"{annotator}_career_id"),
                    "prediction_valid": bool(prediction and ranking),
                    "top1_career_id": ranking[0] if ranking else "",
                    "ranking_json": json.dumps(ranking, ensure_ascii=False),
                    "top1_accuracy": value("career.top1_accuracy"),
                    "hit_at_1": value("career.hit_at_1"),
                    "hit_at_3": value("career.hit_at_3"),
                    "mrr": value("career.mrr"),
                    "ndcg_at_3": value("career.ndcg_at_3"),
                    "model": record.get("llm_model"),
                    "revision_count": record.get("revision_count"),
                    "verification_outcome": record.get("final_verification_status"),
                    "error_type": config_result.get("error_type"),
                    "error_stage": config_result.get("error_stage"),
                })
    return output


def _live_bundle_builder(client: PacedRetryLLMClient, run_id: str):
    extractor_prompt = FrozenProfileBundleExtractor.SYSTEM
    prompt_hash = hashlib.sha256(extractor_prompt.encode("utf-8")).hexdigest()

    def build(candidate: CandidateInput):
        extraction = CVTextExtractor().extract(candidate.cv_path.read_bytes(), candidate.workbook_file)
        redacted = redact_pii(extraction.extracted_text).redacted_text
        recorder = LLMCallProvenance(f"cv-{candidate.cv_sha256[:16]}", run_id, "SHARED_INPUT")
        bundle = FrozenProfileBundleExtractor(recorder.wrap(client)).run(redacted)
        return bundle, recorder.snapshot(), {
            "source_format": extraction.metadata.format,
            "source_size_bytes": extraction.metadata.size_bytes,
            "page_count": extraction.metadata.page_count,
            "character_count": extraction.metadata.character_count,
            "extractor_prompt_sha256": prompt_hash,
        }

    return build, prompt_hash


def _isolated_user_scope(engine: Any, candidate: CandidateInput, run_id: str):
    @contextmanager
    def scope() -> Iterator[int]:
        from app.services import user_service as us
        from scripts.manual_validation import _cleanup_synthetic_user

        unique = uuid.uuid4().hex
        user = us.create_user(
            f"batch_{candidate.cv_sha256[:12]}_{unique}@example.invalid",
            "Synthetic Batch Evaluation User",
        )
        cleanup_error = None
        try:
            yield user.user_id
        finally:
            ok, details = _cleanup_synthetic_user(engine, user.user_id)
            if not ok:
                cleanup_error = BatchSafetyError(
                    f"synthetic user cleanup could not be verified (user_id={user.user_id}; "
                    f"remaining={details.get('remaining')})"
                )
            if cleanup_error:
                raise cleanup_error
    return scope()


def _default_output_dir(run_id: str) -> Path:
    return ExperimentStore().root / "candidate_batches" / run_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crosswalk", type=Path, default=DEFAULT_CROSSWALK)
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--cv-root", type=Path, default=DEFAULT_CV_ROOT)
    parser.add_argument("--okb-workbook", type=Path, default=DEFAULT_OKB_WORKBOOK)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--configuration", action="append", choices=ALL_CONFIGURATIONS)
    parser.add_argument("--limit", type=int, default=None, help="Run only the first N manifest rows.")
    parser.add_argument(
        "--subset-manifest", action="store_true",
        help=(
            "Validate the frozen 12-CV ablation crosswalk (subset of the workbook) "
            "instead of requiring all 43 candidates."
        ),
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the plan without LLM or database operations.")
    parser.add_argument("--execute", action="store_true", help="Run real inference; default mode is dry-run.")
    parser.add_argument("--approve-live-llm", action="store_true")
    parser.add_argument("--cache-redacted-bundles", action="store_true")
    parser.add_argument("--minimum-request-interval", type=float, default=2.0)
    parser.add_argument("--max-retries", type=int, default=4)
    parser.add_argument("--backoff-base-seconds", type=float, default=2.0)
    parser.add_argument("--concurrency", type=int, default=1, choices=[1])
    parser.add_argument("--max-revisions", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    args = parser.parse_args(argv)

    try:
        if args.subset_manifest:
            candidates = load_candidate_manifest(
                args.crosswalk,
                args.workbook,
                args.cv_root,
                expected_count=SUBSET_SIZE,
                allow_subset=True,
            )
        else:
            candidates = load_candidate_manifest(args.crosswalk, args.workbook, args.cv_root)
        if args.limit is not None:
            if args.limit <= 0:
                raise BatchValidationError("--limit must be positive")
            candidates = candidates[:args.limit]
        configurations = args.configuration or list(ALL_CONFIGURATIONS)
        run_id = args.run_id or dt.datetime.now(dt.timezone.utc).strftime("batch-%Y%m%dT%H%M%SZ")
        if args.dry_run and args.execute:
            raise BatchValidationError("choose either --dry-run or --execute")
        if not args.execute:
            print(json.dumps(
                build_dry_run_plan(
                    candidates, configurations, run_id=run_id,
                    manifest_source=str(args.crosswalk),
                ),
                ensure_ascii=False,
                indent=2,
            ))
            return 0
        if not args.approve_live_llm:
            raise BatchSafetyError("live inference requires --approve-live-llm")
        if not args.cache_redacted_bundles:
            raise BatchSafetyError(
                "resume requires --cache-redacted-bundles; the cache contains PII-redacted CV-derived profile data"
            )
        if args.minimum_request_interval < 0 or args.max_retries < 0 or args.backoff_base_seconds < 0:
            raise BatchValidationError("pacing and retry values must be non-negative")

        needs_database = any(configuration != "B0" for configuration in configurations)
        engine = None
        identity = None
        if needs_database:
            engine, identity = resolve_isolated_engine()

        base_client = GeminiClient()
        llm_client = PacedRetryLLMClient(
            base_client,
            minimum_interval_seconds=args.minimum_request_interval,
            max_retries=args.max_retries,
            backoff_base_seconds=args.backoff_base_seconds,
        )
        career_labels = load_career_output_labels(args.okb_workbook)
        output_dir = args.output_dir or _default_output_dir(run_id)
        record_store = ExperimentStore(output_dir / "run_records")
        experiment_runner = ExperimentRunner(
            store=record_store,
            llm_client=llm_client,
            career_labels=career_labels,
            max_revisions=args.max_revisions,
            timeout_seconds=args.timeout_seconds,
            enforce_database_isolation=needs_database,
        )
        bundle_builder, prompt_hash = _live_bundle_builder(llm_client, run_id)

        def user_scope(candidate: CandidateInput):
            if engine is None:
                return nullcontext(1)
            return _isolated_user_scope(engine, candidate, run_id)

        batch = CandidateBatchRunner(
            candidates=candidates,
            configurations=configurations,
            run_id=run_id,
            output_dir=output_dir,
            bundle_cache=RedactedBundleCache(output_dir / "frozen_inputs"),
            experiment_runner=experiment_runner,
            bundle_builder=bundle_builder,
            user_scope=user_scope,
            model=base_client.model,
            extractor_prompt_sha256=prompt_hash,
            database_identity=identity,
            reference_source=str(args.crosswalk),
        )
        report = batch.run()
        print(json.dumps({
            "status": "complete_with_failures" if report["failed_or_incomplete"] else "complete",
            "run_id": run_id,
            "candidate_count": len(candidates),
            "output_dir": str(output_dir),
            "failed_configuration_count": len(report["failed_or_incomplete"]),
            "llm_retry_count": llm_client.total_retries,
        }, ensure_ascii=False, indent=2))
        return 0 if not report["failed_or_incomplete"] else 2
    except (BatchValidationError, BatchSafetyError) as exc:
        print(json.dumps({"status": "REFUSED", "error_type": type(exc).__name__, "message": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())