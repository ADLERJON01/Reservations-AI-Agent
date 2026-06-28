"""DRAFT v2.0.0 LLM output contract — NOT yet wired into the pipeline.

Sibling of `app/models/llm_output.py` (v1.0.0). Kept separate so the live pipeline
and test suite stay green while v2 is reviewed and measured. Promotion = replace the
v1 `Classification`/`EmailExtraction` once the gold re-label + same-model run confirm
v2 matches/beats the v1 baseline (category 79.6%).

What changed vs v1 (the decisions taken 2026-06):
- `category`: 7 → 10 values. The overloaded `service_or_information_inquiry` is split
  into `knowledge_policy_inquiry`, `sales_availability_or_quote_inquiry`,
  `guest_service_or_ancillary_request`, `thread_closure_or_acknowledgment`. Field name
  kept (`category`) to minimise downstream churn; `booking_change_or_cancellation`,
  `inventory_…`, `system_…` keep their names too.
- NEW `inquiry_answer_source`: the RAG-safety signal (kb_policy / internal_system /
  human_judgment / not_applicable / unclear).
- `request_type`: KEPT (name + role) but DEMOTED to a purely descriptive tag (the
  Outlook/dashboard "what is this about" label). No longer a routing gate. Adds
  `ancillary_service_request` (fills the documented gap).
- `expects_human_response` → `requires_human_followup` (fixes the name/definition
  mismatch; values unchanged).
- `booking_lifecycle_stage`: SAME values, NEW convention (stage of the booking the
  email *references*, so inquiries may carry a stage). Schema unchanged.
- The LLM does NOT emit `rag_candidate` / `recommended_action`. Those are DERIVED in
  code (Router): rag_candidate = (category == knowledge_policy_inquiry)
  AND (inquiry_answer_source == kb_policy). "LLM describes, code decides."

Unchanged and imported from v1: the entire extraction layer, plus `SenderType`,
`LifecycleStage`, `Urgency`.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Unchanged in v2 — reuse the v1 definitions verbatim.
from app.models.llm_output import (  # noqa: F401
    Extraction,
    LifecycleStage,
    SenderType,
    Urgency,
)

# ---- enums changed/added in v2 (taxonomy.json v2.0.0) ----
Category = Literal[
    "booking_notification",
    "booking_change_or_cancellation",          # kept name; broadened to existing-booking action/dispute
    "knowledge_policy_inquiry",                # NEW — the only RAG candidate
    "sales_availability_or_quote_inquiry",     # NEW
    "guest_service_or_ancillary_request",      # NEW
    "thread_closure_or_acknowledgment",        # NEW
    "payment_billing_or_rate_issue",
    "inventory_availability_or_stop_sales",
    "system_or_channel_delivery_exception",
    "other_or_unclear",
]

# Descriptive display tag only (NOT routed). Kept name; + ancillary_service_request.
RequestType = Literal[
    "policy_or_general_question",
    "availability_or_quote_inquiry",
    "new_booking_request",
    "modification_request",
    "cancellation_request",
    "ancillary_service_request",               # NEW — fills the ancillary gap
    "payment_or_billing_inquiry",
    "complaint_or_dispute",
    "withdrawal_or_acknowledgment",
    "none",
    "other_or_unclear",
]

# NEW — what kind of source could safely answer the email. Half of the RAG AND-gate.
InquiryAnswerSource = Literal[
    "kb_policy",          # answerable from static KB / policy / facility info
    "internal_system",    # needs live booking/payment/inventory/rate/customer data
    "human_judgment",     # needs staff decision/coordination/exception/arrangement
    "not_applicable",     # no inquiry (notification, thread closure, system notice)
    "unclear",            # inquiry exists but the source needed is unclear
]

RequiresHumanFollowup = Literal["yes", "no", "unclear"]   # renamed from expects_human_response


class ClassificationV2(BaseModel):
    """Descriptive fields only — the LLM never emits a decision (no rag_candidate,
    no recommended_action; those are derived deterministically downstream)."""
    category: Category
    request_type: RequestType                      # descriptive display tag (not routed)
    inquiry_answer_source: InquiryAnswerSource     # RAG-safety signal
    sender_type: SenderType
    booking_lifecycle_stage: LifecycleStage
    requires_human_followup: RequiresHumanFollowup
    urgency_signal: Urgency
    confidence: float = Field(ge=0.0, le=1.0)      # logged, never gates routing (v1 decision kept)
    evidence_short: str = Field(max_length=200)
    reasoning_short: str = Field(max_length=200)


class EmailExtractionV2(BaseModel):
    """Top-level v2 object the LLM must emit per email. Extraction layer unchanged."""
    classification: ClassificationV2
    extraction: Extraction