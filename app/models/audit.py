"""Output of the Audit Agent (#4) — deterministic verification findings.

Maps two ways:
  → locked agent_output_schema.audit block: audit_finding, missing_fields
    (=missing_required_fields), inconsistencies (=consistency_errors +
    grounding_errors), risk_flags.
  → RouterSignals: audit_finding, missing_required_fields, consistency_errors,
    extraction_grounding_errors (=grounding_errors).
"""
from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, Field

AuditFinding = Literal["clean", "missing_fields", "suspected_error", "n/a"]


class AuditOutput(BaseModel):
    """Deterministic audit findings. audit_finding is booking_notification-only
    (n/a otherwise, per the locked spec); the other lists may populate for any
    category."""
    audit_finding: AuditFinding = "n/a"
    missing_required_fields: List[str] = Field(default_factory=list)
    consistency_errors: List[str] = Field(default_factory=list)
    grounding_errors: List[str] = Field(default_factory=list)  # reserved; empty in v1
    risk_flags: List[str] = Field(default_factory=list)
