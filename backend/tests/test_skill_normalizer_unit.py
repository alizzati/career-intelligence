"""
Pure unit tests for skill_normalizer.py. No DB connection, no LLM, no
network. Run: python -m tests.test_skill_normalizer_unit
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.skill_normalizer import normalize_skill

CATALOG = [
    {"skill_id": "S009", "canonical_name": "CI/CD"},
    {"skill_id": "S065", "canonical_name": "Programming"},
    {"skill_id": "S035", "canonical_name": "Database Management"},
    {"skill_id": "S060", "canonical_name": "OOP"},
]


def main():
    print("=== exact match (case/whitespace-insensitive) ===")
    r = normalize_skill("  database management  ", CATALOG)
    print(f"  {r}")
    assert r.method == "exact-deterministic" and r.skill_id == "S035"

    print("\n=== fuzzy match ===")
    r = normalize_skill("Programing", CATALOG)  # typo
    print(f"  {r}")
    assert r.method == "fuzzy-deterministic" and r.skill_id == "S065"

    print("\n=== no deterministic match, no LLM suggestion -> unmatched ===")
    r = normalize_skill("Quantum Computing", CATALOG)
    print(f"  {r}")
    assert r.method == "unmatched" and r.skill_id is None

    print("\n=== no deterministic match, VALID LLM suggestion -> llm-assisted ===")
    r = normalize_skill("continuous delivery pipelines", CATALOG, llm_suggested_skill_id="S009")
    print(f"  {r}")
    assert r.method == "llm-assisted" and r.skill_id == "S009"

    print("\n=== no deterministic match, HALLUCINATED LLM suggestion (not in catalog) -> discarded, unmatched ===")
    r = normalize_skill("blockchain governance", CATALOG, llm_suggested_skill_id="S999_DOES_NOT_EXIST")
    print(f"  {r}")
    assert r.method == "unmatched" and r.skill_id is None, \
        "REGRESSION: a hallucinated skill_id leaked through the normalizer"

    print("\nALL SKILL NORMALIZER UNIT TESTS PASSED.")


def test_normalizer_diagnostics_cover_exact_fuzzy_unmatched_and_ambiguous():
    exact = normalize_skill(" database management ", CATALOG)
    assert exact.outcome == "matched" and exact.exact_match is True
    assert exact.fuzzy_candidates[0].similarity == 1.0

    fuzzy = normalize_skill("Programing", CATALOG)
    assert fuzzy.outcome == "matched" and fuzzy.method == "fuzzy-deterministic"
    assert fuzzy.fuzzy_candidates[0].skill_id == "S065"
    assert fuzzy.fuzzy_candidates[0].meets_threshold is True
    assert fuzzy.fuzzy_candidates[0].similarity == fuzzy.score

    unmatched = normalize_skill("Quantum Computing", CATALOG)
    assert unmatched.outcome == "unmatched"
    assert unmatched.skill_id is None
    assert unmatched.fuzzy_candidates
    assert all(not candidate.meets_threshold for candidate in unmatched.fuzzy_candidates)

    ambiguous_catalog = [
        {"skill_id": "S-A", "canonical_name": "abcdefghijklmnopq"},
        {"skill_id": "S-B", "canonical_name": "abcdefghijklmnopr"},
    ]
    ambiguous = normalize_skill("abcdefghijklmnopx", ambiguous_catalog)
    assert ambiguous.outcome == "ambiguous"
    assert ambiguous.skill_id is None
    assert len(ambiguous.fuzzy_candidates) >= 2
    assert ambiguous.fuzzy_candidates[0].similarity >= 0.88
    assert ambiguous.fuzzy_candidates[0].similarity == ambiguous.fuzzy_candidates[1].similarity


if __name__ == "__main__":
    main()
