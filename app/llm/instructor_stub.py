"""Parked seam: a LiteLLM + Instructor backend.

NOT implemented on purpose. The model-selection smoke test abandoned this stack
because it could not disable "thinking" on reasoning models (200-400s/call) and
its tool-calling mode broke the small models (see SMOKE_DECISION.md / HANDOVER §7).

Kept as a clearly-marked seam so the decision to "keep both open" is honoured:
if a downstream requirement ever needs the Instructor route (e.g. multi-provider
support), implement `extract()` here against the LLMClient protocol — the rest of
the pipeline depends only on that protocol and will not need to change.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from app.llm.client import LLMResult


class InstructorClient:
    """Placeholder implementing the LLMClient protocol shape — raises until built."""

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
        raise NotImplementedError(
            "Instructor/LiteLLM backend is parked (see SMOKE_DECISION.md). "
            "Default to OllamaNativeClient. Implement this only if a downstream "
            "requirement justifies reviving the Instructor route."
        )
