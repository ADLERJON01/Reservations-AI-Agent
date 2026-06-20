"""Output Generator Agent (#7).

Formats the already-decided result into the human-facing artifact. Dispatches by
recommended_action; it makes NO routing decisions. Deterministic for the
structured artifacts (audit_checklist / escalation_summary / internal_notes);
the LLM is used ONLY for the grounded customer-facing draft_reply.

Design principles (post-review):
  - Surface upstream uncertainty: missing fields / validator flags / audit
    warnings are foregrounded; incomplete extraction is shown as incomplete.
  - internal_notes is concise (minimal for clean cases; a structured packet for
    manual review). Full trace lives in state/DB, not here.
  - draft_reply gets STRUCTURAL self-validation here (real, non-empty sources);
    SEMANTIC operational-claim blocking is Guardrails' (#8) job, not this agent's.
  - clarification_draft is deferred (null in v1).
"""
from __future__ import annotations

from typing import List, Optional

from app.config import get_settings
from app.llm.client import LLMClient
from app.models.output import GeneratedReply, OutputArtifacts
from app.models.retrieval import RetrievalSource
from app.models.state import AgentState

AGENT_NAME = "output_generator"

_AUDIT_ACTIONS = {"audit_only", "audit_with_attention", "audit_only_with_note"}
_ESCALATION_TARGET = {
    "escalate_to_reservations_team": "Reservations Team",
    "escalate_to_payment_or_billing": "Payment / Billing Team",
    "escalate_to_inventory_or_operations": "Inventory / Operations Team",
    "escalate_to_technical_or_operations": "Technical / Operations Team",
}
# (label, extraction_group, field) — the fields a human verifies / a summary needs.
_KEY_FIELDS = [
    ("Booking reference", "booking_identity", "booking_reference"),
    ("Guest", "guest", "guest_name"),
    ("Hotel", "booking_identity", "hotel_name"),
    ("Check-in", "stay", "check_in_date"),
    ("Check-out", "stay", "check_out_date"),
    ("Room type", "room_and_rate", "room_type"),
    ("Total", "financials", "total_amount"),
    ("Currency", "financials", "currency"),
]

DRAFT_SYSTEM_PROMPT = (
    "You draft a customer-service reply for Pestana Hotels using ONLY the provided "
    "FAQ sources. Rules:\n"
    "- Answer ONLY from the sources; never invent policies, prices, dates, or facts.\n"
    "- This is a DRAFT for a human agent to review — it is never sent automatically.\n"
    "- Do NOT confirm or perform any action: no booking, change, cancellation, "
    "payment, refund, or availability confirmation.\n"
    "- Do NOT claim access to any internal or reservation system.\n"
    "- If the sources do not answer the question, say a colleague will follow up.\n"
    "- Retain anonymized MASKED_* tokens verbatim.\n"
    "Output reply_text (the customer-facing draft) and used_source_ids (the id of "
    "each source you actually used)."
)


def generate_output(state: AgentState, reply_client: Optional[LLMClient] = None) -> AgentState:
    """Produce state.output for the decided recommended_action."""
    state.agent_path.append(AGENT_NAME)
    action = state.recommended_action

    if state.llm_output is None or action == "manual_review_unclear":
        state.output = _manual_review_notes(state)
    elif action in _AUDIT_ACTIONS:
        state.output = _audit_checklist(state)
    elif action in _ESCALATION_TARGET:
        state.output = OutputArtifacts(escalation_summary=_escalation_summary(state),
                                       internal_notes=_internal_notes(state))
    elif action == "draft_reply_with_rag":
        state.output = _draft_reply(state, reply_client)
    else:  # unknown/None action — fail safe to a review note (no silent skip)
        state.output = _manual_review_notes(state)
    return state


# ---------- deterministic helpers ----------
def _field(ext, group: str, name: str):
    v = getattr(getattr(ext, group), name, None)
    return v if v not in (None, "") else None


def _internal_notes(state: AgentState) -> str:
    """Concise reviewer-facing note. Minimal for clean cases."""
    base = f"Routed by {state.applied_rule_id} ({state.recommended_action})."
    extras: List[str] = []
    if state.audit:
        if state.audit.missing_required_fields:
            extras.append(f"{len(state.audit.missing_required_fields)} missing field(s)")
        if state.audit.risk_flags:
            extras.append("risk: " + ", ".join(state.audit.risk_flags))
    if state.validator and state.validator.validation_result == "flagged":
        extras.append("validator flagged")
    if not extras:
        return f"No issues detected. {base}"
    return f"{base} Attention: " + "; ".join(extras) + "."


def _audit_checklist(state: AgentState) -> OutputArtifacts:
    ext = state.llm_output.extraction
    audit = state.audit
    items: List[str] = []
    for label, group, name in _KEY_FIELDS:
        v = _field(ext, group, name)
        items.append(f"Verify {label}: {v}" if v is not None else f"⚠ {label}: (not extracted)")

    if audit:
        if audit.missing_required_fields:
            items.append("⚠ Missing required field(s): " + ", ".join(audit.missing_required_fields))
        for err in audit.consistency_errors:
            items.append(f"⚠ Consistency: {err}")
        if audit.risk_flags:
            items.append("⚠ Risk flag(s): " + ", ".join(audit.risk_flags))
        items.append(f"Audit finding: {audit.audit_finding}")

    if state.validator and state.validator.validation_result == "flagged":
        flagged = ", ".join(state.validator.flagged_fields) or "(see validator)"
        items.append(f"⚠ Validator flagged: {flagged}")

    clean = bool(audit) and audit.audit_finding == "clean"
    items.append("Action: routine audit vs PMS; no issues detected."
                 if clean else
                 "Action: verify the flagged/missing items before treating this as clean.")
    return OutputArtifacts(audit_checklist=items, internal_notes=_internal_notes(state))


def _escalation_summary(state: AgentState) -> str:
    cls = state.llm_output.classification
    ext = state.llm_output.extraction
    target = _ESCALATION_TARGET.get(state.recommended_action, "Internal Team")
    lines = [f"Escalation summary — {target}", "",
             f"Reason: {state.routing_reason}", "",
             "Classification:",
             f"- Category: {cls.predicted_category}",
             f"- Request type: {cls.request_type}", "",
             "Key extracted details:"]
    for label, group, name in _KEY_FIELDS:
        v = _field(ext, group, name)
        lines.append(f"- {label}: {v if v is not None else '(not extracted)'}")

    audit = state.audit
    issues: List[str] = []
    if audit:
        issues += list(audit.consistency_errors)
        if audit.missing_required_fields:
            issues.append("Missing: " + ", ".join(audit.missing_required_fields))
        if audit.risk_flags:
            issues.append("Risk: " + ", ".join(audit.risk_flags))
    if issues:
        lines += ["", "Issues:"] + [f"- {i}" for i in issues]

    lines += ["", "System limitations:",
              "- No access to PMS / CRS / payment systems; no booking action has been performed.",
              "", "Suggested next step:",
              "- Verify in the internal system and draft/approve a customer response manually."]
    return "\n".join(lines)


def _manual_review_notes(state: AgentState) -> OutputArtifacts:
    lines = ["Manual review required.", "", f"Reason: {state.routing_reason}", ""]
    if state.llm_output is not None:
        cls = state.llm_output.classification
        lines += ["System interpretation:",
                  f"- Category: {cls.predicted_category}",
                  f"- Request type: {cls.request_type}",
                  f"- Confidence (logged, not gated): {cls.confidence}"]
    else:
        lines += ["System interpretation: no valid LLM output (schema-invalid)."]
    if state.validator and state.validator.validation_result == "flagged":
        lines.append("- Validator flagged: " + (", ".join(state.validator.flagged_fields) or "(see validator)"))
    if state.audit:
        if state.audit.audit_finding != "n/a":
            lines.append(f"- Audit: {state.audit.audit_finding}")
        for err in state.audit.consistency_errors:
            lines.append(f"- Consistency: {err}")
        if state.audit.missing_required_fields:
            lines.append("- Missing: " + ", ".join(state.audit.missing_required_fields))
    lines += ["", "Suggested action:",
              "- Inspect the original email manually.",
              "- Do not use any generated customer-facing text."]
    return OutputArtifacts(internal_notes="\n".join(lines))


# ---------- LLM draft (the one free-text, customer-facing artifact) ----------
def _sources_block(sources: List[RetrievalSource]) -> str:
    blocks = []
    for s in sources:
        q = s.metadata.get("question") or s.source_title or ""
        a = s.metadata.get("answer") or s.chunk_text or ""
        blocks.append(f"[{s.source_id}] Q: {q}\nA: {a}")
    return "\n\n".join(blocks)


def _draft_withheld(state: AgentState, reason: str) -> OutputArtifacts:
    """Decline to emit an unsafe/ungrounded draft. No re-routing — flag for the human."""
    return OutputArtifacts(internal_notes=(
        f"Draft withheld ({reason}). Escalate to the reservations team for a manual response."))


def _draft_reply(state: AgentState, reply_client: Optional[LLMClient]) -> OutputArtifacts:
    sources = state.retrieval.sources if state.retrieval else []
    if not sources:
        return _draft_withheld(state, "no retrieval sources")

    s = get_settings()
    if reply_client is None:
        from app.llm.ollama_native import OllamaNativeClient
        reply_client = OllamaNativeClient()

    question = (state.retrieval.query_text if state.retrieval else None) or (state.email.subject or "")
    user_prompt = (f"Customer question:\n{question}\n\n"
                   f"FAQ sources:\n{_sources_block(sources)}\n\n"
                   f"Write the draft reply.")
    result = reply_client.call_structured(
        DRAFT_SYSTEM_PROMPT, user_prompt, response_model=GeneratedReply,
        model=s.primary_model, temperature=s.classifier_temperature, seed=s.classifier_seed)

    if not result.valid or result.output is None:
        return _draft_withheld(state, f"generation failed: {result.error or 'unknown'}")

    reply: GeneratedReply = result.output
    valid_ids = {src.source_id for src in sources}
    used = [sid for sid in reply.used_source_ids if sid in valid_ids]
    # STRUCTURAL self-validation: non-empty grounded reply citing real sources.
    if not reply.reply_text.strip() or not used:
        return _draft_withheld(state, "draft failed source validation (empty or uncited)")

    cited = "\n".join(f"- [{src.source_id}] {src.source_title}"
                      for src in sources if src.source_id in used)
    notes = (f"Draft grounded in {len(used)} FAQ source(s):\n{cited}\n"
             f"Draft-only — human review required before sending.")
    return OutputArtifacts(draft_reply=reply.reply_text.strip(), used_source_ids=used,
                           internal_notes=notes)
