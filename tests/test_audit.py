"""Audit (#4): fully deterministic, offline. Covers consistency rules,
completeness per lifecycle, the cancellation exemption, non-booking n/a, and
skip-when-empty.
"""
from app.agents.audit import AGENT_NAME, audit
from app.models.llm_output import EmailExtraction
from app.models.state import AgentState, EmailInput


def _classification(**over):
    base = {
        "predicted_category": "booking_notification",
        "sender_type": "automated_system",
        "request_type": "none",
        "booking_lifecycle_stage": "new",
        "expects_human_response": "no",
        "urgency_signal": "routine",
        "confidence": 0.9,
        "evidence_short": "e",
        "reasoning_short": "r",
    }
    base.update(over)
    return base


# A complete "new" booking notification (all always-required fields present).
_COMPLETE_NEW = {
    "booking_identity": {"source_channel": "Booking.com", "booking_reference": "6310459722",
                         "hotel_name": "Pestana - Brussels", "notification_type": "new"},
    "guest": {"guest_name": "MASKED_NAME_x"},
    "stay": {"check_in_date": "2026-03-06", "check_out_date": "2026-03-08", "adults": 2},
    "financials": {"total_amount": 208.17, "currency": "EUR"},
}


def _state(classification: dict, extraction: dict) -> AgentState:
    out = EmailExtraction.model_validate({"classification": classification, "extraction": extraction})
    return AgentState(email=EmailInput(email_id="e"), llm_output=out)


def test_clean_booking_notification():
    state = audit(_state(_classification(), _COMPLETE_NEW))
    assert state.audit.audit_finding == "clean"
    assert state.audit.missing_required_fields == []
    assert state.audit.risk_flags == []
    assert AGENT_NAME in state.agent_path


def test_missing_required_field():
    ext = {**_COMPLETE_NEW, "financials": {"currency": "EUR"}}  # total_amount absent
    state = audit(_state(_classification(), ext))
    assert state.audit.audit_finding == "missing_fields"
    assert "financials.total_amount" in state.audit.missing_required_fields


def test_checkout_before_checkin_is_suspected_error():
    ext = {**_COMPLETE_NEW, "stay": {"check_in_date": "2026-03-08",
                                     "check_out_date": "2026-03-06", "adults": 2}}
    state = audit(_state(_classification(), ext))
    assert state.audit.audit_finding == "suspected_error"   # precedence over missing
    assert "checkout_before_checkin" in state.audit.risk_flags
    assert state.audit.consistency_errors


def test_price_without_currency_flag():
    ext = {**_COMPLETE_NEW, "financials": {"total_amount": 100.0}}  # currency null
    state = audit(_state(_classification(), ext))
    assert "price_without_currency" in state.audit.risk_flags
    assert state.audit.audit_finding == "suspected_error"


def test_lifecycle_mismatch_flag():
    cls = _classification(booking_lifecycle_stage="new")
    ext = {**_COMPLETE_NEW, "booking_identity": {**_COMPLETE_NEW["booking_identity"],
                                                "notification_type": "cancelled"}}
    state = audit(_state(cls, ext))
    assert "lifecycle_mismatch" in state.audit.risk_flags


def test_cancellation_zero_total_is_not_flagged():
    cls = _classification(booking_lifecycle_stage="cancelled")
    ext = {
        "booking_identity": {"source_channel": "Hotelbeds", "booking_reference": "60-2752249",
                             "hotel_name": "Pestana CR7", "notification_type": "cancelled",
                             "cancelled_on_date": "2026-02-19"},
        "guest": {"guest_name": "MASKED_NAME_y"},
        "financials": {"total_amount": 0.0},   # 0.00 valid for cancellations, currency null OK
    }
    state = audit(_state(cls, ext))
    assert "price_without_currency" not in state.audit.risk_flags
    assert state.audit.audit_finding == "clean"


def test_paid_any_of_payment_group():
    cls = _classification(booking_lifecycle_stage="paid")
    base = {**_COMPLETE_NEW,
            "booking_identity": {**_COMPLETE_NEW["booking_identity"], "notification_type": "paid"},
            "payment": {"payment_status": "Paid"}}  # neither method nor guarantee_type
    state = audit(_state(cls, base))
    assert "payment.payment_method|payment.guarantee_type" in state.audit.missing_required_fields
    # supplying one of the group clears it
    base2 = {**base, "payment": {"payment_status": "Paid", "guarantee_type": "PrePay"}}
    state2 = audit(_state(cls, base2))
    assert "payment.payment_method|payment.guarantee_type" not in state2.audit.missing_required_fields


def test_non_booking_category_is_na_but_still_checks_consistency():
    cls = _classification(predicted_category="payment_billing_or_rate_issue",
                          booking_lifecycle_stage="n/a", request_type="payment_or_billing_inquiry")
    ext = {"financials": {"total_amount": 50.0}}  # currency null → still flagged
    state = audit(_state(cls, ext))
    assert state.audit.audit_finding == "n/a"
    assert state.audit.missing_required_fields == []
    assert "price_without_currency" in state.audit.risk_flags


def test_skips_when_no_llm_output():
    state = audit(AgentState(email=EmailInput(email_id="e")))
    assert state.audit.audit_finding == "n/a"
    assert AGENT_NAME in state.agent_path
