"""Prompts for the Classifier+Extractor Agent (#2).

Kept separate from the agent logic so the deferred few-shot prompt-engineering
work (smoke handoff Task #2) can iterate here without touching orchestration.

Lineage: SYSTEM_PROMPT / CATEGORY_GUIDE / build_user_prompt are ported from the
proven Sandbox/run_smoke.py and enriched with concise facet definitions
(taxonomy.json) per the approved spec.
"""
from __future__ import annotations

from app.config import get_settings
from app.models.state import EmailInput

# --- system prompt: role + the locked output rules ---
SYSTEM_PROMPT = (
    "You are an email classification + extraction engine for a hotel group "
    "(Pestana). For each email you receive, output ONE JSON object that matches "
    "the provided schema exactly.\n"
    "Rules:\n"
    "- The object has exactly two top-level keys: \"classification\" and \"extraction\".\n"
    "- predicted_category MUST be one of the 7 allowed categories.\n"
    "- Categories are OPERATIONAL (how the team handles the mail), not topical. "
    "Classify by the inner content of forwarded mail, not the forwarder.\n"
    "- Assign every facet from the allowed facet values only.\n"
    "- Absent scalar fields = null; absent lists = []. Never output the string \"null\".\n"
    "- Never invent values not present in the email.\n"
    "- Retain anonymized MASKED_* tokens verbatim.\n"
    "- total_amount = 0.00 is VALID for cancellation notifications (not a missing field).\n"
    "- booking_lifecycle_stage must mirror extraction.booking_identity.notification_type.\n"
    "- Keep evidence_short and reasoning_short under 200 characters."
)

# --- the 7 operational categories (proven smoke-test text) ---
CATEGORY_GUIDE = (
    "Allowed categories:\n"
    "1. booking_notification — system/templated channel email about a single booking "
    "lifecycle event (new/paid/pre-arrival/modified/cancelled) that is audited vs PMS.\n"
    "2. booking_change_or_cancellation — change/cancellation of an EXISTING booking that "
    "needs the team to review/validate.\n"
    "3. service_or_information_inquiry — human-written question, quote, new-booking request "
    "or service request.\n"
    "4. payment_billing_or_rate_issue — primary topic is payment, billing, invoices, fiscal "
    "data, rates, tariffs or commercial contracts.\n"
    "5. inventory_availability_or_stop_sales — room inventory, allotment, stop-sales, "
    "availability coordination.\n"
    "6. system_or_channel_delivery_exception — system alert/error/exception or "
    "delivery/sync failure from a channel manager, PMS or OTA infrastructure.\n"
    "7. other_or_unclear — anything that does not confidently fit the above."
)

# --- 5 descriptive facets (concise per-value defs from taxonomy.json) ---
FACET_GUIDE = (
    "Facets (assign each independently from its allowed values):\n"
    "sender_type — who authored the inner content: automated_system (channel manager/OTA), "
    "partner_or_agency (external agency/wholesaler/DMC), direct_guest (end traveler), "
    "internal_pestana_staff (Pestana staff/reservations), unknown.\n"
    "request_type — what is asked: policy_or_general_question, availability_or_quote_inquiry, "
    "new_booking_request, modification_request, cancellation_request, payment_or_billing_inquiry, "
    "complaint_or_dispute, withdrawal_or_acknowledgment, none (purely informational notification), "
    "other_or_unclear.\n"
    "booking_lifecycle_stage — new, paid, pre_arrival, modified, cancelled, n/a "
    "(alert/exception/general inquiry).\n"
    "expects_human_response — yes (solicits reply/decision), no (purely informational; routine "
    "audit-vs-PMS does NOT count), unclear.\n"
    "urgency_signal — routine, urgent (URGENT/URGENTE/PLEASE REPLY, payment-problem warnings, "
    "imminent arrival), sensitive_complaint (complaint/dispute/sensitive issue)."
)


# --- extraction-emphasis block ---
# Proven to lift mean key-field completeness 32%→72% on ministral-3:3b
# (Sandbox/extraction_diagnostic.py, variant C): the cause of under-extraction was
# prompt laziness, NOT token budget. Appended LAST — the exact position tested.
EXTRACTION_EMPHASIS = (
    "EXTRACTION IS MANDATORY AND THOROUGH. If a value appears anywhere in the email you "
    "MUST populate the matching field — never leave a present value null. Examples:\n"
    "- 'Check-in: 06-Mar-2026' -> stay.check_in_date = '2026-03-06'\n"
    "- 'Total Price: 208.17 EUR' -> financials.total_amount = 208.17, financials.currency = 'EUR'\n"
    "- channel name (e.g. Booking.com) -> booking_identity.source_channel\n"
    "- 'Booking Confirmation Id: 6310459722' -> booking_identity.booking_reference\n"
    "- hotel (e.g. 'Pestana - Brussels') -> booking_identity.hotel_name\n"
    "- guest name (incl. MASKED_NAME_*) -> guest.guest_name\n"
    "Use null ONLY when the email genuinely lacks the value."
)


def build_system_prompt() -> str:
    """Full system prompt: rules + category guide + facet guide + extraction emphasis.

    The emphasis block is appended last — the position proven in
    Sandbox/extraction_diagnostic.py to lift completeness 32%→72%."""
    return f"{SYSTEM_PROMPT}\n\n{CATEGORY_GUIDE}\n\n{FACET_GUIDE}\n\n{EXTRACTION_EMPHASIS}"


def build_user_prompt(email: EmailInput, *, body_char_limit: int | None = None) -> str:
    """Per-email user prompt. Feeds body_clean (truncated); forwarding-invariance
    is handled by the system prompt, not by stripping the wrapper here."""
    limit = body_char_limit if body_char_limit is not None else get_settings().body_char_limit
    body = (email.body_clean or "")[:limit]
    return (
        f"--- EMAIL ---\n"
        f"Subject: {email.subject or ''}\n"
        f"From: {email.from_raw or ''}\n\n"
        f"Body:\n{body}\n"
        f"--- END EMAIL ---\n\n"
        f"Return ONE JSON object with the two top-level keys "
        f"\"classification\" and \"extraction\"."
    )


# =====================================================================
# Validator Agent (#3) — LLM semantic critique only
# =====================================================================

VALIDATOR_SYSTEM_PROMPT = (
    "You are a verification critic for a hotel email-processing pipeline (Pestana). "
    "You are given an email and a PROPOSED JSON output (classification + extraction) "
    "produced by another model. Your job is to judge whether that output is faithful "
    "to the email — NOT to rewrite it.\n"
    "Output ONE JSON object matching the schema exactly, with these fields:\n"
    "- validation_result: \"confirmed\" if the output is well-supported by the email, "
    "\"flagged\" if you find any unsupported, hallucinated, inconsistent, or clearly "
    "missed value.\n"
    "- flagged_fields: list of dotted JSON paths you dispute "
    "(e.g. \"classification.predicted_category\", \"extraction.guest.guest_name\"). "
    "Empty list when confirmed.\n"
    "- reasoning_short: one sentence, under 200 characters.\n"
    "- revised_confidence: 0-1, your confidence that the proposed output is correct.\n"
    "Rules:\n"
    "- Judge ONLY against what the email actually says. Flag a value only if the email "
    "does not support it (hallucination) or contradicts it.\n"
    "- A field left null/empty is NOT an error if the email does not contain that "
    "information. Do not flag absent-but-unknowable fields.\n"
    "- total_amount = 0.00 is valid for cancellation notifications.\n"
    "- Do NOT propose corrected values. Only flag.\n"
    "- Do NOT invent new requirements beyond fidelity to the email."
)


def build_validator_system_prompt() -> str:
    return VALIDATOR_SYSTEM_PROMPT


def build_validator_user_prompt(email: EmailInput, llm_output,
                                *, body_char_limit: int | None = None) -> str:
    """Critic prompt: the email + the proposed JSON to be verified."""
    limit = body_char_limit if body_char_limit is not None else get_settings().body_char_limit
    body = (email.body_clean or "")[:limit]
    proposed = llm_output.model_dump_json(indent=2)
    return (
        f"--- EMAIL ---\n"
        f"Subject: {email.subject or ''}\n"
        f"From: {email.from_raw or ''}\n\n"
        f"Body:\n{body}\n"
        f"--- END EMAIL ---\n\n"
        f"--- PROPOSED OUTPUT (to verify) ---\n"
        f"{proposed}\n"
        f"--- END PROPOSED OUTPUT ---\n\n"
        f"Return ONE JSON object: validation_result, flagged_fields, "
        f"reasoning_short, revised_confidence."
    )
