"""Router Agent (#5).

Pure-Python, fully deterministic — the "code decides" layer. Two parts:
  build_router_signals(state) → RouterSignals   (derive facts + decision flags)
  route(signals) → RoutingDecision               (ordered guard clauses)

Design (locked 2026-06-07, reviewer-endorsed):
  - Category-primary: true global pre-empts only (schema-invalid, force flags);
    everything else dispatches by category, with sub-logic inside each branch.
  - NEVER gates on confidence (classifier or validator). confidence is carried
    for logging only. See memory: open-item-confidence-gating.
  - Validator flag is a CONTRIBUTING signal, not a sole gate: it only changes the
    outcome of an otherwise-clean booking_notification (→ audit_only_with_note).
    For hard-escalation categories the route stays category-driven.
  - Deterministic Audit (audit_finding / consistency) is the backbone.
  - kb_answerable is unknown here; policy questions are RAG *candidates*
    (rag_required) resolved by RAG (#6) later.

The RULES catalog mirrors the guard clauses and seeds the generated rules
artifact (no runtime JSON-DSL). A test asserts route()'s rule_ids ⊆ RULES.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.models.router_signals import RoutingDecision, RouterSignals
from app.models.state import AgentState

AGENT_NAME = "router"

_HARD_ESCALATION = {
    "payment_billing_or_rate_issue": ("escalate_to_payment_or_billing",
                                      "Payment/billing/fiscal topic — internal validation by the payment team."),
    "inventory_availability_or_stop_sales": ("escalate_to_inventory_or_operations",
                                             "Inventory/availability/stop-sales — operations team."),
    "system_or_channel_delivery_exception": ("escalate_to_technical_or_operations",
                                             "System/channel/delivery exception — technical/operations team."),
    "booking_change_or_cancellation": ("escalate_to_reservations_team",
                                       "Change/cancellation of an existing booking — reservations team."),
}


@dataclass(frozen=True)
class Rule:
    """A documented routing rule — mirrors a guard clause; feeds the artifact."""
    id: str
    priority: int
    condition: str
    action: str


# Catalog in evaluation order. Kept in sync with route() (asserted by tests).
RULES: list[Rule] = [
    Rule("R001_SCHEMA_INVALID", 1, "schema_valid is False (no usable LLM output)", "manual_review_unclear"),
    Rule("R002_FORCE_MANUAL", 2, "force_manual_review is True", "manual_review_unclear"),
    Rule("R003_OTHER_UNCLEAR", 3, "category == other_or_unclear", "manual_review_unclear"),
    Rule("R040_PAYMENT", 40, "category == payment_billing_or_rate_issue", "escalate_to_payment_or_billing"),
    Rule("R041_INVENTORY", 41, "category == inventory_availability_or_stop_sales", "escalate_to_inventory_or_operations"),
    Rule("R042_SYSTEM", 42, "category == system_or_channel_delivery_exception", "escalate_to_technical_or_operations"),
    Rule("R043_CHANGE_CANCEL", 43, "category == booking_change_or_cancellation", "escalate_to_reservations_team"),
    Rule("R020_BN_SUSPECTED", 20, "booking_notification AND audit_finding == suspected_error", "audit_with_attention"),
    Rule("R021_BN_MISSING", 21, "booking_notification AND audit_finding == missing_fields", "audit_with_attention"),
    Rule("R022_BN_CLEAN_FLAGGED", 22, "booking_notification AND clean AND validator flagged", "audit_only_with_note"),
    Rule("R023_BN_CLEAN", 23, "booking_notification AND clean AND not flagged", "audit_only"),
    Rule("R024_BN_OTHER", 24, "booking_notification AND audit_finding == n/a (unexpected)", "audit_with_attention"),
    Rule("R030_INQ_POLICY", 30, "service_or_information_inquiry AND policy_or_general_question (pre-RAG candidate)", "draft_reply_with_rag"),
    Rule("R030A_INQ_POLICY_ANSWERABLE", 30, "policy question AND kb_answerable is True (post-RAG)", "draft_reply_with_rag"),
    Rule("R030B_INQ_POLICY_UNANSWERABLE", 30, "policy question AND kb_answerable is False (post-RAG)", "escalate_to_reservations_team"),
    Rule("R031_INQ_WITHDRAWAL", 31, "service_or_information_inquiry AND request_type == withdrawal_or_acknowledgment", "audit_only_with_note"),
    Rule("R032_INQ_DEFAULT", 32, "service_or_information_inquiry (any other request_type)", "escalate_to_reservations_team"),
    Rule("R999_FALLBACK", 999, "no rule matched", "manual_review_unclear"),
]


def build_router_signals(state: AgentState) -> RouterSignals:
    """Derive the routing facts + decision flags from the upstream agent outputs."""
    out = state.llm_output
    if out is None:
        msg = next((e.get("message") for e in state.errors
                    if e.get("agent_name") == "classifier_extractor"), None)
        return RouterSignals(schema_valid=False, llm_parse_error=True, llm_error_message=msg)

    cls = out.classification
    audit = state.audit
    validator = state.validator

    category = cls.predicted_category
    request_type = cls.request_type
    expects = cls.expects_human_response
    urgency = cls.urgency_signal
    audit_finding = audit.audit_finding if audit else "n/a"

    # Decision flags (taxonomy_proposal §4.1/4.2). audit_finding is interpreted as
    # ∈ {missing_fields, suspected_error} rather than "≠ clean", so n/a (non-booking)
    # does not spuriously trigger requires_internal_system on audit grounds.
    audit_attention = audit_finding in {"missing_fields", "suspected_error"}
    outbound = (expects == "yes") or audit_attention or (urgency in {"urgent", "sensitive_complaint"})
    requires_internal = (
        category in _HARD_ESCALATION
        or audit_attention
        or (category == "service_or_information_inquiry"
            and request_type not in {"policy_or_general_question", "withdrawal_or_acknowledgment"})
    )
    rag_required = (category == "service_or_information_inquiry"
                    and request_type == "policy_or_general_question")

    return RouterSignals(
        schema_valid=True,
        category=category, request_type=request_type,
        expects_human_response=expects, urgency_signal=urgency,
        classifier_confidence=cls.confidence,
        validator_result=(validator.validation_result if validator else "skipped"),
        validator_flagged_fields=(validator.flagged_fields if validator else []),
        consistency_errors=(audit.consistency_errors if audit else []),
        missing_required_fields=(audit.missing_required_fields if audit else []),
        risk_flags=(audit.risk_flags if audit else []),
        audit_finding=audit_finding,
        requires_internal_system=requires_internal,
        outbound_action_required=outbound,
        rag_required=rag_required,
        kb_answerable=None,
    )


def route(signals: RouterSignals) -> RoutingDecision:
    """Map signals → one recommended_action via ordered guard clauses.

    Confidence (classifier or validator) is intentionally NOT consulted.
    """
    s = signals

    # --- global pre-empts ---
    if not s.schema_valid:
        return _d("R001_SCHEMA_INVALID", "manual_review_unclear",
                  "LLM output failed schema validation; nothing to route on.")
    if s.force_manual_review:
        return _d("R002_FORCE_MANUAL", "manual_review_unclear",
                  s.force_escalation_reason or "An upstream agent forced manual review.")
    if s.category == "other_or_unclear":
        return _d("R003_OTHER_UNCLEAR", "manual_review_unclear",
                  "Category is other_or_unclear.")

    # --- hard-escalation categories (category-driven; validator/risk only annotate) ---
    if s.category in _HARD_ESCALATION:
        action, reason = _HARD_ESCALATION[s.category]
        rid = {"payment_billing_or_rate_issue": "R040_PAYMENT",
               "inventory_availability_or_stop_sales": "R041_INVENTORY",
               "system_or_channel_delivery_exception": "R042_SYSTEM",
               "booking_change_or_cancellation": "R043_CHANGE_CANCEL"}[s.category]
        return _d(rid, action, reason)

    # --- booking_notification: audit_finding governs; validator nudges the clean case ---
    if s.category == "booking_notification":
        if s.audit_finding == "suspected_error":
            return _d("R020_BN_SUSPECTED", "audit_with_attention",
                      "Booking notification with a suspected error from the audit.")
        if s.audit_finding == "missing_fields":
            return _d("R021_BN_MISSING", "audit_with_attention",
                      "Booking notification missing required field(s) for its lifecycle.")
        if s.audit_finding == "clean":
            if s.validator_result == "flagged":
                return _d("R022_BN_CLEAN_FLAGGED", "audit_only_with_note",
                          "Audit clean but the validator flagged the output for review.")
            return _d("R023_BN_CLEAN", "audit_only",
                      "Clean booking notification — routine audit only.")
        # audit_finding == n/a on a booking shouldn't happen; be safe.
        return _d("R024_BN_OTHER", "audit_with_attention",
                  "Booking notification without a determinable audit verdict.")

    # --- service_or_information_inquiry ---
    if s.category == "service_or_information_inquiry":
        if s.request_type == "policy_or_general_question":
            if s.kb_answerable is True:
                return _d("R030A_INQ_POLICY_ANSWERABLE", "draft_reply_with_rag",
                          "Policy/general question answerable from the KB (RAG confirmed).")
            if s.kb_answerable is False:
                return _d("R030B_INQ_POLICY_UNANSWERABLE", "escalate_to_reservations_team",
                          "Policy/general question not answerable from the KB; escalate.")
            return _d("R030_INQ_POLICY", "draft_reply_with_rag",
                      "Policy/general question — RAG candidate (kb_answerable resolved by RAG).")
        if s.request_type == "withdrawal_or_acknowledgment":
            return _d("R031_INQ_WITHDRAWAL", "audit_only_with_note",
                      "Withdrawal/acknowledgment — file with a note; no reply needed.")
        return _d("R032_INQ_DEFAULT", "escalate_to_reservations_team",
                  "Service/information inquiry requiring the reservations team.")

    # --- terminal fallback ---
    return _d("R999_FALLBACK", "manual_review_unclear",
              "No routing rule matched.")


def route_email(state: AgentState) -> AgentState:
    """Agent entry: build signals, decide, write results onto the state."""
    signals = build_router_signals(state)
    decision = route(signals)
    state.router_signals = signals
    state.recommended_action = decision.recommended_action
    state.routing_reason = decision.routing_reason
    state.applied_rule_id = decision.rule_id
    state.agent_path.append(AGENT_NAME)
    return state


def _d(rule_id: str, action: str, reason: str) -> RoutingDecision:
    return RoutingDecision(recommended_action=action, routing_reason=reason, rule_id=rule_id)


# --- generated documentation artifact (no runtime JSON-DSL) ---
def generate_rules_artifact(outputs_dir: Path | None = None) -> tuple[Path, Path]:
    """Write the rule catalog as an auditable artifact for the thesis/appendix.

    Documentation only — runtime behaviour is the route() function, tested directly.
    """
    out = outputs_dir or get_settings().outputs_dir
    rules = [r.__dict__ for r in sorted(RULES, key=lambda r: r.priority)]
    json_path = out / "routing_rules.generated.json"
    json_path.write_text(json.dumps(
        {"description": "Generated from app/agents/router.py route(). Documentation only; "
                        "runtime behaviour is the Python router, not this file.",
         "evaluation_order": "ascending priority; first matching guard wins",
         "rules": rules}, indent=2))
    md_lines = ["# Routing Rules (generated)", "",
                "Generated from `app/agents/router.py`. Documentation only — runtime "
                "behaviour is the `route()` guard clauses, tested directly.", "",
                "| Priority | Rule ID | Condition | Action |", "|---:|---|---|---|"]
    md_lines += [f"| {r.priority} | {r.id} | {r.condition} | {r.action} |"
                 for r in sorted(RULES, key=lambda r: r.priority)]
    md_path = out / "routing_rules.generated.md"
    md_path.write_text("\n".join(md_lines) + "\n")
    return json_path, md_path


if __name__ == "__main__":
    j, m = generate_rules_artifact()
    print(f"wrote {j}\nwrote {m}")
