"""List model names available to the configured GEMINI_API_KEY (no CV data, key never printed).
Run from backend/ with the venv active:  python list_gemini_models.py"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.getcwd())

from dotenv import load_dotenv
from google import genai

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

key = os.environ.get("GEMINI_API_KEY")
if not key:
    print("GEMINI_API_KEY is not set (checked environment and backend/.env).")
    raise SystemExit(1)

configured = os.environ.get("CAREER_LLM_MODEL") or "(not set; the code default would be used)"
print("CAREER_LLM_MODEL =", configured)

try:
    client = genai.Client(api_key=key)
    names = []
    for model in client.models.list():
        actions = getattr(model, "supported_actions", None)
        if actions is not None and "generateContent" not in actions:
            continue  # skip embedding / other non-text-generation models
        names.append(model.name.replace("models/", ""))
except Exception as exc:
    print("LIST FAILED:", type(exc).__name__, "| code =", getattr(exc, "code", None))
    print(str(getattr(exc, "message", exc))[:300])
    raise SystemExit(1)

for name in sorted(names):
    print(" ", name)
print(f"\n{len(names)} models support generateContent")
print("configured model is listed:", configured in names)
