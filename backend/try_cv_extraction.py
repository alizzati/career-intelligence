"""Manual check of CV reading + extraction. Writes nothing to the database.

  python try_cv_extraction.py path\\to\\cv.pdf          # stage 1 only, no LLM call
  python try_cv_extraction.py path\\to\\cv.pdf --llm    # + stage 2, ONE Gemini call
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())  # run from backend/

from app.services.cv_text_extraction_service import CVTextExtractionError, CVTextExtractor
from app.services.pii_redaction_service import redact_pii, redact_structured_value


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    use_llm = "--llm" in sys.argv
    if not args:
        print(__doc__)
        return 2
    path = args[0]
    with open(path, "rb") as f:
        content = f.read()

    print("=== STAGE 1: text extraction ===")
    try:
        result = CVTextExtractor().extract(content, os.path.basename(path))
    except CVTextExtractionError as exc:
        print(f"REJECTED: code={exc.code} | {exc}")
        return 1
    m = result.metadata
    print(f"format={m.format} size={m.size_bytes}B pages={m.page_count} chars={m.character_count}")
    print("--- extracted text (raw, local only) ---")
    print(result.extracted_text)

    redaction = redact_pii(result.extracted_text)
    print("\n=== PII redaction (this is what the LLM would receive) ===")
    print(f"replacements={redaction.replacement_count} types={list(redaction.detected_types)}")
    print(redaction.redacted_text)

    if not use_llm:
        print("\n(Stage 2 skipped. Add --llm to run the structured extraction, 1 Gemini call.)")
        return 0

    print("\n=== STAGE 2: structured extraction (1 Gemini call, same prompt as ProfileAgent) ===")
    from app.agents.llm_client import GeminiClient
    from app.agents.profile_agent import EXTRACTION_SYSTEM_PROMPT, ProfileAgent
    from app.agents.skill_normalizer import normalize_skill
    from app.services import retrieval_service as rs

    catalog = [s.model_dump() for s in rs.get_all_skills()]  # read-only
    prompt = ProfileAgent(llm_client=None)._build_user_prompt(redaction.redacted_text, catalog)
    try:
        client = GeminiClient()
        print(f"model={client.model}")
        extracted = client.complete_json(system=EXTRACTION_SYSTEM_PROMPT, user=prompt, max_tokens=8192)
    except Exception as exc:
        print("LLM FAILED:", type(exc).__name__, "| code =", getattr(exc, "code", None))
        print(str(getattr(exc, "message", exc))[:300])
        return 1

    extracted = redact_structured_value(extracted)
    print(json.dumps(extracted, indent=2, ensure_ascii=False))

    print("\n=== Skill normalization preview (deterministic, nothing saved) ===")
    for s in extracted.get("skills") or []:
        if not isinstance(s, dict) or not s.get("claimed_skill"):
            continue
        n = normalize_skill(s["claimed_skill"], catalog, s.get("candidate_skill_id"))
        print(f"{s['claimed_skill']!r:40} -> {n.skill_id} ({n.method})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())