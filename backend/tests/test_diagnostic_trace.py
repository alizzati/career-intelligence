"""Offline unit tests for the diagnostic trace builder.

No database, no network, no LLM. Every object built here is a real project schema
instance so the trace is tested against the contracts the pipeline actually produces.
"""
from __future__ import annotations

import json

import pytest

from app.agents.profile_agent import ProfileAgentResult, SkillNormalizationReport
from app.agents.skill_normalizer import NormalizationResult
from app.diagnostics import trace as tr
from app.inspection.recorder import Recorder
from app.schemas.career_fit import CareerRecommendationOut, ScoreBreakdownOut, SkillRefOut
from app.schemas.learning_roadmap import LearningRoadmapItem, LearningRoadmapOut
from app.schemas.skill_gap import (
    MatchedUserClaim, SkillGapItem, SkillGapResult, UnmatchedUserClaim,
)
from app.schemas.skill_gap_agent import SkillGapAnalysisOut, SkillGapNarrative
from app.schemas.verification import VerificationCheck, VerificationResult

EMAIL = "int.person@example.invalid"
PHONE = "0812-5555-0123"
HANDLE = "https://github.com/int.person"
PERSON = "Int Person"

WEIGHTS = {"core_weight": 2.0, "supporting_weight": 1.0, "confidence_multiplier": {"high": 1.0},
           "claim_only_multiplier": 0.5, "proficiency_modifier": 0.1}


def _breakdown(**overrides):
    payload = {
        "total_weight": 3.0, "total_contribution": 1.5, "core_required_count": 1,
        "supporting_required_count": 1, "matched_linked_count": 1,
        "matched_claimed_only_count": 0, "missing_count": 1, "weights_used": WEIGHTS,
    }
    payload.update(overrides)
    return ScoreBreakdownOut(**payload)


def _ref(skill_id, name="Skill"):
    return SkillRefOut(skill_id=skill_id, canonical_name=name, evidence_class="CORE")


def recommendations():
    return [
        CareerRecommendationOut(
            career_id="C1", canonical_name="Backend Engineer", domain="Engineering",
            fit_score=0.5, score_breakdown=_breakdown(),
            matched_skills=[_ref("S001", "SQL")], claimed_only_skills=[],
            missing_skills_preview=[_ref("S002", "Networking")],
            reasoning="Deterministic fit reflected.", reasoning_source="fallback-template",
        ),
        CareerRecommendationOut(
            career_id="C2", canonical_name="Data Analyst", domain="Data",
            fit_score=0.25, score_breakdown=_breakdown(total_weight=4.0, total_contribution=1.0),
            matched_skills=[], claimed_only_skills=[_ref("S004", "Data Analysis")],
            missing_skills_preview=[], reasoning="Deterministic fit reflected.",
            reasoning_source="fallback-template",
        ),
    ]


def skill_gap_analysis():
    deterministic = SkillGapResult(
        user_id=1, career_id="C1", canonical_name="Backend Engineer", domain="Engineering",
        fit_score=0.5, total_weight=3.0, total_contribution=1.5, score_breakdown=_breakdown(),
        matched_evidenced=[
            SkillGapItem(
                skill_id="S001", canonical_name="SQL", status="matched_evidenced",
                evidence_class="CORE", kb_confidence="high", weight=2.0, contribution=2.0,
                matched_user_claim=MatchedUserClaim(
                    claimed_skill="SQL", proficiency="intermediate",
                    evidence_status="linked", evidence_count=1,
                ),
            )
        ],
        matched_claimed_only=[
            SkillGapItem(
                skill_id="S002", canonical_name="Networking", status="matched_claimed_only",
                evidence_class="SUPPORTING", kb_confidence="medium", weight=1.0, contribution=0.5,
                matched_user_claim=MatchedUserClaim(
                    claimed_skill="Networking", proficiency=None,
                    evidence_status="none", evidence_count=0,
                ),
            )
        ],
        missing=[
            SkillGapItem(
                skill_id="S003", canonical_name="Database Management", status="missing",
                evidence_class="CORE", kb_confidence="high", weight=2.0, contribution=0.0,
            )
        ],
        unmatched_user_claims=[
            UnmatchedUserClaim(
                user_skill_id=9, claimed_skill="Totally Unmapped Claim", proficiency=None,
                evidence_status="none", evidence_count=0,
            )
        ],
    )
    narrative = SkillGapNarrative(summary="Synthetic summary.", conclusion="Synthetic conclusion.")
    return SkillGapAnalysisOut(
        skill_gap=deterministic, narrative=narrative, narrative_source="fallback-template",
        validation_notes=["deterministic template used"],
    )


def roadmap():
    return LearningRoadmapOut(
        skill_gap=skill_gap_analysis().skill_gap,
        items=[
            LearningRoadmapItem(
                skill_id="S002", canonical_name="Networking", gap_status="matched_claimed_only",
                evidence_class="SUPPORTING", kb_confidence="medium",
                knowledge_base_basis="KB basis text.", learning_action="add_linked_evidence",
            ),
            LearningRoadmapItem(
                skill_id="S003", canonical_name="Database Management", gap_status="missing",
                evidence_class="CORE", kb_confidence="high",
                knowledge_base_basis="KB basis text.", learning_action="develop_skill",
            ),
        ],
        summary="Synthetic roadmap summary.",
        narrative_source="fallback-template",
    )


def verification():
    return VerificationResult(
        status="PASS",
        checks=[
            VerificationCheck(check="recommendation.career_set", status="PASS", reason="ok"),
            VerificationCheck(check="skill_gap.category_integrity", status="PASS", reason="ok"),
        ],
        unsupported_claims=[],
        required_revision=[],
    )


def profile_result():
    return ProfileAgentResult(
        user_id=1,
        extracted={
            "skills": [
                {"claimed_skill": "SQL", "proficiency": "intermediate", "candidate_skill_id": "S001"},
                {"claimed_skill": "Totally Unmapped Claim", "proficiency": None,
                 "candidate_skill_id": None},
            ],
            "evidence": [
                {"claimed_skill": "SQL", "evidence_type": "project",
                 "description": f"Built a tool with {EMAIL} and {PHONE}", "url": HANDLE},
            ],
            "education": [
                {"institution": f"University of {PERSON}", "degree": "BSc",
                 "field_of_study": "IT", "start_date": "2020", "end_date": "2024",
                 "description": f"Contact {EMAIL}"},
            ],
            "experience": [],
            "projects": [
                {"title": "Synthetic", "description": "Synthetic project", "url": None,
                 "role": "Developer"},
            ],
            "certifications": [],
        },
        normalizations=[
            SkillNormalizationReport(
                "SQL", NormalizationResult("S001", "SQL", "exact-deterministic", 1.0)),
            SkillNormalizationReport(
                "Totally Unmapped Claim", NormalizationResult(None, None, "unmatched", None)),
        ],
        skills_persisted=2,
        evidence_persisted=1,
    )


def build_full_trace(*, analysis=None, stages=None, recorder=None):
    staged = {
        "extraction": tr.build_extraction_stage(
            document={"format": "pdf", "size_bytes": 1234, "page_count": 2, "character_count": 900},
            redaction={"detected_types": ["EMAIL", "PHONE"], "replacement_count": 3},
            http_status=200,
        ),
        "profile": tr.build_profile_stage(profile_result()),
        "okb_retrieval": tr.stage(
            "ok",
            payload={
                "career_count": 2,
                "careers": [
                    {"career_id": "C1", "requirements": [{"skill_id": "S001"},
                                                         {"skill_id": "S002"}, {"skill_id": "S003"}]},
                    {"career_id": "C2", "requirements": [{"skill_id": "S004"}]},
                ],
            },
        ),
        "career_fit": tr.build_career_fit_stage(recommendations(), computations=[
            {"seq": 1, "stage": "career_recommendation", "called_from": "career_recommendation_agent",
             "fit_score": 0.5, "total_weight": 3.0, "total_contribution": 1.5,
             "required_ids": ["S001", "S002", "S003"]},
        ]),
        "skill_gap": tr.build_skill_gap_stage(skill_gap_analysis()),
        "roadmap": tr.build_roadmap_stage(roadmap()),
        "verification": tr.build_verification_stage(verification(), revision_count=0, revision_limit=2),
    }
    staged["final"] = tr.build_final_stage(
        final_status="VERIFIED", verified=True, target_career_id="C1",
        revision_count=0, revision_limit=2, revision_target=None, last_stage="final_result",
        errors=[], ranked=recommendations(),
    )
    if stages:
        staged.update(stages)
    trace_analysis = analysis or {
        "source": "cv_upload", "http_status": 200, "duration_ms": 1234.5,
        "response_final_status": "VERIFIED", "analysis_id": "abc123",
        "analysis_log_path": "analysis_logs/cv01_deadbeef.analysis_log.json", "error": None,
    }
    return tr.build_trace(
        run={
            "run_id": "test-run", "started_at": "2026-01-01T00:00:00Z", "llm_mode": "fake_llm",
            "llm_mode_label": "plumbing", "model": "FakeLLM",
            "model_version": tr.UNAVAILABLE_MODEL_VERSION, "provider": "FakeLLM",
            "sdk_version": "not applicable",
            "prompt_catalog_version": tr.prompt_catalog_version(),
            "kb_version": tr.UNAVAILABLE_KB_VERSION,
        },
        cv={
            "cv_id": "cv01_deadbeef", "sha256": "a" * 64, "format": "pdf",
            "size_bytes": 1234, "upload_name": "cv01_deadbeef.pdf",
            "trace_path": "traces/cv01_deadbeef.trace.json",
        },
        analysis=trace_analysis,
        stages=staged,
        recorder=recorder or Recorder(),
        consistency_observations=tr.observe_consistency(analysis=trace_analysis, stages=staged),
    )


# --------------------------------------------------------------------------- schema
def test_trace_declares_its_schema_and_every_stage():
    trace = build_full_trace()

    assert trace["schema_version"] == tr.TRACE_SCHEMA_VERSION
    assert list(trace["stages"]) == list(tr.STAGE_ORDER)
    for name in tr.STAGE_ORDER:
        assert trace["stages"][name]["status"] in tr.STAGE_STATUSES


def test_trace_is_json_serializable_and_only_contains_expected_sections():
    trace = build_full_trace()

    json.dumps(trace)
    assert set(trace) == {
        "schema_version", "run", "cv", "analysis", "stages", "llm_calls", "node_events",
        "agent_runs", "warnings", "privacy", "unavailable_fields", "consistency_note",
        "consistency_observations",
    }


def test_skill_gap_keeps_exactly_the_four_frozen_categories():
    stage = tr.build_skill_gap_stage(skill_gap_analysis())

    categories = stage["payload"]["categories"]
    assert set(categories) == {
        "matched_evidenced", "matched_claimed_only", "missing", "unmatched_user_claims",
    }
    assert stage["payload"]["counts"] == {
        "matched_evidenced": 1, "matched_claimed_only": 1, "missing": 1,
        "unmatched_user_claims": 1,
    }

    def keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from keys(item)

    for key in keys(stage["payload"]):
        lowered = key.lower()
        assert not lowered.startswith("priority"), key
        assert not lowered.startswith("tier"), key
        assert "target_proficiency" not in lowered, key
        assert "required_proficiency" not in lowered, key


def test_unmatched_user_claims_are_not_reinterpreted_as_missing_skills():
    stage = tr.build_skill_gap_stage(skill_gap_analysis())

    missing_ids = {row["skill_id"] for row in stage["payload"]["categories"]["missing"]}
    unmatched = stage["payload"]["categories"]["unmatched_user_claims"]
    assert missing_ids == {"S003"}
    assert [row["claimed_skill"] for row in unmatched] == ["Totally Unmapped Claim"]
    assert all("skill_id" not in row for row in unmatched)


def test_career_fit_stage_preserves_order_and_marks_the_source_of_truth():
    stage = tr.build_career_fit_stage(recommendations(), computations=[
        {"seq": 3, "stage": "career_recommendation", "called_from": "career_recommendation_agent",
         "fit_score": 0.5, "total_weight": 3.0, "total_contribution": 1.5,
         "required_ids": ["S001", "S002", "S003"]},
    ])

    ranked = stage["payload"]["ranked"]
    assert [row["career_id"] for row in ranked] == ["C1", "C2"]
    assert [row["rank"] for row in ranked] == [1, 2]
    assert stage["payload"]["compute_career_fit_call_count"] == 1
    assert stage["payload"]["compute_career_fit_calls"][0]["fit_score"] == 0.5
    assert "never recomputes" in stage["payload"]["note"]


def test_final_stage_reports_rank_and_fit_for_the_target_career():
    trace = build_full_trace()
    final = trace["stages"]["final"]["payload"]

    assert final["target_career_id"] == "C1"
    assert final["target_rank"] == 1
    assert final["target_fit_score"] == pytest.approx(0.5)
    assert final["top1_career_id"] == "C1"
    assert final["top2_career_id"] == "C2"


# --------------------------------------------------------------------------- honesty
def test_unavailable_fields_are_declared_and_never_estimated():
    trace = build_full_trace()
    serialized = json.dumps(trace)

    assert trace["llm_calls"]["tokens"].startswith("unavailable")
    assert trace["llm_calls"]["cost_usd"].startswith("unavailable")
    declared = {item["field"] for item in trace["unavailable_fields"]}
    assert "llm_calls[].total_tokens" in declared
    assert "llm_calls[].cost_usd" in declared
    assert "run.model_version" in declared
    assert "run.generation_settings" in declared
    assert trace["run"]["model_version"].startswith("unavailable")
    # No fabricated numeric usage anywhere.
    for forbidden in ("usage_metadata", "prompt_token_count", "total_token_count"):
        assert forbidden not in serialized


def test_missing_stage_is_not_reached_and_does_not_invent_numbers():
    trace = build_full_trace(stages={
        "skill_gap": tr.stage("not_reached", notes=["no result"]),
        "roadmap": tr.stage("not_reached", notes=["no result"]),
        "verification": tr.stage("not_reached", notes=["no result"]),
    })
    row = tr.build_csv_row(trace)

    assert trace["stages"]["skill_gap"]["status"] == "not_reached"
    assert row["gap_matched_evidenced_count"] is None
    assert row["gap_missing_count"] is None
    assert row["verification_status"] is None
    assert row["roadmap_items_count"] is None


# --------------------------------------------------------------------------- privacy
def test_raw_pii_and_urls_never_enter_the_trace():
    trace = build_full_trace()
    serialized = json.dumps(trace, ensure_ascii=False)

    for sentinel in (EMAIL, PHONE, HANDLE, "int.person"):
        assert sentinel not in serialized, sentinel
    evidence = trace["stages"]["profile"]["payload"]["evidence"]
    assert evidence and evidence[0]["url_present"] is True
    assert "url" not in evidence[0]


def test_trace_declares_that_no_raw_text_or_filename_is_stored():
    trace = build_full_trace()
    privacy = trace["privacy"]

    assert privacy["raw_cv_text_persisted"] is False
    assert privacy["original_filename_persisted"] is False
    assert privacy["raw_prompt_persisted"] is False
    assert privacy["raw_llm_response_persisted"] is False
    for forbidden in ("raw_text", "content", "filename", "text"):
        assert forbidden not in trace["cv"]


def test_profile_stage_records_extraction_and_normalization_outcomes():
    stage = tr.build_profile_stage(profile_result())
    payload = stage["payload"]

    assert payload["counts"]["skills_extracted"] == 2
    assert payload["counts"]["skills_normalized"] == 1
    assert payload["counts"]["skills_unmatched"] == 1
    assert payload["match_methods"] == {"exact-deterministic": 1, "unmatched": 1}
    by_claim = {row["claimed_skill"]: row for row in payload["skills"]}
    assert by_claim["SQL"]["matched_skill_id"] == "S001"
    assert by_claim["Totally Unmapped Claim"]["matched"] is False


# --------------------------------------------------------------------------- CSV
def test_csv_row_has_exactly_the_declared_columns_and_scalar_values():
    trace = build_full_trace()
    row = tr.build_csv_row(trace)

    assert tuple(row) == tr.CSV_COLUMNS
    for column, value in row.items():
        assert isinstance(value, (str, int, float, bool, type(None))), (column, type(value))


def test_csv_row_reports_the_diagnostic_summary_fields():
    row = tr.build_csv_row(build_full_trace())

    assert row["cv_id"] == "cv01_deadbeef"
    assert row["file_format"] == "pdf"
    assert row["http_status"] == 200
    assert row["final_status"] == "VERIFIED"
    assert row["verified"] is True
    assert row["top1_career_id"] == "C1"
    assert row["gap_missing_count"] == 1
    assert row["gap_unmatched_user_claims_count"] == 1
    assert row["verification_checks_total"] == 2
    assert row["total_duration_ms"] == 1234.5
    assert row["trace_path"] == "traces/cv01_deadbeef.trace.json"


def test_csv_row_records_stage_errors_instead_of_hiding_them():
    stages = {"profile": tr.stage("failed", error={"error_type": "RuntimeError"})}
    trace = build_full_trace(stages=stages)
    row = tr.build_csv_row(trace)

    assert "profile:RuntimeError" in (row["stage_errors"] or "")


# --------------------------------------------------------------------------- observations
def test_consistency_observations_are_labelled_as_diagnostic_only():
    trace = build_full_trace()
    observations = trace["consistency_observations"]

    assert observations
    for item in observations:
        assert item["observation_only"] is True
        assert item["result"] in {"PASS", "WARN", "SKIP"}
    assert "NOT the Step 12 verification result" in trace["consistency_note"]


def test_consistency_warns_when_response_and_state_disagree():
    mismatched = {
        "source": "cv_upload", "http_status": 200, "duration_ms": 10.0,
        "response_final_status": "VERIFIED", "analysis_id": None,
        "analysis_log_path": None, "error": None,
    }
    stages = {"final": tr.stage("ok", payload={"final_status": "VERIFICATION_FAILED"})}
    trace = build_full_trace(analysis=mismatched, stages=stages)
    checks = {item["check"]: item["result"] for item in trace["consistency_observations"]}

    assert checks["api_response_matches_workflow_state"] == "WARN"
