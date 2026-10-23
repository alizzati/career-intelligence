"""Regression tests for the serialization/redaction defects behind the Step 16 failures.
Pure unit tests: no DB, no LLM, no workflow."""
import json
from types import SimpleNamespace as NS

import pytest

from app.inspection import artifact as art
from app.inspection.recorder import Recorder, _safe_workflow_errors, clean_str, to_jsonable

DIGEST_WITH_16_DIGITS = "a" + "1234567890123456" + "b" * 47


@pytest.mark.parametrize("value", ["long", "profile_analysis", "ValueError", "", "plain text 123",
                                   "mail x.y@example.test", "0812-5555-0199"])
def test_clean_str_always_returns_a_string(value):
    assert isinstance(clean_str(value), str)


def test_clean_str_keeps_ordinary_text_and_redacts_pii():
    assert clean_str("profile_analysis") == "profile_analysis"
    assert "x.y@example.test" not in clean_str("mail x.y@example.test")
    assert "[REDACTED_EMAIL]" in clean_str("mail x.y@example.test")


def test_clean_str_truncation_keeps_a_string_marker():
    out = clean_str("z" * 900, 600)
    assert isinstance(out, str) and "truncated" in out and len(out) < 700


def test_digest_survives_and_ordinary_dict_keys_are_stable():
    assert to_jsonable({"sha256": DIGEST_WITH_16_DIGITS, "stage": "x"}) == {
        "sha256": DIGEST_WITH_16_DIGITS, "stage": "x"}
    assert None not in to_jsonable({"a": 1, "long": "v"})


def test_all_digit_numbers_are_still_redacted():
    assert clean_str("3174012345678901") != "3174012345678901"


def test_colliding_redacted_keys_are_not_silently_merged():
    out = to_jsonable({"3174012345678901": 1, "3174012345678902": 2})
    assert len(out) == 2 and sorted(out.values()) == [1, 2]


def test_safe_workflow_errors_keep_stage_and_type_but_never_the_message():
    errors = _safe_workflow_errors([{"stage": "profile_analysis", "error_type": "ValueError",
                                     "message": "PRIVATE_SENTINEL"}])
    assert errors == [{"stage": "profile_analysis", "error_type": "ValueError"}]


def test_safe_context_values_omits_absent_keys_and_non_scalars():
    out = art._safe_context_values(
        {"client_type": "FakeLLM", "test_double": True, "model": None, "nested": {"x": 1}, "extra": 5},
        ("client_type", "provider", "model", "test_double", "nested"))
    assert out == {"client_type": "FakeLLM", "model": None, "test_double": True}
    assert art._safe_context_values(None, ("a",)) == {}
    assert art._safe_context_values({"careers": 10}, ("careers", "skills", "sources")) == {"careers": 10}


def test_llm_runtime_is_explicit_when_no_client_and_uses_model_when_known():
    assert art._llm_runtime(None)["model"] == "unavailable"
    fake = NS(model_name="SomeFake")
    assert art._llm_runtime(fake)["model"] == "SomeFake"


def test_minimal_artifact_has_expected_top_level_structure_and_no_none_keys():
    rec = Recorder()
    artifact = art.build_artifact(rec, {
        "run_id": "r", "started_at": "t", "mode": "m", "mode_label": "L",
        "final_state": {"final_status": "ERROR", "revision_count": 0, "target_career_id": None,
                        "errors": [{"stage": "x", "error_type": "E", "message": "SECRET_MSG"}]},
        "max_revisions": 2, "llm": {"client_type": "FakeLLM", "test_double": True},
        "kb_counts_before": {"careers": 10}, "kb_counts_after": {"careers": 10}})
    for key in ("schema_version", "run_metadata", "workflow_execution", "verification_agent",
                "cross_stage_checks", "independent_reference_checks", "final_output"):
        assert key in artifact, key
    assert artifact["run_metadata"]["kb_unchanged"] is True
    assert artifact["independent_reference_checks"] == "unavailable"
    assert artifact["final_output"]["errors"] == [{"stage": "x", "error_type": "E"}]
    assert "SECRET_MSG" not in json.dumps(artifact)
    assert "null" not in json.dumps(list(artifact.keys()))


def test_kb_unchanged_is_unavailable_without_counts():
    rec = Recorder()
    artifact = art.build_artifact(rec, {
        "run_id": "r", "started_at": "t", "mode": "m", "mode_label": "L",
        "final_state": {"final_status": "VERIFIED", "revision_count": 0, "errors": []}})
    assert artifact["run_metadata"]["kb_unchanged"] == "unavailable"