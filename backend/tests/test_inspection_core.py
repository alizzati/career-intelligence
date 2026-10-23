"""Inspection core tests: no DB, no LLM, no real agents. Fake agents/modules only.
They prove the recorder/serializer/checks behave as designed; they say nothing about real model quality."""
import json
import types
from types import SimpleNamespace as NS

import pytest
from langgraph.graph import END, START, StateGraph
from typing import NotRequired, TypedDict

from app.inspection import artifact as art
from app.inspection.recorder import AgentProxy, Recorder, RecordingLLMClient, to_jsonable


def fake_modules():
    rs = types.ModuleType("app.services.retrieval_service")
    rs.get_all_careers = lambda: [NS(career_id="C1"), NS(career_id="C2")]
    rs.get_career_skills = lambda cid: [NS(skill=NS(skill_id="S1", canonical_name="A"), evidence_class="CORE",
                                           confidence="high", evidence_source_text="kb text")]
    for n in ("get_all_skills", "get_career", "get_occupations_for_career", "get_occupation_competencies",
              "get_skill_evidence", "get_occupational_context"):
        setattr(rs, n, lambda *a, **k: [])
    us = types.ModuleType("app.services.user_service")
    us.get_user_full_profile = lambda uid: NS(skills=[NS(user_skill_id=1, claimed_skill="A", skill_id="S1",
        normalized_skill="A", proficiency=None, evidence_status="none", evidence=[])],
        education=[], experience=[], projects=[], certifications=[])
    for n in ("add_education", "add_experience", "add_project", "add_certification", "add_user_skill", "add_skill_evidence"):
        setattr(us, n, lambda *a, **k: NS(user_skill_id=9))
    return rs, us


def test_to_jsonable_redacts_truncates_and_serializes():
    out = to_jsonable({"a": "mail me at x.y@example.test", "k": "AIzaSyABCDEFGHIJKLMNOPQRSTUV123",
                       "long": "z" * 900, "nested": [NS], "n": float("nan")})
    text = json.dumps(out)
    assert "x.y@example.test" not in text and "AIzaSy" not in text
    assert "truncated" in out["long"] and len(out["long"]) < 700
    json.dumps(out)


def test_proxy_forwards_and_returns_the_identical_object_and_records_io():
    rec, (rs, us) = Recorder(), fake_modules()
    payload = object()

    class Agent:
        llm_client = "x"
        def run(self, user_id):
            rs.get_career_skills("C1"); us.get_user_full_profile(user_id)
            return payload
    proxy = AgentProxy(rec, "skill_gap", Agent())
    with rec.instrument(rs=rs, us=us):
        out = proxy.run(5)
    assert out is payload and proxy.llm_client == "x"
    run = rec.agent_runs[0]
    assert run["raw_output"] is payload and run["raw_args"] == (5,)
    assert [rec.io[i]["function"] for i in run["io_idx"]] == [
        "retrieval_service.get_career_skills", "user_service.get_user_full_profile"]


def test_instrumentation_restores_originals_even_on_exception():
    rec, (rs, us) = Recorder(), fake_modules()
    originals = (rs.get_career_skills, us.add_user_skill)
    with pytest.raises(RuntimeError):
        with rec.instrument(rs=rs, us=us):
            assert rs.get_career_skills is not originals[0]
            raise RuntimeError("boom")
    assert (rs.get_career_skills, us.add_user_skill) == originals


def test_missing_function_becomes_a_warning_not_an_error():
    rec, (rs, us) = Recorder(), fake_modules()
    del rs.get_career
    with rec.instrument(rs=rs, us=us):
        pass
    assert any("get_career" in w for w in rec.warnings)


def test_agent_exception_is_recorded_and_still_propagates():
    rec = Recorder()
    class Bad:
        def run(self):
            raise ValueError("secret@example.test inside message")
    with pytest.raises(ValueError):
        AgentProxy(rec, "profile", Bad()).run()
    err = rec.agent_runs[0]["error"]
    assert err["type"] == "ValueError" and "message" not in err and "origin" in err


def test_exception_messages_and_workflow_error_text_never_enter_trace():
    sentinel = "PRIVATE_EXCEPTION_SENTINEL"
    rec = Recorder()

    class Bad:
        def run(self):
            raise ValueError(sentinel)

    with pytest.raises(ValueError):
        AgentProxy(rec, "profile", Bad()).run()
    rec.observer("node_update", {
        "node": "final_result",
        "update": {"errors": [{"stage": "profile_analysis", "error_type": "ValueError", "message": sentinel}]},
    })

    encoded = json.dumps({"agents": rec.agent_runs, "nodes": rec.node_events})
    assert sentinel not in encoded
    assert "message" not in rec.agent_runs[0]["error"]
    assert rec.node_events[0]["errors"] == [
        {"stage": "profile_analysis", "error_type": "ValueError"}
    ]


def test_llm_recorder_stores_no_text_and_keeps_error_codes():
    rec = Recorder()
    class Inner:
        model = "m"
        def __init__(self): self.calls = []
        def complete_json(self, system, user, max_tokens=2000):
            self.calls.append(max_tokens)
            if "boom429" in user:
                e = Exception("quota"); e.code = 429; e.status = "RESOURCE_EXHAUSTED"; raise e
            if "badjson" in user:
                json.loads('{"a": "unterminated')
            return {"summary": "TOP SECRET RESPONSE TEXT"}
    inner = Inner(); llm = RecordingLLMClient(inner, rec)
    system = "You are an information-extraction component in a career system"
    llm.complete_json(system=system, user="PRIVATE CV TEXT")
    with pytest.raises(Exception):
        llm.complete_json(system=system, user="boom429", max_tokens=300)
    with pytest.raises(json.JSONDecodeError):
        llm.complete_json(system=system, user="badjson")
    dump = json.dumps(rec.llm)
    assert "PRIVATE CV TEXT" not in dump and "TOP SECRET" not in dump
    assert inner.calls == [2000, 300, 2000]                    # default left to the client, not forced
    assert rec.llm[0]["max_tokens"] is None and "default" in rec.llm[0]["max_tokens_source"]
    assert rec.llm[0]["prompt_id"] == "profile_extraction" and rec.llm[0]["response"]["top_level_keys"] == ["summary"]
    assert rec.llm[1]["error"]["code"] == 429 and rec.llm[1]["error"]["status"] == "RESOURCE_EXHAUSTED"
    assert rec.llm[2]["error"]["type"] == "JSONDecodeError" and rec.llm[2]["error"]["json_error_position"]["char"] > 0


# --- observer logic copied from CareerWorkflow._invoke_observed (the real class is not importable here)
def invoke_observed(graph, initial_state, observer):
    final_state = None
    for mode, chunk in graph.stream(initial_state, stream_mode=["updates", "values"]):
        if mode == "values":
            final_state = chunk
        elif mode == "updates" and isinstance(chunk, dict):
            for node_name, update in chunk.items():
                try:
                    observer("node_update", {"node": node_name, "update": update})
                except Exception:
                    pass
    if final_state is None:
        raise RuntimeError("no state")
    return final_state


class S(TypedDict):
    user_id: int
    revision_count: int
    final_status: str
    stage: str
    errors: list
    secret: NotRequired[str]


def toy_graph():
    g = StateGraph(S)
    g.add_node("a", lambda s: {"stage": "a", "final_status": "RUNNING"})
    g.add_node("decide", lambda s: ({"stage": "rev", "revision_count": s["revision_count"] + 1}
                                    if s["revision_count"] < 1 else {"stage": "x", "final_status": "VERIFIED"}))
    g.add_node("fin", lambda s: {"stage": "final_result"})
    g.add_edge(START, "a"); g.add_edge("a", "decide")
    g.add_conditional_edges("decide", lambda s: "fin" if s["final_status"] == "VERIFIED" else "a", {"fin": "fin", "a": "a"})
    g.add_edge("fin", END)
    return g.compile()


def test_observed_stream_equals_invoke_and_observer_errors_do_not_matter():
    init = {"user_id": 1, "revision_count": 0, "final_status": "RUNNING", "stage": "start", "errors": [], "secret": "s"}
    g = toy_graph()
    seen = []
    assert invoke_observed(g, dict(init), lambda e, p: seen.append(p["node"])) == g.invoke(dict(init))
    assert seen == ["a", "decide", "a", "decide", "fin"]
    def bad(e, p): raise RuntimeError("observer bug")
    assert invoke_observed(g, dict(init), bad) == g.invoke(dict(init))


# --- artifact + checks with fake agent outputs
def ev(rec, node, **kw):
    rec.node_events.append({"seq": len(rec.node_events) + 1, "node": node, "attempt": 1, "t_ms": 0,
        "update_keys": [], "stage": None, "final_status": kw.get("final_status", "RUNNING"),
        "revision_count": kw.get("revision_count"), "revision_target": kw.get("revision_target"),
        "target_career_id": None, "errors": [], "agent_run_seqs": []})


def ctx(**over):
    base = {"run_id": "r", "started_at": "t", "mode": "diagnostic", "mode_label": "L",
            "final_state": {"final_status": "VERIFIED", "revision_count": 0, "target_career_id": "C1", "errors": []},
            "max_revisions": 2}
    base.update(over)
    return base


def by_id(report):
    return {c["id"]: c for c in report["checks"]}


def test_checks_without_evidence_are_not_reported_as_pass():
    rec = Recorder()
    report = art.run_checks(rec, ctx())
    assert "PASS" not in {c["result"] for c in report["checks"]}
    assert by_id(report)["X9"]["result"] == "UNAVAILABLE"


def test_execution_order_check_detects_wrong_routing_and_accepts_valid_loop():
    good = Recorder()
    for n, kw in [("profile_analysis", {}), ("career_recommendation", {}), ("skill_gap_analysis", {}),
                  ("learning_roadmap", {}), ("verification", {}),
                  ("verification_decision", {"revision_count": 1, "revision_target": "roadmap"}),
                  ("learning_roadmap", {}), ("verification", {}),
                  ("verification_decision", {"final_status": "VERIFIED"}), ("final_result", {})]:
        ev(good, n, **kw)
    assert art.c_order(good, ctx(final_state={"final_status": "VERIFIED", "revision_count": 1}))["result"] == "PASS"
    bad = Recorder()
    for n in ("profile_analysis", "skill_gap_analysis"):
        ev(bad, n)
    assert art.c_order(bad, ctx())["result"] == "FAIL"


def test_score_check_fails_when_agent_output_disagrees_with_calculator_call():
    rec, (rs, us) = Recorder(), fake_modules()
    gap_obj = NS(fit_score=0.9, career_id="C1")
    rec_out = [NS(career_id="C1", fit_score=0.5)]
    rec.agent_runs += [{"agent": "career_recommendation", "raw_output": rec_out, "raw_args": (), "error": None, "seq": 1},
                       {"agent": "skill_gap", "raw_output": NS(skill_gap=gap_obj), "raw_args": (), "error": None, "seq": 2}]
    with rec.instrument(rs=rs, us=us):
        rs.get_career_skills("C1")
    for stage in ("career_recommendation", "skill_gap", "verification"):
        rec.computations.append({"stage": stage, "required_ids": ["S1"], "fit_score": 0.5})
    r = art.c_scores(rec, ctx())
    assert r["result"] == "FAIL" and "skill-gap fit_score" in r["detail"][0]
    gap_obj.fit_score = 0.5
    assert art.c_scores(rec, ctx())["result"] == "PASS"


def test_artifact_is_json_roundtrippable_and_contains_no_sensitive_text():
    rec, (rs, us) = Recorder(), fake_modules()
    class P:
        def run(self, user_id, raw_profile_text):
            return NS(extracted={"skills": [{"claimed_skill": "mail a.b@example.test"}]}, normalizations=[],
                      skills_persisted=1, evidence_persisted=0)
    cv = "SECRET CV BODY about Jane, phone 0812-5555-0100"
    with rec.instrument(rs=rs, us=us):
        AgentProxy(rec, "profile", P()).run(7, cv)
    artifact = art.build_artifact(rec, ctx(input_source="cv_file",
                                           final_state={"final_status": "ERROR", "errors": [{"stage": "x", "error_type": "E", "message": "n"}]}))
    text = json.dumps(artifact)
    assert json.loads(text)["schema_version"] == art.SCHEMA_VERSION
    for secret in ("a.b@example.test", "SECRET CV BODY", "0812-5555-0100"):
        assert secret not in text
    assert artifact["profile_agent"]["executed"] is True
    assert artifact["skill_gap_agent"] == {"executed": False, "reason": "not reached: an earlier stage ended with ERROR"}
    assert artifact["profile_agent"]["executions"][0]["input_actual"]["redacted_text"]["chars"] == len(cv)


def test_artifact_runtime_provenance_and_payload_fingerprints_are_explicit_and_private():
    rec = Recorder()
    claim_sentinel = "CLAIM_PRIVATE_SENTINEL"
    profile_sentinel = "PROFILE_PRIVATE_SENTINEL"

    class Profile:
        def run(self, user_id, raw_profile_text):
            return NS(
                extracted={
                    "skills": [{"claimed_skill": claim_sentinel, "candidate_skill_id": None}],
                    "education": [{"institution": profile_sentinel}],
                },
                normalizations=[],
                skills_persisted=0,
                evidence_persisted=0,
            )

    class FakeLLM:
        model_name = "FakeModelForTests"

        def complete_json(self, system, user, max_tokens=2000):
            return {"summary": "PRIVATE_LLM_RESPONSE_SENTINEL"}

    client = RecordingLLMClient(FakeLLM(), rec)
    client.complete_json(
        system="You are an information-extraction component",
        user="PRIVATE_PROMPT_SENTINEL",
        max_tokens=91,
    )
    AgentProxy(rec, "profile", Profile()).run(7, "PRIVATE_CV_SENTINEL")
    context = ctx(
        llm_client=client,
        git_commit="a" * 40,
        input_document={
            "format": "txt",
            "size_bytes": 42,
            "sha256": "b" * 64,
            "filename": "PRIVATE_FILENAME_SENTINEL",
        },
        final_state={
            "final_status": "ERROR",
            "revision_count": 0,
            "target_career_id": None,
            "errors": [{"stage": "profile_analysis", "error_type": "ValueError",
                        "message": "PRIVATE_WORKFLOW_ERROR_SENTINEL"}],
        },
    )

    artifact = art.build_artifact(rec, context)
    encoded = json.dumps(artifact)
    for sentinel in (
        claim_sentinel,
        profile_sentinel,
        "PRIVATE_LLM_RESPONSE_SENTINEL",
        "PRIVATE_PROMPT_SENTINEL",
        "PRIVATE_CV_SENTINEL",
        "PRIVATE_WORKFLOW_ERROR_SENTINEL",
        "PRIVATE_FILENAME_SENTINEL",
    ):
        assert sentinel not in encoded

    metadata = artifact["run_metadata"]
    assert metadata["git_commit"] == "a" * 40
    assert metadata["input_document"] == {
        "format": "txt",
        "size_bytes": 42,
        "sha256": "b" * 64,
    }
    assert metadata["llm_runtime"]["provider"] == "test_double"
    assert metadata["llm_runtime"]["model"] == "FakeModelForTests"
    assert metadata["llm_runtime"]["sdk"]["used_by_run"] is False
    assert metadata["llm_runtime"]["generation_settings"]["value"].startswith("unavailable")
    assert metadata["per_call_token_limits"] == [{
        "stage": "workflow",
        "prompt_id": "profile_extraction",
        "max_tokens": 91,
        "source": "passed by agent",
    }]
    assert len(metadata["prompt_identities"][0]["prompt_sha256"]) == 64
    assert len(metadata["prompt_identities"][0]["system_prompt_sha256"]) == 64
    assert metadata["kb_version"].startswith("unavailable")
    assert artifact["profile_agent"]["executions"][0]["output_agent"]["extracted_summary"]["item_counts"] == {
        "skills": 1,
        "education": 1,
    }
    assert artifact["final_output"]["errors"] == [
        {"stage": "profile_analysis", "error_type": "ValueError"}
    ]


def test_gemini_runtime_metadata_uses_runtime_model_and_marks_sdk_defaults_unpinned():
    from app.agents.llm_client import GeminiClient

    client = GeminiClient.__new__(GeminiClient)
    client.model = "synthetic-configured-model"
    info = art._llm_runtime(client)

    assert info["provider"] == "google_genai"
    assert info["model"] == "synthetic-configured-model"
    assert info["sdk"]["package"] == "google-genai"
    assert info["sdk"]["used_by_run"] is True
    assert info["generation_settings"]["max_output_tokens"]["source"] == "explicit"
    assert info["generation_settings"]["temperature"]["source"].startswith("SDK default")
    assert info["sdk_retries"].startswith("unavailable")