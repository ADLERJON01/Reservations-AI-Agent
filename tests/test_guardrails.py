"""Guardrails (#8): deterministic, offline. Covers the no-op paths, the Core 5
block rules (EN + PT), precision (legitimate policy text must pass), the negation
guard, and the block behaviour (redact draft, preserve it, flag, don't re-route).
"""
import pytest

from app.agents.guardrails import AGENT_NAME, check_guardrails
from app.models.output import OutputArtifacts
from app.models.state import AgentState, EmailInput


def _state(draft, *, action="draft_reply_with_rag", internal_notes="grounded note"):
    output = OutputArtifacts(draft_reply=draft, used_source_ids=["faq_001"],
                             internal_notes=internal_notes) if draft is not None else \
        OutputArtifacts(audit_checklist=["Verify X"], internal_notes=internal_notes)
    return AgentState(email=EmailInput(email_id="e"), output=output,
                      recommended_action=action, applied_rule_id="R030A")


def _run(draft, **kw):
    st = _state(draft, **kw)
    check_guardrails(st)
    return st


# ---------- no-op paths ----------
def test_noop_when_no_draft():
    st = _run(None, action="audit_only")          # audit path → no draft_reply
    assert st.guardrails.passed is True
    assert st.guardrails.blocked_claims == []
    assert st.output.audit_checklist == ["Verify X"]   # untouched
    assert AGENT_NAME in st.agent_path


def test_noop_when_output_is_none():
    st = AgentState(email=EmailInput(email_id="e"), recommended_action="manual_review_unclear")
    check_guardrails(st)
    assert st.guardrails.passed is True
    assert AGENT_NAME in st.agent_path


# ---------- precision: legitimate grounded drafts must PASS ----------
@pytest.mark.parametrize("draft", [
    "You can cancel free of charge up to 48 hours before arrival.",
    "Refunds may take up to 10 business days according to policy.",
    "Please contact the reservations team to confirm availability.",
    "We cannot guarantee availability; please contact reservations.",   # negation guard
    "According to our cancellation policy, no-shows are charged the first night.",
])
def test_clean_policy_drafts_pass(draft):
    st = _run(draft)
    assert st.guardrails.passed is True, draft
    assert st.output.draft_reply == draft          # not redacted


# ---------- Core 5 blocks (EN + PT) ----------
@pytest.mark.parametrize("draft, rule_id", [
    ("I have confirmed your booking for those dates.", "GR001_ACTION_PERFORMED"),
    ("Your reservation has been cancelled as requested.", "GR001_ACTION_PERFORMED"),
    ("A sua reserva foi alterada com sucesso.", "GR001_ACTION_PERFORMED"),
    ("I checked our system and your booking is there.", "GR002_SYSTEM_ACCESS"),
    ("Verifiquei no nosso sistema e está tudo certo.", "GR002_SYSTEM_ACCESS"),
    ("Your room is reserved and waiting for you.", "GR003_FIRM_COMMITMENT"),
    ("Your payment has been processed successfully.", "GR004_PAYMENT_REFUND"),
    ("O reembolso foi processado esta manhã.", "GR004_PAYMENT_REFUND"),
    ("The room is available for your dates.", "GR005_AVAILABILITY_PRICE"),
])
def test_forbidden_claims_blocked(draft, rule_id):
    st = _run(draft)
    assert st.guardrails.passed is False, draft
    assert st.guardrails.blocked_claims[0].rule_id == rule_id
    assert st.output.draft_reply is None                       # redacted


# ---------- block behaviour ----------
def test_block_redacts_and_preserves_and_flags():
    draft = "Good news! I have confirmed your booking. Let me know if you need anything."
    st = _run(draft, internal_notes="Draft grounded in 1 FAQ source(s).")
    g = st.guardrails
    assert g.passed is False
    assert g.escalation_reason and "withheld" in g.escalation_reason
    # draft withheld but preserved for audit, with a loud notice + the rule id
    assert st.output.draft_reply is None
    assert "DRAFT BLOCKED BY GUARDRAILS" in st.output.internal_notes
    assert "GR001_ACTION_PERFORMED" in st.output.internal_notes
    assert draft in st.output.internal_notes                   # original kept
    assert "Draft grounded in 1 FAQ source(s)." in st.output.internal_notes  # prior note kept


def test_block_does_not_overwrite_recommended_action():
    st = _run("Your refund has been processed.")
    assert st.guardrails.passed is False
    assert st.recommended_action == "draft_reply_with_rag"     # Router still owns routing


def test_only_offending_sentence_is_flagged():
    draft = ("Thank you for your message. I have cancelled your booking. "
             "Our team remains at your disposal.")
    st = _run(draft)
    assert len(st.guardrails.blocked_claims) == 1
    assert "cancelled your booking" in st.guardrails.blocked_claims[0].claim_text.lower()
