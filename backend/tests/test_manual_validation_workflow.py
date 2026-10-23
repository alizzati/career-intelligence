"""Inspection mode against the REAL CareerWorkflow, with the fake agents already used by test_api_analysis.
No DB, no LLM. Proves observer/proxy equivalence and artifact behaviour; NOT real-model quality."""
import json
from types import SimpleNamespace

import pytest

from app.inspection import artifact as art
from app.inspection.recorder import AgentProxy, Recorder
from scripts.manual_validation import RecordingWorkflow, _write_artifact
from tests.test_api_analysis import (
    FakeGapAgent, FakeProfileAgent, FakeRecAgent, FakeRoadmapAgent, FakeVerifier, failing, make_workflow,
)

RAW = "Backend engineer. Email: sinta@example.test Phone: 0812-3456-7890"


def snapshot(state):
    v = state.get("verification")
    return {"final_status": state["final_status"], "revision_count": state["revision_count"],
            "target_career_id": state.get("target_career_id"), "stage": state["stage"],
            "errors": state["errors"], "verification": v.status if v else None,
            "recommendations": [r.career_id for r in (state.get("recommendations") or [])]}


SCENARIOS = {
    "verified": lambda: FakeVerifier(),
    "revision_then_pass": lambda: FakeVerifier([failing("roadmap.gap_coverage"), failing("x", "PASS")]),
    "verifier_error": lambda: FakeVerifier(error=RuntimeError("boom")),
}


def plain(name):
    wf, _ = make_workflow(verification_agent=SCENARIOS[name]())
    return wf.run(user_id=17, raw_profile_text=RAW)


def observed(name, *, proxies=True, observer=True):
    rec, v = Recorder(), SCENARIOS[name]()
    kw = dict(verification_agent=v)
    if proxies:
        kw = dict(profile_agent=AgentProxy(rec, "profile", FakeProfileAgent()),
                  career_recommendation_agent=AgentProxy(rec, "career_recommendation", FakeRecAgent()),
                  skill_gap_agent=AgentProxy(rec, "skill_gap", FakeGapAgent()),
                  learning_roadmap_agent=AgentProxy(rec, "roadmap", FakeRoadmapAgent()),
                  verification_agent=AgentProxy(rec, "verification", v))
    wf, _ = make_workflow(**kw)
    state = wf.run(user_id=17, raw_profile_text=RAW, observer=rec.observer if observer else None)
    return rec, state


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_inspection_does_not_change_the_normal_result(name):
    expected = snapshot(plain(name))
    assert snapshot(observed(name)[1]) == expected                       # proxies + observer
    assert snapshot(observed(name, observer=False)[1]) == expected       # proxies only
    assert snapshot(observed(name, proxies=False)[1]) == expected        # observer only


def test_observer_failure_never_affects_the_run():
    wf, _ = make_workflow()
    def bad(event, payload): raise RuntimeError("observer bug")
    assert snapshot(wf.run(user_id=17, raw_profile_text=RAW, observer=bad)) == snapshot(plain("verified"))


def test_without_observer_the_graph_is_invoked_not_streamed():
    wf, _ = make_workflow()
    real, calls = wf.graph, []
    wf.graph = SimpleNamespace(invoke=lambda s: calls.append("invoke") or real.invoke(s),
                               stream=lambda *a, **k: calls.append("stream") or real.stream(*a, **k))
    wf.run(user_id=17, raw_profile_text=RAW)
    assert calls == ["invoke"]


def test_node_updates_are_actual_and_revision_routing_is_recorded():
    rec, state = observed("revision_then_pass")
    nodes = [e["node"] for e in rec.node_events]
    assert nodes.count("learning_roadmap") == 2 and nodes[0] == "profile_analysis" and nodes[-1] == "final_result"
    assert [r["agent"] for r in rec.agent_runs].count("roadmap") == 2
    ctx = {"final_state": state, "max_revisions": 2}
    assert art.c_order(rec, ctx)["result"] == "PASS"
    assert art.c_final(rec, ctx)["result"] == "PASS"
    assert art.c_verifier_inputs(rec, ctx)["result"] == "PASS"
    artifact = art.build_artifact(rec, {
        "run_id": "revision-run",
        "started_at": "t",
        "mode": "test",
        "mode_label": "offline test double",
        "final_state": state,
        "max_revisions": 2,
    })
    transition = artifact["workflow_execution"]["revision_transitions"][0]
    assert transition["revision_target"] == "roadmap"
    assert transition["verification_checks_requiring_revision"] == [
        {"check": "roadmap.gap_coverage", "status": "FAIL"}
    ]
    assert isinstance(transition["changed_output_fields"], list)


def test_manual_validation_runner_records_real_workflow_node_updates():
    trace = {}
    _, dependencies = make_workflow()
    workflow = RecordingWorkflow(trace=trace, **dependencies)

    result = workflow.run(user_id=17, raw_profile_text=RAW)

    assert result["final_status"] == "VERIFIED"
    nodes = [event["node"] for event in trace["workflow_node_events"]]
    assert nodes == [
        "profile_analysis", "career_recommendation", "skill_gap_analysis",
        "learning_roadmap", "verification", "verification_decision", "final_result",
    ]
    assert RAW not in json.dumps(trace["workflow_node_events"])


def test_artifact_end_to_end_is_serializable_private_and_honest_about_unavailable_evidence(tmp_path):
    rec, state = observed("verified")
    artifact = art.build_artifact(rec, {"run_id": "r", "started_at": "t", "mode": "diagnostic", "mode_label": "L",
                                        "final_state": state, "max_revisions": 2, "input_source": "builtin_synthetic_text"})
    text = json.dumps(artifact)
    assert json.loads(text)["run_metadata"]["verified"] is True
    for secret in ("sinta@example.test", "0812-3456-7890", "Backend engineer."):
        assert secret not in text
    summary = artifact["cross_stage_checks"]["summary"]
    assert "ERROR" not in summary                       # no bug in the inspection tool itself
    results = {c["id"]: c["result"] for c in artifact["cross_stage_checks"]["checks"]}
    assert results["X5"] == "UNAVAILABLE" and results["X3"] == "UNAVAILABLE"   # no KB reads recorded with fakes
    assert results["X7"] in ("UNAVAILABLE", "PASS")
    assert artifact["roadmap_agent"]["executions"][0]["input_actual"]["same_object_as_skill_gap_output"] is True
    path = _write_artifact(artifact, tmp_path)
    assert path.name == "r.json"
    assert json.loads(path.read_text(encoding="utf-8")) == artifact


def test_agent_failure_is_reported_accurately_and_downstream_agents_are_not_claimed():
    rec, state = observed("verifier_error")
    artifact = art.build_artifact(rec, {"run_id": "r", "started_at": "t", "mode": "diagnostic", "mode_label": "L",
                                        "final_state": state, "max_revisions": 2})
    assert state["final_status"] == "ERROR"
    assert artifact["verification_agent"]["executions"][0]["error"]["type"] == "RuntimeError"
    assert artifact["verification_agent"]["executions"][0]["output_agent"] is None
    assert artifact["run_metadata"]["verified"] is False
    assert artifact["final_output"]["errors"][0]["stage"] == "verification"