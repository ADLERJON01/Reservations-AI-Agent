# Routing Rules (generated)

Generated from `app/agents/router.py`. Documentation only — runtime behaviour is the `route()` guard clauses, tested directly.

| Priority | Rule ID | Condition | Action |
|---:|---|---|---|
| 1 | R001_SCHEMA_INVALID | schema_valid is False (no usable LLM output) | manual_review_unclear |
| 2 | R002_FORCE_MANUAL | force_manual_review is True | manual_review_unclear |
| 3 | R003_OTHER_UNCLEAR | category == other_or_unclear | manual_review_unclear |
| 20 | R020_BN_SUSPECTED | booking_notification AND audit_finding == suspected_error | audit_with_attention |
| 21 | R021_BN_MISSING | booking_notification AND audit_finding == missing_fields | audit_with_attention |
| 22 | R022_BN_CLEAN_FLAGGED | booking_notification AND clean AND validator flagged | audit_only_with_note |
| 23 | R023_BN_CLEAN | booking_notification AND clean AND not flagged | audit_only |
| 24 | R024_BN_OTHER | booking_notification AND audit_finding == n/a (unexpected) | audit_with_attention |
| 30 | R030_INQ_POLICY | service_or_information_inquiry AND request_type == policy_or_general_question | draft_reply_with_rag |
| 31 | R031_INQ_WITHDRAWAL | service_or_information_inquiry AND request_type == withdrawal_or_acknowledgment | audit_only_with_note |
| 32 | R032_INQ_DEFAULT | service_or_information_inquiry (any other request_type) | escalate_to_reservations_team |
| 40 | R040_PAYMENT | category == payment_billing_or_rate_issue | escalate_to_payment_or_billing |
| 41 | R041_INVENTORY | category == inventory_availability_or_stop_sales | escalate_to_inventory_or_operations |
| 42 | R042_SYSTEM | category == system_or_channel_delivery_exception | escalate_to_technical_or_operations |
| 43 | R043_CHANGE_CANCEL | category == booking_change_or_cancellation | escalate_to_reservations_team |
| 999 | R999_FALLBACK | no rule matched | manual_review_unclear |
