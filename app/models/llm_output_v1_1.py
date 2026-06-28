"""DRAFT v1.1 LLM output contract — v1's 7 categories + the v2 RAG-safety patch.

The evidence-based final design: keep v1's reliable 7-category routing backbone and
add the orthogonal `inquiry_answer_source` safety signal (the part of v2 that actually
bought the RAG precision). NOT yet wired into the live pipeline.

vs v1.0.0:
- category: UNCHANGED (the proven 7).
- NEW `inquiry_answer_source` (the RAG-safety signal; reused from v2).
- `request_type`: + `ancillary_service_request` (reused from v2); descriptive tag.
- `expects_human_response` -> `requires_human_followup` (reused from v2).
- `booking_lifecycle_stage`: same values, v2 "referenced booking" convention.

rag_candidate is DERIVED in code (never emitted):
    (category == service_or_information_inquiry) AND (inquiry_answer_source == kb_policy)

Extraction layer + SenderType/LifecycleStage/Urgency unchanged (imported from v1);
RequestType/InquiryAnswerSource/RequiresHumanFollowup reused from v2.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.llm_output import Extraction, LifecycleStage, SenderType, Urgency  # noqa: F401
from app.models.llm_output_v2 import (  # noqa: F401
    InquiryAnswerSource,
    RequestType,
    RequiresHumanFollowup,
)

# v1's proven 7 operational categories (unchanged).
Category = Literal[
    "booking_notification",
    "booking_change_or_cancellation",
    "service_or_information_inquiry",
    "payment_billing_or_rate_issue",
    "inventory_availability_or_stop_sales",
    "system_or_channel_delivery_exception",
    "other_or_unclear",
]


class ClassificationV11(BaseModel):
    """Descriptive fields only — no rag_candidate / recommended_action (derived in code)."""
    category: Category
    request_type: RequestType                      # descriptive display tag (not routed)
    inquiry_answer_source: InquiryAnswerSource     # the RAG-safety signal
    sender_type: SenderType
    booking_lifecycle_stage: LifecycleStage
    requires_human_followup: RequiresHumanFollowup
    urgency_signal: Urgency
    confidence: float = Field(ge=0.0, le=1.0)      # logged, never gates routing
    evidence_short: str = Field(max_length=200)
    reasoning_short: str = Field(max_length=200)


class EmailExtractionV11(BaseModel):
    """Top-level v1.1 object the LLM must emit per email. Extraction layer unchanged."""
    classification: ClassificationV11
    extraction: Extraction