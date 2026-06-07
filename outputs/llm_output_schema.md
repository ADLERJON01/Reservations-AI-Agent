# LLM Output Schema — Phase 2 (Locked v1.0.0)

Human-readable companion to `llm_output_schema.json`. Describes the JSON
structure that the Classifier+Extractor Agent emits per email. Pure
description — no routing decisions, no audit findings.

> **Status: locked v1.0.0** (2026-05-25). Loaded as a Pydantic model
> via Instructor at runtime. Validated against the `taxonomy.json`
> vocabulary.

---

## 1. Design principles

1. **Description, not decision.** The LLM pulls what is in the email
   and assigns it labels from the locked vocabulary. It does NOT
   decide what should happen. Decisions are the Router Agent's job.
2. **Two blocks, one call.** The LLM emits `classification` +
   `extraction` in a single structured JSON response. One LLM call
   per email.
3. **Forwarding-invariant.** The wrapper `Trade → Pestana RPA` is
   ignored; classification and extraction depend on the embedded
   original email.
4. **`null` for absent, `[]` for empty lists.** No `"null"` string.
5. **Anonymized tokens retained verbatim.** `MASKED_NAME_xxx`,
   `MASKED_EMAIL_xxx`, etc., stay as-is.
6. **Canonical lifecycle source.**
   `extraction.booking_identity.notification_type` is canonical;
   `classification.booking_lifecycle_stage` mirrors it.
7. **No inference fields.** Audit findings, validator results,
   handling decisions, and outputs are not part of this schema.

---

## 2. Top-level structure

```text
{
  "classification": { ... },   // 9 fields
  "extraction":     { ... }    // 9 groups
}
```

---

## 3. `classification` block

Predicted by the LLM. All values must come from the `taxonomy.json`
vocabulary.

| Field | Type | Description |
|---|---|---|
| `predicted_category` | enum (7 values) | One of the 7 categories in `taxonomy.json`. |
| `sender_type` | enum (5 values) | Who authored the underlying email content. |
| `request_type` | enum (10 values) | What the email is asking. |
| `booking_lifecycle_stage` | enum (6 values) | Lifecycle stage the email concerns. **Mirrors** `extraction.booking_identity.notification_type`. |
| `expects_human_response` | enum (3 values: yes / no / unclear) | Does the email solicit a reply? |
| `urgency_signal` | enum (3 values: routine / urgent / sensitive_complaint) | Tone / urgency markers. |
| `confidence` | float 0-1 | Self-reported. Coarse signal for the router (threshold 0.75). |
| `evidence_short` | string \| null | Brief quoted span(s) from the email supporting the classification. Max ~200 chars. |
| `reasoning_short` | string \| null | One-sentence reasoning for the category choice. Max ~200 chars. |

See `taxonomy.json` for the canonical enum values and per-value
descriptions.

---

## 4. `extraction` block — structure

The extraction has 9 groups:

| Group | Purpose |
|---|---|
| `booking_identity` | Who/where/when of the booking from the system's view |
| `guest` | Lead guest + additional travelers (when listed) |
| `stay` | Dates, nights, rooms, occupancy |
| `room_and_rate` | Room type, rate plan, meal plan, daily breakdown, promotions |
| `financials` | Currency, totals, taxes, commission, balance |
| `payment` | Payment method, guarantee, virtual card details, card metadata |
| `policies` | Cancellation / no-show / prepayment terms |
| `requests_and_remarks` | Raw remarks text and any staff instructions |
| `links` | Secure extranet link and other source URLs |

See `llm_output_schema.json` for the literal null-filled template and
field types.

---

## 5. Field reference (extraction)

### 5.1 `booking_identity`

| Field | Type | Notes |
|---|---|---|
| `source_channel` | string \| null | E.g. `"Booking.com"`, `"Expedia"`, `"Mirai"`. Free text — do not normalize. |
| `notification_type` | enum \| null | One of `"new"`, `"paid"`, `"pre_arrival"`, `"modified"`, `"cancelled"`, or `null`. **Canonical**: `classification.booking_lifecycle_stage` mirrors this. |
| `booking_reference` | string \| null | Channel-specific format. E.g. Booking.com numeric, Mirai `26021961117`, Juniper `66FYCW`, ODIGEO `EDR-9bf045dc...`. |
| `hotel_name` | string \| null | E.g. `"Pestana - Lisboa Vintage"`, `"Hotel Pestana Cidadela Cascais"`. |
| `property_id` | string \| null | Channel-specific property/hotel ID, when present. |
| `booking_created_date` | string \| null | ISO date `YYYY-MM-DD` if parseable. |
| `modified_on_date` | string \| null | Only for `notification_type = modified`. |
| `cancelled_on_date` | string \| null | Only for `notification_type = cancelled`. |

### 5.2 `guest`

| Field | Type | Notes |
|---|---|---|
| `guest_name` | string \| null | Lead / primary guest as shown. May be `MASKED_NAME_xxx` — keep verbatim. |
| `guest_email` | string \| null | May be anonymized. Rarely present in channel templates. |
| `guest_phone` | string \| null | May be anonymized. |
| `guest_language` | string \| null | E.g. `"Portuguese"`, `"English"`. |
| `additional_travelers` | list of `{name, age}` | Empty `[]` when no rooming list or only lead guest named. Populated for group bookings (Juniper, wholesale). |

### 5.3 `stay`

| Field | Type | Notes |
|---|---|---|
| `check_in_date` | string \| null | ISO date `YYYY-MM-DD`. |
| `check_out_date` | string \| null | ISO date `YYYY-MM-DD`. |
| `number_of_nights` | int \| null | Populate only if explicitly shown. |
| `number_of_rooms` | int \| null | Default to `1` only if explicitly stated. |
| `adults` | int \| null | |
| `children` | int \| null | |
| `child_ages` | list of int | Empty `[]` if no children or ages not stated. |

### 5.4 `room_and_rate`

| Field | Type | Notes |
|---|---|---|
| `room_type` | string \| null | E.g. `"Superior Room, Balcony - Breakfast Included"`. Often empty in cancellation notifications. |
| `rate_plan` | string \| null | E.g. `"Limited Time Deal"`, `"OD Lite - Wholesale"`. |
| `meal_plan` | string \| null | E.g. `"Breakfast Included"`, `"Tudo Incluido"`. |
| `daily_rate_breakdown` | list of `{date, rate_id, price, currency, description}` | Empty `[]` otherwise. |
| `promotion` | string \| null | E.g. `"5% Long Stay Reduction S26"`. |
| `benefits_included` | string \| null | Free text from the email. |

### 5.5 `financials`

| Field | Type | Notes |
|---|---|---|
| `currency` | string \| null | Usually `"EUR"`. |
| `total_amount` | float \| null | `0.00` is valid for cancellation notifications — not a missing field. |
| `tax_amount` | float \| null | |
| `tax_breakdown` | list of `{description, amount, currency}` | E.g. `{ description: "IVA (6%)", amount: 24.71, currency: "EUR" }`. |
| `commission_amount` | float \| null | |
| `balance` | float \| null | |

### 5.6 `payment`

| Field | Type | Notes |
|---|---|---|
| `payment_method` | string \| null | E.g. `"Virtual Card"`, `"Credit card"`, `"Hotel Collect"`, `"Expedia Collect"`. |
| `payment_status` | string \| null | E.g. `"Paid"`, `"Pending"`, `"Prepaid"`. |
| `guarantee_type` | string \| null | E.g. `"VIRTUAL CREDITCARD"`, `"PrePay"`. Distinct from `payment_method`. |
| `virtual_card_present` | bool \| null | |
| `virtual_card_activation_date` | string \| null | ISO date. |
| `virtual_card_deactivation_date` | string \| null | ISO date. |
| `card_type` | string \| null | E.g. `"MC"`, `"VISA"`. |
| `card_last4` | string \| null | E.g. `"9463"`. |

### 5.7 `policies`

| Field | Type | Notes |
|---|---|---|
| `cancellation_policy` | string \| null | Free text. |
| `free_cancellation_deadline` | string \| null | E.g. `"até 2 dias antes da chegada"`. |
| `non_refundable` | bool \| null | |
| `no_show_policy` | string \| null | |
| `prepayment_policy` | string \| null | |

### 5.8 `requests_and_remarks`

| Field | Type | Notes |
|---|---|---|
| `raw_remarks` | string \| null | **Verbatim.** Do NOT interpret. Includes "Remarks:" / "Special requests" / "Reservation Remarks" / "Extra Information" sections. Boilerplate detection is the audit module's job. |
| `hotel_staff_instructions` | string \| null | Distinct from guest remarks. Rare. |

### 5.9 `links`

| Field | Type | Notes |
|---|---|---|
| `secure_extranet_link` | string \| null | E.g. SiteMinder URL `http://app.siteminder.com/web/...`. |
| `source_links` | list of string | Other URLs in the email. Empty `[]` otherwise. |

---

## 6. Required vs optional

A small subset of fields is operationally **required** for a complete
audit. The required list depends on the booking lifecycle stage —
cancellation notifications routinely have empty `room_type` and
`total_amount = 0.00`, and that is not a missing-field error.

**The required-field logic lives in the audit module (Phase 6 spec)**,
not in this extraction schema. The LLM's job is to populate whatever
is present and leave the rest `null` — regardless of lifecycle.

Preliminary expected-present-at-extraction fields per lifecycle (to be
finalized in audit spec):

| Lifecycle | Always expected | Conditionally expected |
|---|---|---|
| `new` | `source_channel`, `booking_reference`, `hotel_name`, `guest_name`, `check_in_date`, `check_out_date`, `adults`, `total_amount`, `currency` | `room_type`, `rate_plan`, `payment_method` or `guarantee_type` |
| `paid` | new + `payment_method` or `guarantee_type` and `payment_status` | `room_type`, `rate_plan` |
| `pre_arrival` | `source_channel`, `booking_reference`, `hotel_name`, `guest_name`, `check_in_date` | `room_type` (best-effort) |
| `modified` | `source_channel`, `booking_reference`, `hotel_name`, `guest_name`, `check_in_date`, `check_out_date`, `modified_on_date` | `room_type`, `rate_plan` |
| `cancelled` | `source_channel`, `booking_reference`, `hotel_name`, `guest_name`, `cancelled_on_date` | (most other fields expected blank) |

---

## 7. Out of scope for this schema

The following are **NOT** in `llm_output`. They live in
`agent_output_schema.json` under their respective blocks:

- `validator` block (`validation_result`, `flagged_fields`, ...)
- `audit` block (`audit_finding`, `missing_fields`, `inconsistencies`, ...)
- `routing` block (`outbound_action_required`, `requires_internal_system`, `kb_answerable`, `recommended_action`, ...)
- `retrieval` block (RAG sources)
- `output` block (`audit_checklist`, `escalation_summary`, ...)
- `guardrails` block
- `logs` block

Keeping `llm_output` free of these makes evaluation cleaner:
classification accuracy and extraction accuracy can be measured
independently of audit, validator, routing, and generation logic.

---

## 8. Local LLM friendliness

- Maximum nesting depth: **2** (e.g., `extraction.stay.adults`). One
  exception: `additional_travelers` is a list of flat objects.
- All lists default to `[]`, not `null`.
- All scalar absent values default to `null`. The LLM should be
  prompted to **never** emit `"null"` (string).
- The prompt should explicitly forbid inventing values not present in
  the email. Anonymized tokens are retained verbatim.
- The prompt should remind the model that `total_amount = 0.00` is
  valid for cancellation notifications.

---

## 9. Spec references

- `taxonomy.json` — canonical label vocabulary
- `llm_output_schema.json` — machine-readable template (loaded as Pydantic via Instructor)
- `agent_output_schema.json` — full pipeline output containing this block
- `routing_rules.json` — how `classification` is consumed by the Router
- `taxonomy_proposal.md` — prose specification of the taxonomy
- `CHANGELOG.md` — version history
