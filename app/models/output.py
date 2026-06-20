"""Output Generator (#7) contracts.

OutputArtifacts mirrors the locked agent_output_schema.output block (exactly one
of the four forms populated + internal_notes), plus a runtime-only
used_source_ids for draft traceability. GeneratedReply is the LLM contract for
the one free-text, customer-facing artifact (draft_reply).
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class OutputArtifacts(BaseModel):
    audit_checklist: List[str] = Field(default_factory=list)
    escalation_summary: Optional[str] = None
    clarification_draft: Optional[str] = None   # deferred — null in v1
    draft_reply: Optional[str] = None
    internal_notes: Optional[str] = None
    # runtime-only traceability (not in the locked block)
    used_source_ids: List[str] = Field(default_factory=list)


class GeneratedReply(BaseModel):
    """What the LLM emits for a grounded draft_reply."""
    reply_text: str
    used_source_ids: List[str] = Field(default_factory=list)
