"""Router (#5): fully deterministic, offline. Covers the action matrix, the
decision-flag computation, the philosophy guards (confidence ignored; validator
flag alone doesn't force manual_review), and rule-catalog anti-drift.
"""
from app.agents.router import RULES, build_router_signals, route, route_email
from app.models.audit import AuditOutput
from app.models.llm_output import EmailExtraction
from app.models.router_signals import RouterSignals
from app.models.state import AgentState, EmailInput, ValidatorOutput


def _signals(**over) -> RouterSignals:
    base = dict(schema_valid=True, category="booking_notification", request_type="none",
                expects_human_response="no", urgency_signal="routine",
                audit_finding="clean", validator_result="confirmed")
    base.update(over)
    return RouterSignals(**base)


# --- global pre-empts ---
def test_schema_invalid_to_manual_review():
    d = route(_signals(schema_valid=False))
    assert d.recommended_action == "manual_review_unclear"
    assert d.rule_id == "R001_SCHEMA_INVALID"


def test_force_manual_review():
    d = route(_signals(force_manual_review=True))
    assert d.recommended_action == "manual_review_unclear"
    assert d.rule_id == "R002_FORCE_MANUAL"


def test_other_or_unclear_to_manual_review():
    d = route(_signals(category="other_or_unclear"))
    assert d.recommended_action == "manual_review_unclear"


# --- hard-escalation categories ---
def test_hard_escalations():
    cases = {
        "payment_billing_or_rate_issue": "escalate_to_payment_or_billing",
        "inventory_availability_or_stop_sales": "escalate_to_inventory_or_operations",
        "system_or_channel_delivery_exception": "escalate_to_technical_or_operations",
        "booking_change_or_cancellation": "escalate_to_reservations_team",
    }
    for cat, action in cases.items():
        assert route(_signals(category=cat)).recommended_action == action


# --- booking_notification sub-logic ---
def test_booking_clean_is_audit_only():
    d = route(_signals(category="booking_notification", audit_finding="clean"))
    assert d.recommended_action == "audit_only"


def test_booking_missing_is_attention():
    d = route(_signals(audit_finding="missing_fields"))
    assert d.recommended_action == "audit_with_attention"


def test_booking_suspected_is_attention():
    d = route(_signals(audit_finding="suspected_error"))
    assert d.recommended_action == "audit_with_attention"


def test_booking_clean_but_validator_flagged_is_note():
    d = route(_signals(audit_finding="clean", validator_result="flagged"))
    assert d.recommended_action == "audit_only_with_note"
    assert d.rule_id == "R022_BN_CLEAN_FLAGGED"


# --- service inquiry sub-logic ---
def test_policy_question_is_rag_candidate():
    d = route(_signals(category="service_or_information_inquiry",
                       request_type="policy_or_general_question"))
    assert d.recommended_action == "draft_reply_with_rag"


def test_withdrawal_is_note():
    d = route(_signals(category="service_or_information_inquiry",
                       request_type="withdrawal_or_acknowledgment"))
    assert d.recommended_action == "audit_only_with_note"


def test_service_inquiry_default_escalates():
    d = route(_signals(category="service_or_information_inquiry",
                       request_type="new_booking_request"))
    assert d.recommended_action == "escalate_to_reservations_team"


# --- PHILOSOPHY GUARDS (protect the corrected design) ---
def test_low_confidence_is_ignored():
    # a clean booking with very low confidence must still be audit_only
    d = route(_signals(audit_finding="clean", classifier_confidence=0.01))
    assert d.recommended_action == "audit_only"


def test_validator_flag_alone_does_not_force_manual_review():
    # flagged + hard-escalation category → still category-driven, NOT manual_review
    d = route(_signals(category="payment_billing_or_rate_issue", validator_result="flagged"))
    assert d.recommended_action == "escalate_to_payment_or_billing"


# --- decision-flag computation in build_router_signals ---
def _state(category, request_type="none", audit_finding="clean", expects="no",
           urgency="routine") -> AgentState:
    out = EmailExtraction.model_validate({
        "classification": {"predicted_category": category, "sender_type": "automated_system",
                           "request_type": request_type, "booking_lifecycle_stage": "new",
                           "expects_human_response": expects, "urgency_signal": urgency,
                           "confidence": 0.5, "evidence_short": "e", "reasoning_short": "r"},
        "extraction": {}})
    return AgentState(email=EmailInput(email_id="e"), llm_output=out,
                      audit=AuditOutput(audit_finding=audit_finding),
                      validator=ValidatorOutput(validation_result="confirmed"))


def test_flags_payment_requires_internal_and_outbound():
    sig = build_router_signals(_state("payment_billing_or_rate_issue"))
    assert sig.requires_internal_system is True


def test_flags_policy_question_no_internal_and_rag_required():
    sig = build_router_signals(_state("service_or_information_inquiry",
                                      request_type="policy_or_general_question"))
    assert sig.requires_internal_system is False
    assert sig.rag_required is True
    assert sig.kb_answerable is None


def test_flags_outbound_on_missing_fields():
    sig = build_router_signals(_state("booking_notification", audit_finding="missing_fields"))
    assert sig.outbound_action_required is True


def test_build_signals_schema_invalid_when_no_output():
    state = AgentState(email=EmailInput(email_id="e"),
                       errors=[{"agent_name": "classifier_extractor", "message": "boom"}])
    sig = build_router_signals(state)
    assert sig.schema_valid is False and sig.llm_parse_error is True
    assert sig.llm_error_message == "boom"


# --- agent entry writes through to state ---
def test_route_email_writes_state():
    state = route_email(_state("booking_notification", audit_finding="clean"))
    assert state.recommended_action == "audit_only"
    assert state.applied_rule_id == "R023_BN_CLEAN"
    assert state.routing_reason
    assert "router" in state.agent_path
    assert state.router_signals is not None


# --- anti-drift: every rule_id route() can emit exists in the catalog ---
def test_route_rule_ids_subset_of_catalog():
    catalog_ids = {r.id for r in RULES}
    emitted = set()
    samples = [
        _signals(schema_valid=False),
        _signals(force_manual_review=True),
        _signals(category="other_or_unclear"),
        _signals(category="payment_billing_or_rate_issue"),
        _signals(category="inventory_availability_or_stop_sales"),
        _signals(category="system_or_channel_delivery_exception"),
        _signals(category="booking_change_or_cancellation"),
        _signals(audit_finding="suspected_error"),
        _signals(audit_finding="missing_fields"),
        _signals(audit_finding="clean", validator_result="flagged"),
        _signals(audit_finding="clean"),
        _signals(audit_finding="n/a"),
        _signals(category="service_or_information_inquiry", request_type="policy_or_general_question"),
        _signals(category="service_or_information_inquiry", request_type="withdrawal_or_acknowledgment"),
        _signals(category="service_or_information_inquiry", request_type="new_booking_request"),
    ]
    for sig in samples:
        emitted.add(route(sig).rule_id)
    assert emitted <= catalog_ids
    # and the catalog has no duplicate ids
    assert len(catalog_ids) == len(RULES)
