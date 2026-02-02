from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..config import Settings


class LlmError(RuntimeError):
    pass


@dataclass(frozen=True)
class LlmJsonResult:
    raw_text: str
    data: dict[str, Any]


class GeminiClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.gemini_api_key:
            raise LlmError("Missing GEMINI_API_KEY. Set it in env or .env.")
        try:
            from google import genai  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise LlmError("google-genai is not installed. `pip install google-genai`.") from exc
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._model = settings.llm_model
        self._temperature = settings.llm_temperature

    def generate_json(self, prompt: str) -> LlmJsonResult:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config={"temperature": self._temperature},
            )
        except Exception as exc:
            raise LlmError(f"LLM call failed: {exc}") from exc

        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise LlmError("LLM returned empty response.text")
        data = _parse_json_object(text)
        return LlmJsonResult(raw_text=text, data=data)

    def generate_text(self, prompt: str) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config={"temperature": self._temperature},
            )
        except Exception as exc:
            raise LlmError(f"LLM call failed: {exc}") from exc
        text = getattr(response, "text", None)
        if not isinstance(text, str):
            return ""
        return text.strip()


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
    # best-effort: grab first {...} block
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise LlmError("Expected JSON object in response")
    candidate = cleaned[start : end + 1]
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LlmError(f"Invalid JSON from LLM: {exc}") from exc
    if not isinstance(value, dict):
        raise LlmError("Expected top-level JSON object")
    return value
