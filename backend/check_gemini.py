"""Minimal Gemini connectivity check. Sends a trivial prompt, no profile data."""
import os
import sys

sys.path.insert(0, os.getcwd())  # run from backend/

from app.agents.llm_client import GeminiClient

try:
    client = GeminiClient()
    print(f"model = {client.model}")
    print("key set =", bool(client.api_key), "| length =", len(client.api_key))
    print("OK:", client.complete_json(
        system='Return only a JSON object.', user='Return {"ok": true}.', max_tokens=100))
except Exception as exc:
    print("FAILED:", type(exc).__name__)
    print("code    =", getattr(exc, "code", None))
    print("status  =", getattr(exc, "status", None))
    print("message =", str(getattr(exc, "message", exc))[:400])