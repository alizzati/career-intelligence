"""Run a synthetic, FakeLLM-backed CV through the real FastAPI workflow.

This temporary diagnostic captures allowlisted stage snapshots only. It never
records prompts, credentials, raw CV text, account email, or full user records.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.agents.career_recommendation_agent import CareerRecommendationAgent
from app.agents.learning_roadmap_agent import LearningRoadmapAgent
from app.agents.profile_agent import ProfileAgent
from app.agents.skill_gap_agent import SkillGapAgent
from app.agents.verification_agent import VerificationAgent
from app.api.dependencies import get_workflow
from app.core.config import get_settings
from app.core.db import get_engine
from app.main import create_app
from app.services import retrieval_service as rs
from app.services import user_service as us
from app.workflows.career_workflow import CareerWorkflow


SYNTHETIC_EMAIL = "synthetic.candidate@example.invalid"
SYNTHETIC_PHONE = "0812-5555-0199"
SYNTHETIC_ADDRESS = "Jl. Contoh Sintetis No. 12"
CV_TEXT = (
    "Name: Synthetic Candidate\n"
    f"Email: {SYNTHETIC_EMAIL}\n"
    f"Phone: {SYNTHETIC_PHONE}\n"
    f"Address: {SYNTHETIC_ADDRESS}\n"
    "Profile: An IT graduate with a synthetic project portfolio.\n"
)
UNMATCHED_CLAIM = "Synthetic Unmapped Research Claim"


def _dump(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(value)
    return value


def _safe_profile(profile):
    return {
        "skills": [
            {
                "user_skill_id": item.user_skill_id,
                "claimed_skill": item.claimed_skill,
                "skill_id": item.skill_id,
                "normalized_skill": item.normalized_skill,
                "proficiency": item.proficiency,
                "evidence_status": item.evidence_status,
                "evidence": [_dump(evidence) for evidence in item.evidence],
            }
            for item in profile.skills
        ],
        "education": [_dump(item) for item in profile.education],
        "experience": [_dump(item) for item in profile.experience],
        "projects": [_dump(item) for item in profile.projects],
        "certifications": [_dump(item) for item in profile.certifications],
    }


def _source_ids(context):
    return sorted({
        mapping.provenance.provenance_id
        for mappings in context.source_mappings.values()
        for mapping in mappings
        if mapping.provenance is not None
    })


def _independent_fit_score(required, user_skills, weights):
    """Recompute Step 8's documented arithmetic without its calculator."""
    total_weight = 0.0
    total_contribution = 0.0
    for requirement in required:
        base = (
            weights["core_weight"]
            if requirement.evidence_class.upper() == "CORE"
            else weights["supporting_weight"]
        )
        weight = base * weights.get("confidence_multiplier", {}).get(
            requirement.confidence, 1.0
        )
        total_weight += weight
        matches = [item for item in user_skills if item.skill_id == requirement.skill.skill_id]
        linked = [item for item in matches if item.evidence_status == "linked"]
        match = linked[0] if linked else (matches[0] if matches else None)
        if match is None:
            continue
        base_contribution = (
            weight if match.evidence_status == "linked"
            else weight * weights["claim_only_multiplier"]
        )
        has_proficiency = bool(match.proficiency) and match.proficiency.strip().lower() not in (
            "", "unspecified", "none"
        )
        contribution = (
            min(base_contribution * (1 + weights["proficiency_modifier"]), weight)
            if has_proficiency else base_contribution
        )
        total_contribution += contribution
    return total_contribution / total_weight if total_weight else 0.0


class RecordingFakeLLM:
    model_name = "FakeLLM"

    def __init__(self, skill_one, skill_two, skill_one_id, skill_two_id):
        self.skill_one = skill_one
        self.skill_two = skill_two
        self.skill_one_id = skill_one_id
        self.skill_two_id = skill_two_id
        self.calls = []

    def complete_json(self, system, user, max_tokens=2000):
        category = "unknown"
        if "information-extraction component" in system:
            category = "profile_extraction"
            result = {
                "skills": [
                    {"claimed_skill": self.skill_one, "proficiency": "intermediate",
                     "candidate_skill_id": self.skill_one_id},
                    {"claimed_skill": self.skill_two, "proficiency": None,
                     "candidate_skill_id": self.skill_two_id},
                    {"claimed_skill": UNMATCHED_CLAIM, "proficiency": None,
                     "candidate_skill_id": None},
                ],
                "evidence": [{
                    "claimed_skill": self.skill_one, "evidence_type": "project",
                    "description": "Synthetic project evidence", "url": None,
                }],
                "education": [{
                    "institution": "Synthetic University", "degree": "Bachelor",
                    "field_of_study": "Information Technology", "start_date": None,
                    "end_date": None, "description": "Synthetic education",
                }],
                "experience": [],
                "projects": [{
                    "title": "Synthetic Project", "description": "Synthetic project",
                    "url": None, "role": "Developer",
                }],
                "certifications": [],
            }
        elif "semantic grounding checker" in system:
            category, result = "verification_semantic_review", {"unsupported_claims": []}
        elif "Your ONLY job" in system:
            category, result = "career_reasoning", {
                "reasoning": "The deterministic fit reflects the supplied canonical skill information."
            }
        elif "narrative layer of a skill-gap report" in system:
            category, result = "skill_gap_narrative", {}
        elif "short overview of a learning-focus list" in system:
            category, result = "roadmap_summary", {
                "summary": "The learning focus follows the supplied skill-gap result."
            }
        else:
            raise AssertionError("Unexpected LLM request in diagnostic run.")
        leaked = any(value in system + user for value in (
            SYNTHETIC_EMAIL, SYNTHETIC_PHONE, SYNTHETIC_ADDRESS,
        ))
        self.calls.append({
            "stage": category,
            "model": self.model_name,
            "prompt_character_count": len(system) + len(user),
            "synthetic_pii_leak": leaked,
        })
        if leaked:
            raise AssertionError("Synthetic PII reached a FakeLLM prompt.")
        return copy.deepcopy(result)


class RecordingProfileAgent(ProfileAgent):
    def __init__(self, llm, trace):
        super().__init__(llm)
        self.trace = trace

    def run(self, user_id, raw_profile_text):
        event = {
            "sequence": len(self.trace["executions"]) + 1,
            "node": "profile_analysis",
            "attempt": 1,
            "input": {
                "redacted_profile_text": raw_profile_text,
                "text_character_count": len(raw_profile_text),
                "detected_redaction_markers": sorted({
                    marker for marker in (
                        "[REDACTED_NAME]", "[REDACTED_EMAIL]",
                        "[REDACTED_PHONE]", "[REDACTED_ADDRESS]",
                    ) if marker in raw_profile_text
                }),
            },
        }
        result = super().run(user_id, raw_profile_text)
        profile = us.get_user_full_profile(user_id)
        event["output"] = {
            "agent_result": {
                "extracted": result.extracted,
                "normalizations": [_dump(item) for item in result.normalizations],
                "skills_persisted": result.skills_persisted,
                "evidence_persisted": result.evidence_persisted,
            },
            "persisted_profile_readback": _safe_profile(profile),
        }
        self.trace["executions"].append(event)
        return result


class RecordingCareerAgent(CareerRecommendationAgent):
    def __init__(self, llm, trace):
        super().__init__(llm_client=llm)
        self.trace = trace

    def run(self, user_id):
        profile = us.get_user_full_profile(user_id)
        candidates = []
        for career in rs.get_all_careers():
            skills = rs.get_career_skills(career.career_id)
            context = rs.get_occupational_context(career.career_id)
            candidates.append({
                "career_id": career.career_id,
                "canonical_name": career.canonical_name,
                "source_provenance_ids": _source_ids(context),
                "required_skills": [{
                    "relationship_id": item.relationship_id,
                    "skill_id": item.skill.skill_id,
                    "canonical_name": item.skill.canonical_name,
                    "evidence_class": item.evidence_class,
                    "confidence": item.confidence,
                    "mapping_method": item.mapping_method,
                    "evidence_source_text": item.evidence_source_text,
                } for item in skills],
            })
        result = super().run(user_id)
        self.trace["executions"].append({
            "sequence": len(self.trace["executions"]) + 1,
            "node": "career_recommendation",
            "attempt": 1,
            "input": {
                "database_profile_read": _safe_profile(profile),
                "candidate_careers_from_knowledge_base": candidates,
            },
            "output": [_dump(item) for item in result],
        })
        return result


class RecordingSkillGapAgent(SkillGapAgent):
    def __init__(self, llm, trace):
        super().__init__(llm_client=llm)
        self.trace = trace

    def run(self, user_id, career_id):
        profile = us.get_user_full_profile(user_id)
        career = rs.get_career(career_id)
        required = rs.get_career_skills(career_id)
        result = super().run(user_id, career_id)
        self.trace["executions"].append({
            "sequence": len(self.trace["executions"]) + 1,
            "node": "skill_gap_analysis",
            "attempt": 1,
            "input": {
                "database_profile_read": _safe_profile(profile),
                "selected_career": _dump(career),
                "required_skills_from_knowledge_base": [_dump(item) for item in required],
            },
            "output": _dump(result),
        })
        return result


class RecordingRoadmapAgent(LearningRoadmapAgent):
    def __init__(self, llm, trace):
        super().__init__(llm_client=llm)
        self.trace = trace

    def run(self, result):
        gap = result.skill_gap if hasattr(result, "skill_gap") else result
        context = rs.get_occupational_context(gap.career_id)
        output = super().run(result)
        self.trace["executions"].append({
            "sequence": len(self.trace["executions"]) + 1,
            "node": "learning_roadmap",
            "attempt": 1,
            "input": {
                "step_9_skill_gap": _dump(gap),
                "occupational_context_career_id": context.career.career_id,
                "career_skill_relationship_ids": [
                    item.relationship_id for item in context.career_skills
                ],
                "source_provenance_ids": _source_ids(context),
            },
            "output": _dump(output),
        })
        return output


class RecordingVerificationAgent(VerificationAgent):
    def __init__(self, llm, trace):
        super().__init__(llm_client=llm)
        self.trace = trace

    def run(self, recommendations, skill_gap, roadmap):
        result = super().run(recommendations, skill_gap, roadmap)
        self.trace["executions"].append({
            "sequence": len(self.trace["executions"]) + 1,
            "node": "verification",
            "attempt": 1,
            "input": {
                "recommendations": [_dump(item) for item in recommendations],
                "skill_gap": _dump(skill_gap),
                "roadmap": _dump(roadmap),
            },
            "output": _dump(result),
        })
        return result


class RecordingWorkflow(CareerWorkflow):
    def __init__(self, *, trace, **kwargs):
        self.trace = trace
        super().__init__(**kwargs)

    def _verification_decision(self, state):
        update = super()._verification_decision(state)
        self.trace.setdefault("routing", []).append({
            "node": "verification_decision",
            "revision_count_before": state["revision_count"],
            "verification_status": state["verification"].status,
            "decision": update,
        })
        return update

    def _after_decision(self, state):
        destination = super()._after_decision(state)
        self.trace.setdefault("routing", []).append({
            "node": "conditional_edge_after_verification_decision",
            "destination": destination,
            "revision_count": state["revision_count"],
        })
        return destination


class CaptureLogs(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.buffer = io.StringIO()

    def emit(self, record):
        self.buffer.write(self.format(record) + "\n")


def run():
    os.environ["CAREER_API_ACKNOWLEDGE_NO_AUTH"] = "true"
    os.environ["CAREER_API_ALLOW_REMOTE_CLIENTS"] = "true"
    if hasattr(get_settings, "cache_clear"):
        get_settings.cache_clear()

    engine = get_engine()
    if (engine.url.host or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Diagnostic runner requires a loopback PostgreSQL database.")
    with engine.connect() as connection:
        database_name = connection.execute(text("SELECT current_database()")).scalar_one()
        career_count = connection.execute(text("SELECT count(*) FROM careers")).scalar_one()
    if database_name != "career_intelligence" or career_count != 10:
        raise RuntimeError("Diagnostic runner requires the local canonical Knowledge Base.")

    careers = rs.get_all_careers()
    selected = next(
        ((career, skills) for career in careers
         if len(skills := rs.get_career_skills(career.career_id)) >= 2),
        None,
    )
    if selected is None:
        raise RuntimeError("Knowledge Base has no career with two required skills.")
    career, required = selected
    skill_one, skill_two = required[:2]
    trace = {"executions": [], "routing": []}
    llm = RecordingFakeLLM(
        skill_one.skill.canonical_name, skill_two.skill.canonical_name,
        skill_one.skill.skill_id, skill_two.skill.skill_id,
    )
    workflow = RecordingWorkflow(
        trace=trace,
        llm_client=llm,
        max_revisions=2,
        profile_agent=RecordingProfileAgent(llm, trace),
        career_recommendation_agent=RecordingCareerAgent(llm, trace),
        skill_gap_agent=RecordingSkillGapAgent(llm, trace),
        learning_roadmap_agent=RecordingRoadmapAgent(llm, trace),
        verification_agent=RecordingVerificationAgent(llm, trace),
    )
    app = create_app()
    app.dependency_overrides[get_workflow] = lambda: workflow
    synthetic_user_id = None
    captured = CaptureLogs()
    logger = logging.getLogger()
    logger.addHandler(captured)
    logger.setLevel(logging.DEBUG)

    try:
        with TestClient(app) as client:
            created = client.post("/analysis/users", json={
                "email": f"manual-validation-{uuid.uuid4().hex}@example.invalid",
                "full_name": "Synthetic Manual Validation User",
            })
            if created.status_code != 201:
                raise RuntimeError(f"Synthetic user creation failed ({created.status_code}).")
            synthetic_user_id = created.json()["user_id"]
            response = client.post(
                "/analysis/cv",
                data={
                    "user_id": str(synthetic_user_id),
                    "target_career_id": career.career_id,
                },
                files={"file": ("synthetic.txt", CV_TEXT.encode("utf-8"), "text/plain")},
            )
            if response.status_code != 200:
                raise RuntimeError(f"Synthetic CV workflow failed ({response.status_code}).")
            api_output = response.json()
    finally:
        logger.removeHandler(captured)
        if synthetic_user_id is not None:
            with engine.begin() as connection:
                deleted = connection.execute(
                    text("DELETE FROM users WHERE user_id = :user_id"),
                    {"user_id": synthetic_user_id},
                )
            if deleted.rowcount != 1:
                raise RuntimeError("Could not safely remove the exact synthetic user.")

    log_text = captured.buffer.getvalue()
    raw_markers = (SYNTHETIC_EMAIL, SYNTHETIC_PHONE, SYNTHETIC_ADDRESS)
    if any(marker in log_text for marker in raw_markers):
        raise RuntimeError("Synthetic PII appeared in captured application logs.")
    if any(call["synthetic_pii_leak"] for call in llm.calls):
        raise RuntimeError("Synthetic PII appeared in an LLM prompt.")
    if any(marker in json.dumps(api_output) for marker in raw_markers):
        raise RuntimeError("Synthetic PII appeared in the API response.")

    recommendations = api_output["recommendations"]
    career_ids = {item.career_id for item in careers}
    recommendation_ids = {item["career_id"] for item in recommendations}
    score_checks = []
    user_skill_rows = us.get_user_full_profile(synthetic_user_id)
    if user_skill_rows is not None:
        raise RuntimeError("Synthetic profile was not removed during cleanup.")
    # The actual persisted snapshot is already captured before cleanup.
    stored_skills = trace["executions"][0]["output"]["persisted_profile_readback"]["skills"]
    stored_by_id = {item["skill_id"]: item for item in stored_skills if item["skill_id"]}
    from types import SimpleNamespace
    score_user_skills = [
        SimpleNamespace(
            skill_id=item["skill_id"],
            evidence_status=item["evidence_status"],
            proficiency=item["proficiency"],
        )
        for item in stored_skills
    ]
    candidates = trace["executions"][1]["input"]["candidate_careers_from_knowledge_base"]
    for recommendation in recommendations:
        candidate = next(
            item for item in candidates if item["career_id"] == recommendation["career_id"]
        )
        required_inputs = [
            SimpleNamespace(
                skill=SimpleNamespace(skill_id=item["skill_id"]),
                evidence_class=item["evidence_class"],
                confidence=item["confidence"],
            )
            for item in candidate["required_skills"]
        ]
        expected_score = _independent_fit_score(
            required_inputs, score_user_skills,
            recommendation["score_breakdown"]["weights_used"],
        )
        score_checks.append(
            abs(round(expected_score, 4) - recommendation["fit_score"]) < 0.00001
        )
    gap = api_output["skill_gap"]["skill_gap"]
    required_ids = {
        required_item["skill_id"]
        for career_record in trace["executions"][1]["input"]["candidate_careers_from_knowledge_base"]
        if career_record["career_id"] == career.career_id
        for required_item in career_record["required_skills"]
    }
    linked_ids = {
        item["skill_id"] for item in stored_skills
        if item["skill_id"] and item["evidence_status"] == "linked"
    }
    claimed_only_ids = {
        item["skill_id"] for item in stored_skills
        if item["skill_id"] and item["evidence_status"] != "linked"
    }
    expected_categories = {
        "matched_evidenced": required_ids & linked_ids,
        "matched_claimed_only": required_ids & claimed_only_ids,
        "missing": required_ids - linked_ids - claimed_only_ids,
        "unmatched_user_claims": {
            item["user_skill_id"] for item in stored_skills if item["skill_id"] is None
        },
    }
    actual_categories = {
        "matched_evidenced": {item["skill_id"] for item in gap["matched_evidenced"]},
        "matched_claimed_only": {item["skill_id"] for item in gap["matched_claimed_only"]},
        "missing": {item["skill_id"] for item in gap["missing"]},
        "unmatched_user_claims": {
            item["user_skill_id"] for item in gap["unmatched_user_claims"]
        },
    }
    extracted_skills = trace["executions"][0]["output"]["agent_result"]["extracted"]["skills"]
    expected_roadmap_ids = {
        item["skill_id"]
        for category in ("matched_claimed_only", "missing")
        for item in gap[category]
    }
    roadmap_ids = {item["skill_id"] for item in api_output["roadmap"]["items"]}
    verification = api_output["verification"]
    checks = {
        "all_10_canonical_careers_recommended": recommendation_ids == career_ids,
        "career_fit_independently_recomputed": all(score_checks),
        "canonical_skill_ids_persisted": (
            skill_one.skill.skill_id in stored_by_id
            and skill_two.skill.skill_id in stored_by_id
        ),
        "persisted_claims_match_extraction": all(
            any(
                row["claimed_skill"] == item["claimed_skill"]
                and row["skill_id"] == item["candidate_skill_id"]
                for row in stored_skills
            )
            for item in extracted_skills
        ),
        "step_9_categories_match_independent_reference": actual_categories == expected_categories,
        "all_four_step_9_categories_present": all(
            category in gap for category in (
                "matched_evidenced", "matched_claimed_only", "missing", "unmatched_user_claims"
            )
        ),
        "roadmap_covers_claimed_only_and_missing": expected_roadmap_ids == roadmap_ids,
        "verification_reports_pass": (
            verification["status"] == "PASS"
            and all(item["status"] == "PASS" for item in verification["checks"])
        ),
        "workflow_finished_verified": api_output["final_status"] == "VERIFIED",
        "profile_input_redacted": bool(
            trace["executions"][0]["input"]["detected_redaction_markers"]
        ),
        "synthetic_pii_absent_from_prompts_logs_api": (
            not any(call["synthetic_pii_leak"] for call in llm.calls)
            and not any(marker in log_text for marker in raw_markers)
            and not any(marker in json.dumps(api_output) for marker in raw_markers)
        ),
    }

    for event in trace["executions"]:
        if event["node"] == "career_recommendation":
            # Step 8 does not expose the internal per-requirement arithmetic,
            # so the manual reference above independently recomputes its scores.
            event["unavailable"] = [
                "Internal CareerFitResult per-requirement records are not returned by the agent."
            ]
        if event["node"] == "skill_gap_analysis":
            event["database_profile_source"] = "user_service.get_user_full_profile"
        if event["node"] == "learning_roadmap":
            event["unavailable"] = ["No standalone learning-resource records are used by Step 11."]
    trace["llm_calls"] = llm.calls
    trace["cross_stage_checks"] = {
        key: {"status": "PASS" if passed else "FAIL"}
        for key, passed in checks.items()
    }
    trace["final_api_output"] = api_output
    trace["errors"] = []
    trace["log_scan"] = {
        "captured_log_character_count": len(log_text),
        "synthetic_pii_found": False,
    }
    trace["cleanup"] = {"synthetic_user_deleted_by_exact_id": True}
    trace["run"] = {
        "run_id": uuid.uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "fake_llm_database_backed",
        "database_name": database_name,
        "canonical_career_count": career_count,
        "target_career_id": career.career_id,
        "input_file": {
            "filename": "synthetic.txt",
            "format": "txt",
            "size_bytes": len(CV_TEXT.encode("utf-8")),
            "sha256": hashlib.sha256(CV_TEXT.encode("utf-8")).hexdigest(),
        },
        "raw_cv_text_included": False,
        "complete_prompts_included": False,
        "credentials_included": False,
    }
    if not all(checks.values()):
        failed = [key for key, value in checks.items() if not value]
        raise RuntimeError(f"Manual validation checks failed: {', '.join(failed)}")

    output_dir = Path(__file__).resolve().parents[1] / "artifacts" / "manual_validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{trace['run']['run_id']}.json"
    encoded = json.dumps(trace, indent=2, ensure_ascii=False)
    if any(marker in encoded for marker in raw_markers):
        raise RuntimeError("Synthetic PII was found in the diagnostic artifact.")
    output_file.write_text(encoded, encoding="utf-8")
    print(json.dumps({
        "artifact": str(output_file),
        "status": "PASS",
        "checks": len(checks),
        "llm_call_count": len(llm.calls),
        "synthetic_user_cleaned": True,
    }, indent=2))


if __name__ == "__main__":
    run()
