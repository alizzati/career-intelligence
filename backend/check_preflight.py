"""Read-only preflight. Run from backend/ (venv active).
  python check_preflight.py                       # versions + source evidence, no network
  python check_preflight.py --probe cv.pdf        # + ONE Gemini call: finish_reason and token usage
  python check_preflight.py --probe cv.pdf --max-tokens 8192
Prints sizes/metadata only: never CV text, prompts or model output."""
import argparse, importlib.metadata as md, inspect, json, os, sys
sys.path.insert(0, os.getcwd())

ap = argparse.ArgumentParser()
ap.add_argument("--probe"); ap.add_argument("--max-tokens", type=int, default=2000)
args = ap.parse_args()

print("python", sys.version.split()[0])
for p in ("langgraph", "google-genai", "pydantic", "fastapi"):
    try: print(p, md.version(p))
    except md.PackageNotFoundError: print(p, "NOT INSTALLED")

from app.agents.profile_agent import EXTRACTION_SYSTEM_PROMPT, ProfileAgent
from app.agents import llm_client as lc
run_src, llm_src = inspect.getsource(ProfileAgent.run), inspect.getsource(lc)
print("\nProfileAgent.run passes max_tokens to complete_json:", "max_tokens" in run_src)
print("llm_client sets thinking_config:", "thinking_config" in llm_src)
print("CareerWorkflow.run has 'observer' parameter:", end=" ")
try:
    from app.workflows.career_workflow import CareerWorkflow
    print("observer" in inspect.signature(CareerWorkflow.run).parameters)
except Exception as exc:
    print("cannot import", type(exc).__name__)

if args.probe:
    from google.genai import types
    from app.agents.profile_agent import ProfileAgent as PA
    from app.services import retrieval_service as rs
    from app.services.cv_text_extraction_service import CVTextExtractor
    from app.services.pii_redaction_service import redact_pii
    client = lc.GeminiClient()
    text = redact_pii(CVTextExtractor().extract(open(args.probe, "rb").read(), os.path.basename(args.probe)).extracted_text).redacted_text
    prompt = PA(llm_client=None)._build_user_prompt(text, [s.model_dump() for s in rs.get_all_skills()])
    print(f"\nPROBE: model={client.model} max_output_tokens={args.max_tokens} prompt_chars={len(prompt)}")
    try:
        r = client.client.models.generate_content(model=client.model, contents=prompt, config=types.GenerateContentConfig(
            system_instruction=EXTRACTION_SYSTEM_PROMPT, response_mime_type="application/json", max_output_tokens=args.max_tokens))
    except Exception as exc:
        print("API error:", type(exc).__name__, "code =", getattr(exc, "code", None)); raise SystemExit(1)
    u = r.usage_metadata
    print("finish_reason:", getattr(r.candidates[0], "finish_reason", None) if r.candidates else "no candidates")
    for f in ("prompt_token_count", "candidates_token_count", "thoughts_token_count", "total_token_count"):
        print(f"{f}:", getattr(u, f, None))
    body = (r.text or "")
    print("response_chars:", len(body))
    try: json.loads(body); print("json_parse: OK")
    except json.JSONDecodeError as e: print(f"json_parse: FAILED at char {e.pos} ({e.msg})")