"""Stage 3.4.1 unit tests: acceptance-gate helpers and semantic safety.

No database and no live LLM are used. The DB-backed acceptance lifecycle is
covered in tests/test_evidence_acceptance_integration.py.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import evidence_acceptance_service as gate  # noqa: E402


class DecisionLLM:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = []

    def complete_json(self, system, user, max_tokens=2000):
        self.calls.append((system, user, max_tokens))
        if self.error is not None:
            raise self.error
        return self.payload


def candidate(skill_id="S001", skill_label="Python"):
    return {
        "candidate_id": 1,
        "user_id": 1,
        "cv_id": "cv-1",
        "source_type": "project",
        "source_table": "user_projects",
        "source_id": 10,
        "skill_id": skill_id,
        "claimed_skill": skill_label,
        "evidence_text": "Developed a REST API using Python",
    }


def test_self_report_phrasings_are_classified_as_self_report():
    for text in (
        "Skills: Python, Java, SQL",
        "Familiar with Python",
        "Knowledge of SQL databases",
        "Proficient in Python",
        "Self-assessed Python level: advanced",
    ):
        assert gate.classify_evidence_content("project", text) == "self_report", text


def test_activity_phrasings_are_not_self_report():
    for text in (
        "Developed a REST API using Python",
        "Built a dashboard using Power BI",
        "Designed and implemented a normalized schema",
        "Completed a capstone project using SQL",
    ):
        assert gate.classify_evidence_content("project", text) == "activity", text


def test_source_type_alone_does_not_classify_ambiguous_text_as_activity():
    assert gate.classify_evidence_content("project", "Python skills") == "ambiguous"
    assert gate.classify_evidence_content("work_experience", "Responsible for systems") == "ambiguous"


def test_bare_claim_or_claim_list_is_self_report_from_content():
    assert gate.classify_evidence_content("other", "Python", "Python") == "self_report"
    assert gate.classify_evidence_content("project", "Python, SQL", "Python") == "self_report"


def test_url_only_is_rejected_by_the_pattern():
    assert gate._URL_ONLY.match("https://example.test/portfolio")
    assert gate._URL_ONLY.match("www.example.test/portfolio")
    assert not gate._URL_ONLY.match("Portfolio: https://example.test/portfolio")


def test_semantic_role_without_client_cannot_pass():
    decision, reason = gate._semantic_assess(None, candidate(), "Python", None)
    assert decision == gate.SEMANTIC_REVISE
    assert "not treated as PASS" in reason


def test_semantic_role_malformed_output_cannot_pass():
    for payload in ({}, {"decision": "PASS", "reason": "ok"},
                    {"decision": "PASS", "reason": "", "skill_id": "S001"},
                    {"decision": "MAYBE", "reason": "ok", "skill_id": "S001"},
                    {"decision": "PASS", "reason": "ok", "skill_id": "S999"}):
        decision, _ = gate._semantic_assess(
            DecisionLLM(payload=payload), candidate(), "Python", None,
        )
        assert decision == gate.SEMANTIC_REVISE, payload


def test_semantic_role_provider_error_cannot_pass():
    decision, reason = gate._semantic_assess(
        DecisionLLM(error=RuntimeError("provider down")), candidate(), "Python", None,
    )
    assert decision == gate.SEMANTIC_REVISE
    assert "not treated as PASS" in reason


def test_semantic_role_accepts_a_valid_pass_for_the_same_skill():
    llm = DecisionLLM(payload={
        "decision": "PASS", "reason": "The activity demonstrates the skill.",
        "skill_id": "S001",
    })
    decision, reason = gate._semantic_assess(llm, candidate(), "Python", None)
    assert decision == gate.SEMANTIC_PASS
    assert "demonstrates" in reason
    assert llm.calls


def test_cv_identity_is_stable_and_distinguishes_content():
    first = gate.cv_identity(1, "Developed a REST API using Python")
    again = gate.cv_identity(1, "  developed   a rest api using python ")
    other = gate.cv_identity(1, "Built a dashboard using Power BI")
    assert first == again
    assert first != other
    assert gate.cv_identity(1, None).startswith("unverified-")


def test_candidate_key_deduplicates_identical_evidence():
    a = gate.candidate_key(1, "cv", "user_projects", 10, "S001", "Built an API")
    b = gate.candidate_key(1, "cv", "user_projects", 10, "S001", "  built an api ")
    c = gate.candidate_key(1, "cv", "user_projects", 10, "S002", "Built an API")
    assert a == b
    assert a != c


def test_skill_mention_uses_word_boundaries():
    assert gate._mentions_skill("Python", "Completed Python Programming certification")
    assert gate._mentions_skill("SQL", "Advanced SQL")
    assert not gate._mentions_skill("R", "React developer")
    assert not gate._mentions_skill("Java", "JavaScript developer")
