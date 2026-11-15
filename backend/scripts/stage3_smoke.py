"""Stage 3 controlled end-to-end smoke test: one CV, four configurations.

This script is an orchestrator, not a pipeline implementation. It uses:

* ``CVTextExtractor`` for the selected CV,
* ``FrozenProfileBundleExtractor`` for the shared frozen bundle,
* ``ExperimentRunner.run_case`` for B0, B2, B3, and F,
* the existing ``CareerWorkflow`` and agents inside the runner,
* ``ExperimentStore`` for file-based experiment artifacts.

Safety
------
* Requires ``--approve-live-llm`` before any provider call.
* Refuses to run unless ``CAREER_DB_NAME`` is an isolated ``_eval``/``_test``
  database, ``CAREER_DB_URL`` is unset, and the server-confirmed database and
  loopback host match the configured target.
* Reads exactly one PDF under ``docs/cv_test``; never a directory.
* Creates one synthetic user, writes only to the isolated evaluation database,
  and removes that exact user after the run unless ``--keep-user`` is passed.
* Never reads the ground-truth workbook. Workbook hash and mapping status are
  supplied separately for the evaluation metadata file only.
* Prints no CV text, names, emails, phone numbers, or annotation values.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import text  # noqa: E402

from app.agents.llm_client import GeminiClient  # noqa: E402
from app.core.db import get_engine  # noqa: E402
from app.evaluation.baseline_inference import (  # noqa: E402
    CareerOutputLabel,
    FrozenProfileBundle,
    FrozenProfileBundleExtractor,
)
from app.evaluation.experiment_store import ExperimentStore  # noqa: E402
from app.evaluation.runner import (  # noqa: E402
    ExperimentRunner,
    LLMCallProvenance,
    assert_isolated_database,
    database_name,
    fingerprint_bundle,
)
from app.evaluation.schemas import ConfigId  # noqa: E402
from app.services import retrieval_service as rs  # noqa: E402
from app.services import user_service as us  # noqa: E402
from app.services.cv_text_extraction_service import CVTextExtractor  # noqa: E402
from app.workflows.career_workflow import CareerWorkflow  # noqa: E402

USER_TABLES = (
    "user_skill_evidence",
    "user_skills",
    "user_preferences",
    "user_education",
    "user_experience",
    "user_projects",
    "user_certifications",
    "user_profiles",
    "users",
)
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


class SmokeSafetyError(RuntimeError):
    """The Stage 3 smoke test refused an unsafe input or target."""


def _utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _validate_isolated_target() -> dict[str, Any]:
    if os.environ.get("CAREER_DB_URL", "").strip():
        raise SmokeSafetyError(
            "CAREER_DB_URL is set; refuse to run because the effective target "
            "could bypass the isolated-database name check."
        )
    configured = database_name()
    assert_isolated_database(configured)
    engine = get_engine()
    host = engine.url.host or "unavailable"
    if host not in LOOPBACK_HOSTS:
        raise SmokeSafetyError(
            f"database host {host!r} is not loopback; refuse to run."
        )
    with engine.connect() as connection:
        server_database = connection.execute(text("select current_database()")).scalar_one()
    if server_database != configured:
        raise SmokeSafetyError(
            "server-confirmed database does not match the configured isolated target."
        )
    return {
        "name": configured,
        "host": host,
        "port": engine.url.port,
        "server_current_database": server_database,
    }


def _select_cv(requested: str | None) -> Path:
    default = REPO_ROOT / "docs" / "cv_test" / "cv_test_001_CS.pdf"
    path = Path(requested) if requested else default
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    else:
        path = path.resolve()
    allowed_root = (REPO_ROOT / "docs" / "cv_test").resolve()
    if allowed_root not in path.parents:
        raise SmokeSafetyError(
            "the Stage 3 CV must be a single file under docs/cv_test; "
            "data/cv_test and other directories are refused."
        )
    if not path.is_file():
        raise SmokeSafetyError("the selected CV is not a readable file.")
    if path.suffix.lower() != ".pdf":
        raise SmokeSafetyError("the Stage 3 smoke test requires a PDF input.")
    return path


def _load_or_create_bundle(
    *,
    cv_path: Path,
    extracted_text: str,
    client: Any,
    bundle_file: Path | None,
) -> tuple[FrozenProfileBundle, Path, bool]:
    input_sha = _sha256_file(cv_path)
    if bundle_file is not None and bundle_file.is_file():
        payload = json.loads(bundle_file.read_text(encoding="utf-8"))
        if payload.get("input_file_sha256") != input_sha:
            raise SmokeSafetyError(
                "the supplied bundle file does not belong to the selected CV."
            )
        bundle = FrozenProfileBundle.model_validate(payload["bundle"])
        return bundle, bundle_file, True

    bundle = FrozenProfileBundleExtractor(client).run(extracted_text)
    bundle = FrozenProfileBundle.model_validate(bundle)
    target = bundle_file or (
        Path(tempfile.gettempdir())
        / "opencode"
        / f"stage3_bundle_{input_sha[:16]}.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {"input_file_sha256": input_sha, "bundle": bundle.model_dump(mode="json")},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return bundle, target, False


def _user_row_counts(engine, user_id: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        for table in USER_TABLES:
            if table == "user_skill_evidence":
                counts[table] = connection.execute(
                    text(
                        "SELECT count(*) FROM user_skill_evidence WHERE user_skill_id IN "
                        "(SELECT user_skill_id FROM user_skills WHERE user_id = :user_id)"
                    ),
                    {"user_id": user_id},
                ).scalar_one()
            else:
                counts[table] = connection.execute(
                    text(f"SELECT count(*) FROM {table} WHERE user_id = :user_id"),
                    {"user_id": user_id},
                ).scalar_one()
    return counts


def _recommendation_summary(record) -> list[dict[str, Any]]:
    state = record.raw_structured_output or {}
    baseline = state.get("baseline_result")
    rows: Any
    if isinstance(baseline, dict):
        rows = baseline.get("recommendations")
    else:
        rows = state.get("recommendations")
    summary: list[dict[str, Any]] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        summary.append(
            {
                "career_id": row.get("career_id"),
                "rank": row.get("rank"),
                "fit_score": row.get("fit_score"),
            }
        )
    return summary


def _skill_gap_summary(record) -> dict[str, Any] | None:
    state = record.raw_structured_output or {}
    baseline = state.get("baseline_result")
    if isinstance(baseline, dict):
        gap = baseline.get("skill_gap")
    else:
        outer = state.get("skill_gap")
        gap = outer.get("skill_gap") if isinstance(outer, dict) else outer
    if not isinstance(gap, dict):
        return None
    categories = ("matched_evidenced", "matched_claimed_only", "missing", "unmatched_user_claims")
    counts = {
        key: len(gap.get(key, [])) if isinstance(gap.get(key), list) else None
        for key in categories
    }
    statuses: dict[str, str] = {}
    for key in ("matched_evidenced", "matched_claimed_only", "missing"):
        for item in gap.get(key, []) if isinstance(gap.get(key), list) else []:
            if isinstance(item, dict) and isinstance(item.get("skill_id"), str):
                statuses.setdefault(item["skill_id"], key)
            elif isinstance(item, str):
                statuses.setdefault(item, key)
    unmatched = gap.get("unmatched_user_claims")
    claim_matches = gap.get("claim_matches") if isinstance(gap.get("claim_matches"), dict) else {}
    mapped_mentions = [
        mention_id for ids in claim_matches.values() if isinstance(ids, list)
        for mention_id in ids if isinstance(mention_id, str)
    ]
    return {
        "status": gap.get("status", "AVAILABLE"),
        "career_id": gap.get("career_id"),
        "fit_score": gap.get("fit_score"),
        "categories_present": all(key in gap for key in categories),
        "category_counts": counts,
        "required_skill_total": len(statuses) if statuses else None,
        "category_sets_disjoint": (
            all(counts[key] is not None for key in categories[:3])
            and len(statuses) == sum(counts[key] for key in categories[:3])
            if statuses else None
        ),
        "unmatched_claims_valid": (
            isinstance(unmatched, list)
            and len(unmatched) == len(set(unmatched))
            and not (set(unmatched) & set(mapped_mentions))
            if isinstance(unmatched, list) and all(isinstance(item, str) for item in unmatched)
            else None
        ),
        "unmatched_claim_count": len(unmatched) if isinstance(unmatched, list) else None,
    }


def _roadmap_summary(record) -> dict[str, Any] | None:
    state = record.raw_structured_output or {}
    roadmap = state.get("roadmap")
    if not isinstance(roadmap, dict):
        return None
    items = roadmap.get("items") if isinstance(roadmap.get("items"), list) else []
    gap = state.get("skill_gap")
    gap_result = gap.get("skill_gap") if isinstance(gap, dict) else None
    expected: set[str] = set()
    if isinstance(gap_result, dict):
        for key in ("matched_claimed_only", "missing"):
            for item in gap_result.get(key, []) if isinstance(gap_result.get(key), list) else []:
                if isinstance(item, dict) and isinstance(item.get("skill_id"), str):
                    expected.add(item["skill_id"])
    covered = {
        item.get("skill_id")
        for item in items
        if isinstance(item, dict) and isinstance(item.get("skill_id"), str)
    }
    return {
        "item_count": len(items),
        "grounded_item_count": sum(
            1
            for item in items
            if isinstance(item, dict)
            and isinstance(item.get("knowledge_base_basis"), str)
            and item["knowledge_base_basis"].strip()
        ),
        "expected_skill_count": len(expected),
        "covered_skill_count": len(expected & covered),
        "coverage_complete": expected.issubset(covered) if expected else None,
        "narrative_source": roadmap.get("narrative_source"),
        "llm_error_present": bool(roadmap.get("llm_error")),
    }


def _verification_summary(record) -> dict[str, Any] | None:
    state = record.raw_structured_output or {}
    verification = state.get("verification")
    if not isinstance(verification, dict):
        return None
    checks = verification.get("checks") if isinstance(verification.get("checks"), list) else []
    check_statuses: dict[str, int] = {}
    for check in checks:
        if isinstance(check, dict) and isinstance(check.get("status"), str):
            check_statuses[check["status"]] = check_statuses.get(check["status"], 0) + 1
    return {
        "status": verification.get("status"),
        "check_count": len(checks),
        "check_status_counts": check_statuses,
        "unsupported_claim_count": len(
            verification.get("unsupported_claims", [])
        ) if isinstance(verification.get("unsupported_claims"), list) else None,
        "required_revision": verification.get("required_revision"),
    }


def _record_summary(record) -> dict[str, Any]:
    return {
        "configuration_id": record.configuration_id,
        "configuration_label": record.configuration_label,
        "execution_status": record.execution_status,
        "persisted": record.persisted,
        "record_path": record.record_path,
        "start_timestamp_utc": record.start_timestamp_utc,
        "completion_timestamp_utc": record.completion_timestamp_utc,
        "duration_ms": round(record.duration_ms, 2),
        "input_bundle_fingerprint": record.input_bundle_fingerprint,
        "error_type": record.error_type,
        "error_stage": record.error_stage,
        "error_message_length": len(record.error_message) if record.error_message else 0,
        "error_message_sha256": _sha256_text(record.error_message) if record.error_message else None,
        "first_pass_verification_status": record.first_pass_verification_status,
        "final_verification_status": record.final_verification_status,
        "revision_count": record.revision_count,
        "llm_provider": record.llm_provider,
        "llm_model": record.llm_model,
        "inference_settings": record.inference_settings,
        "okb_usage": record.okb_usage,
        "okb_snapshot_fingerprint": record.okb_snapshot_fingerprint,
        "okb_counts": record.okb_counts,
        "capabilities": record.capabilities,
        "database_target": record.database_target,
        "database_write_guard": record.database_write_guard,
        "git_commit": record.git_commit,
        "git_dirty": record.git_dirty,
        "recommendations": _recommendation_summary(record),
        "skill_gap": _skill_gap_summary(record),
        "roadmap": _roadmap_summary(record),
        "verification": _verification_summary(record),
    }


def _career_labels() -> list[CareerOutputLabel]:
    careers = rs.get_all_careers()
    if len(careers) != 10:
        raise SmokeSafetyError(f"expected 10 canonical careers, found {len(careers)}")
    return [
        CareerOutputLabel(career_id=career.career_id, career_name=career.canonical_name)
        for career in careers
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stage3_smoke",
        description="Controlled one-CV Stage 3 smoke test for B0, B2, B3, and F.",
    )
    parser.add_argument("--cv", default=None, help="Single PDF under docs/cv_test.")
    parser.add_argument("--case-id", default="S3-CV-001", help="Stable anonymized case ID.")
    parser.add_argument("--run-id", default=None, help="Run ID; defaults to a UTC timestamp.")
    parser.add_argument(
        "--bundle-file",
        type=Path,
        default=None,
        help="Reuse a previously generated frozen bundle for the same CV.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Experiment store root; defaults to backend/artifacts/experiments.",
    )
    parser.add_argument("--max-revisions", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=float, default=600.0)
    parser.add_argument(
        "--annotation-workbook-file",
        default="Candidate_Profiles_Data.xlsx",
        help="Filename recorded in evaluation metadata only.",
    )
    parser.add_argument(
        "--annotation-workbook-sha256",
        default=None,
        help="SHA-256 recorded in evaluation metadata only.",
    )
    parser.add_argument(
        "--annotation-mapping-status",
        default="NOT_MAPPED_NO_FILENAME_MATCH",
        help="Mapping status recorded in evaluation metadata only.",
    )
    parser.add_argument("--keep-user", action="store_true", help="Keep the synthetic user.")
    parser.add_argument(
        "--approve-live-llm",
        action="store_true",
        help="Required: allow real provider calls with the selected CV.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.approve_live_llm:
        print(json.dumps({
            "status": "REFUSED",
            "error_type": "SmokeSafetyError",
            "message": "Pass --approve-live-llm to allow real provider calls.",
        }, indent=2))
        return 2

    try:
        database = _validate_isolated_target()
        cv_path = _select_cv(args.cv)
        run_id = args.run_id or f"stage3-{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        input_sha = _sha256_file(cv_path)

        extraction = CVTextExtractor().extract(cv_path.read_bytes(), cv_path.name)
        metadata = extraction.metadata
        client = GeminiClient()
        shared_llm_recorder = LLMCallProvenance(args.case_id, run_id, "SHARED_INPUT")
        extraction_client = shared_llm_recorder.wrap(client)
        bundle, bundle_path, reused = _load_or_create_bundle(
            cv_path=cv_path,
            extracted_text=extraction.extracted_text,
            client=extraction_client,
            bundle_file=args.bundle_file,
        )
        bundle_fingerprint = fingerprint_bundle(bundle)
        labels = _career_labels()

        user = us.create_user(
            email=f"stage3-smoke+{run_id}@example.invalid",
            full_name="Stage 3 Smoke User",
        )
        user_id = user.user_id
        engine = get_engine()
        before_counts = _user_row_counts(engine, user_id)

        runner = ExperimentRunner(
            store=ExperimentStore(root=args.output_dir),
            llm_client=client,
            career_labels=labels,
            max_revisions=args.max_revisions,
            enforce_database_isolation=True,
            timeout_seconds=args.timeout_seconds,
        )
        runner_metadata = {
            "stage": "3",
            "smoke_test": True,
            "case_id": args.case_id,
            "input_file_name": cv_path.name,
            "input_file_sha256": input_sha,
            "input_file_bytes": cv_path.stat().st_size,
            "cv_format": metadata.format,
            "cv_page_count": metadata.page_count,
            "cv_character_count": metadata.character_count,
            "bundle_schema": "frozen_profile_bundle/1.0",
            "extraction_prompt_sha256": hashlib.sha256(
                FrozenProfileBundleExtractor.SYSTEM.encode("utf-8")
            ).hexdigest(),
            "bundle_fingerprint": bundle_fingerprint,
            "bundle_reused_from_file": reused,
            "shared_input_llm_calls": shared_llm_recorder.snapshot(),
            "bundle_skill_mention_count": len(bundle.skill_mentions),
            "bundle_evidence_span_count": sum(
                len(mention.evidence_spans) for mention in bundle.skill_mentions
            ),
            "bundle_education_count": len(bundle.education),
            "bundle_experience_count": len(bundle.experience),
            "bundle_project_count": len(bundle.projects),
            "bundle_certification_count": len(bundle.certifications),
            "synthetic_user_id": user_id,
            "llm_provider": "Google Gemini (google-genai)",
            "llm_model": client.model,
            "career_label_source": "OKB get_all_careers()",
            "database": database,
        }
        try:
            result = runner.run_case(
                case_id=args.case_id,
                run_id=run_id,
                bundle=bundle,
                user_id=user_id,
                metadata=runner_metadata,
                configurations=("B0", "B2", "B3", "F"),
                timeout_seconds=args.timeout_seconds,
            )
        except Exception:
            # Preserve the failure, but never leave the synthetic user behind.
            if not args.keep_user:
                from scripts.manual_validation import _cleanup_synthetic_user

                _cleanup_synthetic_user(engine, user_id)
            raise

        after_counts = _user_row_counts(engine, user_id)
        cleanup: dict[str, Any] | None = None
        if not args.keep_user:
            from scripts.manual_validation import _cleanup_synthetic_user

            ok, detail = _cleanup_synthetic_user(engine, user_id)
            cleanup = {"ok": ok, **detail}

        case_dir = ExperimentStore(root=args.output_dir).case_directory(args.case_id, run_id)
        case_dir.mkdir(parents=True, exist_ok=True)
        evaluation_metadata = {
            "schema": "stage3_evaluation_metadata/1.0",
            "case_id": args.case_id,
            "run_id": run_id,
            "annotation_workbook_filename": args.annotation_workbook_file,
            "annotation_workbook_sha256": args.annotation_workbook_sha256,
            "annotation_mapping_status": args.annotation_mapping_status,
            "written_after_inference": True,
            "annotation_values_included": False,
            "formal_metrics_calculated": False,
        }
        (case_dir / "stage3_evaluation_metadata.json").write_text(
            json.dumps(evaluation_metadata, indent=2), encoding="utf-8"
        )

        records = [_record_summary(record) for record in result.records]
        summary = {
            "schema": "stage3_smoke_summary/1.0",
            "case_id": args.case_id,
            "run_id": run_id,
            "generated_at_utc": _utc_now(),
            "input": {
                "file_name": cv_path.name,
                "sha256": input_sha,
                "bytes": cv_path.stat().st_size,
                "format": metadata.format,
                "page_count": metadata.page_count,
                "character_count": metadata.character_count,
            },
            "bundle": {
                "schema": "frozen_profile_bundle/1.0",
                "fingerprint": bundle_fingerprint,
                "reused_from_file": reused,
                "bundle_file": str(bundle_path),
                "skill_mentions": len(bundle.skill_mentions),
                "evidence_spans": sum(len(item.evidence_spans) for item in bundle.skill_mentions),
                "education": len(bundle.education),
                "experience": len(bundle.experience),
                "projects": len(bundle.projects),
                "certifications": len(bundle.certifications),
            },
            "database": database,
            "llm": {
                "provider": "Google Gemini (google-genai)",
                "model": client.model,
                "sdk_version": "2.31.0",
            },
            "synthetic_user": {
                "user_id": user_id,
                "rows_before_run": before_counts,
                "rows_after_run": after_counts,
                "cleanup": cleanup,
            },
            "manifest": {
                "path": result.manifest.manifest_path,
                "persisted": result.manifest.persisted,
                "partial": result.manifest.partial,
                "successful_configurations": result.manifest.successful_configurations,
                "failed_configurations": result.manifest.failed_configurations,
                "input_bundle_fingerprint": result.manifest.input_bundle_fingerprint,
                "git_commit": result.manifest.git_commit,
                "git_dirty": result.manifest.git_dirty,
                "git_diff_sha256": result.manifest.git_diff_sha256,
            },
            "records": records,
            "shared_input_checks": {
                "same_case_id": all(record.case_id == args.case_id for record in result.records),
                "same_bundle_fingerprint": len(
                    {record.input_bundle_fingerprint for record in result.records}
                ) == 1,
                "distinct_configuration_ids": [record.configuration_id for record in result.records],
                "distinct_record_paths": len(
                    {record.record_path for record in result.records}
                ) == len(result.records),
            },
            "evaluation_metadata_path": str(case_dir / "stage3_evaluation_metadata.json"),
            "summary_path": str(case_dir / "stage3_summary.json"),
        }
        (case_dir / "stage3_summary.json").write_text(
            json.dumps(summary, indent=2), encoding="utf-8"
        )
        print(json.dumps(summary, indent=2))
        return 0 if not result.manifest.failed_configurations else 1
    except SmokeSafetyError as exc:
        print(json.dumps({
            "status": "REFUSED",
            "error_type": type(exc).__name__,
            "message": str(exc)[:400],
        }, indent=2))
        return 2
    except Exception as exc:  # type-only: a driver error may carry connection details
        message = str(exc)
        # Keep the diagnostic out of the console (it can echo CV/connection data)
        # and expose only safe fingerprint metadata.
        diagnostic_path = (
            Path(tempfile.gettempdir()) / "opencode" / "stage3_driver_error.txt"
        )
        diagnostic_path.parent.mkdir(parents=True, exist_ok=True)
        diagnostic_path.write_text(message, encoding="utf-8")
        print(json.dumps({
            "status": "FAIL",
            "error_type": type(exc).__name__,
            "message_length": len(message),
            "message_sha256": _sha256_text(message),
            "diagnostic_path": str(diagnostic_path),
        }, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
