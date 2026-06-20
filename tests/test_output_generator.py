"""Output Generator (#7): offline tests over every dispatch branch.

The agent makes NO routing decisions — it formats the already-decided
recommended_action. Deterministic artifacts (audit_checklist / escalation_summary
/ manual-review notes) need no LLM; only the customer-facing draft_reply calls the
model, via an injected fake client (no Ollama). The draft path must self-validate
(non-empty text citing real source ids) or withhold.
"""
from app.agents.output_generator import AGENT_NAME, generate_output
from app.llm.client import LLMResult
from app.models.audit import AuditOutput
from app.models.llm_output import EmailExtraction
from app.models.output import GeneratedReply
from app.models.retrieval import RetrievalOutput, RetrievalSource
from app.models.state import AgentState, EmailInput, ValidatorOutput


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


# A complete booking: all eight _KEY_FIELDS present → a clean checklist has no ⚠.
_COMPLETE = {
    "booking_identity": {"source_channel": "Booking.com", "booking_reference": "631",
                         "hotel_name": "Pestana - Brussels", "notification_type": "new"},
    "guest": {"guest_name": "MASKED_NAME_x"},
    "stay": {"check_in_date": "2026-03-06", "check_out_date": "2026-03-08", "adults": 2},
    "room_and_rate": {"room_type": "Double Room"},
    "financials": {"total_amount": 208.17, "currency": "EUR"},
}

_INQUIRY = _classification(predicted_category="service_or_information_inquiry",
                           sender_type="direct_guest",
                           request_type="policy_or_general_question",
                           booking_lifecycle_stage="n/a", expects_human_response="yes")

_UNSET = object()


def _llm_output(classification=None, extraction=None):
    return EmailExtraction.model_validate({
        "classification": classification or _classification(),
        "extraction": extraction if extraction is not None else _COMPLETE,
    })


def _state(action, *, llm_output=_UNSET, audit=None, validator=None, retrieval=None,
           routing_reason="test reason", applied_rule_id="R000_TEST") -> AgentState:
    if llm_output is _UNSET:
        llm_output = _llm_output()
    return AgentState(
        email=EmailInput(email_id="e", subject="Subject", body_clean="body"),
        llm_output=llm_output, audit=audit, validator=validator, retrieval=retrieval,
        recommended_action=action, routing_reason=routing_reason, applied_rule_id=applied_rule_id,
    )


class _FakeReplyClient:
    """Returns a fixed LLMResult; matches the LLMClient.call_structured signature."""
    def __init__(self, result):
        self._result = result

    def call_structured(self, system_prompt, user_prompt, *, response_model,
                        model=None, temperature=None, seed=None):
        return self._result


def _reply_client(reply_text="You can cancel up to 48h before arrival.",
                  source_ids=("faq_001",), valid=True, error=None):
    output = GeneratedReply(reply_text=reply_text, used_source_ids=list(source_ids)) if valid else None
    return _FakeReplyClient(LLMResult(valid, output, error, 1.0, "m"))


def _draft_state():
    """A policy-inquiry state with one real retrieved source (faq_001)."""
    sources = [RetrievalSource(
        source_id="faq_001", source_title="Cancellation policy",
        chunk_text="You can cancel free of charge until 48h before arrival.",
        score=0.9, raw_distance=0.1,
        metadata={"question": "What is the cancellation policy?",
                  "answer": "You can cancel free of charge until 48h before arrival."})]
    retrieval = RetrievalOutput(used=True, sources=sources,
                                query_text="cancellation policy", kb_answerable=True)
    return _state("draft_reply_with_rag", llm_output=_llm_output(_INQUIRY),
                  retrieval=retrieval, applied_rule_id="R030A_INQ_POLICY_ANSWERABLE")


# ---------- audit checklist ----------
def test_audit_only_clean_checklist():
    st = _state("audit_only", audit=AuditOutput(audit_finding="clean"))
    generate_output(st)
    out = st.output
    assert out.audit_checklist
    assert any("Verify Booking reference: 631" in i for i in out.audit_checklist)
    assert out.audit_checklist[-1] == "Action: routine audit vs PMS; no issues detected."
    assert not any("⚠" in i for i in out.audit_checklist)
    assert out.internal_notes.startswith("No issues detected.")
    assert out.draft_reply is None
    assert out.clarification_draft is None
    assert AGENT_NAME in st.agent_path


def test_audit_with_attention_surfaces_warnings():
    audit = AuditOutput(audit_finding="suspected_error",
                        missing_required_fields=["financials.total_amount"],
                        consistency_errors=["checkout_before_checkin"],
                        risk_flags=["price_without_currency"])
    validator = ValidatorOutput(validation_result="flagged", flagged_fields=["total_amount"])
    st = _state("audit_with_attention", audit=audit, validator=validator)
    generate_output(st)
    items = st.output.audit_checklist
    assert any("⚠ Missing required field(s)" in i for i in items)
    assert any("⚠ Consistency: checkout_before_checkin" in i for i in items)
    assert any("⚠ Risk flag(s): price_without_currency" in i for i in items)
    assert any("⚠ Validator flagged: total_amount" in i for i in items)
    assert items[-1] == "Action: verify the flagged/missing items before treating this as clean."


def test_checklist_marks_unextracted_field():
    ext = {**_COMPLETE, "financials": {"currency": "EUR"}}  # total_amount absent
    st = _state("audit_only", llm_output=_llm_output(extraction=ext),
                audit=AuditOutput(audit_finding="clean"))
    generate_output(st)
    items = st.output.audit_checklist
    assert "⚠ Total: (not extracted)" in items
    assert any("Verify Currency: EUR" in i for i in items)


# ---------- escalation ----------
def test_escalation_summary_and_notes():
    st = _state("escalate_to_reservations_team", routing_reason="needs reservations team",
                applied_rule_id="R043_CHANGE_CANCEL",
                llm_output=_llm_output(_classification(
                    predicted_category="booking_change_or_cancellation",
                    request_type="cancellation_request", booking_lifecycle_stage="cancelled")))
    generate_output(st)
    out = st.output
    assert out.escalation_summary
    assert "Reservations Team" in out.escalation_summary
    assert "needs reservations team" in out.escalation_summary
    assert "No access to PMS / CRS / payment systems" in out.escalation_summary
    assert out.internal_notes
    assert out.draft_reply is None
    assert out.audit_checklist == []


def test_escalation_target_label_map():
    st = _state("escalate_to_payment_or_billing",
                llm_output=_llm_output(_classification(
                    predicted_category="payment_billing_or_rate_issue",
                    request_type="payment_or_billing_inquiry", booking_lifecycle_stage="n/a")))
    generate_output(st)
    assert "Payment / Billing Team" in st.output.escalation_summary


# ---------- manual review / schema-invalid ----------
def test_manual_review_notes():
    st = _state("manual_review_unclear", routing_reason="ambiguous",
                applied_rule_id="R003_OTHER_UNCLEAR")
    generate_output(st)
    out = st.output
    assert "Manual review required" in out.internal_notes
    assert "Do not use any generated customer-facing text." in out.internal_notes
    assert out.draft_reply is None
    assert out.audit_checklist == []


def test_schema_invalid_notes():
    st = _state("manual_review_unclear", llm_output=None, applied_rule_id="R001_SCHEMA_INVALID")
    generate_output(st)
    assert "no valid LLM output (schema-invalid)." in st.output.internal_notes


# ---------- grounded draft reply ----------
def test_draft_reply_happy_path():
    st = _draft_state()
    generate_output(st, reply_client=_reply_client())
    out = st.output
    assert out.draft_reply == "You can cancel up to 48h before arrival."
    assert out.used_source_ids == ["faq_001"]
    assert "Draft grounded in 1 FAQ source" in out.internal_notes


def test_draft_withheld_no_sources():
    st = _state("draft_reply_with_rag", llm_output=_llm_output(_INQUIRY),
                retrieval=RetrievalOutput(used=True, sources=[]))
    # A valid client is supplied: if the early withhold regressed, draft_reply would
    # be populated and the assertion below would fail loudly.
    generate_output(st, reply_client=_reply_client())
    assert st.output.draft_reply is None
    assert "Draft withheld (no retrieval sources)" in st.output.internal_notes


def test_draft_withheld_uncited_source():
    st = _draft_state()
    generate_output(st, reply_client=_reply_client(source_ids=["faq_999"]))
    assert st.output.draft_reply is None
    assert "draft failed source validation (empty or uncited)" in st.output.internal_notes


def test_draft_withheld_empty_text():
    st = _draft_state()
    generate_output(st, reply_client=_reply_client(reply_text="   "))
    assert st.output.draft_reply is None
    assert "draft failed source validation (empty or uncited)" in st.output.internal_notes


def test_draft_withheld_generation_failed():
    st = _draft_state()
    generate_output(st, reply_client=_reply_client(valid=False, error="boom"))
    assert st.output.draft_reply is None
    assert "generation failed: boom" in st.output.internal_notes
