"""RouterSignals — the internal contract the Router (#5) consumes.

This is an INTERNAL, ADJUSTABLE Pydantic model, NOT the locked public schema.
It collects every signal computed before routing so the Router can stay a pure,
deterministic, testable decision layer ("LLM describes, code decides").

Design decisions baked in (2026-06-06, see memory: architecture-routing-signals):
  - Deterministic checks (grounding / consistency / completeness) are produced by
    the Audit/Verification agent (#4), NOT by the LLM Validator (#3).
  - The Validator emits only the semantic-critique fields below.
  - Routing NEVER gates on confidence; it is carried for logging/calibration only.
  - Keep this lean and adjustable through Phase 2; promote useful parts into the
    locked agent_output_schema.json only after the 378-email batch run.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# The Router's only output. Mirrors recommended_action in the locked spec (HANDOVER §5).
RecommendedAction = Literal[
    "audit_only",
    "audit_with_attention",
    "audit_only_with_note",
    "draft_reply_with_rag",
    "escalate_to_reservations_team",
    "escalate_to_payment_or_billing",
    "escalate_to_inventory_or_operations",
    "escalate_to_technical_or_operations",
    "manual_review_unclear",
]


class RouterSignals(BaseModel):
    """All pre-routing signals, composed by build_router_signals() from agent outputs."""

    # --- schema / LLM output validity (from the Classifier+Extractor wrapper) ---
    schema_valid: bool = True
    llm_parse_error: bool = False
    llm_error_message: Optional[str] = None

    # --- classifier descriptive fields the Router keys on ---
    category: Optional[str] = None
    request_type: Optional[str] = None
    inquiry_answer_source: Optional[str] = None        # taxonomy_v1_1 — drives the RAG gate
    requires_human_followup: Optional[str] = None       # renamed from expects_human_response
    urgency_signal: Optional[str] = None
    # classifier metadata (logged only — NEVER gates routing)
    classifier_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    # --- Validator (#3): LLM semantic critique only ---
    validator_result: Literal["confirmed", "flagged", "skipped"] = "skipped"
    validator_flagged_fields: List[str] = Field(default_factory=list)
    validator_notes: List[str] = Field(default_factory=list)

    # --- deterministic verification (Audit #4) ---
    extraction_grounding_errors: List[str] = Field(default_factory=list)
    consistency_errors: List[str] = Field(default_factory=list)
    missing_required_fields: List[str] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)
    audit_finding: Literal[
        "clean", "missing_fields", "suspected_error", "n/a"
    ] = "n/a"

    # --- deterministic routing helpers (router-computed decision flags) ---
    requires_internal_system: bool = False
    outbound_action_required: bool = False
    rag_required: bool = False             # policy question → RAG candidate (#9 ordering)
    kb_answerable: Optional[bool] = None   # None until RAG (#6) has run

    # --- safety escape hatch (any upstream agent may set) ---
    force_manual_review: bool = False
    force_escalation_reason: Optional[str] = None


class RoutingDecision(BaseModel):
    """The Router's output: one action, plus traceability."""
    recommended_action: RecommendedAction
    routing_reason: str
    rule_id: str
