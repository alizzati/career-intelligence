"""Focused offline tests for the X2 profile-consistency check.

Synthetic profiles and a hand-built Recorder only: no database, no LLM, no workflow run.
"""
from datetime import datetime

import pytest

from app.inspection import artifact as art
from app.inspection.recorder import Recorder
from app.schemas.user import (
    UserFullProfileOut, UserOut, UserSkillEvidenceOut, UserSkillOut,
)


def _skill(**overrides):
    data = {
        "user_skill_id": 1,
        "claimed_skill": "Synthetic Claim",
        "skill_id": "S001",
        "normalized_skill": "Synthetic Skill",
        "proficiency": "intermediate",
        "evidence_status": "linked",
        "confidence": "unknown",
        "evidence": [UserSkillEvidenceOut(evidence_id=1, evidence_type="project")],
    }
    data.update(overrides)
    return UserSkillOut(**data)


def _profile(skills):
    return UserFullProfileOut(
        user=UserOut(user_id=1, email="synthetic@example.invalid",
                     full_name="Synthetic User", created_at=datetime(2026, 1, 1)),
        skills=list(skills),
    )


def _recorder(reads, *, profile_run=None, write_seqs=(), extra_profile_runs=()):
    """Build the recorder structures X2 reads: raw_io reads, io writes, agent-run io links.

    ``extra_profile_runs`` is a sequence of ``(run_seq, write_seqs)`` pairs and is only used to
    document the latest-run cutoff when the Profile Agent is recorded more than once.
    """
    rec = Recorder()
    rec.raw_io = [
        {"seq": seq, "function": "get_user_full_profile", "stage": stage, "nested": False,
         "args": (1,), "kwargs": {}, "result": result}
        for seq, stage, result in reads
    ]
    rec.io, io_idx = [], []

    def add_writes(sequences):
        indices = []
        for seq in sequences:
            indices.append(len(rec.io))
            rec.io.append({"seq": seq, "stage": "profile", "category": "db_write",
                           "function": "user_service.add_user_skill", "nested": False,
                           "args": None, "result": None, "error": None})
        return indices

    rec.agent_runs = []
    if profile_run is not None:
        rec.agent_runs.append({"agent": "profile", "seq": profile_run,
                               "io_idx": add_writes(write_seqs)})
    for run_seq, sequences in extra_profile_runs:
        rec.agent_runs.append({"agent": "profile", "seq": run_seq,
                               "io_idx": add_writes(sequences)})
    return rec


def test_x2_passes_after_ignoring_pre_persistence_read():
    empty, populated = _profile([]), _profile([_skill()])
    rec = _recorder(
        [(1, "workflow", empty),
         (6, "career_recommendation", populated),
         (7, "skill_gap", populated),
         (8, "verification", populated)],
        profile_run=2, write_seqs=(3, 4, 5),
    )

    result = art.c_profile_views(rec, {"post_run_profile": populated})

    assert result["result"] == "PASS"
    assert result["compared"]["persistence_cutoff_seq"] == 5
    assert result["compared"]["ignored_pre_persistence_reads"] == [
        {"seq": 1, "stage": "workflow"}]
    assert result["compared"]["reads_by_stage"] == {
        "career_recommendation": 1, "skill_gap": 1, "verification": 1, "post_run": 1}


def test_x2_uses_profile_run_seq_when_no_writes_recorded():
    populated = _profile([_skill()])
    rec = _recorder(
        [(1, "workflow", _profile([])),
         (4, "career_recommendation", populated),
         (5, "skill_gap", populated)],
        profile_run=3,
    )

    result = art.c_profile_views(rec, {"post_run_profile": populated})

    assert result["result"] == "PASS"
    assert result["compared"]["persistence_cutoff_seq"] == 3
    assert result["compared"]["ignored_pre_persistence_reads"] == [
        {"seq": 1, "stage": "workflow"}]


def test_x2_uses_latest_profile_agent_run_cutoff():
    empty, populated = _profile([]), _profile([_skill()])
    rec = _recorder(
        [(1, "workflow", empty),
         (5, "career_recommendation", empty),   # after the first profile run, before the second
         (8, "skill_gap", populated),
         (9, "verification", populated)],
        profile_run=2, write_seqs=(3, 4),
        extra_profile_runs=[(6, (7,))],
    )

    result = art.c_profile_views(rec, {"post_run_profile": populated})

    assert result["result"] == "PASS"
    assert result["compared"]["persistence_cutoff_seq"] == 7
    assert result["compared"]["ignored_pre_persistence_reads"] == [
        {"seq": 1, "stage": "workflow"},
        {"seq": 5, "stage": "career_recommendation"}]
    assert result["compared"]["reads_by_stage"] == {
        "skill_gap": 1, "verification": 1, "post_run": 1}


def test_x2_passes_with_two_distinct_agents_after_persistence():
    populated = _profile([_skill()])
    rec = _recorder(
        [(1, "workflow", _profile([])),
         (6, "career_recommendation", populated),
         (7, "skill_gap", populated)],
        profile_run=2, write_seqs=(3, 4, 5),
    )

    result = art.c_profile_views(rec, {"post_run_profile": populated})

    assert result["result"] == "PASS"
    assert result["compared"]["reads_by_stage"] == {
        "career_recommendation": 1, "skill_gap": 1, "post_run": 1}


def test_x2_unavailable_when_two_reads_come_from_the_same_agent():
    populated = _profile([_skill()])
    rec = _recorder(
        [(1, "workflow", _profile([])),
         (6, "career_recommendation", populated),
         (7, "career_recommendation", populated)],
        profile_run=2, write_seqs=(3, 4, 5),
    )

    result = art.c_profile_views(rec, {"post_run_profile": populated})

    assert result["result"] == "UNAVAILABLE"
    assert result["detail"] == (
        "fewer than two distinct workflow agents read the profile after persistence")
    assert result["compared"]["reads_by_stage"] == {
        "career_recommendation": 2, "post_run": 1}


def test_x2_unavailable_when_post_run_is_the_only_second_read():
    populated = _profile([_skill()])
    rec = _recorder(
        [(1, "workflow", _profile([])),
         (6, "career_recommendation", populated)],
        profile_run=2, write_seqs=(3, 4, 5),
    )

    result = art.c_profile_views(rec, {"post_run_profile": populated})

    assert result["result"] == "UNAVAILABLE"
    assert result["compared"]["reads_by_stage"] == {
        "career_recommendation": 1, "post_run": 1}


def test_x2_ignores_post_persistence_read_with_none_result():
    """The contract defines no rule for a read that returned no profile.

    Existing behaviour is preserved: such a read is neither compared nor counted, and the
    post-run snapshot still does not count as a second agent read.
    """
    populated = _profile([_skill()])
    rec = _recorder(
        [(1, "workflow", _profile([])),
         (6, "career_recommendation", populated),
         (7, "skill_gap", None)],
        profile_run=2, write_seqs=(3, 4, 5),
    )

    result = art.c_profile_views(rec, {"post_run_profile": populated})

    assert result["result"] == "UNAVAILABLE"
    assert result["compared"]["reads_by_stage"] == {
        "career_recommendation": 1, "post_run": 1}
    assert result["compared"]["ignored_pre_persistence_reads"] == [
        {"seq": 1, "stage": "workflow"}]


@pytest.mark.parametrize("overrides", [
    {"skill_id": "S002"},
    {"evidence_status": "none"},
    {"proficiency": None},
    {"evidence": []},
])
def test_x2_fails_on_meaningful_post_persistence_difference(overrides):
    populated, changed = _profile([_skill()]), _profile([_skill(**overrides)])
    rec = _recorder(
        [(1, "workflow", _profile([])),
         (6, "career_recommendation", populated),
         (7, "skill_gap", populated),
         (8, "verification", changed)],
        profile_run=2, write_seqs=(3, 4, 5),
    )

    result = art.c_profile_views(rec, {"post_run_profile": populated})

    assert result["result"] == "FAIL"
    assert result["detail"] == "profile signature differs between reads"


def test_x2_keeps_workflow_read_when_no_profile_agent_run():
    populated = _profile([_skill()])
    rec = _recorder(
        [(1, "workflow", populated),
         (2, "workflow", populated),
         (3, "career_recommendation", populated),
         (4, "skill_gap", populated)],
    )

    result = art.c_profile_views(rec, {"post_run_profile": populated})

    assert result["result"] == "PASS"
    assert result["compared"]["persistence_cutoff_seq"] is None
    assert result["compared"]["ignored_pre_persistence_reads"] == []
    assert result["compared"]["reads_by_stage"]["workflow"] == 2


def test_x2_detects_workflow_read_difference_when_no_profile_agent_run():
    populated, changed = _profile([_skill()]), _profile([_skill(skill_id="S002")])
    rec = _recorder(
        [(1, "workflow", populated),
         (2, "workflow", changed),
         (3, "career_recommendation", populated),
         (4, "skill_gap", populated)],
    )

    result = art.c_profile_views(rec, {"post_run_profile": populated})

    assert result["result"] == "FAIL"


def test_x2_unavailable_when_fewer_than_two_comparable_reads():
    populated = _profile([_skill()])
    rec = _recorder(
        [(1, "workflow", _profile([])),
         (6, "career_recommendation", populated)],
        profile_run=2, write_seqs=(3, 4, 5),
    )

    result = art.c_profile_views(rec, {"post_run_profile": None})

    assert result["result"] == "UNAVAILABLE"
    assert result["compared"]["ignored_pre_persistence_reads"] == [
        {"seq": 1, "stage": "workflow"}]
