"""Offline tests for the diagnostic CV runner.

REAL: FastAPI app + route, CareerWorkflow, all five agents, Recorder instrumentation,
trace builder, CSV/manifest writing.
REPLACED: retrieval_service / user_service (in-memory doubles) and the LLM (scripted
test double). No PostgreSQL, no network, no live provider.

These tests never establish diagnostic validity with a real model; they prove the
runner plumbing, the privacy behaviour, and the failure handling.
"""
from __future__ import annotations

import csv
import copy
import json
import os
import re
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import URL

from app.diagnostics import runner as runner_mod
from app.diagnostics import trace as trace_mod
from app.schemas.retrieval import CareerOut, CareerSkillOut, OccupationalContextOut, SkillOut
from app.schemas.user import (
    EducationOut, ExperienceOut, CertificationOut, ProjectOut, UserFullProfileOut, UserOut,
    UserSkillEvidenceOut, UserSkillOut,
)
from app.services import retrieval_service as rs
from app.services import user_service as us
from app.services.date_normalization import normalize_date_value

EMAIL = "budi.santoso@example.invalid"
PHONE = "0812-5555-0123"
PERSON = "Budi Santoso"
RAW_CV = (
    f"Name: {PERSON}\n"
    f"Email: {EMAIL}\n"
    f"Phone: {PHONE}\n"
    "Backend developer with SQL project experience.\n"
)

CAREERS = [
    CareerOut(career_id="C1", canonical_name="Backend Engineer", domain="Engineering"),
    CareerOut(career_id="C2", canonical_name="Data Analyst", domain="Data"),
]
SKILLS = {
    sid: SkillOut(skill_id=sid, canonical_name=name, skill_group_id="SG1", status="active")
    for sid, name in (
        ("S001", "SQL"), ("S002", "Networking"), ("S003", "Database Management"),
        ("S004", "Data Analysis"),
    )
}


def _req(career_id, skill_id, evidence_class, confidence):
    return CareerSkillOut(
        relationship_id=f"R_{career_id}_{skill_id}", skill=SKILLS[skill_id],
        evidence_class=evidence_class, confidence=confidence, mapping_method="test",
        evidence_source_text="KB basis text.",
    )


REQUIRED = {
    "C1": [_req("C1", "S001", "CORE", "high"), _req("C1", "S002", "SUPPORTING", "medium"),
           _req("C1", "S003", "CORE", "high")],
    "C2": [_req("C2", "S004", "CORE", "high"), _req("C2", "S001", "SUPPORTING", "medium")],
}

EXTRACTION = {
    "skills": [
        {"claimed_skill": "SQL", "proficiency": "intermediate", "candidate_skill_id": "S001"},
        {"claimed_skill": "Networking", "proficiency": None, "candidate_skill_id": "S002"},
        {"claimed_skill": "Totally Unmapped Claim", "proficiency": None, "candidate_skill_id": None},
    ],
    "evidence": [{"claimed_skill": "SQL", "evidence_type": "project",
                  "description": f"Synthetic project built with {EMAIL}", "url": None}],
    "education": [{"institution": "Synthetic University", "degree": "BSc",
                   "field_of_study": "IT", "start_date": "2020", "end_date": "2024",
                   "description": "Synthetic"}],
    "experience": [], "projects": [], "certifications": [],
}


class ScriptedLLM:
    model_name = "ScriptedDiagnosticLLM"

    def __init__(self, extraction=None):
        self.extraction = copy.deepcopy(extraction or EXTRACTION)
        self.prompts: list[str] = []

    def complete_json(self, system, user, max_tokens=2000):
        self.prompts.append(user)
        if "information-extraction component" in system:
            return copy.deepcopy(self.extraction)
        if "semantic grounding checker" in system:
            return {"unsupported_claims": []}
        if "Your ONLY job" in system:
            return {"reasoning": "The deterministic fit reflects the supplied skill information."}
        if "narrative layer of a skill-gap report" in system:
            return {}
        if "short overview of a learning-focus list" in system:
            return {"summary": "The learning focus follows the supplied skill-gap result."}
        raise AssertionError("Unexpected LLM request in the diagnostic test double.")


class MemoryUsers:
    """In-memory stand-in for user_service with the same signatures."""

    def __init__(self):
        self.skills, self.education, self.created = [], [], []
        self._n = 0

    def _id(self):
        self._n += 1
        return self._n

    def create_user(self, email, full_name=None):
        self._n += 1
        self.created.append(self._n)
        return SimpleNamespace(user_id=self._n, email=email, full_name=full_name)

    def add_education(self, user_id, institution, degree=None, field_of_study=None,
                      start_date=None, end_date=None, description=None):
        row = EducationOut(
            education_id=self._id(), institution=institution, degree=degree,
            field_of_study=field_of_study,
            start_date=normalize_date_value(start_date, field_name="start_date"),
            end_date=normalize_date_value(end_date, field_name="end_date", is_end_date=True),
            description=description,
        )
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

    def add_user_skill(self, user_id, claimed_skill, skill_id=None, normalized_skill=None,
                       proficiency=None):
        existing = next((s for s in self.skills if s.claimed_skill == claimed_skill), None)
        if existing:
            return existing.model_copy(deep=True)
        row = UserSkillOut(
            user_skill_id=self._id(), claimed_skill=claimed_skill, skill_id=skill_id,
            normalized_skill=normalized_skill, proficiency=proficiency,
            evidence_status="none", confidence="unknown", evidence=[],
        )
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
            user=UserOut(user_id=user_id, email="memory@example.invalid",
                         full_name="Memory User", created_at=datetime(2026, 1, 1)),
            education=[row.model_copy(deep=True) for row in self.education],
            skills=[row.model_copy(deep=True) for row in self.skills],
        )


def _context(career_id):
    career = next(c for c in CAREERS if c.career_id == career_id)
    return OccupationalContextOut(
        career=career, occupations=[], career_skills=REQUIRED[career_id], competencies=[],
        tasks={}, technologies={}, source_mappings={},
    )


@pytest.fixture
def memory(monkeypatch):
    store = MemoryUsers()
    monkeypatch.setattr(rs, "get_all_skills", lambda: list(SKILLS.values()))
    monkeypatch.setattr(rs, "get_all_careers", lambda: list(CAREERS))
    monkeypatch.setattr(rs, "get_career",
                        lambda cid: next((c for c in CAREERS if c.career_id == cid), None))
    monkeypatch.setattr(rs, "get_career_skills", lambda cid: list(REQUIRED[cid]))
    monkeypatch.setattr(rs, "get_occupational_context",
                        lambda cid: _context(cid) if cid in REQUIRED else None)
    monkeypatch.setattr(rs, "get_skill_evidence", lambda sid: [])
    for name in ("create_user", "add_education", "add_experience", "add_project",
                 "add_certification", "add_user_skill", "add_skill_evidence",
                 "get_user_full_profile"):
        monkeypatch.setattr(us, name, getattr(store, name))
    return store


@pytest.fixture
def database_seam():
    calls = []

    def cleanup(user_id):
        calls.append(user_id)
        return True, {"deleted": {"users": 1}, "remaining": {}}

    def seam():
        return {"name": "memory_kb", "host": "loopback", "port": 0,
                "server_current_database": "memory_kb"}, cleanup

    seam.calls = calls
    return seam


def write_cv(directory, name, text=RAW_CV):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def options(tmp_path, *, files=("Budi_Santoso_CV.txt",), run_id="run-1", **overrides):
    input_dir = tmp_path / "input"
    for name in files:
        if not (input_dir / name).exists():
            write_cv(input_dir, name)
    payload = {
        "run_id": run_id,
        "input_dir": input_dir,
        "output_dir": tmp_path / "out",
        "fake_llm": True,
    }
    payload.update(overrides)
    return runner_mod.DiagnosticOptions(**payload)


# --------------------------------------------------------------------------- inputs
def test_discover_cvs_lists_only_supported_files(tmp_path):
    write_cv(tmp_path, "b.pdf", "%PDF-1.4")
    write_cv(tmp_path, "a.txt")
    (tmp_path / "notes.md").write_text("ignore me", encoding="utf-8")
    (tmp_path / "subdir").mkdir()

    names = [path.name for path in runner_mod.discover_cvs(tmp_path)]

    assert names == ["a.txt", "b.pdf"]


def test_discover_cvs_refuses_an_empty_folder(tmp_path):
    with pytest.raises(runner_mod.DiagnosticSafetyError):
        runner_mod.discover_cvs(tmp_path)


def test_cv_identity_uses_content_only_and_never_the_file_name():
    payload = b"some cv bytes"

    meta = runner_mod.cv_identity(payload, ".pdf", 1)

    assert meta["cv_id"].startswith("cv01_")
    assert meta["sha256"] == __import__("hashlib").sha256(payload).hexdigest()
    assert meta["format"] == "pdf"
    assert meta["size_bytes"] == len(payload)
    assert meta["upload_name"] == f"{meta['cv_id']}.pdf"
    assert "path" not in meta and "filename" not in meta


def test_default_run_id_is_filesystem_safe():
    run_id = runner_mod.default_run_id()

    assert runner_mod.RUN_ID_PATTERN.fullmatch(run_id)
    assert re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{6}", run_id)


# --------------------------------------------------------------------------- gates
def test_live_llm_is_refused_without_explicit_approval():
    opts = runner_mod.DiagnosticOptions(
        run_id="r", input_dir=__import__("pathlib").Path("."), output_dir=__import__("pathlib").Path(".")
    )

    with pytest.raises(runner_mod.DiagnosticSafetyError):
        runner_mod.resolve_llm_client(opts)


def test_ambiguous_llm_mode_is_refused():
    opts = runner_mod.DiagnosticOptions(
        run_id="r", input_dir=__import__("pathlib").Path("."), output_dir=__import__("pathlib").Path("."),
        fake_llm=True, approve_live_llm=True,
    )

    with pytest.raises(runner_mod.DiagnosticSafetyError):
        runner_mod.resolve_llm_client(opts)


def test_fake_llm_mode_is_labelled_as_plumbing_only():
    _client, mode, label = runner_mod.resolve_llm_client(__import__("unittest.mock", fromlist=[""]).MagicMock(
        fake_llm=True, approve_live_llm=False))

    assert mode == "fake_llm"
    assert "never diagnostic validity" in label


def _fake_engine(host="localhost", database="career_intelligence_e2e_test"):
    url = URL.create("postgresql+psycopg2", username="postgres", password="x",
                     host=host, port=5433, database=database)
    engine = MagicMock()
    engine.url = url
    conn = MagicMock()
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=conn)
    ctx.__exit__ = MagicMock(return_value=False)
    engine.connect.return_value = ctx
    return engine, conn


def test_database_seam_rejects_a_non_isolated_database(monkeypatch):
    engine, conn = _fake_engine(database="career_intelligence")
    conn.execute.return_value.scalar_one.return_value = "career_intelligence"
    monkeypatch.setenv("CAREER_E2E_ISOLATED_DB_OK", "career_intelligence_e2e_test")
    monkeypatch.setattr("app.core.db.get_engine", lambda: engine, raising=False)

    with pytest.raises(runner_mod.DiagnosticSafetyError) as excinfo:
        runner_mod.default_database_seam()

    assert "isolated test database" in str(excinfo.value)


def test_database_seam_rejects_a_missing_opt_in(monkeypatch):
    engine, conn = _fake_engine()
    conn.execute.return_value.scalar_one.return_value = "career_intelligence_e2e_test"
    monkeypatch.delenv("CAREER_E2E_ISOLATED_DB_OK", raising=False)
    monkeypatch.setattr("app.core.db.get_engine", lambda: engine, raising=False)

    with pytest.raises(runner_mod.DiagnosticSafetyError):
        runner_mod.default_database_seam()


def test_existing_run_directory_is_never_overwritten(tmp_path):
    opts = options(tmp_path)
    (opts.output_dir / opts.run_id).mkdir(parents=True)

    with pytest.raises(runner_mod.DiagnosticSafetyError) as excinfo:
        runner_mod.run_diagnostic(opts, llm_client=ScriptedLLM(), database=lambda: ({}, lambda _uid: (True, {})))

    assert "Refusing to overwrite" in str(excinfo.value)


# --------------------------------------------------------------------------- end to end
def test_end_to_end_run_writes_trace_csv_and_summary(memory, database_seam, tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_ANALYSIS_LOG_DIR", str(tmp_path / "outside_logs"))
    opts = options(tmp_path)
    llm = ScriptedLLM()

    result = runner_mod.run_diagnostic(opts, llm_client=llm, database=database_seam)

    run_dir = tmp_path / "out" / "run-1"
    assert result["status"] == "PASS"
    assert result["counts"] == {"total": 1, "completed": 1, "failed": 0, "errored": 0}
    for name in ("run.json", "manifest.csv", "summary.md"):
        assert (run_dir / name).is_file(), name

    cv_id = next(p.stem.replace(".trace", "") for p in (run_dir / "traces").glob("*.trace.json"))
    trace = json.loads((run_dir / "traces" / f"{cv_id}.trace.json").read_text(encoding="utf-8"))

    assert trace["schema_version"] == trace_mod.TRACE_SCHEMA_VERSION
    assert trace["stages"]["extraction"]["status"] == "ok"
    assert trace["stages"]["extraction"]["payload"]["format"] == "txt"
    assert trace["stages"]["profile"]["status"] == "ok"
    assert trace["stages"]["okb_retrieval"]["status"] == "ok"
    assert trace["stages"]["career_fit"]["payload"]["career_count"] == len(CAREERS)
    assert trace["stages"]["skill_gap"]["payload"]["career_id"] == "C1"
    assert trace["stages"]["verification"]["payload"]["status"] == "PASS"
    assert trace["stages"]["final"]["payload"]["final_status"] == "VERIFIED"
    assert trace["analysis"]["analysis_id"]

    counts = trace["stages"]["profile"]["payload"]["counts"]
    assert counts["skills_extracted"] == 3
    assert counts["skills_normalized"] == 2
    assert counts["skills_unmatched"] == 1

    gap_counts = trace["stages"]["skill_gap"]["payload"]["counts"]
    assert set(gap_counts) == set(trace_mod.SKILL_GAP_CATEGORIES)
    assert sum(gap_counts[name] for name in ("matched_evidenced", "matched_claimed_only", "missing")) == 3
    assert gap_counts["unmatched_user_claims"] == 1

    assert trace["privacy"]["synthetic_user_deleted"] is True
    assert database_seam.calls == memory.created

    # The Step 16 log is captured next to the trace, under the neutral cv_id name.
    log_files = list((run_dir / "analysis_logs").glob("*.json"))
    assert [path.name for path in log_files] == [f"{cv_id}.analysis_log.json"]
    log = json.loads(log_files[0].read_text(encoding="utf-8"))
    assert log["schema_version"] == "analysis_log/1.0"
    assert log["analysis_id"] == trace["analysis"]["analysis_id"]

    with (run_dir / "manifest.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert tuple(rows[0]) == trace_mod.CSV_COLUMNS
    assert rows[0]["cv_id"] == cv_id
    assert rows[0]["final_status"] == "VERIFIED"
    assert rows[0]["verification_status"] == "PASS"
    assert rows[0]["analysis_id"] == trace["analysis"]["analysis_id"]
    assert rows[0]["trace_path"] == f"traces/{cv_id}.trace.json"

    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "PASS"
    assert manifest["llm_mode"] == "injected"
    assert manifest["privacy"]["synthetic_users_deleted"] is True

    # The diagnostic writer must not disturb the caller's Step 16 log directory.
    assert os.environ["CAREER_ANALYSIS_LOG_DIR"] == str(tmp_path / "outside_logs")


def test_run_artifacts_never_contain_the_file_name_or_cv_pii(memory, database_seam, tmp_path):
    # A --cv selection carries an original file name; it must still never reach an artifact.
    opts = options(tmp_path, files=("Budi_Santoso_CV.txt",), selected=("Budi_Santoso_CV",))
    result = runner_mod.run_diagnostic(opts, llm_client=ScriptedLLM(), database=database_seam)
    run_dir = __import__("pathlib").Path(result["run_dir"])

    corpus = "\n".join(
        path.read_text(encoding="utf-8-sig", errors="ignore")
        for path in run_dir.rglob("*") if path.is_file()
    )
    for sentinel in (PERSON, EMAIL, PHONE, "Budi_Santoso_CV"):
        assert sentinel not in corpus, sentinel

    manifest = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    assert manifest["input"]["selection_restricted"] is True
    assert len(manifest["input"]["selected_cv_ids"]) == 1
    assert manifest["input"]["selected_cv_ids"][0].startswith("cv01_")


def test_runner_continues_after_a_failing_cv_and_records_the_error(memory, database_seam, tmp_path):
    opts = options(tmp_path, files=("a_broken.pdf", "b_good.txt"))
    (opts.input_dir / "a_broken.pdf").write_bytes(b"%PDF-1.7 malformed")

    result = runner_mod.run_diagnostic(opts, llm_client=ScriptedLLM(), database=database_seam)

    run_dir = tmp_path / "out" / "run-1"
    with (run_dir / "manifest.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert result["status"] == "PASS"
    assert len(rows) == 2
    by_status = {row["http_status"]: row for row in rows}
    assert by_status["422"]["extraction_status"] == "failed"
    assert by_status["422"]["extraction_error_code"] == "unreadable_document"
    assert by_status["422"]["final_status"] == ""
    assert by_status["200"]["final_status"] == "VERIFIED"
    assert by_status["422"]["analysis_id"] == ""

    traces = sorted((run_dir / "traces").glob("*.trace.json"))
    assert len(traces) == 2
    failed_trace = next(
        json.loads(path.read_text(encoding="utf-8")) for path in traces
        if json.loads(path.read_text(encoding="utf-8"))["analysis"]["http_status"] == 422
    )
    assert failed_trace["stages"]["extraction"]["status"] == "failed"
    assert failed_trace["stages"]["profile"]["status"] == "not_reached"
    assert failed_trace["stages"]["career_fit"]["status"] == "not_reached"


def test_selected_cv_restricts_the_run(memory, database_seam, tmp_path):
    opts = options(tmp_path, files=("one.txt", "two.txt"), selected=("two",))

    result = runner_mod.run_diagnostic(opts, llm_client=ScriptedLLM(), database=database_seam)

    assert result["counts"]["total"] == 1


def test_unknown_selection_is_refused(tmp_path):
    opts = options(tmp_path, files=("one.txt",), selected=("missing",))

    with pytest.raises(runner_mod.DiagnosticSafetyError):
        runner_mod.run_diagnostic(opts, llm_client=ScriptedLLM(),
                                  database=lambda: ({}, lambda _uid: (True, {})))
