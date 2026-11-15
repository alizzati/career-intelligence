"""Stage 2C experiment runner tests; all LLM/DB/workflow dependencies are fakes."""
from __future__ import annotations

import json
import hashlib
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.evaluation.baseline_inference import (
    B0Capability,
    B2SkillGap,
    BaselineInferenceResult,
    CareerOutputLabel,
    FrozenProfileBundle,
    RankedCareer,
    SkillMention,
)
from app.evaluation.experiment_store import ExperimentStore
from app.evaluation.runner import (
    ExperimentRunner,
    IsolationError,
    LLMCallProvenance,
    OkbSnapshot,
    SharedInputError,
    assert_isolated_database,
    database_name,
    fingerprint_bundle,
)


class FakeLLM:
    model = "fake-model"

    def complete_json(self, *, system, user, max_tokens):  # pragma: no cover - never called
        raise AssertionError("the experiment runner must not call the LLM directly")


class RecordingWorkflow:
    def __init__(self, state=None, *, error=None, delay=0.0):
        self.state = state
        self.error = error
        self.delay = delay
        self.calls: list[dict] = []

    def run(self, **kwargs):
        self.calls.append(kwargs)
        if self.delay:
            time.sleep(self.delay)
        if self.error is not None:
            raise self.error
        return self.state


def labels() -> list[CareerOutputLabel]:
    return [
        CareerOutputLabel(career_id=f"C{i:02d}", career_name=f"Career {i}")
        for i in range(1, 11)
    ]


def bundle() -> FrozenProfileBundle:
    return FrozenProfileBundle(
        extracted_cv_text="Redacted CV: Python used in a project.",
        skill_mentions=[
            SkillMention(
                mention_id="m0001",
                text="Python",
                evidence_spans=["Python used in a project"],
            )
        ],
        experience=[{"role_title": "Developer", "company": "Example"}],
        education=[{"institution": "Example University", "degree": "BSc"}],
    )


def ranked(career_labels: list[CareerOutputLabel]) -> list[RankedCareer]:
    return [
        RankedCareer(
            career_id=item.career_id,
            rank=index,
            rationale="Profile evidence supports this ranking.",
        )
        for index, item in enumerate(career_labels, start=1)
    ]


def b0_state() -> dict:
    career_labels = labels()
    result = BaselineInferenceResult(
        configuration_id="B0",
        recommendations=ranked(career_labels),
        skill_gap=B0Capability(reason="B0 has no OKB and no skill-gap analysis."),
        roadmap=B0Capability(reason="B0 does not generate a roadmap."),
        verification=B0Capability(reason="B0 does not run verification."),
    )
    return {
        "user_id": 101,
        "configuration_id": "B0",
        "final_status": "UNVERIFIED",
        "stage": "final_result",
        "revision_count": 0,
        "errors": [],
        "baseline_result": result,
        "recommendations": result.recommendations,
        "skill_gap": None,
        "roadmap": None,
        "verification": None,
        "first_pass_verification_status": None,
    }


def b2_state() -> dict:
    career_labels = labels()
    result = BaselineInferenceResult(
        configuration_id="B2",
        recommendations=ranked(career_labels),
        skill_gap=B2SkillGap(
            career_id="C01",
            matched_evidenced=["S01"],
            matched_claimed_only=[],
            missing=["S02"],
            unmatched_user_claims=[],
            claim_matches={"S01": ["m0001"]},
        ),
        roadmap=B0Capability(reason="B2 does not generate a roadmap."),
        verification=B0Capability(reason="B2 does not run verification."),
    )
    return {
        "user_id": 101,
        "configuration_id": "B2",
        "final_status": "UNVERIFIED",
        "stage": "final_result",
        "revision_count": 0,
        "errors": [],
        "baseline_result": result,
        "recommendations": result.recommendations,
        "skill_gap": None,
        "roadmap": None,
        "verification": None,
        "first_pass_verification_status": None,
    }


def b3_state() -> dict:
    return {
        "user_id": 101,
        "configuration_id": "B3",
        "final_status": "UNVERIFIED",
        "stage": "final_result",
        "revision_count": 0,
        "errors": [],
        "recommendations": [
            {
                "career_id": "C01",
                "fit_score": 0.9,
                "matched_skills": [{"skill_id": "S01"}],
                "claimed_only_skills": [],
                "missing_skills_preview": [{"skill_id": "S02"}],
            }
        ],
        "skill_gap": {
            "skill_gap": {
                "career_id": "C01",
                "matched_evidenced": [{"skill_id": "S01"}],
                "matched_claimed_only": [],
                "missing": [{"skill_id": "S02"}],
                "unmatched_user_claims": [],
            }
        },
        "roadmap": {
            "items": [
                {
                    "skill_id": "S02",
                    "gap_status": "missing",
                    "learning_action": "develop_skill",
                    "knowledge_base_basis": "approved KB relation",
                }
            ]
        },
        "verification": None,
        "first_pass_verification_status": None,
    }


def f_state(
    *, first_pass: str = "FAIL", final: str = "PASS", revisions: int = 1
) -> dict:
    state = b3_state()
    state.update(
        {
            "configuration_id": "F",
            "final_status": "VERIFIED" if final == "PASS" else "VERIFICATION_FAILED",
            "revision_count": revisions,
            "first_pass_verification_status": first_pass,
            "verification": {
                "status": final,
                "checks": [
                    {"check": "recommendation.ranking", "status": final},
                    {"check": "roadmap.gap_coverage", "status": "PASS"},
                ],
                "unsupported_claims": [],
                "required_revision": [],
            },
        }
    )
    return state


def okb() -> OkbSnapshot:
    return OkbSnapshot(
        fingerprint="a" * 64,
        counts={"careers": 10, "skills": 87, "career_skills": 155},
        components=["careers", "skills", "career_skills"],
    )


def git() -> dict:
    return {
        "git_commit": "b" * 40,
        "git_dirty": True,
        "git_diff_sha256": "c" * 64,
    }


def make_runner(tmp_path: Path, states: dict[str, dict] | None = None):
    workflows = {
        configuration_id: RecordingWorkflow(state)
        for configuration_id, state in (states or {
            "B0": b0_state(),
            "B2": b2_state(),
            "B3": b3_state(),
            "F": f_state(),
        }).items()
    }
    store = ExperimentStore(tmp_path / "experiments")
    runner = ExperimentRunner(
        store=store,
        llm_client=FakeLLM(),
        career_labels=labels(),
        workflow_factory=lambda configuration_id: workflows[configuration_id],
        okb_fingerprint_provider=okb,
        git_provenance_provider=git,
        enforce_database_isolation=False,
    )
    return runner, store, workflows


def run_all(runner: ExperimentRunner):
    return runner.run_case(
        case_id="case-001",
        run_id="run-001",
        bundle=bundle(),
        user_id=101,
        metadata={"dataset_type": "R", "split": "pilot"},
    )


# 1. Running one case under B0, B2, B3, and F.
def test_runs_one_case_under_all_four_configurations(tmp_path):
    runner, store, _ = make_runner(tmp_path)
    result = run_all(runner)

    assert [record.configuration_id for record in result.records] == ["B0", "B2", "B3", "F"]
    assert all(record.execution_status == "success" for record in result.records)
    assert all(record.persisted for record in result.records)
    assert result.manifest.partial is False
    assert result.manifest.successful_configurations == ["B0", "B2", "B3", "F"]
    for record in result.records:
        assert Path(record.record_path).is_file()
        assert store.read_run("case-001", "run-001", record.configuration_id)[
            "configuration_id"
        ] == record.configuration_id
    manifest = store.read_manifest("case-001", "run-001")
    assert manifest["schema_version"] == "experiment_manifest/1.0"
    assert manifest["persisted"] is True


def test_resume_reuses_successful_configurations_and_retries_only_failures(tmp_path):
    runner, _, workflows = make_runner(tmp_path)
    workflows["B2"].error = RuntimeError("temporary failure")

    first = run_all(runner)
    assert {record.configuration_id for record in first.records if record.execution_status == "success"} == {
        "B0", "B3", "F",
    }
    assert {key: len(workflow.calls) for key, workflow in workflows.items()} == {
        "B0": 1, "B2": 1, "B3": 1, "F": 1,
    }

    workflows["B2"].error = None
    workflows["B2"].state = b2_state()
    second = run_all(runner)

    assert all(record.execution_status == "success" for record in second.records)
    assert {key: len(workflow.calls) for key, workflow in workflows.items()} == {
        "B0": 1, "B2": 2, "B3": 1, "F": 1,
    }


# 2. Identical bundle fingerprints across configurations.
def test_identical_bundle_fingerprint_across_configurations(tmp_path):
    runner, store, workflows = make_runner(tmp_path)
    result = run_all(runner)

    fingerprints = {record.input_bundle_fingerprint for record in result.records}
    assert len(fingerprints) == 1
    expected = fingerprint_bundle(bundle())
    assert fingerprints == {expected}
    assert result.manifest.input_bundle_fingerprint == expected
    for configuration_id in ("B0", "B2", "B3", "F"):
        assert store.read_run("case-001", "run-001", configuration_id)[
            "input_bundle_fingerprint"
        ] == expected
    passed_bundles = [
        workflows[configuration_id].calls[0]["profile_bundle"]
        for configuration_id in ("B0", "B2", "B3", "F")
    ]
    assert all(item is passed_bundles[0] for item in passed_bundles)


# 3. Configuration-specific output persistence.
def test_configuration_specific_outputs_are_persisted_separately(tmp_path):
    runner, store, _ = make_runner(tmp_path)
    result = run_all(runner)
    by_config = {record.configuration_id: record for record in result.records}

    assert by_config["B0"].raw_structured_output["baseline_result"]["skill_gap"]["status"] == (
        "NOT_APPLICABLE"
    )
    assert by_config["B0"].normalized_evaluation_output["skill_gap"] is None
    assert by_config["B0"].normalized_evaluation_output["recommendation"]["ranking"][0] == "C01"

    assert by_config["B2"].raw_structured_output["baseline_result"]["skill_gap"][
        "matched_evidenced"
    ] == ["S01"]
    assert by_config["B2"].normalized_evaluation_output["skill_gap"][
        "required_skill_status"
    ] == {"S01": "matched_evidenced", "S02": "missing"}

    assert by_config["B3"].raw_structured_output["verification"] is None
    assert by_config["B3"].normalized_evaluation_output["roadmap"]["items"][0][
        "skill_id"
    ] == "S02"
    assert by_config["B3"].normalized_evaluation_output["verification"]["status"] == (
        "unavailable"
    )

    assert by_config["F"].raw_structured_output["verification"]["status"] == "PASS"
    assert by_config["F"].normalized_evaluation_output["verification"]["status"] == "PASS"
    assert by_config["F"].normalized_evaluation_output["verification"]["checks"][0][
        "check"
    ] == "recommendation.ranking"

    files = {
        configuration_id: Path(by_config[configuration_id].record_path)
        for configuration_id in ("B0", "B2", "B3", "F")
    }
    assert len({path.name for path in files.values()}) == 4
    assert all(path.is_file() for path in files.values())
    assert len(store.list_run_records("case-001", "run-001")) == 4


# 4. Partial failure isolation.
def test_partial_failure_is_isolated_and_recorded(tmp_path):
    runner, store, workflows = make_runner(tmp_path)
    workflows["B2"].state = {
        "configuration_id": "B2",
        "final_status": "ERROR",
        "stage": "baseline_inference",
        "revision_count": 0,
        "errors": [
            {
                "stage": "baseline_inference",
                "error_type": "RuntimeError",
                "message": "provider unavailable",
            }
        ],
    }
    result = run_all(runner)
    by_config = {record.configuration_id: record for record in result.records}

    assert by_config["B2"].execution_status == "model_api_failure"
    assert by_config["B2"].error_type == "RuntimeError"
    assert by_config["B2"].error_message == "provider unavailable"
    assert by_config["B2"].persisted is True
    for configuration_id in ("B0", "B3", "F"):
        assert by_config[configuration_id].execution_status == "success"
        assert by_config[configuration_id].persisted is True
        assert Path(by_config[configuration_id].record_path).is_file()
    assert result.manifest.partial is True
    assert result.manifest.successful_configurations == ["B0", "B3", "F"]
    assert result.manifest.failed_configurations == ["B2"]
    persisted_failure = store.read_run("case-001", "run-001", "B2")
    assert persisted_failure["execution_status"] == "model_api_failure"
    assert persisted_failure["persisted"] is True


def test_okb_retrieval_failure_is_isolated_and_classified(tmp_path):
    workflows = {
        "B0": RecordingWorkflow(b0_state()),
        "B2": RecordingWorkflow(b2_state()),
        "B3": RecordingWorkflow(b3_state()),
        "F": RecordingWorkflow(f_state()),
    }
    store = ExperimentStore(tmp_path / "experiments")
    runner = ExperimentRunner(
        store=store,
        llm_client=FakeLLM(),
        career_labels=labels(),
        workflow_factory=lambda configuration_id: workflows[configuration_id],
        okb_fingerprint_provider=lambda: (_ for _ in ()).throw(RuntimeError("OKB offline")),
        git_provenance_provider=git,
        enforce_database_isolation=False,
    )
    result = run_all(runner)
    by_config = {record.configuration_id: record for record in result.records}

    assert by_config["B0"].execution_status == "success"
    assert by_config["B0"].okb_usage == "NOT_APPLICABLE"
    for configuration_id in ("B2", "B3", "F"):
        assert by_config[configuration_id].execution_status == "retrieval_failure"
        assert by_config[configuration_id].okb_usage == "RETRIEVAL_FAILED"
        assert by_config[configuration_id].okb_snapshot_fingerprint is None
    assert result.manifest.partial is True
    assert result.manifest.successful_configurations == ["B0"]
    assert result.manifest.failed_configurations == ["B2", "B3", "F"]


# 5. Correct NOT_APPLICABLE values.
def test_not_applicable_values_are_explicit_not_zero_or_false(tmp_path):
    runner, _, _ = make_runner(tmp_path)
    result = run_all(runner)
    by_config = {record.configuration_id: record for record in result.records}

    b0 = by_config["B0"]
    assert b0.okb_usage == "NOT_APPLICABLE"
    assert b0.okb_snapshot_fingerprint is None
    assert b0.okb_counts is None
    assert b0.capabilities == {
        "skill_gap": "NOT_APPLICABLE",
        "roadmap": "NOT_APPLICABLE",
        "verification": "NOT_APPLICABLE",
    }
    assert b0.first_pass_verification_status == "NOT_APPLICABLE"
    assert b0.final_verification_status == "NOT_APPLICABLE"

    b2 = by_config["B2"]
    assert b2.okb_usage == "USED"
    assert b2.capabilities == {
        "skill_gap": "AVAILABLE",
        "roadmap": "NOT_APPLICABLE",
        "verification": "NOT_APPLICABLE",
    }
    assert b2.first_pass_verification_status == "NOT_APPLICABLE"
    assert b2.final_verification_status == "NOT_APPLICABLE"

    b3 = by_config["B3"]
    assert b3.capabilities["verification"] == "NOT_APPLICABLE"
    assert b3.first_pass_verification_status == "NOT_APPLICABLE"
    assert b3.final_verification_status == "NOT_APPLICABLE"
    assert b3.revision_count == 0
    assert b3.raw_structured_output["verification"] is None

    f = by_config["F"]
    assert f.capabilities["verification"] == "AVAILABLE"
    assert f.final_verification_status == "PASS"


# 6. No ground-truth leakage.
def test_ground_truth_is_not_passed_to_workflows_or_metadata(tmp_path):
    runner, _, workflows = make_runner(tmp_path)
    run_all(runner)
    for configuration_id, workflow in workflows.items():
        call = workflow.calls[0]
        assert set(call) <= {"user_id", "profile_bundle", "career_labels"}
        if configuration_id in {"B0", "B2"}:
            assert "career_labels" in call
        else:
            assert "career_labels" not in call
        assert "target_career_id" not in call
        assert "raw_profile_text" not in call
        assert "metadata" not in call
        assert "ground_truth" not in json.dumps(call, default=str)

    with pytest.raises(SharedInputError, match="ground-truth"):
        runner.run_configuration(
            case_id="case-001",
            run_id="run-002",
            configuration_id="B0",
            bundle=bundle(),
            user_id=101,
            metadata={"ground_truth_career_ids": ["C01"]},
        )

    data = bundle().model_dump()
    data["ground_truth_career_ids"] = ["C01"]
    with pytest.raises(SharedInputError, match="ground_truth_career_ids"):
        runner.run_configuration(
            case_id="case-001",
            run_id="run-003",
            configuration_id="B0",
            bundle=data,
            user_id=101,
        )


# 7. Correct first-pass and final verification recording.
def test_first_pass_and_final_verification_are_recorded(tmp_path):
    runner, _, _ = make_runner(tmp_path)
    result = run_all(runner)
    by_config = {record.configuration_id: record for record in result.records}

    f = by_config["F"]
    assert f.first_pass_verification_status == "FAIL"
    assert f.final_verification_status == "PASS"
    assert f.revision_count == 1
    assert f.normalized_evaluation_output["verification"]["first_pass_status"] == "FAIL"
    assert f.normalized_evaluation_output["verification"]["status"] == "PASS"
    assert f.normalized_evaluation_output["verification"]["revision_count"] == 1

    b3 = by_config["B3"]
    assert b3.first_pass_verification_status == "NOT_APPLICABLE"
    assert b3.final_verification_status == "NOT_APPLICABLE"
    assert b3.revision_count == 0


def test_nonpassing_final_verification_is_preserved(tmp_path):
    runner, _, _ = make_runner(
        tmp_path,
        states={
            "B0": b0_state(),
            "B2": b2_state(),
            "B3": b3_state(),
            "F": f_state(first_pass="REVISE", final="FAIL", revisions=2),
        },
    )
    result = run_all(runner)
    f = {record.configuration_id: record for record in result.records}["F"]
    assert f.execution_status == "success"
    assert f.first_pass_verification_status == "REVISE"
    assert f.final_verification_status == "FAIL"
    assert f.revision_count == 2


# 8. Correct metadata and error recording.
def test_metadata_and_error_recording(tmp_path):
    runner, store, workflows = make_runner(tmp_path)
    workflows["B2"].state = {
        "configuration_id": "B2",
        "final_status": "ERROR",
        "stage": "baseline_inference",
        "revision_count": 0,
        "errors": [
            {
                "stage": "baseline_inference",
                "error_type": "ValueError",
                "message": "B2 categories must classify each required skill exactly once",
            }
        ],
    }
    result = run_all(runner)
    record = {item.configuration_id: item for item in result.records}["B2"]

    assert record.case_id == "case-001"
    assert record.run_id == "run-001"
    assert record.configuration_id == "B2"
    assert record.configuration_label
    assert record.execution_status == "validation_failure"
    assert record.error_type == "ValueError"
    assert record.error_stage == "baseline_inference"
    assert "classify each required skill" in record.error_message
    assert record.llm_provider == "FakeLLM"
    assert record.llm_model == "fake-model"
    baseline_prompt = record.prompt_identifiers["prompts"]["baseline_inference"]
    assert baseline_prompt["sha256"] == baseline_prompt["version"].removeprefix("sha256:")
    assert len(baseline_prompt["sha256"]) == 64
    assert record.inference_settings["response_format"] == "json"
    assert record.inference_settings["max_revisions"] == 0
    assert record.git_commit == "b" * 40
    assert record.git_dirty is True
    assert record.git_diff_sha256 == "c" * 64
    assert record.metadata == {"dataset_type": "R", "split": "pilot"}
    assert record.okb_snapshot_fingerprint == "a" * 64
    assert record.okb_counts == {"careers": 10, "skills": 87, "career_skills": 155}
    assert record.start_timestamp_utc.endswith("Z")
    assert record.completion_timestamp_utc.endswith("Z")
    assert record.duration_ms >= 0
    assert store.read_run("case-001", "run-001", "B2")["error_type"] == "ValueError"


def test_timeout_and_incomplete_output_are_distinguished(tmp_path):
    runner, _, workflows = make_runner(tmp_path)
    workflows["B0"].delay = 0.2
    result = runner.run_case(
        case_id="case-001",
        run_id="run-timeout",
        bundle=bundle(),
        user_id=101,
        configurations=["B0"],
        timeout_seconds=0.01,
    )
    assert result.records[0].execution_status == "timeout"
    assert result.records[0].error_type == "ExperimentTimeoutError"

    runner, _, workflows = make_runner(tmp_path)
    incomplete = b3_state()
    incomplete.pop("roadmap")
    workflows["B3"].state = incomplete
    result = runner.run_case(
        case_id="case-001",
        run_id="run-incomplete",
        bundle=bundle(),
        user_id=101,
        configurations=["B3"],
    )
    assert result.records[0].execution_status == "incomplete_output"
    assert "roadmap" in result.records[0].error_message


class FailingStore(ExperimentStore):
    def __init__(self, root, *, fail_configuration):
        super().__init__(root)
        self.fail_configuration = fail_configuration

    def write_run(self, record):
        if record.configuration_id == self.fail_configuration:
            raise OSError("disk full")
        return super().write_run(record)


def test_persistence_failure_is_recorded_without_losing_other_runs(tmp_path):
    workflows = {
        configuration_id: RecordingWorkflow(state)
        for configuration_id, state in {
            "B0": b0_state(),
            "B2": b2_state(),
            "B3": b3_state(),
            "F": f_state(),
        }.items()
    }
    store = FailingStore(tmp_path / "experiments", fail_configuration="B2")
    runner = ExperimentRunner(
        store=store,
        llm_client=FakeLLM(),
        career_labels=labels(),
        workflow_factory=lambda configuration_id: workflows[configuration_id],
        okb_fingerprint_provider=okb,
        git_provenance_provider=git,
        enforce_database_isolation=False,
    )
    result = run_all(runner)
    by_config = {record.configuration_id: record for record in result.records}

    assert by_config["B2"].execution_status == "persistence_failure"
    assert by_config["B2"].pre_persistence_status == "success"
    assert by_config["B2"].persisted is False
    assert by_config["B2"].persistence_error_type == "OSError"
    assert by_config["B2"].persistence_error_message == "disk full"
    assert not Path(by_config["B2"].record_path).exists()
    for configuration_id in ("B0", "B3", "F"):
        assert by_config[configuration_id].execution_status == "success"
        assert by_config[configuration_id].persisted is True
    assert result.manifest.failed_configurations == ["B2"]
    assert result.manifest.partial is True


# 9. Prevention of writes to the main application database.
def test_main_database_is_rejected_by_the_isolation_guard():
    assert assert_isolated_database("career_intelligence_eval") == "career_intelligence_eval"
    assert assert_isolated_database("career_intelligence_e2e_test") == (
        "career_intelligence_e2e_test"
    )
    with pytest.raises(IsolationError, match="protected database"):
        assert_isolated_database("career_intelligence_main")
    with pytest.raises(IsolationError, match="protected database"):
        assert_isolated_database("career_intelligence")
    with pytest.raises(IsolationError, match="not an isolated"):
        assert_isolated_database("some_other_database")


def test_database_url_to_main_overrides_and_rejects_an_e2e_name(monkeypatch):
    monkeypatch.setenv("CAREER_DB_NAME", "career_intelligence_e2e_test")
    monkeypatch.setenv(
        "CAREER_DB_URL",
        "postgresql+psycopg2://localhost:5433/career_intelligence_main",
    )

    assert database_name() == "configuration_mismatch"
    with pytest.raises(IsolationError, match="disagrees with the database named by CAREER_DB_URL"):
        assert_isolated_database()


def test_effective_engine_main_is_rejected_before_connection(monkeypatch):
    monkeypatch.setenv("CAREER_DB_NAME", "career_intelligence_e2e_test")
    monkeypatch.delenv("CAREER_DB_URL", raising=False)

    class MainEngine:
        url = SimpleNamespace(host="localhost", database="career_intelligence_main", port=5433)

        def connect(self):
            raise AssertionError("the main database must be rejected before connect")

    monkeypatch.setattr("app.core.db.get_engine", lambda: MainEngine())
    runner = ExperimentRunner(enforce_database_isolation=True)
    with pytest.raises(IsolationError, match="effective engine database"):
        runner._default_okb_snapshot()


def test_server_main_identity_is_rejected_before_okb_read(monkeypatch):
    monkeypatch.setenv("CAREER_DB_NAME", "career_intelligence_e2e_test")
    monkeypatch.delenv("CAREER_DB_URL", raising=False)

    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def execute(self, statement):
            assert "current_database" in str(statement)
            return SimpleNamespace(scalar_one=lambda: "career_intelligence_main")

    class IsolatedUrlEngine:
        url = SimpleNamespace(host="localhost", database="career_intelligence_e2e_test", port=5433)
        def connect(self): return Connection()

    monkeypatch.setattr("app.core.db.get_engine", lambda: IsolatedUrlEngine())
    monkeypatch.setattr(
        "app.evaluation.runner.compute_okb_snapshot",
        lambda: pytest.fail("OKB retrieval must not follow a mismatched server identity"),
    )
    runner = ExperimentRunner(enforce_database_isolation=True)
    with pytest.raises(IsolationError, match="server-confirmed database"):
        runner._default_okb_snapshot()


def test_runner_refuses_real_execution_against_main_database(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_DB_NAME", "career_intelligence_main")
    monkeypatch.setattr(
        "app.evaluation.runner.CareerWorkflow",
        lambda **kwargs: pytest.fail("a workflow must not be constructed against the main DB"),
    )
    store = ExperimentStore(tmp_path / "experiments")
    runner = ExperimentRunner(
        store=store,
        llm_client=FakeLLM(),
        career_labels=labels(),
        okb_fingerprint_provider=okb,
        git_provenance_provider=git,
        enforce_database_isolation=True,
    )
    record = runner.run_configuration(
        case_id="case-001",
        run_id="run-guard",
        configuration_id="B3",
        bundle=bundle(),
        user_id=101,
    )
    assert record.execution_status == "validation_failure"
    assert record.error_type == "IsolationError"
    assert record.error_stage == "database_isolation"
    assert record.database_target == "career_intelligence_main"
    assert record.database_write_guard == "ENFORCED"
    assert record.persisted is True


def test_prompt_hash_provenance_is_persisted_for_shared_and_configuration_calls(tmp_path):
    class CallClient:
        model = "provenance-test-model"
        temperature = 0.2

        def complete_json(self, *, system, user, max_tokens):
            return {"ok": True}

    client = CallClient()
    shared = LLMCallProvenance("case-prov", "run-prov", "SHARED_INPUT")
    shared.wrap(client).complete_json(
        system="SYSTEM_SENTINEL", user="USER_SENTINEL", max_tokens=19,
    )

    class Workflow:
        def __init__(self):
            self.llm_client = client

        def run(self, **kwargs):
            self.llm_client.complete_json(
                system="CONFIG_SYSTEM", user="CONFIG_USER", max_tokens=23,
            )
            return b0_state()

    runner = ExperimentRunner(
        store=ExperimentStore(tmp_path / "experiments"),
        career_labels=labels(),
        workflow_factory=lambda _: Workflow(),
        git_provenance_provider=git,
        enforce_database_isolation=False,
    )
    record = runner.run_configuration(
        case_id="case-prov", run_id="run-prov", configuration_id="B0",
        bundle=bundle(), user_id=101,
        metadata={"shared_input_llm_calls": shared.snapshot()},
    )
    calls = record.llm_call_provenance
    assert [call["configuration_id"] for call in calls] == ["SHARED_INPUT", "B0"]
    assert all(call["case_id"] == "case-prov" and call["run_id"] == "run-prov" for call in calls)
    assert calls[0]["system_prompt_sha256"] == hashlib.sha256(b"SYSTEM_SENTINEL").hexdigest()
    assert calls[0]["user_prompt_sha256"] == hashlib.sha256(b"USER_SENTINEL").hexdigest()
    assert calls[1]["system_prompt_sha256"] == hashlib.sha256(b"CONFIG_SYSTEM").hexdigest()
    assert calls[1]["user_prompt_sha256"] == hashlib.sha256(b"CONFIG_USER").hexdigest()
    assert record.source_state_fingerprint is not None
    persisted = Path(record.record_path).read_text(encoding="utf-8")
    assert "SYSTEM_SENTINEL" not in persisted and "USER_SENTINEL" not in persisted
    assert "source_state_fingerprint" in persisted


def test_raw_run_diagnostics_include_normalization_candidates_without_claim_text():
    from app.agents.skill_normalizer import FuzzyMatchCandidate, NormalizationResult

    profile_result = SimpleNamespace(normalizations=[SimpleNamespace(
        mention_id="m0001",
        claimed_skill="Sensitive user phrase",
        result=NormalizationResult(
            None, None, "unmatched", None, outcome="unmatched",
            fuzzy_candidates=[FuzzyMatchCandidate("S001", "Access Control", 0.31, False)],
        ),
    )])
    output = ExperimentRunner._raw_output({"profile_result": profile_result})
    diagnostic = output["normalization_diagnostics"][0]
    assert diagnostic["mention_id"] == "m0001"
    assert diagnostic["outcome"] == "unmatched"
    assert diagnostic["fuzzy_candidates"][0]["similarity"] == 0.31
    assert "Sensitive user phrase" not in json.dumps(output)
