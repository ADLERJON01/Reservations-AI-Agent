"""The locked LLM output contract — what the Classifier+Extractor (#2) must emit.

Derived faithfully from outputs/llm_output_schema.json (structure) +
outputs/taxonomy.json v1.0.0 (enums). Promoted unchanged from the validated
Sandbox/schema_model.py used in the model-selection smoke test, so "schema
valid" means exactly what the project means.

Enums are Literal[...] so any out-of-vocabulary category/facet value fails
validation — this model is the contract gate for every LLM call.

NOTE (confidence): `confidence` stays a float here by decision (2026-06-06).
It is logged/calibrated, never used to gate routing; the dashboard may render
derived low/med/high buckets. Do not bump this to an enum without a calibrated
justification + CHANGELOG entry. See memory: open-item-confidence-gating.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# ---- enums (taxonomy.json v1.0.0) ----
Category = Literal[
    "booking_notification",
    "booking_change_or_cancellation",
    "service_or_information_inquiry",
    "payment_billing_or_rate_issue",
    "inventory_availability_or_stop_sales",
    "system_or_channel_delivery_exception",
    "other_or_unclear",
]
SenderType = Literal[
    "automated_system", "partner_or_agency", "direct_guest",
    "internal_pestana_staff", "unknown",
]
RequestType = Literal[
    "policy_or_general_question", "availability_or_quote_inquiry",
    "new_booking_request", "modification_request", "cancellation_request",
    "ancillary_service_request",                       # taxonomy_v1_1 (transfers/extras)
    "payment_or_billing_inquiry", "complaint_or_dispute",
    "withdrawal_or_acknowledgment", "none", "other_or_unclear",
]
# taxonomy_v1_1: the RAG-safety signal — what kind of source would answer the inquiry.
InquiryAnswerSource = Literal[
    "kb_policy", "internal_system", "human_judgment", "not_applicable", "unclear",
]
LifecycleStage = Literal["new", "paid", "pre_arrival", "modified", "cancelled", "n/a"]
# taxonomy_v1_1: renamed from ExpectsHuman ("response" → "reply OR decision/action").
RequiresHumanFollowup = Literal["yes", "no", "unclear"]
ExpectsHuman = RequiresHumanFollowup                  # legacy alias (older eval scripts)
Urgency = Literal["routine", "urgent", "sensitive_complaint"]


class Classification(BaseModel):
    predicted_category: Category
    sender_type: SenderType
    request_type: RequestType                          # descriptive tag (NOT a routing gate in v1_1)
    inquiry_answer_source: InquiryAnswerSource         # taxonomy_v1_1 — drives the derived RAG gate
    booking_lifecycle_stage: LifecycleStage
    requires_human_followup: RequiresHumanFollowup     # renamed from expects_human_response
    urgency_signal: Urgency
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_short: str = Field(max_length=200)
    reasoning_short: str = Field(max_length=200)


# ---- extraction sub-objects ----
class Traveler(BaseModel):
    name: Optional[str] = None
    age: Optional[int] = None


class BookingIdentity(BaseModel):
    source_channel: Optional[str] = None
    notification_type: Optional[str] = None
    booking_reference: Optional[str] = None
    hotel_name: Optional[str] = None
    property_id: Optional[str] = None
    booking_created_date: Optional[str] = None
    modified_on_date: Optional[str] = None
    cancelled_on_date: Optional[str] = None


class Guest(BaseModel):
    guest_name: Optional[str] = None
    guest_email: Optional[str] = None
    guest_phone: Optional[str] = None
    guest_language: Optional[str] = None
    additional_travelers: List[Traveler] = Field(default_factory=list)


class Stay(BaseModel):
    check_in_date: Optional[str] = None
    check_out_date: Optional[str] = None
    number_of_nights: Optional[int] = None
    number_of_rooms: Optional[int] = None
    adults: Optional[int] = None
    children: Optional[int] = None
    child_ages: List[int] = Field(default_factory=list)


class DailyRate(BaseModel):
    date: Optional[str] = None
    rate_id: Optional[str] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    description: Optional[str] = None


class RoomAndRate(BaseModel):
    room_type: Optional[str] = None
    rate_plan: Optional[str] = None
    meal_plan: Optional[str] = None
    daily_rate_breakdown: List[DailyRate] = Field(default_factory=list)
    promotion: Optional[str] = None
    benefits_included: Optional[str] = None


class TaxLine(BaseModel):
    description: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None


class Financials(BaseModel):
    currency: Optional[str] = None
    total_amount: Optional[float] = None
    tax_amount: Optional[float] = None
    tax_breakdown: List[TaxLine] = Field(default_factory=list)
    commission_amount: Optional[float] = None
    balance: Optional[float] = None


class Payment(BaseModel):
    payment_method: Optional[str] = None
    payment_status: Optional[str] = None
    guarantee_type: Optional[str] = None
    virtual_card_present: Optional[bool] = None
    virtual_card_activation_date: Optional[str] = None
    virtual_card_deactivation_date: Optional[str] = None
    card_type: Optional[str] = None
    card_last4: Optional[str] = None


class Policies(BaseModel):
    cancellation_policy: Optional[str] = None
    free_cancellation_deadline: Optional[str] = None
    non_refundable: Optional[bool] = None
    no_show_policy: Optional[str] = None
    prepayment_policy: Optional[str] = None


class RequestsAndRemarks(BaseModel):
    raw_remarks: Optional[str] = None
    hotel_staff_instructions: Optional[str] = None


class Links(BaseModel):
    secure_extranet_link: Optional[str] = None
    source_links: List[str] = Field(default_factory=list)


class Extraction(BaseModel):
    booking_identity: BookingIdentity = Field(default_factory=BookingIdentity)
    guest: Guest = Field(default_factory=Guest)
    stay: Stay = Field(default_factory=Stay)
    room_and_rate: RoomAndRate = Field(default_factory=RoomAndRate)
    financials: Financials = Field(default_factory=Financials)
    payment: Payment = Field(default_factory=Payment)
    policies: Policies = Field(default_factory=Policies)
    requests_and_remarks: RequestsAndRemarks = Field(default_factory=RequestsAndRemarks)
    links: Links = Field(default_factory=Links)


class EmailExtraction(BaseModel):
    """Top-level object the LLM must emit per email."""
    classification: Classification
    extraction: Extraction
