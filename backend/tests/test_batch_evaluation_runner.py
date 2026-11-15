from __future__ import annotations

import csv
import hashlib
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.evaluation import batch_runner as batch
from app.evaluation.baseline_inference import FrozenProfileBundle, SkillMention


CAREER_IDS = [f"C{index:02d}" for index in range(1, 11)]


def _crosswalk_row(candidate_id: str, filename: str, path: str, cv_hash: str, label="Data Analyst"):
    career_id, canonical, status = (
        ("C09", "Cybersecurity Engineer/Analyst", "ALIAS")
        if label == "Cybersecurity Analyst"
        else ("C04", "Data Analyst", "EXACT")
    )
    return {
        "candidate_id": candidate_id,
        "workbook_file": filename,
        "proposed_cv_path": path,
        "cv_match_category": "EXACT",
        "cv_match_evidence": "Exact explicit filename match",
        "cv_sha256": cv_hash,
        "annotator_1": label,
        "annotator_1_career_id": career_id,
        "annotator_1_canonical_name": canonical,
        "annotator_1_mapping_status": status,
        "annotator_2": label,
        "annotator_2_career_id": career_id,
        "annotator_2_canonical_name": canonical,
        "annotator_2_mapping_status": status,
        "annotator_agreement": "AGREE",
    }


def _write_crosswalk(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _patch_workbook(monkeypatch, rows):
    monkeypatch.setattr(
        batch,
        "_xlsx_sheet_rows",
        lambda path, sheet: rows if sheet == "Candidates Overview" else [],
    )


def _temp_candidate(tmp_path: Path, candidate_id="candidate-1"):
    cv_root = tmp_path / "cvs"
    cv_root.mkdir(exist_ok=True)
    cv_path = cv_root / f"{candidate_id}.txt"
    content = b"private fixture bytes; never extracted in these tests"
    cv_path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    return batch.CandidateInput(
        candidate_id=candidate_id,
        workbook_file=cv_path.name,
        cv_path=cv_path,
        cv_sha256=digest,
        annotator_1="Data Analyst",
        annotator_1_career_id="C04",
        annotator_1_canonical_name="Data Analyst",
        annotator_1_mapping_status="EXACT",
        annotator_2="Data Scientist",
        annotator_2_career_id="C06",
        annotator_2_canonical_name="Data Scientist",
        annotator_2_mapping_status="EXACT",
    )


def test_current_crosswalk_validates_all_43_candidates_and_hashes():
    root = Path(__file__).resolve().parents[2]
    candidates = batch.load_candidate_manifest(
        root / "docs/experiments/candidate_cv_career_crosswalk_draft.csv",
        root / "data/ground_truth/Candidate_Profiles_Data.xlsx",
        root / "frontend/dignostic_testing/input_cvs",
    )
    assert len(candidates) == 43
    assert len({candidate.candidate_id for candidate in candidates}) == 43
    assert len({candidate.cv_path for candidate in candidates}) == 43
    assert all(candidate.cv_path.is_file() for candidate in candidates)
    assert all(len(candidate.cv_sha256) == 64 for candidate in candidates)
    assert all(candidate.annotator_1 and candidate.annotator_2 for candidate in candidates)
    cybersecurity = next(item for item in candidates if item.annotator_1 == "Cybersecurity Analyst")
    assert cybersecurity.annotator_1_career_id == "C09"
    assert cybersecurity.annotator_1_mapping_status == "ALIAS"


def test_b0_career_labels_load_from_frozen_taxonomy_workbook():
    root = Path(__file__).resolve().parents[2]
    labels = batch.load_career_output_labels(root / "data/occupational_knowledge_base_verified_v1_0.xlsx")
    assert len(labels) == 10
    assert {label.career_id for label in labels} == set(CAREER_IDS)
    cybersecurity = next(label for label in labels if label.career_id == "C09")
    assert cybersecurity.career_name == "Cybersecurity Engineer/Analyst"


def test_manifest_rejects_missing_candidate_row(tmp_path, monkeypatch):
    cv_root = tmp_path / "cvs"
    cv_root.mkdir()
    content = b"cv"
    (cv_root / "candidate-1.txt").write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    row = _crosswalk_row("candidate-1", "candidate-1.txt", "candidate-1.txt", digest)
    _write_crosswalk(tmp_path / "crosswalk.csv", [row])
    _patch_workbook(monkeypatch, [
        {"user_id": "candidate-1", "file": "candidate-1.txt", "annotator_1": "Data Analyst", "annotator_2": "Data Analyst"},
        {"user_id": "candidate-2", "file": "candidate-2.txt", "annotator_1": "Data Analyst", "annotator_2": "Data Analyst"},
    ])
    with pytest.raises(batch.BatchValidationError, match="expected 2 workbook and crosswalk rows"):
        batch.load_candidate_manifest(
            tmp_path / "crosswalk.csv", tmp_path / "workbook.xlsx", cv_root, expected_count=2,
        )


@pytest.mark.parametrize("problem", ["duplicate_path", "missing_file", "hash_mismatch", "extension_difference"])
def test_manifest_rejects_invalid_cv_paths_and_hashes(tmp_path, monkeypatch, problem):
    cv_root = tmp_path / "cvs"
    cv_root.mkdir()
    content = b"cv fixture"
    (cv_root / "candidate-1.txt").write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    row = _crosswalk_row("candidate-1", "candidate-1.txt", "candidate-1.txt", digest)
    workbook_rows = [{"user_id": "candidate-1", "file": "candidate-1.txt",
                      "annotator_1": "Data Analyst", "annotator_2": "Data Analyst"}]
    rows = [dict(row)]
    expected_count = 1
    if problem == "duplicate_path":
        rows.append(dict(row, candidate_id="candidate-2"))
        workbook_rows.append({**workbook_rows[0], "user_id": "candidate-2"})
        expected_count = 2
    elif problem == "missing_file":
        rows[0]["proposed_cv_path"] = "missing.txt"
        rows[0]["workbook_file"] = "missing.txt"
        workbook_rows[0]["file"] = "missing.txt"
    elif problem == "hash_mismatch":
        rows[0]["cv_sha256"] = "0" * 64
    elif problem == "extension_difference":
        rows[0]["workbook_file"] = "candidate-1.pdf"
        workbook_rows[0]["file"] = "candidate-1.pdf"
    _write_crosswalk(tmp_path / "crosswalk.csv", rows)
    _patch_workbook(monkeypatch, workbook_rows)
    with pytest.raises(batch.BatchValidationError):
        batch.load_candidate_manifest(
            tmp_path / "crosswalk.csv", tmp_path / "workbook.xlsx", cv_root,
            expected_count=expected_count,
        )


class _FakeRecord:
    def __init__(self, configuration_id, *, status="success", ranking=None):
        self.configuration_id = configuration_id
        self.execution_status = status
        self.error_type = None if status == "success" else "ProviderUnavailable"
        self.error_stage = None if status == "success" else "inference"
        ranking = ranking or CAREER_IDS
        self.normalized_evaluation_output = (
            {"recommendation": {"ranking": ranking, "fit_scores": {}}}
            if status == "success" else None
        )
        self.capabilities = {
            "roadmap": "NOT_APPLICABLE" if configuration_id in {"B0", "B2"} else "AVAILABLE",
            "verification": "NOT_APPLICABLE" if configuration_id in {"B0", "B2", "B3"} else "AVAILABLE",
        }
        self.llm_model = "fake-model"
        self.revision_count = 0
        self.final_verification_status = "NOT_APPLICABLE" if configuration_id != "F" else "PASS"
        self.metadata = {}

    def model_dump(self, mode="json"):
        return {
            "configuration_id": self.configuration_id,
            "execution_status": self.execution_status,
            "error_type": self.error_type,
            "error_stage": self.error_stage,
            "normalized_evaluation_output": self.normalized_evaluation_output,
            "capabilities": self.capabilities,
            "llm_model": self.llm_model,
            "revision_count": self.revision_count,
            "final_verification_status": self.final_verification_status,
            "metadata": self.metadata,
        }


class _FakeExperimentRunner:
    def __init__(self, *, status="success", ranking=None):
        self.calls = []
        self.status = status
        self.ranking = ranking

    def run_case(self, **kwargs):
        self.calls.append(kwargs)
        records = [
            _FakeRecord(configuration, status=self.status, ranking=self.ranking)
            for configuration in kwargs["configurations"]
        ]
        return SimpleNamespace(records=records)


def _bundle():
    return FrozenProfileBundle(
        extracted_cv_text="[REDACTED] Python project work",
        skill_mentions=[SkillMention(mention_id="m0001", text="Python", evidence_spans=["Python project"])],
    )


def _batch(tmp_path, candidate, fake_runner, bundle_builder, configs=None):
    output_dir = tmp_path / "artifacts"
    return batch.CandidateBatchRunner(
        candidates=[candidate],
        configurations=configs or batch.ALL_CONFIGURATIONS,
        run_id="unit-run",
        output_dir=output_dir,
        bundle_cache=batch.RedactedBundleCache(output_dir / "frozen_inputs"),
        experiment_runner=fake_runner,
        bundle_builder=bundle_builder,
        user_scope=lambda item: nullcontext(123),
        model="fake-model",
        extractor_prompt_sha256="e" * 64,
    )


def test_batch_keeps_annotator_references_separate_and_pairs_one_bundle(tmp_path):
    candidate = _temp_candidate(tmp_path)
    extraction_calls = []

    def build_bundle(item):
        extraction_calls.append(item.candidate_id)
        return _bundle(), [], {"source_format": "txt", "extractor_prompt_sha256": "e" * 64}

    ranking = ["C04", *[career_id for career_id in CAREER_IDS if career_id != "C04"]]
    fake_runner = _FakeExperimentRunner(ranking=ranking)
    result = _batch(tmp_path, candidate, fake_runner, build_bundle).run()
    assert len(fake_runner.calls) == 1
    call = fake_runner.calls[0]
    assert call["configurations"] == ["B0", "B2", "B3", "F"]
    assert call["bundle"].model_dump() == _bundle().model_dump()
    assert call["case_id"] == f"cv-{candidate.cv_sha256[:16]}"
    assert extraction_calls == [candidate.candidate_id]
    serialized_metadata = json.dumps(call["metadata"])
    assert "Data Analyst" not in serialized_metadata
    assert "Data Scientist" not in serialized_metadata
    assert candidate.candidate_id not in serialized_metadata
    assert candidate.workbook_file not in serialized_metadata
    assert set(result["aggregate_by_configuration_and_annotator"]["B0"]) == {"annotator_1", "annotator_2"}
    annotator_1 = result["aggregate_by_configuration_and_annotator"]["B0"]["annotator_1"]
    annotator_2 = result["aggregate_by_configuration_and_annotator"]["B0"]["annotator_2"]
    assert annotator_1["metrics"]["career.top1_accuracy"]["value"] == 1.0
    assert annotator_2["metrics"]["career.top1_accuracy"]["value"] == 0.0
    assert not any(key.startswith("roadmap.") for key in annotator_1["metrics"])
    case_artifact = json.loads((tmp_path / "artifacts/cases/candidate-1.json").read_text())
    assert case_artifact["references"]["annotator_1"]["career_id"] == "C04"
    assert case_artifact["references"]["annotator_2"]["career_id"] == "C06"


def test_bundle_cache_prevents_repeating_shared_extraction(tmp_path):
    candidate = _temp_candidate(tmp_path)
    builds = []
    runner = _FakeExperimentRunner()

    def build_bundle(item):
        builds.append(item.candidate_id)
        return _bundle(), [], {"source_format": "txt"}

    _batch(tmp_path, candidate, runner, build_bundle).run()
    _batch(tmp_path, candidate, runner, build_bundle).run()
    assert builds == [candidate.candidate_id]


def test_failed_inference_has_no_fabricated_ranking(tmp_path):
    candidate = _temp_candidate(tmp_path)
    runner = _FakeExperimentRunner(status="model_api_failure")
    result = _batch(tmp_path, candidate, runner, lambda item: (_bundle(), [], {})).run()
    config = result["cases"][0]["configurations"]["B0"]
    assert config["execution_status"] == "model_api_failure"
    assert config["evaluations"]["annotator_1"]["metrics"]["career.top1_accuracy"]["status"] == "unavailable"
    assert config["normalized_evaluation_output"] is None
    assert result["failed_or_incomplete"]


def test_batch_stops_on_database_safety_failure(tmp_path):
    from contextlib import contextmanager

    first = _temp_candidate(tmp_path, "candidate-1")
    second = _temp_candidate(tmp_path, "candidate-2")
    runner = _FakeExperimentRunner()

    @contextmanager
    def unsafe_scope(candidate):
        raise batch.BatchSafetyError("cleanup could not be verified")
        yield 1

    output_dir = tmp_path / "artifacts"
    batch_runner = batch.CandidateBatchRunner(
        candidates=[first, second],
        configurations=["B3"],
        run_id="unsafe-run",
        output_dir=output_dir,
        bundle_cache=batch.RedactedBundleCache(output_dir / "frozen_inputs"),
        experiment_runner=runner,
        bundle_builder=lambda item: (_bundle(), [], {}),
        user_scope=unsafe_scope,
        model="fake-model",
        extractor_prompt_sha256="e" * 64,
    )

    with pytest.raises(batch.BatchSafetyError, match="cleanup could not be verified"):
        batch_runner.run()
    assert runner.calls == []


def test_incomplete_ranking_is_not_counted_as_a_valid_prediction(tmp_path):
    candidate = _temp_candidate(tmp_path)
    runner = _FakeExperimentRunner(ranking=["C04"])
    result = _batch(tmp_path, candidate, runner, lambda item: (_bundle(), [], {})).run()
    config = result["cases"][0]["configurations"]["B0"]
    assert config["source_execution_status"] == "success"
    assert config["execution_status"] == "incomplete_output"
    assert config["normalized_evaluation_output"] is None
    assert config["evaluations"]["annotator_1"]["metrics"]["career.top1_accuracy"]["status"] == "unavailable"


def test_cli_dry_run_does_not_initialize_live_dependencies(tmp_path, monkeypatch, capsys):
    candidate = _temp_candidate(tmp_path)
    monkeypatch.setattr(batch, "load_candidate_manifest", lambda *args: [candidate])
    monkeypatch.setattr(batch, "resolve_isolated_engine", lambda: pytest.fail("dry-run touched DB"))
    monkeypatch.setattr(batch, "GeminiClient", lambda: pytest.fail("dry-run constructed an LLM"))

    assert batch.main(["--dry-run", "--limit", "1"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["mode"] == "dry_run"
    assert plan["llm_calls"] == 0
    assert plan["database_operations"] == 0


def test_dry_run_plan_reports_no_model_or_database_operations(tmp_path):
    candidate = _temp_candidate(tmp_path)
    plan = batch.build_dry_run_plan([candidate])
    assert plan["planned_configuration_runs"] == 4
    assert plan["database_required"] is True
    assert plan["profile_persistence_required"] is True
    assert plan["inference_label_leakage"] is False
    assert plan["llm_calls"] == 0
    assert plan["database_operations"] == 0


def test_isolated_database_guard_rejects_main_before_connect(monkeypatch):
    monkeypatch.setenv("CAREER_DB_NAME", batch.ALLOWED_DATABASE)
    monkeypatch.setenv("CAREER_DB_HOST", batch.ALLOWED_DATABASE_HOST)
    monkeypatch.setenv("CAREER_DB_PORT", str(batch.ALLOWED_DATABASE_PORT))
    monkeypatch.setenv(batch.DATABASE_OPT_IN, batch.ALLOWED_DATABASE)
    monkeypatch.delenv("CAREER_DB_URL", raising=False)

    class MainEngine:
        url = SimpleNamespace(host="localhost", database="career_intelligence_main", port=5433)

        def connect(self):
            raise AssertionError("must reject main before opening a connection")

    with pytest.raises(batch.BatchSafetyError, match="loopback isolated e2e database"):
        batch._is_isolated_engine(MainEngine())


def test_isolated_database_guard_checks_server_identity(monkeypatch):
    monkeypatch.setenv("CAREER_DB_NAME", batch.ALLOWED_DATABASE)
    monkeypatch.setenv("CAREER_DB_HOST", batch.ALLOWED_DATABASE_HOST)
    monkeypatch.setenv("CAREER_DB_PORT", str(batch.ALLOWED_DATABASE_PORT))
    monkeypatch.setenv(batch.DATABASE_OPT_IN, batch.ALLOWED_DATABASE)
    monkeypatch.delenv("CAREER_DB_URL", raising=False)

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, statement):
            assert "current_database" in str(statement)
            return SimpleNamespace(scalar_one=lambda: "career_intelligence_main")

    class Engine:
        url = SimpleNamespace(host="localhost", database=batch.ALLOWED_DATABASE, port=5433)
        def connect(self): return Connection()

    with pytest.raises(batch.BatchSafetyError, match="server-confirmed"):
        batch._is_isolated_engine(Engine())


def test_paced_retry_client_retries_transient_failures_only():
    class Client:
        model = "fake-model"
        def __init__(self): self.calls = 0
        def complete_json(self, **kwargs):
            self.calls += 1
            if self.calls < 3:
                raise TimeoutError("transient")
            return {"ok": True}

    client = Client()
    paced = batch.PacedRetryLLMClient(
        client,
        minimum_interval_seconds=0,
        max_retries=2,
        backoff_base_seconds=0,
        sleep=lambda _: None,
    )
    assert paced.complete_json(system="s", user="u") == {"ok": True}
    assert client.calls == 3
    assert paced.last_call_retry_count == 2
    assert paced.total_retries == 2