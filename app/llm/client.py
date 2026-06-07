"""The LLM client contract.

Defines the interface every backend (native Ollama, a future Instructor route)
must satisfy, plus the structured result type. This is the "keep both open"
seam: callers depend on LLMClient, never on a concrete backend.

Schema-generic: one structured-output call serves every LLM agent. The caller
passes the Pydantic `response_model` it wants back (EmailExtraction for the
Classifier, ValidatorResult for the Validator, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from pydantic import BaseModel


@dataclass
class LLMResult:
    """Outcome of one structured-output call. `output` is set iff `valid` is True."""
    valid: bool
    output: Optional[BaseModel]
    error: Optional[str]
    latency_s: float
    model: str
    raw_content: Optional[str] = None


class LLMClient(Protocol):
    """A backend that turns (system, user) prompts into a validated Pydantic object."""

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
        """Run one call and validate the response against `response_model`.

        Implementations must NOT raise on a bad/invalid model response — they
        return LLMResult(valid=False, ...) so the pipeline can route on it.
        """
        ...
