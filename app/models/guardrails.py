"""Guardrails (#8) contracts — mirrors the locked agent_output_schema.guardrails
block: { passed, blocked_claims:[{claim_text, rule_id, reason}], escalation_reason }.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class BlockedClaim(BaseModel):
    """One forbidden customer-facing claim found in a draft."""
    claim_text: str          # the offending sentence (verbatim from the draft)
    rule_id: str             # the forbidden-claim rule that matched
    reason: str              # human-readable explanation


class GuardrailsOutput(BaseModel):
    """passed=False blocks the output and forces escalation (per the locked spec)."""
    passed: bool = True
    blocked_claims: List[BlockedClaim] = Field(default_factory=list)
    escalation_reason: Optional[str] = None
