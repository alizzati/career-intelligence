
import json
import os
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv
from google import genai
from google.genai import types

from app.agents.llm_errors import LLMInvalidResponseError, LLMQuotaExceededError


class LLMClient(Protocol):
    def complete_json(
        self, system: str, user: str, max_tokens: int = 2000
    ) -> dict:
        """Return a parsed JSON object from the model's response."""
        ...


class GeminiClient:
    """Gemini implementation of the project's JSON LLM interface."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ):
        load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        self.model = (
            model
            or os.environ.get("CAREER_LLM_MODEL")
            or "gemini-3.8-flash"
        )
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY")

        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. "
                "Configure it in the environment before calling Gemini."
            )

        self.client = genai.Client(api_key=self.api_key)

    def complete_json(
        self, system: str, user: str, max_tokens: int = 2000
    ) -> dict:
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    max_output_tokens=max_tokens,
                ),
            )
        except Exception as exc:
            if getattr(exc, "code", None) == 429:
                raise LLMQuotaExceededError() from None
            raise

        raw = (response.text or "").strip()
        if not raw:
            raise LLMInvalidResponseError()

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            raise LLMInvalidResponseError() from None
        if not isinstance(result, dict):
            raise LLMInvalidResponseError()

        return result