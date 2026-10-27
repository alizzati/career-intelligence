"""Offline end-to-end inspection test.

REAL: CareerWorkflow, Profile/CareerRecommendation/SkillGap/LearningRoadmap/Verification agents,
Recorder, AgentProxy, RecordingLLMClient, build_artifact, _write_artifact.
REPLACED: retrieval_service / user_service functions (in-memory KB and user store) and the LLM
(scripted test double). No PostgreSQL, no network, no live provider.
This shows the artifact path works on a real workflow run; it says nothing about real-model quality."""
import copy
import json
from datetime import datetime

import pytest

from app.agents import career_recommendation_agent as career_agent_module
from app.agents import verification_agent as verification_agent_module
from app.agents.career_recommendation_agent import CareerRecommendationAgent
from app.agents.learning_roadmap_agent import LearningRoadmapAgent
from app.agents.profile_agent import ProfileAgent
from app.agents.skill_gap_agent import SkillGapAgent
from app.agents.verification_agent import VerificationAgent
from app.inspection import artifact as art
from app.inspection.recorder import AgentProxy, Recorder, RecordingLLMClient, to_jsonable
from app.schemas.retrieval import CareerOut, CareerSkillOut, OccupationalContextOut, SkillOut
from app.schemas.user import (
    CertificationOut, EducationOut, ExperienceOut, ProjectOut, UserFullProfileOut, UserOut,
    UserSkillEvidenceOut, UserSkillOut,
)
from app.schemas.verification import VerificationCheck, VerificationResult
from app.services import retrieval_service as rs
from app.services import skill_gap_service
from app.services import user_service as us
from app.services.date_normalization import normalize_date_value
from app.services.pii_redaction_service import redact_pii
from app.workflows.career_workflow import CareerWorkflow
from scripts.manual_validation import _write_artifact

CAREERS = [CareerOut(career_id="C1", canonical_name="Backend Engineer", domain="Engineering"),
           CareerOut(career_id="C2", canonical_name="Data Analyst", domain="Data")]
SKILLS = {sid: SkillOut(skill_id=sid, canonical_name=name, skill_group_id="SG1", status="active")
          for sid, name in (("S001", "SQL"), ("S002", "Networking"),
                            ("S003", "Database Management"), ("S004", "Data Analysis"))}


def req(career_id, sid, evidence_class, confidence, basis):
    return CareerSkillOut(relationship_id=f"R_{career_id}_{sid}", skill=SKILLS[sid],
                          evidence_class=evidence_class, confidence=confidence,
                          mapping_method="test", evidence_source_text=basis)


REQUIRED = {
    "C1": [req("C1", "S001", "CORE", "high", "SQL basis."),
           req("C1", "S002", "SUPPORTING", "medium", "Network basis."),
           req("C1", "S003", "CORE", "high", "Database basis.")],
    "C2": [req("C2", "S004", "CORE", "high", "Analysis basis."),
           req("C2", "S001", "SUPPORTING", "medium", "SQL basis for data work.")],
}

RAW_CV = ("Name: Synthetic Person\nEmail: int.person@example.invalid\nPhone: 0812-5555-0123\n"
          "Address: Jl. Sintetis No. 5\nBackend developer with SQL project experience.\n")
EXTRACTION = {
    "skills": [{"claimed_skill": "SQL", "proficiency": "intermediate", "candidate_skill_id": "S001"},
               {"claimed_skill": "Networking", "proficiency": None, "candidate_skill_id": "S002"},
               {"claimed_skill": "Totally Unmapped Claim", "proficiency": None, "candidate_skill_id": None}],
    "evidence": [{"claimed_skill": "SQL", "evidence_type": "project",
                  "description": "Synthetic project evidence", "url": None}],
    "education": [{"institution": "Synthetic University", "degree": "BSc", "field_of_study": "IT",
                   "start_date": "Aug 2020", "end_date": "Jul 2024", "description": "Synthetic"}],
    "experience": [], "projects": [], "certifications": [],
}
SENTINELS = ("int.person@example.invalid", "0812-5555-0123", "Synthetic Person", "Jl. Sintetis No. 5",
             "Totally Unmapped Claim", "Synthetic University", "PRIVATE_PROVIDER_FAILURE_SENTINEL")
NODES = ["profile_analysis", "career_recommendation", "skill_gap_analysis", "learning_roadmap",
         "verification", "verification_decision", "final_result"]


class MemoryUsers:
    """Minimal in-memory stand-in for user_service (same signatures and return types)."""

    def __init__(self):
        self.skills, self.education, self._n = [], [], 0

    def _id(self):
        self._n += 1
        return self._n

    def add_education(self, user_id, institution, degree=None, field_of_study=None,
                      start_date=None, end_date=None, description=None):
        row = EducationOut(
            education_id=self._id(), institution=institution, degree=degree, field_of_study=field_of_study,
            start_date=normalize_date_value(start_date, field_name="start_date"),
            end_date=normalize_date_value(end_date, field_name="end_date", is_end_date=True),
            description=description)
        self.education.append(row)
        return row

    def add_experience(self, user_id, company, role_title, employment_type=None, start_date=None,
                       end_date=None, description=None):
        return ExperienceOut(experience_id=self._id(), company=company, role_title=role_title)

    def add_project(self, user_id, title, description=None, url=None, role=None):
        return ProjectOut(project_id=self._id(), title=title)

    def add_certification(self, user_id, name, issuer=None, issue_date=None, expiry_date=None,
                          credential_url=None):
        return CertificationOut(certification_id=self._id(), name=name)

    def add_user_skill(self, user_id, claimed_skill, skill_id=None, normalized_skill=None, proficiency=None):
        existing = next((s for s in self.skills if s.claimed_skill == claimed_skill), None)
        if existing:                                    # insert-only, like Step 14.4
            return existing.model_copy(deep=True)
        row = UserSkillOut(user_skill_id=self._id(), claimed_skill=claimed_skill, skill_id=skill_id,
                           normalized_skill=normalized_skill, proficiency=proficiency,
                           evidence_status="none", confidence="unknown", evidence=[])
        self.skills.append(row)
        return row.model_copy(deep=True)

    def add_skill_evidence(self, user_skill_id, evidence_type, source_table=None, source_id=None,
                           description=None, url=None):
        target = next(s for s in self.skills if s.user_skill_id == user_skill_id)
        evidence = UserSkillEvidenceOut(evidence_id=self._id(), evidence_type=evidence_type,
                                        description=description, url=url)
        target.evidence.append(evidence)
        target.evidence_status = "linked"
        return evidence

    def get_user_full_profile(self, user_id):
        return UserFullProfileOut(
            user=UserOut(user_id=user_id, email="memory@example.invalid", full_name="Memory User",
                         created_at=datetime(2026, 1, 1)),
            education=[e.model_copy(deep=True) for e in self.education],
            skills=[s.model_copy(deep=True) for s in self.skills])


def context(career_id):
    career = next(c for c in CAREERS if c.career_id == career_id)
    return OccupationalContextOut(career=career, occupations=[], career_skills=REQUIRED[career_id],
                                  competencies=[], tasks={}, technologies={}, source_mappings={})


@pytest.fixture
def memory(monkeypatch):
    store = MemoryUsers()
    monkeypatch.setattr(rs, "get_all_skills", lambda: list(SKILLS.values()))
    monkeypatch.setattr(rs, "get_all_careers", lambda: list(CAREERS))
    monkeypatch.setattr(rs, "get_career", lambda cid: next((c for c in CAREERS if c.career_id == cid), None))
    monkeypatch.setattr(rs, "get_career_skills", lambda cid: list(REQUIRED[cid]))
    monkeypatch.setattr(rs, "get_occupational_context", lambda cid: context(cid) if cid in REQUIRED else None)
    monkeypatch.setattr(rs, "get_skill_evidence", lambda sid: [])
    for name in ("add_education", "add_experience", "add_project", "add_certification",
                 "add_user_skill", "add_skill_evidence", "get_user_full_profile"):
        monkeypatch.setattr(us, name, getattr(store, name))
    return store


class FakeScriptedLLM:
    model_name = "FakeScriptedLLM"

    def __init__(self, fail_extraction=False):
        self.fail_extraction, self.prompts = fail_extraction, []

    def complete_json(self, system, user, max_tokens=2000):
        self.prompts.append(user)
        if "information-extraction component" in system:
            if self.fail_extraction:
                raise RuntimeError("PRIVATE_PROVIDER_FAILURE_SENTINEL")
            return copy.deepcopy(EXTRACTION)
        if "semantic grounding checker" in system:
            return {"unsupported_claims": []}
        if "Your ONLY job" in system:
            return {"reasoning": "The deterministic fit reflects the supplied canonical skill information."}
        if "narrative layer of a skill-gap report" in system:
            return {}                                   # unusable on purpose -> deterministic fallback
        if "short overview of a learning-focus list" in system:
            return {"summary": "The learning focus follows the supplied skill-gap result."}
        raise AssertionError("unexpected LLM request")


class FailOnceVerifier:
    """First call returns a synthetic roadmap FAIL; later calls delegate to the REAL verifier."""

    def __init__(self, real):
        self.real, self.calls = real, 0

    def run(self, recommendations, skill_gap, roadmap):
        self.calls += 1
        if self.calls == 1:
            return VerificationResult(
                status="FAIL", required_revision=["synthetic revision"],
                checks=[VerificationCheck(check="roadmap.gap_coverage", status="FAIL", reason="synthetic")])
        return self.real.run(recommendations, skill_gap, roadmap)


def run_inspected(memory, llm, *, wrap_verifier=None, precheck_profile_read=False):
    rec = Recorder()
    client = RecordingLLMClient(llm, rec)
    verifier = VerificationAgent(llm_client=client)
    workflow = CareerWorkflow(
        llm_client=client, max_revisions=2,
        profile_agent=AgentProxy(rec, "profile", ProfileAgent(client)),
        career_recommendation_agent=AgentProxy(rec, "career_recommendation",
                                               CareerRecommendationAgent(llm_client=client)),
        skill_gap_agent=AgentProxy(rec, "skill_gap", SkillGapAgent(llm_client=client)),
        learning_roadmap_agent=AgentProxy(rec, "roadmap", LearningRoadmapAgent(llm_client=client)),
        verification_agent=AgentProxy(rec, "verification", wrap_verifier(verifier) if wrap_verifier else verifier))
    with rec.instrument(rs=rs, us=us, fit_modules=(career_agent_module, skill_gap_service,
                                                   verification_agent_module)):
        if precheck_profile_read:                       # API existence check before the workflow
            assert us.get_user_full_profile(1) is not None
        state = workflow.run(user_id=1, target_career_id="C1", raw_profile_text=RAW_CV,
                             observer=rec.observer)
    artifact = art.build_artifact(rec, {
        "run_id": "inmem", "started_at": "t0", "mode": "in_memory_integration",
        "mode_label": "Real agents, in-memory KB/users, scripted LLM test double",
        "input_source": "synthetic_text", "user": 1, "target_requested": "C1", "final_state": state,
        "max_revisions": 2, "llm_client": client,
        "llm": {"client_type": type(llm).__name__, "test_double": True},
        "scoring_weights": workflow.career_recommendation_agent._target.weights,
        "database": {"name": "career_intelligence_e2e_test", "host": "localhost", "port": 5433,
                     "server_current_database": "career_intelligence_e2e_test"},
        "post_run_profile": memory.get_user_full_profile(1)})
    return artifact, state, rec


def results(artifact):
    return {c["id"]: c["result"] for c in artifact["cross_stage_checks"]["checks"]}


def test_real_workflow_on_in_memory_kb_populates_artifact_and_restores_instrumentation(memory, tmp_path):
    llm = FakeScriptedLLM()
    artifact, state, rec = run_inspected(memory, llm)

    assert state["final_status"] == "VERIFIED" and state["revision_count"] == 0
    meta = artifact["run_metadata"]
    assert meta["verified"] is True and meta["llm"]["calls_total"] == 6
    assert meta["llm_runtime"]["provider"] == "test_double"
    assert meta["llm_runtime"]["generation_settings"]["value"].startswith("unavailable")
    assert meta["kb_version"].startswith("unavailable") and meta["kb_unchanged"] == "unavailable"
    assert {c["prompt_id"]: c["max_tokens"] for c in meta["per_call_token_limits"]} == {
        "profile_extraction": 8192, "career_reasoning": 300, "skill_gap_narrative": 1500,
        "roadmap_summary": 500, "verification_semantic": 1200}
    assert artifact["workflow_execution"]["nodes_in_order"] == NODES
    for section in ("profile_agent", "career_recommendation_agent", "skill_gap_agent",
                    "roadmap_agent", "verification_agent"):
        assert artifact[section]["executed"] is True, section

    checks = results(artifact)
    assert not {k: v for k, v in checks.items() if v in ("FAIL", "ERROR")}, checks
    for cid in ("X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9", "X10"):
        assert checks[cid] == "PASS", (cid, checks)

    # hand-computed (default weights): C1 = 1.2125/2.425 = 0.5 ; C2 = 0.425/1.425 = 0.2982
    ranked = artifact["career_recommendation_agent"]["executions"][0]["output_agent"]["ranked"]
    assert [r["career_id"] for r in ranked] == ["C1", "C2"]
    assert ranked[0]["fit_score"] == pytest.approx(0.5, abs=5e-5)
    assert ranked[1]["fit_score"] == pytest.approx(0.425 / 1.425, abs=5e-5)

    dumped = json.dumps(artifact)
    for sentinel in SENTINELS:
        assert sentinel not in dumped, sentinel
    for prompt in llm.prompts:
        assert "int.person@example.invalid" not in prompt and "0812-5555-0123" not in prompt

    path = _write_artifact(artifact, tmp_path)
    assert json.loads(path.read_text(encoding="utf-8")) == artifact
    # instrumentation restored: the module attributes are the store's own bound methods again
    assert us.get_user_full_profile == memory.get_user_full_profile
    assert us.add_user_skill == memory.add_user_skill


def test_x2_regression_excludes_precheck_before_profile_persistence(memory):
    """Real Recorder: an API-style read before the Profile Agent must not be compared by X2."""
    artifact, state, rec = run_inspected(memory, FakeScriptedLLM(), precheck_profile_read=True)

    assert state["final_status"] == "VERIFIED"
    assert artifact["run_metadata"]["llm"]["calls_total"] == 6
    x2 = next(c for c in artifact["cross_stage_checks"]["checks"] if c["id"] == "X2")
    assert x2["result"] == "PASS"

    cutoff = x2["compared"]["persistence_cutoff_seq"]
    profile_run = next(r for r in rec.agent_runs if r["agent"] == "profile")
    write_seqs = [rec.io[i]["seq"] for i in profile_run["io_idx"]
                  if rec.io[i]["category"] == "db_write"]
    assert write_seqs and cutoff == max(write_seqs)
    assert x2["compared"]["ignored_pre_persistence_reads"] == [
        {"seq": 1, "stage": "workflow"}]
    assert x2["compared"]["reads_by_stage"] == {
        "career_recommendation": 1, "skill_gap": 1, "verification": 1, "post_run": 1}

    reads = [(e["seq"], e["stage"]) for e in rec.raw_io
             if e["function"] == "get_user_full_profile" and not e["nested"]]
    assert reads[0] == (1, "workflow")
    downstream = [seq for seq, stage in reads if stage != "workflow"]
    assert len(downstream) == 3 and all(seq > cutoff for seq in downstream)


def test_revision_path_is_recorded_with_real_agents(memory):
    artifact, state, _ = run_inspected(memory, FakeScriptedLLM(), wrap_verifier=FailOnceVerifier)

    assert state["final_status"] == "VERIFIED" and state["revision_count"] == 1
    transitions = artifact["workflow_execution"]["revision_transitions"]
    # one entry per verification_decision event: the routed revision + the final VERIFIED decision
    assert len(transitions) == 2
    routed = [t for t in transitions if t["revision_target"]]
    assert len(routed) == 1 and routed[0]["revision_target"] == "roadmap"
    assert routed[0]["verification_checks_requiring_revision"] == [
        {"check": "roadmap.gap_coverage", "status": "FAIL"}]
    assert isinstance(routed[0]["changed_output_fields"], list)
    assert transitions[-1]["revision_target"] is None and transitions[-1]["outcome"] == "VERIFIED"
    assert transitions[-1]["verification_checks_requiring_revision"] == []
    assert len(artifact["roadmap_agent"]["executions"]) == 2
    assert len(artifact["verification_agent"]["executions"]) == 2
    checks = results(artifact)
    assert checks["X9"] == "PASS" and checks["X10"] == "PASS"


def test_extraction_failure_is_reported_as_error_without_leaking_exception_text(memory):
    artifact, state, _ = run_inspected(memory, FakeScriptedLLM(fail_extraction=True))

    assert state["final_status"] == "ERROR"
    assert artifact["run_metadata"]["verified"] is False
    execution = artifact["profile_agent"]["executions"][0]
    assert execution["error"]["type"] == "RuntimeError" and "message" not in execution["error"]
    assert execution["output_agent"] is None
    assert artifact["skill_gap_agent"] == {"executed": False,
                                           "reason": "not reached: an earlier stage ended with ERROR"}
    assert artifact["final_output"]["errors"] == [{"stage": "profile_analysis", "error_type": "RuntimeError"}]
    assert "PRIVATE_PROVIDER_FAILURE_SENTINEL" not in json.dumps(artifact)
    assert not {k for k, v in results(artifact).items() if v in ("FAIL", "ERROR")}


def test_digest_with_a_sixteen_digit_run_survives_the_final_scrub():
    digest = "a" + "1234567890123456" + "b" * 47          # 64 hex chars containing an exact 16-digit run
    assert len(digest) == 64
    assert redact_pii(digest).redacted_text != digest      # why the exemption exists
    assert to_jsonable({"sha256": digest}) == {"sha256": digest}