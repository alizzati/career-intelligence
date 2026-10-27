"""Contract, privacy, and static-runner tests. Offline: in-memory KB/users, scripted LLM test double."""
import ast
import copy
import json
from pathlib import Path

import pytest

from app.inspection.contract import validate_artifact
from scripts import manual_validation
from tests.test_inspection_integration import (  # noqa: F401  (memory is a pytest fixture)
    REQUIRED, SENTINELS, FailOnceVerifier, FakeScriptedLLM, memory, run_inspected)

W = {"core_weight": 1.0, "supporting_weight": 0.5, "claim_only_multiplier": 0.5,
     "confidence_multiplier": {"high": 1.0, "medium": 0.85, "low": 0.7}, "proficiency_modifier": 0.1}
RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "manual_validation.py"

# Real LLM-client import/invocation paths. A plain string such as "google-genai" (used with
# importlib.metadata.version() to record the installed SDK version) is NOT one of them.
_FORBIDDEN_MODULE_ROOTS = frozenset({"google", "anthropic", "openai", "genai"})
_FORBIDDEN_MODULES = ("app.agents.llm_client",)
_FORBIDDEN_NAMES = frozenset({"GeminiClient", "get_llm_client", "genai"})
_DYNAMIC_IMPORTS = frozenset({"import_module", "__import__"})


def forbidden_llm_references(source: str) -> list[str]:
    """Static check for actual LLM-client imports / invocation paths. Returns rule names + line
    numbers only (never source text)."""
    found: list[str] = []

    def bad_module(name: str) -> bool:
        return (name.split(".")[0] in _FORBIDDEN_MODULE_ROOTS
                or any(name == m or name.startswith(m + ".") for m in _FORBIDDEN_MODULES))

    for node in ast.walk(ast.parse(source)):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Import):
            found += [f"line {line}: import of forbidden module" for a in node.names if bad_module(a.name)]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if bad_module(module):
                found.append(f"line {line}: import from forbidden module")
            for alias in node.names:
                if alias.name in _FORBIDDEN_NAMES or bad_module(f"{module}.{alias.name}".strip(".")):
                    found.append(f"line {line}: import of forbidden name")
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            found.append(f"line {line}: use of forbidden name")
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_NAMES:
            found.append(f"line {line}: use of forbidden attribute")
        elif isinstance(node, ast.Call):
            func = node.func
            called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if called in _DYNAMIC_IMPORTS:
                found.append(f"line {line}: dynamic import call")
    return found


def sql_statements(source: str) -> list[str]:
    statements = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "text" and node.args:
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                statements.append(arg.value)
            elif isinstance(arg, ast.JoinedStr):
                statements.append("".join(v.value if isinstance(v, ast.Constant) else "{}" for v in arg.values))
            else:
                pytest.fail("runner builds SQL dynamically in a way this guard cannot inspect")
    return statements


def independent_score(required, skills, weights):
    """Hand transcription of the documented arithmetic; imports no production scoring code."""
    total_w = total_c = 0.0
    for r in required:
        base = weights["core_weight"] if r.evidence_class.upper() == "CORE" else weights["supporting_weight"]
        w = base * weights["confidence_multiplier"].get(r.confidence, 1.0)
        total_w += w
        matches = [s for s in skills if s.skill_id == r.skill.skill_id]
        linked = [s for s in matches if s.evidence_status == "linked"]
        pick = linked[0] if linked else (matches[0] if matches else None)
        if pick is None:
            continue
        c = w if pick.evidence_status == "linked" else w * weights["claim_only_multiplier"]
        if pick.proficiency and pick.proficiency.strip().lower() not in ("", "unspecified", "none"):
            c = min(c * (1 + weights["proficiency_modifier"]), w)
        total_c += c
    return total_c / total_w if total_w else 0.0


def test_success_artifact_satisfies_contract_and_is_strict_json(memory):
    artifact, state, _ = run_inspected(memory, FakeScriptedLLM())
    assert state["final_status"] == "VERIFIED"
    assert validate_artifact(artifact, forbidden=SENTINELS) == []
    json.dumps(artifact, allow_nan=False)


def test_revision_artifact_satisfies_contract(memory):
    artifact, state, _ = run_inspected(memory, FakeScriptedLLM(), wrap_verifier=FailOnceVerifier)
    assert state["revision_count"] == 1
    # individual cross-stage verdicts are asserted in test_inspection_integration; here: structure/privacy
    assert validate_artifact(artifact, forbidden=SENTINELS, allow_failed_checks=True) == []


def test_failure_artifact_is_valid_diagnostic_and_not_marked_successful(memory):
    artifact, state, _ = run_inspected(memory, FakeScriptedLLM(fail_extraction=True))
    assert state["final_status"] == "ERROR"
    assert validate_artifact(artifact, forbidden=SENTINELS) == []
    assert artifact["run_metadata"]["verified"] is False
    assert artifact["profile_agent"]["executions"][0]["error"]["type"] == "RuntimeError"
    assert artifact["skill_gap_agent"]["executed"] is False


def test_provenance_marks_unknowns_explicitly(memory):
    artifact, _, _ = run_inspected(memory, FakeScriptedLLM())
    meta = artifact["run_metadata"]
    assert meta["llm_runtime"]["provider"] == "test_double"
    assert meta["kb_version"].startswith("unavailable")
    assert meta["kb_unchanged"] == "unavailable"
    assert meta["git_commit"] == "unavailable"
    assert artifact["independent_reference_checks"] == "unavailable"


def test_contract_requires_the_isolated_database_identity(memory):
    artifact, _, _ = run_inspected(memory, FakeScriptedLLM())
    assert validate_artifact(artifact) == []

    def mutated(change):
        broken = copy.deepcopy(artifact)
        change(broken["run_metadata"])
        return validate_artifact(broken)

    assert mutated(lambda m: m.pop("database"))
    assert mutated(lambda m: m["database"].update(name="career_intelligence",
                                                  server_current_database="career_intelligence"))
    assert mutated(lambda m: m["database"].update(server_current_database="career_intelligence"))
    assert mutated(lambda m: m["database"].update(host="192.168.1.10"))
    assert mutated(lambda m: m["database"].update(port="5433"))
    assert mutated(lambda m: m["database"].update(username="postgres"))


def test_contract_requires_a_reproducible_digest_for_a_dirty_tree(memory):
    artifact, _, _ = run_inspected(memory, FakeScriptedLLM())
    assert validate_artifact(artifact) == []                    # clean/unavailable is explicit

    dirty = copy.deepcopy(artifact)
    dirty["run_metadata"].update(git_commit="a" * 40, git_dirty=True, git_diff_sha256="b" * 64)
    assert validate_artifact(dirty) == []

    missing_digest = copy.deepcopy(dirty)
    missing_digest["run_metadata"]["git_diff_sha256"] = None
    assert validate_artifact(missing_digest)

    clean_with_digest = copy.deepcopy(dirty)
    clean_with_digest["run_metadata"].update(git_dirty=False)
    assert validate_artifact(clean_with_digest)


def test_runner_verdict_fails_when_the_artifact_contract_fails(memory):
    artifact, _, _ = run_inspected(memory, FakeScriptedLLM())
    ok, summary, violations = manual_validation._final_verdict(
        artifact, harness_error=None, independent=[])
    assert ok and violations == [] and "FAIL" not in summary

    broken = copy.deepcopy(artifact)
    broken.pop("run_metadata")
    ok, _, violations = manual_validation._final_verdict(
        broken, harness_error=None, independent=[])
    assert ok is False and violations


def test_fit_scores_in_artifact_match_independent_recomputation_with_documented_weights(memory):
    artifact, _, _ = run_inspected(memory, FakeScriptedLLM())
    assert artifact["run_metadata"]["scoring_weights"] == W
    ranked = artifact["career_recommendation_agent"]["executions"][0]["output_agent"]["ranked"]
    assert {r["career_id"] for r in ranked} == set(REQUIRED)
    for r in ranked:
        expected = independent_score(REQUIRED[r["career_id"]], memory.skills, W)
        assert abs(expected - r["fit_score"]) <= 5e-5 + 1e-9   # score is round(exact, 4)


def test_contract_detects_each_class_of_violation(memory):
    base, _, _ = run_inspected(memory, FakeScriptedLLM())

    def violations(mutate):
        copy_ = copy.deepcopy(base)
        mutate(copy_)
        return validate_artifact(copy_)

    assert violations(lambda a: a.pop("run_metadata"))
    assert violations(lambda a: a["final_output"].update(extra={"bad key!": 1}))
    assert violations(lambda a: a["run_metadata"].update(note="mail me at x@example.test"))
    assert violations(lambda a: a["run_metadata"]["prompt_identities"][0].update(prompt_sha256="12345678"))
    assert violations(lambda a: a["profile_agent"]["executions"][0].update(
        error={"type": "E", "message": "leak"}))
    assert violations(lambda a: a["run_metadata"].update(verified=False))
    assert violations(lambda a: a["run_metadata"].update(
        harness_error=[{"stage": "harness", "error_type": "X"}]))
    assert violations(lambda a: a.update(execution_trace=a["execution_trace"][1:]))
    assert violations(lambda a: a["run_metadata"].update(kb_version=None))


def test_llm_reference_checker_flags_real_client_paths_and_ignores_sdk_version_strings():
    # Positive controls: each real client import/invocation path must be flagged.
    for snippet in (
        "from google import genai",
        "import google.genai",
        "from google.genai import types",
        "import anthropic",
        "import openai",
        "from app.agents.llm_client import GeminiClient",
        "from app.agents import llm_client",
        "from app.api.dependencies import get_llm_client",
        "client = GeminiClient()",
        "x = module.GeminiClient",
        "c = genai.Client(api_key=k)",
        "m = importlib.import_module('google.genai')",
        "m = __import__('anthropic')",
    ):
        assert forbidden_llm_references(snippet), snippet
    # Negative controls: recording the installed SDK version is not a client import/invocation.
    for snippet in (
        "from importlib import metadata\nv = metadata.version('google-genai')",
        "versions = {'python': '3', 'google_genai_sdk': v}",
        "from app.agents.profile_agent import ProfileAgent",
        "from app.api.dependencies import get_workflow",
    ):
        assert forbidden_llm_references(snippet) == [], snippet


_ALLOWED_RUNNER_DELETES = frozenset({
    "DELETE FROM user_skill_evidence WHERE user_skill_id IN "
    "(SELECT user_skill_id FROM user_skills WHERE user_id = :user_id)",
    "DELETE FROM user_skills WHERE user_id = :user_id",
    "DELETE FROM user_preferences WHERE user_id = :user_id",
    "DELETE FROM user_education WHERE user_id = :user_id",
    "DELETE FROM user_experience WHERE user_id = :user_id",
    "DELETE FROM user_projects WHERE user_id = :user_id",
    "DELETE FROM user_certifications WHERE user_id = :user_id",
    "DELETE FROM user_profiles WHERE user_id = :user_id",
    "DELETE FROM users WHERE user_id = :user_id",
})


def test_runner_sql_is_read_only_except_exact_cleanup_deletes_and_it_has_no_llm_client():
    source = RUNNER.read_text(encoding="utf-8")
    statements = sql_statements(source)
    assert statements
    deletes = set()
    for statement in statements:
        normalized = " ".join(statement.split())
        if normalized.upper().startswith("SELECT "):
            continue
        assert normalized in _ALLOWED_RUNNER_DELETES, normalized
        deletes.add(normalized)
    # The cleanup plan must cover every user-table write in user_repository.py.
    assert "DELETE FROM users WHERE user_id = :user_id" in deletes
    assert "DELETE FROM user_skills WHERE user_id = :user_id" in deletes
    assert "DELETE FROM user_skill_evidence WHERE user_skill_id IN " \
           "(SELECT user_skill_id FROM user_skills WHERE user_id = :user_id)" in deletes
    assert 'if __name__ == "__main__"' in source
    assert forbidden_llm_references(source) == []