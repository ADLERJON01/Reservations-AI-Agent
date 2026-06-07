"""Audit Agent (#4).

Pure-Python, fully deterministic. Verifies the Classifier's output and produces
the sound signals the Router consumes — the "code decides" backbone,
complementary to the Validator's LLM critique. No LLM, no I/O.

Three layers:
  1. Consistency (all categories) → consistency_errors + risk_flags.
  2. Completeness (booking_notification only) → missing_required_fields + audit_finding.
  3. Risk flags = named tags for the consistency anomalies (machine-readable).

Deterministic grounding is intentionally NOT done in v1 (reformatted dates/amounts
and MASKED_* names make substring matching noisy; the Validator covers grounding
semantically). grounding_errors stays reserved/empty.

risk_flags are provisional (v1) — high-precision only. Parked candidates for the
later risk-flag review: payment_topic_with_no_amount, zero_total_non_cancellation,
occupancy_mismatch, request_type/category coherence. (free-form list; easy to add.)
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from app.models.audit import AuditOutput
from app.models.llm_output import Classification, Extraction
from app.models.state import AgentState

AGENT_NAME = "audit"

# Required-field sets per lifecycle (the "always expected" rows of
# llm_output_schema.md §6). Conditionally-expected fields are intentionally NOT
# enforced, to avoid false-positive missing_fields. Each entry is
# (required_paths, any_of_groups) where any_of_groups need >=1 present.
_NEW_REQUIRED = [
    "booking_identity.source_channel", "booking_identity.booking_reference",
    "booking_identity.hotel_name", "guest.guest_name",
    "stay.check_in_date", "stay.check_out_date", "stay.adults",
    "financials.total_amount", "financials.currency",
]
REQUIRED_BY_LIFECYCLE: dict[str, tuple[list[str], list[list[str]]]] = {
    "new": (_NEW_REQUIRED, []),
    "paid": (_NEW_REQUIRED + ["payment.payment_status"],
             [["payment.payment_method", "payment.guarantee_type"]]),
    "pre_arrival": (["booking_identity.source_channel", "booking_identity.booking_reference",
                     "booking_identity.hotel_name", "guest.guest_name",
                     "stay.check_in_date"], []),
    "modified": (["booking_identity.source_channel", "booking_identity.booking_reference",
                  "booking_identity.hotel_name", "guest.guest_name",
                  "stay.check_in_date", "stay.check_out_date",
                  "booking_identity.modified_on_date"], []),
    "cancelled": (["booking_identity.source_channel", "booking_identity.booking_reference",
                   "booking_identity.hotel_name", "guest.guest_name",
                   "booking_identity.cancelled_on_date"], []),
}


def audit(state: AgentState) -> AgentState:
    """Run deterministic verification over state.llm_output, populating state.audit."""
    state.agent_path.append(AGENT_NAME)

    if state.llm_output is None:
        state.audit = AuditOutput(audit_finding="n/a")
        return state

    cls = state.llm_output.classification
    ext = state.llm_output.extraction

    consistency_errors, risk_flags = _consistency_checks(cls, ext)

    missing: list[str] = []
    finding = "n/a"
    if cls.predicted_category == "booking_notification":
        missing = _missing_required(cls.booking_lifecycle_stage, ext)
        if consistency_errors:
            finding = "suspected_error"   # precedence: suspected_error > missing_fields > clean
        elif missing:
            finding = "missing_fields"
        else:
            finding = "clean"

    state.audit = AuditOutput(
        audit_finding=finding,
        missing_required_fields=missing,
        consistency_errors=consistency_errors,
        risk_flags=risk_flags,
    )
    return state


def _consistency_checks(cls: Classification, ext: Extraction) -> tuple[list[str], list[str]]:
    """High-precision deterministic anomalies. Each fired check yields a detailed
    consistency_error and a matching named risk_flag."""
    errors: list[str] = []
    flags: list[str] = []

    # 1. check-out before check-in
    ci = _parse_date(ext.stay.check_in_date)
    co = _parse_date(ext.stay.check_out_date)
    if ci and co and co < ci:
        errors.append(f"stay.check_out_date ({ext.stay.check_out_date}) is before "
                      f"stay.check_in_date ({ext.stay.check_in_date})")
        flags.append("checkout_before_checkin")

    # 2. price present (non-zero) but currency missing
    total = ext.financials.total_amount
    if total is not None and total != 0 and not ext.financials.currency:
        errors.append("financials.total_amount is set but financials.currency is null")
        flags.append("price_without_currency")

    # 3. lifecycle stage disagrees with the canonical notification_type
    stage = cls.booking_lifecycle_stage
    ntype = ext.booking_identity.notification_type
    if ntype and stage and stage != "n/a" and stage != ntype:
        errors.append(f"classification.booking_lifecycle_stage ({stage}) != "
                      f"extraction.booking_identity.notification_type ({ntype})")
        flags.append("lifecycle_mismatch")

    return errors, flags


def _missing_required(lifecycle: str, ext: Extraction) -> list[str]:
    """Required fields absent for the lifecycle stage. Unknown lifecycle → []."""
    spec = REQUIRED_BY_LIFECYCLE.get(lifecycle)
    if spec is None:
        return []
    required, any_of_groups = spec
    missing = [p for p in required if not _present(_get(ext, p))]
    for group in any_of_groups:
        if not any(_present(_get(ext, p)) for p in group):
            missing.append("|".join(group))   # "at least one of"
    return missing


def _get(ext: Extraction, dotted_path: str):
    """Resolve 'group.field' against the extraction object."""
    obj = ext
    for part in dotted_path.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def _present(value) -> bool:
    """Present = not None, not empty string, not empty list. 0 / 0.0 count as present."""
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    if isinstance(value, (list, tuple)) and len(value) == 0:
        return False
    return True


def _parse_date(value: Optional[str]) -> Optional[date]:
    """Parse an ISO date prefix; None if unparseable (don't flag what we can't read)."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None
