"""The Validator's LLM-emitted contract (Agent #3).

Strict enum (confirmed | flagged) so an out-of-vocabulary verdict fails the
Pydantic gate — same discipline as EmailExtraction. Distinct from
state.ValidatorOutput, which is the *stored* form and additionally carries
"skipped" (set by our code when the Validator does not run).

revised_confidence is logged/calibrated, NEVER used to gate routing
(decision 2026-06-06).
"""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field


class ValidatorResult(BaseModel):
    """What the Validator LLM must emit when it critiques a proposed EmailExtraction."""
    validation_result: Literal["confirmed", "flagged"]
    flagged_fields: List[str] = Field(default_factory=list)  # dotted JSON paths
    reasoning_short: str = Field(default="", max_length=200)
    revised_confidence: float = Field(ge=0.0, le=1.0)
