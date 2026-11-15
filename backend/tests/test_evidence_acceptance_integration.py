"""Stage 3.4.1 database integration tests for evidence acceptance.

These tests exercise the real repository, service, and Knowledge Base records.
They are guarded twice:

* ``CAREER_RUN_RUNTIME_DB_TESTS=1`` must be set explicitly.
* ``CAREER_E2E_ISOLATED_DB_OK`` must name the designated test database, and
  the server-confirmed ``current_database()`` must equal that same name.
  ``career_intelligence_main`` can never be touched.

Coverage map (Stage 3.4.1 section 4):
  1  structural rejection of missing/invalid source records
  2  evidence text must be traceable to the supplied CV
  3  self-report alone is not accepted
  4  valid activity evidence can pass semantic verification
  5  malformed/unavailable LLM responses cannot PASS
  6  a structurally invalid candidate cannot be accepted even with LLM PASS
  7  certification title/description rules (issuer optional, expiry ignored)
  8  URL-only project evidence is rejected
  9  evidence-derived skills without an explicit user claim
  10 PASS / REVISE / FAIL acceptance behavior
  11 evidence-only skills become ``matched_evidenced`` with a null claim
  12 all four skill-gap categories retain their approved meanings
  13 duplicate CV + canonical skill cannot multiply credit
  14 one activity may support multiple distinct canonical skills
  15 temporary CV spans are removed after the decision
  16 historical ``linked`` evidence is not automatically trusted
  17 revision cap is covered by ``test_career_workflow_unit.py``
"""
import os
import uuid

import pytest
from sqlalchemy import text

from app.core.db import DatabaseConfigurationError, get_engine
from app.services import evidence_acceptance_service as gate
from app.services import skill_gap_service as sgs
from app.services import user_service as us

ALLOWED_DB = "career_intelligence_e2e_test"
LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Required skills of career C01 used across the scenarios.
SKILL_DATABASE_DESIGN = "S034"
SKILL_DATABASE_MANAGEMENT = "S035"
SKILL_PROGRAMMING = "S065"
SKILL_MISSING_EXAMPLE = "S004"  # Application Monitoring; never claimed in scenario 12


class StubLLM:
    """Deterministic LLM double. It never makes a live provider call."""

    def __init__(self, decision="PASS", skill_id=None, reason="The activity supports the skill.",
                 payload=None, error=None):
        self.decision = decision
        self.skill_id = skill_id
        self.reason = reason
        self.payload = payload
        self.error = error
        self.calls = []

    def complete_json(self, system, user, max_tokens=2000):
        self.calls.append((system, user, max_tokens))
        if self.error is not None:
            raise self.error
        if self.payload is not None:
            return self.payload
        return {"decision": self.decision, "reason": self.reason, "skill_id": self.skill_id}


@pytest.fixture(scope="session")
def local_database():
    if os.environ.get("CAREER_RUN_RUNTIME_DB_TESTS") != "1":
        pytest.skip(
            "Set CAREER_RUN_RUNTIME_DB_TESTS=1 and point the DB settings at "
            "career_intelligence_e2e_test to run runtime evidence tests."
        )
    if os.environ.get("CAREER_E2E_ISOLATED_DB_OK") != ALLOWED_DB:
        pytest.fail(
            f"Runtime evidence tests require explicit opt-in via "
            f"CAREER_E2E_ISOLATED_DB_OK={ALLOWED_DB}."
        )
    try:
        engine = get_engine()
    except DatabaseConfigurationError:
        pytest.fail(
            "Local database is not configured. Set CAREER_DB_URL or the "
            "CAREER_DB_* settings; values are never printed."
        )

    if (engine.url.host or "").lower() not in LOOPBACK_HOSTS:
        pytest.fail("Runtime evidence tests require a loopback database host.")
    if engine.url.database != ALLOWED_DB:
        pytest.fail(f"Runtime evidence tests only run on {ALLOWED_DB}.")

    with engine.connect() as conn:
        current = conn.execute(text("SELECT current_database()")).scalar_one()
        career_count = conn.execute(text("SELECT count(*) FROM careers")).scalar_one()
        candidate_table = conn.execute(
            text("SELECT to_regclass('public.user_evidence_candidates')")
        ).scalar_one()
        accepted_table = conn.execute(
            text("SELECT to_regclass('public.user_accepted_evidence')")
        ).scalar_one()
    if current != ALLOWED_DB:
        pytest.fail(f"Server-confirmed database is not {ALLOWED_DB}.")
    if current == "career_intelligence_main":
        pytest.fail("Runtime evidence tests must never run against career_intelligence_main.")
    if career_count != 10:
        pytest.fail("Runtime evidence tests require the ten canonical careers.")
    if candidate_table is None or accepted_table is None:
        pytest.fail(
            "Evidence acceptance tables are missing; apply "
            "backend/scripts/migrations/2026_11_14_001_evidence_acceptance.sql "
            f"to {ALLOWED_DB}."
        )
    return engine


def _delete_user(engine, user_id: int) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE user_id = :uid"), {"uid": user_id})


@pytest.fixture()
def user(local_database):
    created = us.create_user(
        f"evidence-acceptance-{uuid.uuid4().hex}@example.invalid",
        "Evidence Acceptance Test User",
    )
    try:
        yield created
    finally:
        _delete_user(local_database, created.user_id)


def _candidate(user_id, cv_text, *, skill_id, source_type, source_table,
               source_id, evidence_text, claimed_skill=None, cv_id=None):
    cv_id = cv_id or gate.cv_identity(user_id, cv_text)
    return us.create_evidence_candidate(
        candidate_key=gate.candidate_key(
            user_id, cv_id, source_table, source_id, skill_id, evidence_text,
        ),
        user_id=user_id,
        cv_id=cv_id,
        source_type=source_type,
        source_table=source_table,
        source_id=source_id,
        skill_id=skill_id,
        claimed_skill=claimed_skill,
        evidence_text=evidence_text,
        evidence_span_hash=gate.span_hash(evidence_text),
    )


def _project(user_id, description, title="Test project"):
    return us.add_project(user_id, title=title, description=description)


def _accepted_for(user_id, skill_id):
    return [row for row in us.fetch_accepted_evidence(user_id) if row["skill_id"] == skill_id]


def _candidate_row(user_id, candidate_id):
    return next(
        row for row in us.fetch_evidence_candidates(user_id)
        if row["candidate_id"] == candidate_id
    )


# ---- 1. Structural rejection of missing/invalid source records ----------------
def test_scenario_01_structural_validation_rejects_invalid_sources(user, local_database):
    cv = "Portfolio of database and software work."
    project = _project(user.user_id, "Built a reporting service")
    other = us.create_user(
        f"evidence-other-{uuid.uuid4().hex}@example.invalid", "Other User",
    )
    try:
        other_project = _project(other.user_id, "Built an unrelated service")
    finally:
        # The candidate below is created before cleanup so the FK by user_id
        # never blocks deletion of the other user's project through cascade.
        pass

    cases = {
        "nonexistent_source": _candidate(
            user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="project",
            source_table="user_projects", source_id=2147483000,
            evidence_text="Built a reporting service",
        ),
        "other_users_source": _candidate(
            user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="project",
            source_table="user_projects", source_id=other_project.project_id,
            evidence_text="Built an unrelated service",
        ),
        "disallowed_source_table": _candidate(
            user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="other",
            source_table="users", source_id=user.user_id,
            evidence_text="Portfolio of database and software work.",
        ),
        "missing_source_id": _candidate(
            user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="project",
            source_table="user_projects", source_id=None,
            evidence_text="Built a reporting service",
        ),
        "missing_canonical_skill": _candidate(
            user.user_id, cv, skill_id=None, source_type="project",
            source_table="user_projects", source_id=project.project_id,
            evidence_text="Built a reporting service",
        ),
    }

    try:
        for label, candidate in cases.items():
            result = gate.evaluate_candidate(
                candidate["candidate_id"], cv, StubLLM(skill_id=SKILL_DATABASE_DESIGN),
            )
            assert result["acceptance_status"] == gate.ACCEPTANCE_REJECTED, label
            assert result["candidate"]["structural_status"] == gate.STRUCTURAL_FAILED, label
            assert result["candidate"]["semantic_status"] == gate.SEMANTIC_NOT_ATTEMPTED, label
        assert us.fetch_accepted_evidence(user.user_id) == []
    finally:
        _delete_user(local_database, other.user_id)


# ---- 2. Evidence text must be traceable to the supplied CV --------------------
def test_scenario_02_evidence_text_must_come_from_the_cv(user):
    project = _project(user.user_id, "Designed a normalized schema")
    cv = "Senior project: designed a normalized schema for an inventory system."
    fake_llm = StubLLM(skill_id=SKILL_DATABASE_DESIGN)

    traceable = _candidate(
        user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="project",
        source_table="user_projects", source_id=project.project_id,
        evidence_text="DESIGNED a normalized schema",  # casing/whitespace variant
    )
    invented = _candidate(
        user.user_id, cv, skill_id=SKILL_DATABASE_MANAGEMENT, source_type="project",
        source_table="user_projects", source_id=project.project_id,
        evidence_text="Administered production PostgreSQL clusters",
    )

    accepted = gate.evaluate_candidate(traceable["candidate_id"], cv, fake_llm)
    rejected = gate.evaluate_candidate(invented["candidate_id"], cv, fake_llm)

    assert accepted["acceptance_status"] == gate.ACCEPTANCE_ACCEPTED
    assert rejected["acceptance_status"] == gate.ACCEPTANCE_REJECTED
    assert "not traceable" in rejected["candidate"]["structural_reason"].lower()
    assert [row["skill_id"] for row in us.fetch_accepted_evidence(user.user_id)] == [
        SKILL_DATABASE_DESIGN
    ]


# ---- 3. Self-report alone does not become accepted evidence -------------------
@pytest.mark.parametrize("text", [
    "Skills: Python, Java, SQL",
    "Familiar with Python",
    "Proficient in database design",
])
def test_scenario_03_self_report_is_not_accepted(user, text):
    project = _project(user.user_id, "Self description")
    cv = f"Profile summary.\n{text}\nEnd of summary."
    candidate = _candidate(
        user.user_id, cv, skill_id=SKILL_PROGRAMMING, source_type="project",
        source_table="user_projects", source_id=project.project_id,
        evidence_text=text,
    )
    fake_llm = StubLLM(skill_id=SKILL_PROGRAMMING)

    result = gate.evaluate_candidate(candidate["candidate_id"], cv, fake_llm)

    assert result["candidate"]["structural_status"] == gate.STRUCTURAL_PASSED
    assert result["candidate"]["semantic_status"] == gate.SEMANTIC_FAIL
    assert result["acceptance_status"] == gate.ACCEPTANCE_REJECTED
    assert us.fetch_accepted_evidence(user.user_id) == []
    # Self-report is stopped deterministically before the semantic role.
    assert fake_llm.calls == []


# ---- 4. Valid activity evidence can pass semantic verification ----------------
def test_scenario_04_activity_evidence_passes(user):
    project = _project(user.user_id, "Developed a REST API using Python")
    cv = "Experience: DEVELOPED   a REST API using Python for a course project."
    candidate = _candidate(
        user.user_id, cv, skill_id=SKILL_PROGRAMMING, source_type="project",
        source_table="user_projects", source_id=project.project_id,
        evidence_text="Developed a REST API using Python",
    )
    fake_llm = StubLLM(skill_id=SKILL_PROGRAMMING)

    result = gate.evaluate_candidate(candidate["candidate_id"], cv, fake_llm)

    assert result["candidate"]["structural_status"] == gate.STRUCTURAL_PASSED
    assert result["candidate"]["semantic_status"] == gate.SEMANTIC_PASS
    assert result["acceptance_status"] == gate.ACCEPTANCE_ACCEPTED
    assert fake_llm.calls
    accepted = _accepted_for(user.user_id, SKILL_PROGRAMMING)
    assert len(accepted) == 1
    assert accepted[0]["cv_id"] == candidate["cv_id"]


# ---- 5. Malformed or unavailable LLM responses cannot PASS --------------------
@pytest.mark.parametrize("llm", [
    None,
    StubLLM(payload={}),
    StubLLM(payload={"decision": "PASS", "reason": "ok"}),
    StubLLM(payload={"decision": "MAYBE", "reason": "ok", "skill_id": SKILL_PROGRAMMING}),
    StubLLM(payload={"decision": "PASS", "reason": "ok", "skill_id": "S999"}),
    StubLLM(error=RuntimeError("provider unavailable")),
], ids=["no-client", "empty", "missing-skill", "bad-decision", "wrong-skill", "provider-error"])
def test_scenario_05_unavailable_or_malformed_llm_cannot_pass(user, llm):
    project = _project(user.user_id, "Built a dashboard using Power BI")
    cv = "Built a dashboard using Power BI for the analytics team."
    candidate = _candidate(
        user.user_id, cv, skill_id=SKILL_PROGRAMMING, source_type="project",
        source_table="user_projects", source_id=project.project_id,
        evidence_text="Built a dashboard using Power BI",
    )

    result = gate.evaluate_candidate(candidate["candidate_id"], cv, llm)

    assert result["candidate"]["structural_status"] == gate.STRUCTURAL_PASSED
    assert result["candidate"]["semantic_status"] == gate.SEMANTIC_REVISE
    assert result["acceptance_status"] == gate.ACCEPTANCE_REVISE
    assert us.fetch_accepted_evidence(user.user_id) == []


# ---- 6. Structural failure beats an LLM PASS ----------------------------------
def test_scenario_06_llm_pass_cannot_override_structural_failure(user):
    project = _project(user.user_id, "Designed a normalized schema")
    cv = "Designed a normalized schema for an inventory system."
    candidate = _candidate(
        user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="project",
        source_table="user_projects", source_id=project.project_id,
        evidence_text="Architected a distributed ledger",  # absent from the CV
    )
    fake_llm = StubLLM(decision="PASS", skill_id=SKILL_DATABASE_DESIGN)

    result = gate.evaluate_candidate(candidate["candidate_id"], cv, fake_llm)

    assert result["candidate"]["structural_status"] == gate.STRUCTURAL_FAILED
    assert result["candidate"]["semantic_status"] == gate.SEMANTIC_NOT_ATTEMPTED
    assert result["acceptance_status"] == gate.ACCEPTANCE_REJECTED
    assert fake_llm.calls == []  # semantic role never sees a failed structure
    assert us.fetch_accepted_evidence(user.user_id) == []


# ---- 7. Certification title and description rules -----------------------------
def test_scenario_07_certification_rules(user, local_database):
    clear_title = "Python Programming Certificate"
    ambiguous_title = "Cloud Fundamentals"
    cv = (
        f"Certifications: {clear_title}.\n"
        f"Also completed {ambiguous_title}.\n"
        "Temporary certificate placeholder."
    )

    clear_cert = us.add_certification(
        user.user_id, name=clear_title, issuer=None, expiry_date="2020-01-01",
    )
    ambiguous_cert = us.add_certification(
        user.user_id, name=ambiguous_title, issuer="Some Issuer",
    )
    blank_cert = us.add_certification(
        user.user_id, name="Temporary certificate placeholder",
    )
    with local_database.begin() as conn:
        conn.execute(
            text("UPDATE user_certifications SET name = '   ' WHERE certification_id = :cid"),
            {"cid": blank_cert.certification_id},
        )

    clear = _candidate(
        user.user_id, cv, skill_id=SKILL_PROGRAMMING, source_type="certification",
        source_table="user_certifications", source_id=clear_cert.certification_id,
        evidence_text=clear_title,
    )
    ambiguous = _candidate(
        user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="certification",
        source_table="user_certifications", source_id=ambiguous_cert.certification_id,
        evidence_text=ambiguous_title,
    )
    blank = _candidate(
        user.user_id, cv, skill_id=SKILL_PROGRAMMING, source_type="certification",
        source_table="user_certifications", source_id=blank_cert.certification_id,
        evidence_text="Temporary certificate placeholder",
    )
    # The deterministic certification anchor must not need an LLM call.
    clear_result = gate.evaluate_candidate(clear["candidate_id"], cv, None)
    ambiguous_result = gate.evaluate_candidate(
        ambiguous["candidate_id"], cv, StubLLM(skill_id=SKILL_DATABASE_DESIGN),
    )
    blank_result = gate.evaluate_candidate(blank["candidate_id"], cv, None)

    # Clear title + no issuer + expired date is still accepted (D-08/D-12).
    assert clear_result["acceptance_status"] == gate.ACCEPTANCE_ACCEPTED
    assert clear_result["candidate"]["semantic_status"] == gate.SEMANTIC_PASS
    # An ambiguous relationship is withheld from automatic acceptance (D-10).
    assert ambiguous_result["acceptance_status"] == gate.ACCEPTANCE_REVISE
    assert ambiguous_result["candidate"]["semantic_status"] == gate.SEMANTIC_REVISE
    # A missing title fails the structural gate (D-09).
    assert blank_result["acceptance_status"] == gate.ACCEPTANCE_REJECTED
    assert blank_result["candidate"]["structural_status"] == gate.STRUCTURAL_FAILED
    assert [row["skill_id"] for row in us.fetch_accepted_evidence(user.user_id)] == [
        SKILL_PROGRAMMING
    ]


# ---- 8. URL-only evidence is rejected -----------------------------------------
def test_scenario_08_url_only_project_evidence_is_rejected(user):
    url = "https://portfolio.example.test/projects/inventory"
    project = us.add_project(
        user.user_id, title="Inventory project", description=None, url=url,
    )
    cv = f"Portfolio link: {url}"
    candidate = _candidate(
        user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="project",
        source_table="user_projects", source_id=project.project_id,
        evidence_text=url,
    )
    fake_llm = StubLLM(skill_id=SKILL_DATABASE_DESIGN)

    result = gate.evaluate_candidate(candidate["candidate_id"], cv, fake_llm)

    assert result["candidate"]["structural_status"] == gate.STRUCTURAL_FAILED
    assert result["acceptance_status"] == gate.ACCEPTANCE_REJECTED
    assert "url" in result["candidate"]["structural_reason"].lower()
    assert fake_llm.calls == []
    assert us.fetch_accepted_evidence(user.user_id) == []


# ---- 9. Evidence-derived skills without an explicit claim ---------------------
def test_scenario_09_evidence_derived_skill_without_claim(user):
    project = _project(user.user_id, "Designed a normalized database schema")
    cv = "Designed a normalized database schema for the capstone project."
    candidate = _candidate(
        user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="project",
        source_table="user_projects", source_id=project.project_id,
        evidence_text="Designed a normalized database schema",
    )
    result = gate.evaluate_candidate(
        candidate["candidate_id"], cv, StubLLM(skill_id=SKILL_DATABASE_DESIGN),
    )
    assert result["acceptance_status"] == gate.ACCEPTANCE_ACCEPTED

    profile = us.get_user_full_profile(user.user_id)
    assert profile is not None
    assert all(skill.skill_id != SKILL_DATABASE_DESIGN for skill in profile.skills)
    derived = next(
        skill for skill in profile.effective_skills
        if skill.skill_id == SKILL_DATABASE_DESIGN
    )
    assert derived.source == "evidence"
    assert derived.evidence_status == "linked"
    assert derived.user_skill_id is None
    assert derived.claimed_skill is None
    assert derived.accepted_evidence


# ---- 10. PASS / REVISE / FAIL acceptance behavior -----------------------------
def test_scenario_10_pass_revise_fail_behavior(user):
    texts = {
        "pass": "Implemented an indexing strategy",
        "revise": "Investigated an indexing strategy",
        "fail": "Reviewed a presentation about indexing",
    }
    cv = "Work history:\n" + "\n".join(texts.values())
    candidates = {
        label: _candidate(
            user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="project",
            source_table="user_projects", source_id=_project(user.user_id, text).project_id,
            evidence_text=text,
        )
        for label, text in texts.items()
    }
    decisions = {"pass": "PASS", "revise": "REVISE", "fail": "FAIL"}

    results = {
        label: gate.evaluate_candidate(
            candidate["candidate_id"], cv,
            StubLLM(decision=decisions[label], skill_id=SKILL_DATABASE_DESIGN),
        )
        for label, candidate in candidates.items()
    }

    assert results["pass"]["acceptance_status"] == gate.ACCEPTANCE_ACCEPTED
    assert results["revise"]["acceptance_status"] == gate.ACCEPTANCE_REVISE
    assert results["fail"]["acceptance_status"] == gate.ACCEPTANCE_REJECTED
    accepted = _accepted_for(user.user_id, SKILL_DATABASE_DESIGN)
    assert len(accepted) == 1
    assert accepted[0]["candidate_id"] == candidates["pass"]["candidate_id"]


# ---- 11. Evidence-only skill is matched_evidenced with a null claim -----------
def test_scenario_11_evidence_only_match_has_null_claim(user):
    project = _project(user.user_id, "Designed a normalized database schema")
    cv = "Designed a normalized database schema for the capstone project."
    candidate = _candidate(
        user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="project",
        source_table="user_projects", source_id=project.project_id,
        evidence_text="Designed a normalized database schema",
    )
    gate.evaluate_candidate(
        candidate["candidate_id"], cv, StubLLM(skill_id=SKILL_DATABASE_DESIGN),
    )

    gap = sgs.analyze_skill_gap(user.user_id, "C01")

    evidenced = next(
        item for item in gap.matched_evidenced if item.skill_id == SKILL_DATABASE_DESIGN
    )
    assert evidenced.matched_user_claim is None
    assert evidenced.status == "matched_evidenced"
    assert evidenced.accepted_evidence
    ref = evidenced.accepted_evidence[0]
    assert ref.skill_id == SKILL_DATABASE_DESIGN
    assert ref.cv_id == candidate["cv_id"]
    assert ref.accepted_evidence_id == _accepted_for(
        user.user_id, SKILL_DATABASE_DESIGN
    )[0]["accepted_evidence_id"]


# ---- 12. All four skill-gap categories retain their meanings ------------------
def test_scenario_12_all_four_categories(user):
    cv = (
        "Designed a normalized database schema.\n"
        "Managed database backups and migrations."
    )
    # matched_evidenced: claim + accepted evidence.
    us.add_user_skill(
        user.user_id, claimed_skill="Database Design", skill_id=SKILL_DATABASE_DESIGN,
        normalized_skill="Database Design", proficiency="advanced",
    )
    project = _project(user.user_id, "Designed a normalized database schema")
    candidate = _candidate(
        user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="project",
        source_table="user_projects", source_id=project.project_id,
        evidence_text="Designed a normalized database schema",
    )
    gate.evaluate_candidate(
        candidate["candidate_id"], cv, StubLLM(skill_id=SKILL_DATABASE_DESIGN),
    )
    # matched_claimed_only: claim with no accepted evidence.
    us.add_user_skill(
        user.user_id, claimed_skill="Database Management", skill_id=SKILL_DATABASE_MANAGEMENT,
        normalized_skill="Database Management", proficiency="intermediate",
    )
    # unmatched_user_claims: cannot be normalized to a canonical skill.
    us.add_user_skill(
        user.user_id, claimed_skill="Quantum Basket Weaving", skill_id=None,
        normalized_skill=None,
    )

    gap = sgs.analyze_skill_gap(user.user_id, "C01")

    evidenced_ids = {item.skill_id for item in gap.matched_evidenced}
    claimed_ids = {item.skill_id for item in gap.matched_claimed_only}
    missing_ids = {item.skill_id for item in gap.missing}
    unmatched = {item.claimed_skill for item in gap.unmatched_user_claims}

    assert SKILL_DATABASE_DESIGN in evidenced_ids
    assert SKILL_DATABASE_MANAGEMENT in claimed_ids
    assert SKILL_MISSING_EXAMPLE in missing_ids
    assert "Quantum Basket Weaving" in unmatched
    # An unmatched claim is never reinterpreted as a missing requirement.
    assert SKILL_DATABASE_DESIGN not in missing_ids
    assert SKILL_DATABASE_MANAGEMENT not in missing_ids


# ---- 13. Duplicate credit is suppressed ---------------------------------------
def test_scenario_13_duplicate_cv_and_skill_cannot_multiply_credit(user):
    cv = (
        "Designed a normalized schema for the inventory project.\n"
        "Later designed a normalized schema for the billing project."
    )
    first = _candidate(
        user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="project",
        source_table="user_projects",
        source_id=_project(user.user_id, "Designed a normalized schema for inventory").project_id,
        evidence_text="Designed a normalized schema for the inventory project",
    )
    second = _candidate(
        user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="project",
        source_table="user_projects",
        source_id=_project(user.user_id, "Designed a normalized schema for billing").project_id,
        evidence_text="Later designed a normalized schema for the billing project",
    )

    summary = gate.evaluate_user_candidates(
        user.user_id, cv, StubLLM(skill_id=SKILL_DATABASE_DESIGN),
    )

    assert summary["evaluated"] == 2
    assert summary["accepted"] == 2
    assert summary["duplicate_suppressed"] == 1
    accepted = _accepted_for(user.user_id, SKILL_DATABASE_DESIGN)
    assert len(accepted) == 1
    # The losing candidate remains auditable but creates no extra credit.
    assert _candidate_row(user.user_id, first["candidate_id"])["acceptance_status"] == "accepted"
    assert _candidate_row(user.user_id, second["candidate_id"])["acceptance_status"] == "accepted"


# ---- 14. One activity can support multiple distinct skills --------------------
def test_scenario_14_one_activity_supports_multiple_skills(user):
    description = "Designed a normalized schema and tuned database queries"
    project = _project(user.user_id, description)
    cv = f"Capstone: {description}."
    design = _candidate(
        user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="project",
        source_table="user_projects", source_id=project.project_id,
        evidence_text="Designed a normalized schema",
    )
    management = _candidate(
        user.user_id, cv, skill_id=SKILL_DATABASE_MANAGEMENT, source_type="project",
        source_table="user_projects", source_id=project.project_id,
        evidence_text="tuned database queries",
    )

    gate.evaluate_candidate(
        design["candidate_id"], cv, StubLLM(skill_id=SKILL_DATABASE_DESIGN),
    )
    gate.evaluate_candidate(
        management["candidate_id"], cv, StubLLM(skill_id=SKILL_DATABASE_MANAGEMENT),
    )

    accepted = us.fetch_accepted_evidence(user.user_id)
    assert {row["skill_id"] for row in accepted} == {
        SKILL_DATABASE_DESIGN, SKILL_DATABASE_MANAGEMENT,
    }
    assert {row["source_id"] for row in accepted} == {project.project_id}


# ---- 15. Temporary CV span removal --------------------------------------------
def test_scenario_15_temporary_span_is_removed_after_decision(user):
    text = "Developed a Python data pipeline"
    project = _project(user.user_id, text)
    cv = f"Experience: {text}."
    candidate = _candidate(
        user.user_id, cv, skill_id=SKILL_PROGRAMMING, source_type="project",
        source_table="user_projects", source_id=project.project_id,
        evidence_text=text,
    )
    expected_hash = candidate["evidence_span_hash"]
    assert candidate["evidence_text"] == text

    result = gate.evaluate_candidate(
        candidate["candidate_id"], cv, StubLLM(skill_id=SKILL_PROGRAMMING),
    )
    assert result["acceptance_status"] == gate.ACCEPTANCE_ACCEPTED

    row = _candidate_row(user.user_id, candidate["candidate_id"])
    assert row["evidence_text"] is None
    assert row["span_removed_at"] is not None
    assert row["evidence_span_hash"] == expected_hash
    # Provenance survives even though the raw span is gone.
    accepted = _accepted_for(user.user_id, SKILL_PROGRAMMING)
    assert len(accepted) == 1
    assert accepted[0]["source_id"] == project.project_id


def test_revise_span_survives_until_recheck_then_is_removed(user):
    text = "Investigated a database indexing strategy"
    cv = f"Experience: {text}."
    project = _project(user.user_id, text)
    candidate = _candidate(
        user.user_id, cv, skill_id=SKILL_DATABASE_DESIGN, source_type="project",
        source_table="user_projects", source_id=project.project_id,
        evidence_text=text,
    )

    first = gate.evaluate_candidate(
        candidate["candidate_id"], cv,
        StubLLM(decision="REVISE", skill_id=SKILL_DATABASE_DESIGN),
    )
    assert first["acceptance_status"] == gate.ACCEPTANCE_REVISE
    interim = _candidate_row(user.user_id, candidate["candidate_id"])
    assert interim["evidence_text"] == text
    assert interim["span_removed_at"] is None
    assert _accepted_for(user.user_id, SKILL_DATABASE_DESIGN) == []

    second = gate.reassess_revise_candidates(
        user.user_id,
        StubLLM(decision="PASS", skill_id=SKILL_DATABASE_DESIGN),
    )
    assert second["reassessed"] == 1
    assert second["accepted"] == 1
    final_row = _candidate_row(user.user_id, candidate["candidate_id"])
    assert final_row["evidence_text"] is None
    assert final_row["span_removed_at"] is not None
    assert len(_accepted_for(user.user_id, SKILL_DATABASE_DESIGN)) == 1


# ---- 16. Historical linked evidence is not automatically trusted --------------
def test_scenario_16_historical_linked_evidence_is_not_trusted(user, local_database):
    claim = us.add_user_skill(
        user.user_id, claimed_skill="Database Design", skill_id=SKILL_DATABASE_DESIGN,
        normalized_skill="Database Design", proficiency="advanced",
    )
    # Legacy path: this sets user_skills.evidence_status = 'linked' directly.
    us.add_skill_evidence(
        claim.user_skill_id, evidence_type="project", source_table="user_projects",
        source_id=None, description="Historical legacy evidence", url=None,
        mark_linked=True,
    )
    with local_database.begin() as conn:
        legacy_status = conn.execute(
            text("SELECT evidence_status FROM user_skills WHERE user_skill_id = :id"),
            {"id": claim.user_skill_id},
        ).scalar_one()
    assert legacy_status == "linked"  # the historical row still says linked

    profile = us.get_user_full_profile(user.user_id)
    assert profile is not None
    stored = next(s for s in profile.skills if s.user_skill_id == claim.user_skill_id)
    assert stored.evidence_status == "none"  # effective status ignores legacy linked
    assert stored.accepted_evidence == []
    effective = next(
        s for s in profile.effective_skills if s.skill_id == SKILL_DATABASE_DESIGN
    )
    assert effective.evidence_status == "none"
    assert effective.source == "claim"

    gap = sgs.analyze_skill_gap(user.user_id, "C01")
    assert SKILL_DATABASE_DESIGN in {item.skill_id for item in gap.matched_claimed_only}
    assert SKILL_DATABASE_DESIGN not in {item.skill_id for item in gap.matched_evidenced}
    assert us.fetch_accepted_evidence(user.user_id) == []
