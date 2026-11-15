"""Freeze the deterministic 12-CV subset used by the B0/B2/B3/F ablation.

Run from ``backend/``:

    python -m scripts.freeze_ablation_subset

The script is offline: it hashes the already-labelled CV files, never opens a
CV body, never connects to a database, and never constructs a model client. It
does not modify the 43-row source crosswalk or any source CV.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.evaluation import batch_runner as batch
from app.evaluation.subset_selection import (
    SUBSET_CONFIGURATIONS,
    SUBSET_SCHEMA_VERSION,
    SUBSET_SEED,
    SUBSET_SELECTION_PROCEDURE,
    SUBSET_SIZE,
    select_subset_rows,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_CSV = REPO_ROOT / "docs/experiments/ABLATION_CV_SUBSET_12.csv"
DEFAULT_OUTPUT_MANIFEST = REPO_ROOT / "docs/experiments/ABLATION_CV_SUBSET_12.manifest.json"


class FreezeError(ValueError):
    """The source manifest cannot be frozen safely."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_crosswalk_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise FreezeError("source crosswalk has no header")
            rows = [{key: (value or "").strip() for key, value in row.items()} for row in reader]
            return list(reader.fieldnames), rows
    except OSError as exc:
        raise FreezeError(f"cannot read source crosswalk: {type(exc).__name__}") from None


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def build_manifest(
    *,
    crosswalk_path: Path,
    workbook_path: Path,
    cv_root: Path,
    seed: int = SUBSET_SEED,
) -> tuple[list[str], list[dict[str, str]], dict[str, Any]]:
    fieldnames, rows = _read_crosswalk_rows(crosswalk_path)
    # Validating all 43 rows first guarantees the subset is drawn from a clean,
    # hash-checked source manifest rather than from unverified CSV text.
    validated = batch.load_candidate_manifest(
        crosswalk_path, workbook_path, cv_root, expected_count=batch.EXPECTED_CANDIDATES,
    )
    validated_by_id = {candidate.candidate_id: candidate for candidate in validated}
    if len(validated_by_id) != len(validated):
        raise FreezeError("validated manifest contains duplicate candidate IDs")

    selected = select_subset_rows(rows, seed=seed)
    rows_by_id = {row["candidate_id"]: row for row in rows}
    missing = [row["candidate_id"] for row in selected if row["candidate_id"] not in validated_by_id]
    if missing:
        raise FreezeError(f"selected candidates failed validation: {missing}")

    for row in selected:
        validated_row = validated_by_id[row["candidate_id"]]
        source_row = rows_by_id[row["candidate_id"]]
        if (
            source_row["workbook_file"] != validated_row.workbook_file
            or source_row["annotator_1_career_id"] != validated_row.annotator_1_career_id
            or source_row["annotator_2_career_id"] != validated_row.annotator_2_career_id
        ):
            raise FreezeError(f"selected row changed during validation: {row['candidate_id']}")
        # The validated hash is authoritative; it equals the CSV hash but is
        # recomputed from the actual file bytes.
        row["cv_sha256"] = validated_row.cv_sha256

    source_counts: dict[str, int] = {}
    for row in rows:
        career_id = row["annotator_1_career_id"]
        source_counts[career_id] = source_counts.get(career_id, 0) + 1
    subset_counts: dict[str, int] = {}
    for row in selected:
        career_id = row["annotator_1_career_id"]
        subset_counts[career_id] = subset_counts.get(career_id, 0) + 1

    primary_ids = {
        row["candidate_id"]
        for row in select_subset_rows(rows, seed=seed, expected_size=len(source_counts))
    }
    one_per_category = sorted(primary_ids)
    additional = sorted(
        row["candidate_id"] for row in selected if row["candidate_id"] not in primary_ids
    )

    manifest: dict[str, Any] = {
        "schema_version": SUBSET_SCHEMA_VERSION,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "seed": seed,
        "selection_procedure": SUBSET_SELECTION_PROCEDURE,
        "source_crosswalk": str(crosswalk_path.relative_to(REPO_ROOT)) if crosswalk_path.is_relative_to(REPO_ROOT) else str(crosswalk_path),
        "source_crosswalk_sha256": _sha256_file(crosswalk_path),
        "source_workbook": str(workbook_path.relative_to(REPO_ROOT)) if workbook_path.is_relative_to(REPO_ROOT) else str(workbook_path),
        "source_workbook_sha256": _sha256_file(workbook_path),
        "source_cv_root": str(cv_root.relative_to(REPO_ROOT)) if cv_root.is_relative_to(REPO_ROOT) else str(cv_root),
        "source_candidate_count": len(rows),
        "source_category_counts": dict(sorted(source_counts.items())),
        "subset_size": len(selected),
        "subset_category_counts": dict(sorted(subset_counts.items())),
        "one_representative_per_category": one_per_category,
        "additional_candidates": additional,
        "configurations": list(SUBSET_CONFIGURATIONS),
        "planned_runs": len(selected) * len(SUBSET_CONFIGURATIONS),
        "labels_policy": "evaluator_only; never passed to profile, recommendation, gap, roadmap, or verification agents",
        "same_candidates_for_all_configurations": True,
        "shared_frozen_bundle_per_candidate": True,
        "original_43_row_manifest_unchanged": True,
        "candidates": [
            {
                "candidate_id": row["candidate_id"],
                "workbook_file": row["workbook_file"],
                "proposed_cv_path": row["proposed_cv_path"],
                "cv_sha256": row["cv_sha256"],
                "category_label": row["annotator_1"],
                "annotator_1_career_id": row["annotator_1_career_id"],
                "annotator_1_canonical_name": row["annotator_1_canonical_name"],
                "annotator_2_career_id": row["annotator_2_career_id"],
                "annotator_2_canonical_name": row["annotator_2_canonical_name"],
                "selection_role": (
                    "additional" if row["candidate_id"] in additional else "one_per_category"
                ),
            }
            for row in selected
        ],
    }
    return fieldnames, selected, manifest


def _csv_text(fieldnames: list[str], rows: list[dict[str, str]]) -> str:
    import io

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crosswalk", type=Path, default=batch.DEFAULT_CROSSWALK)
    parser.add_argument("--workbook", type=Path, default=batch.DEFAULT_WORKBOOK)
    parser.add_argument("--cv-root", type=Path, default=batch.DEFAULT_CV_ROOT)
    parser.add_argument("--output-csv", type=Path, default=DEFAULT_OUTPUT_CSV)
    parser.add_argument("--output-manifest", type=Path, default=DEFAULT_OUTPUT_MANIFEST)
    parser.add_argument("--seed", type=int, default=SUBSET_SEED)
    args = parser.parse_args(argv)

    try:
        fieldnames, rows, manifest = build_manifest(
            crosswalk_path=args.crosswalk,
            workbook_path=args.workbook,
            cv_root=args.cv_root,
            seed=args.seed,
        )
    except (FreezeError, batch.BatchValidationError) as exc:
        print(json.dumps({"status": "REFUSED", "error_type": type(exc).__name__, "message": str(exc)}))
        return 2

    _atomic_write(args.output_csv, _csv_text(fieldnames, rows))
    _atomic_write(
        args.output_manifest,
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
    )
    print(json.dumps({
        "status": "frozen",
        "subset_size": manifest["subset_size"],
        "planned_runs": manifest["planned_runs"],
        "seed": manifest["seed"],
        "candidate_ids": [row["candidate_id"] for row in rows],
        "output_csv": str(args.output_csv),
        "output_manifest": str(args.output_manifest),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
