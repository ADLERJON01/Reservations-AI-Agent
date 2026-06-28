"""Default LLM backend: Ollama's native structured-output API.

This is the path proven in the model-selection smoke test (Sandbox/run_smoke.py):
POST /api/chat with think=False and format=<JSON schema of EmailExtraction>,
validated by the same Pydantic model. Faster and more controllable than the
LiteLLM + Instructor route, which could not disable reasoning-model "thinking".
See HANDOVER.md §7 and SMOKE_DECISION.md.
"""
from __future__ import annotations

import time
from functools import lru_cache
from typing import Optional

import requests
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.llm.client import LLMResult


@lru_cache(maxsize=None)
def _schema_for(response_model: type[BaseModel]) -> dict:
    """The JSON schema Ollama enforces, computed once per response model."""
    return response_model.model_json_schema()


class OllamaNativeClient:
    """Talks to a local Ollama server. Implements the LLMClient protocol."""

    def __init__(self, model: Optional[str] = None) -> None:
        self._settings = get_settings()
        self._default_model = model or self._settings.primary_model

    def call_structured(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        response_model: type[BaseModel],
        model: Optional[str] = None,
        temperature: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> LLMResult:
        s = self._settings
        chosen = model or self._default_model
        temp = s.temperature if temperature is None else temperature
        options: dict = {"temperature": temp, "num_predict": s.num_predict,
                         "num_ctx": s.num_ctx}
        if seed is not None:
            options["seed"] = seed

        payload = {
            "model": chosen,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": False,        # mandatory: reasoning models otherwise take 200-400s
            "format": _schema_for(response_model),
            "options": options,
        }

        t0 = time.perf_counter()
        try:
            r = requests.post(s.ollama_chat_url, json=payload, timeout=s.request_timeout_s)
            latency = time.perf_counter() - t0
        except Exception as e:  # network / timeout — surface, don't raise
            return LLMResult(False, None, f"{type(e).__name__}: {str(e)[:250]}",
                             time.perf_counter() - t0, chosen)

        if r.status_code != 200:
            return LLMResult(False, None, f"HTTP {r.status_code}: {r.text[:200]}",
                             latency, chosen)

        content = r.json().get("message", {}).get("content", "")
        try:
            obj = response_model.model_validate_json(content)
            return LLMResult(True, obj, None, latency, chosen, raw_content=content)
        except ValidationError as ve:
            return LLMResult(False, None, f"ValidationError: {str(ve)[:250]}",
                             latency, chosen, raw_content=content)
