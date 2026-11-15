from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from app.evaluation import batch_runner as batch
from app.evaluation.subset_selection import (
    SUBSET_SIZE,
    SubsetSelectionError,
    select_subset_rows,
)

ROOT = Path(__file__).resolve().parents[2]
SUBSET_CSV = ROOT / "docs/experiments/ABLATION_CV_SUBSET_12.csv"
SUBSET_MANIFEST = ROOT / "docs/experiments/ABLATION_CV_SUBSET_12.manifest.json"
SOURCE_CROSSWALK = ROOT / "docs/experiments/candidate_cv_career_crosswalk_draft.csv"
WORKBOOK = ROOT / "data/ground_truth/Candidate_Profiles_Data.xlsx"
CV_ROOT = ROOT / "frontend/dignostic_testing/input_cvs"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]


def test_frozen_subset_manifest_is_valid_and_plans_exactly_48_runs():
    assert SUBSET_CSV.is_file()
    manifest = json.loads(SUBSET_MANIFEST.read_text(encoding="utf-8"))
    candidates = batch.load_candidate_manifest(
        SUBSET_CSV, WORKBOOK, CV_ROOT, expected_count=SUBSET_SIZE, allow_subset=True,
    )
    assert len(candidates) == 12
    assert len({candidate.candidate_id for candidate in candidates}) == 12
    assert all(candidate.cv_path.is_file() for candidate in candidates)
    assert all(len(candidate.cv_sha256) == 64 for candidate in candidates)

    career_ids = {candidate.annotator_1_career_id for candidate in candidates}
    assert career_ids == {f"C{number:02d}" for number in range(1, 11)}
    assert {candidate.candidate_id for candidate in candidates} == {
        row["candidate_id"] for row in manifest["candidates"]
    }

    plan = batch.build_dry_run_plan(
        candidates, batch.ALL_CONFIGURATIONS, manifest_source=str(SUBSET_CSV),
    )
    assert plan["planned_configuration_runs"] == 48
    assert plan["candidate_count"] == 12
    assert plan["configurations"] == ["B0", "B2", "B3", "F"]
    assert plan["database_required"] is True
    assert plan["labels_evaluator_only"] is True
    assert plan["llm_calls"] == 0
    assert plan["database_operations"] == 0
    assert plan["inference_label_leakage"] is False


def test_frozen_subset_is_reproducible_from_seed_and_source_crosswalk():
    manifest = json.loads(SUBSET_MANIFEST.read_text(encoding="utf-8"))
    source_rows = _rows(SOURCE_CROSSWALK)
    selected = select_subset_rows(source_rows, seed=manifest["seed"])
    expected = [
        (row["candidate_id"], row["cv_sha256"], row["annotator_1_career_id"])
        for row in selected
    ]
    recorded = [
        (row["candidate_id"], row["cv_sha256"], row["annotator_1_career_id"])
        for row in manifest["candidates"]
    ]
    assert recorded == expected
    assert manifest["planned_runs"] == 48
    assert manifest["same_candidates_for_all_configurations"] is True
    assert manifest["original_43_row_manifest_unchanged"] is True
    assert manifest["labels_policy"].startswith("evaluator_only")


def test_additional_candidates_come_only_from_multi_sample_categories():
    manifest = json.loads(SUBSET_MANIFEST.read_text(encoding="utf-8"))
    source_counts = manifest["source_category_counts"]
    by_id = {row["candidate_id"]: row for row in manifest["candidates"]}
    extras = manifest["additional_candidates"]
    assert len(extras) == 2
    assert len(manifest["one_representative_per_category"]) == 10
    for candidate_id in extras:
        career_id = by_id[candidate_id]["annotator_1_career_id"]
        assert source_counts[career_id] > 1


def test_subset_selection_rejects_a_source_without_all_ten_categories():
    rows = _rows(SOURCE_CROSSWALK)
    truncated = [row for row in rows if row["annotator_1_career_id"] != "C10"]
    with pytest.raises(SubsetSelectionError, match="exactly 10 career categories"):
        select_subset_rows(truncated)


def test_subset_loader_rejects_a_row_outside_the_workbook(tmp_path, monkeypatch):
    cv_root = tmp_path / "cvs"
    cv_root.mkdir()
    (cv_root / "candidate-1.txt").write_bytes(b"fixture")
    import hashlib

    digest = hashlib.sha256(b"fixture").hexdigest()
    row = {
        "candidate_id": "candidate-1",
        "workbook_file": "candidate-1.txt",
        "proposed_cv_path": "candidate-1.txt",
        "cv_match_category": "EXACT",
        "cv_match_evidence": "fixture",
        "cv_sha256": digest,
        "annotator_1": "Data Analyst",
        "annotator_1_career_id": "C04",
        "annotator_1_canonical_name": "Data Analyst",
        "annotator_1_mapping_status": "EXACT",
        "annotator_2": "Data Analyst",
        "annotator_2_career_id": "C04",
        "annotator_2_canonical_name": "Data Analyst",
        "annotator_2_mapping_status": "EXACT",
        "annotator_agreement": "AGREE",
    }
    with (tmp_path / "crosswalk.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    monkeypatch.setattr(
        batch, "_xlsx_sheet_rows",
        lambda path, sheet: [{"user_id": "other-candidate", "file": "other.txt"}],
    )
    with pytest.raises(batch.BatchValidationError, match="not a subset of the workbook"):
        batch.load_candidate_manifest(
            tmp_path / "crosswalk.csv", tmp_path / "workbook.xlsx", cv_root,
            expected_count=1, allow_subset=True,
        )


def test_cli_subset_dry_run_plans_48_without_live_dependencies(monkeypatch, capsys):
    monkeypatch.setattr(batch, "resolve_isolated_engine", lambda: pytest.fail("dry-run touched DB"))
    monkeypatch.setattr(batch, "GeminiClient", lambda: pytest.fail("dry-run constructed an LLM"))
    assert batch.main([
        "--crosswalk", str(SUBSET_CSV), "--subset-manifest", "--dry-run",
    ]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["planned_configuration_runs"] == 48
    assert plan["candidate_count"] == 12
    assert plan["llm_calls"] == 0
    assert plan["database_operations"] == 0
