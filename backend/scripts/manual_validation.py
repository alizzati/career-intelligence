"""Manual-validation runner: synthetic CV -> real FastAPI app -> real CareerWorkflow and agents.

ONE inspection path: Recorder + AgentProxy + build_artifact(). Agents are the production classes
(no subclasses doing extra reads), so every recorded KB/DB read was made by the agent itself.
Reference values for the independent checks are read AFTER the run, outside the instrumentation,
from the knowledge base and the persisted profile. The artifact is written even when the run or a
check fails. LLM = FakeLLM test double only; no live provider call is made by this script.

WARNING: this creates and then deletes ONE synthetic user (by exact id) in the configured local
`career_intelligence` database. It is not an isolated database.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.agents import career_recommendation_agent as career_agent_module
from app.agents import verification_agent as verification_agent_module
from app.agents.career_recommendation_agent import CareerRecommendationAgent
from app.agents.learning_roadmap_agent import LearningRoadmapAgent
from app.agents.profile_agent import ProfileAgent
from app.agents.skill_gap_agent import SkillGapAgent
from app.agents.verification_agent import VerificationAgent
from app.api.dependencies import get_workflow
from app.core.db import get_engine
from app.inspection.artifact import build_artifact
from app.inspection.recorder import AgentProxy, Recorder, RecordingLLMClient
from app.main import create_app
from app.services import retrieval_service as rs
from app.services import skill_gap_service
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
RAW_MARKERS = (SYNTHETIC_EMAIL, SYNTHETIC_PHONE, SYNTHETIC_ADDRESS)
KB_TABLES = ("careers", "skills", "career_skills", "occupations")   # constants only (used in SQL text)
FIT_TOLERANCE = 5e-5 + 1e-9   # reported score is round(exact, 4): max distance to the exact value is 5e-5


class RecordingFakeLLM:
    """Test double. Establishes nothing about real-model quality or provider settings."""
    model_name = "FakeLLM"

    def __init__(self, skill_one, skill_two, skill_one_id, skill_two_id):
        self.skill_one, self.skill_two = skill_one, skill_two
        self.skill_one_id, self.skill_two_id = skill_one_id, skill_two_id
        self.calls = []

    def complete_json(self, system, user, max_tokens=2000):
        if "information-extraction component" in system:
            stage, result = "profile_extraction", {
                "skills": [
                    {"claimed_skill": self.skill_one, "proficiency": "intermediate",
                     "candidate_skill_id": self.skill_one_id},
                    {"claimed_skill": self.skill_two, "proficiency": None,
                     "candidate_skill_id": self.skill_two_id},
                    {"claimed_skill": UNMATCHED_CLAIM, "proficiency": None, "candidate_skill_id": None},
                ],
                "evidence": [{"claimed_skill": self.skill_one, "evidence_type": "project",
                              "description": "Synthetic project evidence", "url": None}],
                "education": [{"institution": "Synthetic University", "degree": "Bachelor",
                               "field_of_study": "Information Technology", "start_date": None,
                               "end_date": None, "description": "Synthetic education"}],
                "experience": [],
                "projects": [{"title": "Synthetic Project", "description": "Synthetic project",
                              "url": None, "role": "Developer"}],
                "certifications": [],
            }
        elif "semantic grounding checker" in system:
            stage, result = "verification_semantic", {"unsupported_claims": []}
        elif "Your ONLY job" in system:
            stage, result = "career_reasoning", {
                "reasoning": "The deterministic fit reflects the supplied canonical skill information."}
        elif "narrative layer of a skill-gap report" in system:
            stage, result = "skill_gap_narrative", {}
        elif "short overview of a learning-focus list" in system:
            stage, result = "roadmap_summary", {
                "summary": "The learning focus follows the supplied skill-gap result."}
        else:
            raise AssertionError("Unexpected LLM request in diagnostic run.")
        leaked = any(value in system + user for value in RAW_MARKERS)
        self.calls.append({"stage": stage, "synthetic_pii_leak": leaked})
        if leaked:
            raise AssertionError("Synthetic PII reached a FakeLLM prompt.")
        return copy.deepcopy(result)


class RecordingWorkflow(CareerWorkflow):
    """Real CareerWorkflow; only adds the node-update observer and keeps the final state."""

    def __init__(self, *, trace, recorder=None, **kwargs):
        self.trace = trace
        self.recorder = recorder or Recorder()
        self.final_state = None
        super().__init__(**kwargs)

    def run(self, user_id, target_career_id=None, raw_profile_text=None):
        state = super().run(user_id=user_id, target_career_id=target_career_id,
                            raw_profile_text=raw_profile_text, observer=self.recorder.observer)
        self.final_state = state
        self.trace["workflow_node_events"] = self.recorder.node_events
        return state


class CaptureLogs(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.buffer = io.StringIO()

    def emit(self, record):
        self.buffer.write(self.format(record) + "\n")


def _write_artifact(artifact, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{artifact['run_metadata']['run_id']}.json"
    output_file.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    return output_file


def _kb_counts(engine) -> dict:
    with engine.connect() as connection:
        return {t: connection.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in KB_TABLES}


def _independent_fit_score(required, user_skills, weights):
    """Hand transcription of the documented arithmetic; imports no production scoring helper."""
    total_weight = total_contribution = 0.0
    for requirement in required:
        base = (weights["core_weight"] if requirement.evidence_class.upper() == "CORE"
                else weights["supporting_weight"])
        weight = base * weights.get("confidence_multiplier", {}).get(requirement.confidence, 1.0)
        total_weight += weight
        matches = [u for u in user_skills if u.skill_id == requirement.skill.skill_id]
        linked = [u for u in matches if u.evidence_status == "linked"]
        match = linked[0] if linked else (matches[0] if matches else None)
        if match is None:
            continue
        contribution = weight if match.evidence_status == "linked" else weight * weights["claim_only_multiplier"]
        if bool(match.proficiency) and match.proficiency.strip().lower() not in ("", "unspecified", "none"):
            contribution = min(contribution * (1 + weights["proficiency_modifier"]), weight)
        total_contribution += contribution
    return total_contribution / total_weight if total_weight else 0.0


def _check(check_id, name, passed, detail):
    return {"id": check_id, "name": name, "result": "PASS" if passed else "FAIL", "detail": detail}


def _independent_checks(*, api_output, target_id, profile, extracted_skills, profile_input_text,
                        skill_ids):
    """Reference data = fresh KB reads + persisted profile, taken outside the instrumentation."""
    careers = rs.get_all_careers()
    required = {c.career_id: rs.get_career_skills(c.career_id) for c in careers}
    recs = api_output["recommendations"]
    checks = [_check("H1", "all canonical careers recommended exactly once",
                     sorted(r["career_id"] for r in recs) == sorted(required),
                     {"kb_careers": len(required), "recommended": len(recs)})]

    bad_scores = [r["career_id"] for r in recs
                  if abs(_independent_fit_score(required[r["career_id"]], profile.skills,
                                                r["score_breakdown"]["weights_used"]) - r["fit_score"])
                  > FIT_TOLERANCE]
    checks.append(_check("H2", "fit_score of every career vs independent arithmetic",
                         not bad_scores, {"tolerance": FIT_TOLERANCE, "mismatched_careers": bad_scores}))

    gap = api_output["skill_gap"]["skill_gap"]
    req_ids = {i.skill.skill_id for i in required[target_id]}
    present = {s.skill_id for s in profile.skills if s.skill_id}
    linked = {s.skill_id for s in profile.skills if s.skill_id and s.evidence_status == "linked"}
    expected = {"matched_evidenced": req_ids & linked,
                "matched_claimed_only": (req_ids & present) - linked,
                "missing": req_ids - present,
                "unmatched_user_claims": {s.user_skill_id for s in profile.skills if s.skill_id is None}}
    actual = {k: {i["skill_id"] for i in gap[k]} for k in ("matched_evidenced", "matched_claimed_only", "missing")}
    actual["unmatched_user_claims"] = {i["user_skill_id"] for i in gap["unmatched_user_claims"]}
    checks.append(_check("H3", "skill-gap categories vs KB requirements and persisted profile",
                         actual == expected,
                         {k: {"expected": len(expected[k]), "actual": len(actual[k])} for k in expected}))

    roadmap_ids = {i["skill_id"] for i in api_output["roadmap"]["items"]}
    checks.append(_check("H4", "roadmap covers exactly claimed-only + missing",
                         roadmap_ids == expected["matched_claimed_only"] | expected["missing"],
                         {"roadmap_items": len(roadmap_ids)}))

    by_claim = {s.claimed_skill: s.skill_id for s in profile.skills}
    checks.append(_check("H5", "persisted claims keep the extracted canonical skill ids",
                         all(by_claim.get(x["claimed_skill"], "<absent>") == x.get("candidate_skill_id")
                             for x in extracted_skills)
                         and all(i in {s.skill_id for s in profile.skills} for i in skill_ids),
                         {"extracted_claims": len(extracted_skills)}))

    verification = api_output["verification"]
    checks.append(_check("H6", "workflow VERIFIED and every verification check PASS",
                         api_output["final_status"] == "VERIFIED" and verification["status"] == "PASS"
                         and all(c["status"] == "PASS" for c in verification["checks"]),
                         {"final_status": api_output["final_status"], "checks": len(verification["checks"])}))

    checks.append(_check("H7", "profile text given to the Profile Agent was redacted",
                         "[REDACTED_" in profile_input_text
                         and not any(m in profile_input_text for m in RAW_MARKERS), None))
    return checks


def _git_commit() -> str:
    revision = subprocess.run(["git", "-C", str(BACKEND_ROOT.parent), "rev-parse", "--verify", "HEAD"],
                              capture_output=True, text=True, check=False)
    return revision.stdout.strip() if revision.returncode == 0 else "unavailable"


def run() -> int:
    os.environ["CAREER_API_ACKNOWLEDGE_NO_AUTH"] = "true"
    os.environ["CAREER_API_ALLOW_REMOTE_CLIENTS"] = "true"   # TestClient host is "testclient"

    engine = get_engine()
    if (engine.url.host or "").lower() not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("Diagnostic runner requires a loopback PostgreSQL database.")
    with engine.connect() as connection:
        database_name = connection.execute(text("SELECT current_database()")).scalar_one()
        career_count = connection.execute(text("SELECT count(*) FROM careers")).scalar_one()
    if database_name != "career_intelligence" or career_count != 10:
        raise RuntimeError("Diagnostic runner requires the local canonical Knowledge Base.")
    kb_before = _kb_counts(engine)

    careers = rs.get_all_careers()
    selected = next(((c, s) for c in careers if len(s := rs.get_career_skills(c.career_id)) >= 2), None)
    if selected is None:
        raise RuntimeError("Knowledge Base has no career with two required skills.")
    career, required = selected
    skill_one, skill_two = required[:2]

    recorder = Recorder()
    run_id, started_at = uuid.uuid4().hex, datetime.now(timezone.utc).isoformat()
    llm = RecordingFakeLLM(skill_one.skill.canonical_name, skill_two.skill.canonical_name,
                           skill_one.skill.skill_id, skill_two.skill.skill_id)
    recorded_llm = RecordingLLMClient(llm, recorder)
    workflow = RecordingWorkflow(
        trace={}, recorder=recorder, llm_client=recorded_llm, max_revisions=2,
        profile_agent=AgentProxy(recorder, "profile", ProfileAgent(recorded_llm)),
        career_recommendation_agent=AgentProxy(
            recorder, "career_recommendation", CareerRecommendationAgent(llm_client=recorded_llm)),
        skill_gap_agent=AgentProxy(recorder, "skill_gap", SkillGapAgent(llm_client=recorded_llm)),
        learning_roadmap_agent=AgentProxy(recorder, "roadmap", LearningRoadmapAgent(llm_client=recorded_llm)),
        verification_agent=AgentProxy(recorder, "verification", VerificationAgent(llm_client=recorded_llm)),
    )
    app = create_app()
    app.dependency_overrides[get_workflow] = lambda: workflow

    cv_bytes = CV_TEXT.encode("utf-8")
    synthetic_user_id = post_run_profile = api_output = kb_after = None
    harness_error, independent = None, []
    captured, root_logger = CaptureLogs(), logging.getLogger()
    root_logger.addHandler(captured)
    root_logger.setLevel(logging.DEBUG)

    try:
        with recorder.instrument(rs=rs, us=us,
                                 fit_modules=(career_agent_module, skill_gap_service,
                                              verification_agent_module)):
            with TestClient(app) as client:
                created = client.post("/analysis/users", json={
                    "email": f"manual-validation-{uuid.uuid4().hex}@example.invalid",
                    "full_name": "Synthetic Manual Validation User"})
                if created.status_code != 201:
                    raise RuntimeError(f"Synthetic user creation failed ({created.status_code}).")
                synthetic_user_id = created.json()["user_id"]
                response = client.post(
                    "/analysis/cv",
                    data={"user_id": str(synthetic_user_id), "target_career_id": career.career_id},
                    files={"file": ("synthetic.txt", cv_bytes, "text/plain")})
                if response.status_code != 200:
                    raise RuntimeError(f"Synthetic CV workflow failed ({response.status_code}).")
                api_output = response.json()

        # Outside the instrumentation: these reads are references, not agent behaviour.
        post_run_profile = us.get_user_full_profile(synthetic_user_id)
        kb_after = _kb_counts(engine)
        profile_run = next(r for r in recorder.agent_runs if r["agent"] == "profile")
        independent = _independent_checks(
            api_output=api_output, target_id=career.career_id, profile=post_run_profile,
            extracted_skills=profile_run["raw_output"].extracted["skills"],
            profile_input_text=profile_run["raw_args"][1],
            skill_ids=(skill_one.skill.skill_id, skill_two.skill.skill_id))
    except Exception as exc:   # type only: messages may carry sensitive text
        harness_error = [{"stage": "harness", "error_type": type(exc).__name__}]
    finally:
        root_logger.removeHandler(captured)
        cleanup_ok = None
        if synthetic_user_id is not None:
            try:
                with engine.begin() as connection:
                    deleted = connection.execute(text("DELETE FROM users WHERE user_id = :user_id"),
                                                 {"user_id": synthetic_user_id}).rowcount
                cleanup_ok = deleted == 1
            except Exception:
                cleanup_ok = False
            if not cleanup_ok:
                print(f"WARNING: synthetic user {synthetic_user_id} may still exist; delete it by exact id.")

    log_text = captured.buffer.getvalue()
    leaks = {"llm_prompts": any(c["synthetic_pii_leak"] for c in llm.calls),
             "logs": any(m in log_text for m in RAW_MARKERS),
             "api_response": api_output is not None and any(m in json.dumps(api_output) for m in RAW_MARKERS)}
    independent.append(_check("H8", "synthetic PII absent from LLM prompts, logs and API response",
                              not any(leaks.values()), leaks))
    if synthetic_user_id is not None:
        independent.append(_check("H9", "synthetic user deleted by exact id", bool(cleanup_ok), None))

    final_state = workflow.final_state or {"final_status": "ERROR", "revision_count": 0,
                                           "target_career_id": None, "errors": []}
    try:
        sdk_version = metadata.version("google-genai")
    except metadata.PackageNotFoundError:
        sdk_version = "unavailable (google-genai package metadata not installed)"
    artifact = build_artifact(recorder, {
        "run_id": run_id, "started_at": started_at,
        "mode": "fake_llm_database_backed",
        "mode_label": "Synthetic local manual validation with FakeLLM (test double)",
        "input_source": "synthetic_text", "user": synthetic_user_id,
        "target_requested": career.career_id, "final_state": final_state,
        "max_revisions": workflow.max_revisions,
        "input_document": {"format": "txt", "size_bytes": len(cv_bytes),
                           "sha256": hashlib.sha256(cv_bytes).hexdigest()},
        "llm": {"client_type": type(llm).__name__, "test_double": True},
        "llm_client": recorded_llm,
        "scoring_weights": workflow.career_recommendation_agent._target.weights,
        "versions": {"python": sys.version.split()[0], "google_genai_sdk": sdk_version},
        "kb_counts_before": kb_before, "kb_counts_after": kb_after,
        "git_commit": _git_commit(), "post_run_profile": post_run_profile,
        "harness_error": harness_error, "independent_checks": independent,
    })

    output_file = _write_artifact(artifact, BACKEND_ROOT / "artifacts" / "manual_validation")
    summary = artifact["cross_stage_checks"]["summary"]
    ok = (harness_error is None and all(c["result"] == "PASS" for c in independent)
          and not ({"FAIL", "ERROR"} & set(summary)))
    print(json.dumps({"artifact": str(output_file), "status": "PASS" if ok else "FAIL",
                      "final_status": final_state.get("final_status"),
                      "cross_stage_summary": summary,
                      "independent_checks": {c["id"]: c["result"] for c in independent},
                      "harness_error": harness_error, "llm_call_count": len(llm.calls)}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(run())