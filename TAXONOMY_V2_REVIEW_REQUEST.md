# Taxonomy v2 — Second-Opinion Request (updated through v2.1)

**For:** external reviewer. **From:** Erjon (thesis: Pestana AI email-triage agent).
**Updated:** 2026-06-28. **Decision at stake:** lock taxonomy **v2.1**, fall back to
**v1 + a RAG-safety patch**, or stop iterating.

This supersedes the earlier v2.0-only version. It now documents the **full iteration**
— v2.0 → preprocessor v2 → v2.1 — with three-way results, the exact v2.1 classifier
prompt, and the open decision.

---

## 0. Context (one paragraph)

A **local, draft-only, human-in-the-loop** multi-agent pipeline classifies hotel
reservation emails, audits booking notifications, routes them deterministically, and
(only for safe cases) drafts a grounded reply via RAG over an FAQ KB. Hard constraints:
**never sends autonomously; no access to PMS/CRS/payment/inventory; grounded answers
only.** Principle: **"the LLM describes, deterministic code decides."** Classifier
model: **`ministral-3:3b`** via Ollama, temperature 0, structured JSON output gated by
a Pydantic contract. The small local model is a fixed design constraint and is central
to the result.

---

## 1. Why we left v1

v1 (7 categories) scored **79.6% category accuracy** on a 49-email hand-labeled gold
set (enriched prompt). But the gold eval exposed: the `service_or_information_inquiry`
category was **overloaded**; RAG eligibility was gated on a **fragile** signal
(`service… AND request_type == policy_or_general_question`, request_type only 44.9%);
and there was **no explicit mechanism to prevent false RAG candidates** — emails that
look like questions but need live data/staff action and must not be answered from KB.

---

## 2. What v2 is

### 2.1 Categories: 7 → 10 (field still named `category`)
The overloaded service bucket was split into four workflows (★).

| # | category | origin |
|---|---|---|
| 1 | `booking_notification` | kept |
| 2 | `booking_change_or_cancellation` | kept (broadened) |
| 3 | ★ `knowledge_policy_inquiry` | service split |
| 4 | ★ `sales_availability_or_quote_inquiry` | service split |
| 5 | ★ `guest_service_or_ancillary_request` | service split (fills ancillary gap) |
| 6 | ★ `thread_closure_or_acknowledgment` | service split |
| 7 | `payment_billing_or_rate_issue` | kept |
| 8 | `inventory_availability_or_stop_sales` | kept |
| 9 | `system_or_channel_delivery_exception` | kept |
| 10 | `other_or_unclear` | kept |

### 2.2 Fields the LLM emits (descriptive only)
`category` · `request_type` (kept name; **demoted to a descriptive display/Outlook
tag**, added `ancillary_service_request`) · **`inquiry_answer_source`** (NEW:
`kb_policy` / `internal_system` / `human_judgment` / `not_applicable` / `unclear`) ·
`sender_type` · `booking_lifecycle_stage` (new convention: stage of the *referenced*
booking; inquiries can carry one) · **`requires_human_followup`** (renamed from
`expects_human_response`) · `urgency_signal` · `confidence` · `evidence_short` ·
`reasoning_short`.

### 2.3 The RAG-safety mechanism (the core of v2)
`rag_candidate` is **derived in deterministic code, NOT emitted by the LLM**:

```
rag_candidate = (category == knowledge_policy_inquiry) AND (inquiry_answer_source == kb_policy)
```

An **AND-gate of two independent signals** — either vetoes a draft. Availability/quote/
payment/booking/ancillary requests are kept off RAG because they resolve to
`internal_system`/`human_judgment`.

### 2.4 Risk model
Because the system is **draft-only + human-in-the-loop**, a false RAG candidate is
*bounded*: a wrong draft is never sent — the reviewer discards it. The gate exists to
keep drafts **useful and checkable**, not as a last line of defence. Practical
implication: **RAG precision (no false candidates) matters more than recall** — a
*missed* RAG candidate merely escalates (cheap); a *false* one wastes review and risks
automation bias on data-dependent questions.

---

## 3. The iteration: v2.0 → preprocessor v2 → v2.1

We measured three configurations on the **same 49 gold emails, same model**, so each is
directly comparable.

**v2.0** — the initial v2 prompt (10-category guide + decision order + facet guide + 10
few-shot). System prompt fed the whole cleaned body.

**Preprocessor v2** (infrastructure, kept in v2.1) — three deterministic input
improvements:
1. **Strip tracking/redirect URLs** (`awstrack`/`exclaimer`/`pstmrk`/maps/CDN, angle-
   bracket link targets, any >90-char URL). Large noise cuts (e.g. one email 13.1k→8.1k
   chars), freeing the 6,000-char budget for real content.
2. **Strip legal/marketing/social boilerplate** (GDPR/confidentiality blocks, "think
   before printing", social rows) **— signatures kept** (they are the key `sender_type`/
   partner-identity cue).
3. **`latest_message` segmentation** — split the most-recent message from the older
   quoted thread; the user prompt now presents `[MOST RECENT MESSAGE]` first +
   `[EARLIER THREAD — context]`. Targets the thread-closure failure (model was
   classifying on old thread content). Falls back to the whole body when no thread is
   detected; **labels kept soft** (no "classify ONLY by this") so wrapper-forwarded
   emails don't regress.

**v2.1 prompt** — a **trimmed/summarised** adaptation of the reviewer's v2.1 proposal
(kept compact — ~2,369 tokens, *smaller* than v2.0's 2,507 and ~half the reviewer's
full version — to limit attention dilution on the 3B). Changes vs v2.0:
- **Describe-only purity:** removed all routing leakage (no "RAG-eligible" language);
  added an explicit "you do not take actions/send replies/confirm bookings/access
  systems" block tied to the security constraints.
- **"Classify by the LATEST meaningful message; ignore wrappers"** rule (pairs with the
  preprocessor split).
- **Sharper notification-vs-sales boundary** + a compact **Key boundaries** block for
  the five confusable pairs.
- **`inquiry_answer_source` and `requires_human_followup` explicitly decoupled** (a
  system warning is `not_applicable` + `yes`; a pure notification is `not_applicable` +
  `no`).
- Kept the proven v1 `EXTRACTION_EMPHASIS` block last.

---

## 4. The exact v2.1 classifier prompt

**Runtime:** `model=ministral-3:3b`, `temperature=0.0`, `seed=0`, 1 salvage retry at
`temperature=0.3`, `num_ctx=8192`, `num_predict=2000`, body truncated to 6,000 chars.
Structured output: Ollama `/api/chat`, `think=false`, `format` = JSON schema of the v2
Pydantic model. One LLM call per email.

### 4.1 System prompt (verbatim, ~2,369 tokens)

```text
You are an email classification + extraction engine for a hotel group (Pestana). For each email, output ONE JSON object matching the schema exactly.
You only DESCRIBE the email. You do not take actions, send replies, confirm/cancel/modify bookings, confirm availability/prices/payments/refunds, or access systems. Do NOT output routing decisions: there is no rag_candidate or recommended_action field.
Rules:
- Exactly two top-level keys: "classification" and "extraction".
- Categories are OPERATIONAL (how the team handles the mail), not topical. Every category/facet value MUST come from the allowed lists.
- Classify by the LATEST meaningful message. Ignore forwarders/wrappers ("FW:", "Favor dar seguimento", "FYI", signatures, CRM/[ref] markers, external-mail warnings); older thread content is context only.
- Absent scalar = null; absent list = []. Never output the string "null".
- Never invent values not present in the email. Retain MASKED_* tokens verbatim.
- total_amount = 0.00 is VALID for cancellation notifications.
- For channel notifications, booking_lifecycle_stage mirrors extraction.booking_identity.notification_type.
- Keep evidence_short and reasoning_short under 200 characters.

Allowed categories (OPERATIONAL — how the team handles it, not the topic):
1. booking_notification — a SYSTEM/TEMPLATED channel message (sender automated_system) reporting ONE lifecycle event (new/paid/pre-arrival/modified/cancelled), incl. post-hoc 'Modified'/'Cancelled' notices. Booking details/dates/prices/payment/cancellation-policy inside a template do NOT make it a request. If a HUMAN wrote it, it is NOT this category.
2. booking_change_or_cancellation — a HUMAN asks to change/cancel/validate an EXISTING booking, or disputes one (incl. cancellation-fee disputes, 'is my booking confirmed?').
3. knowledge_policy_inquiry — a HUMAN asks a general policy/amenity/facility question (parking, check-in/out, pets, breakfast, wifi, pool, accessibility, general cancellation policy).
4. sales_availability_or_quote_inquiry — a HUMAN/partner asks for availability, a quote/proposal/rate, to hold rooms, or to create a NEW booking (incl. 'send a payment link to book', partner request-to-book).
5. guest_service_or_ancillary_request — a HUMAN asks staff to ARRANGE/PROVIDE/PRICE a service or extra (transfer, crib, extra bed, late check-in, restaurant, special assistance).
6. thread_closure_or_acknowledgment — the LATEST message only thanks/acknowledges/withdraws, with no new ask.
7. payment_billing_or_rate_issue — primary topic is payment/billing/invoice/fiscal data (VAT/NIF/CIF)/rate/VCC/credit-card/refund/commission (even as a question or automated alert).
8. inventory_availability_or_stop_sales — managing inventory/allotment/stop-sales/availability coordination (operational); NOT a guest/partner asking to book a stay.
9. system_or_channel_delivery_exception — a GENUINE technical/delivery/sync failure (PMS/channel-manager/OTA error, 'could not be delivered/found'). NOT payment, NOT availability.
10. other_or_unclear — auto-acks with no operational content, spam, garbled/empty, unclassifiable.
Decision order — top-down, STOP at the first match:
a) garbled/empty/unclassifiable -> other_or_unclear
b) latest message only thanks/acknowledges/withdraws (ignore older thread) -> thread_closure_or_acknowledgment
c) system/templated channel booking notice -> booking_notification
d) genuine technical/delivery/sync failure -> system_or_channel_delivery_exception
e) primary topic payment/billing/rate/refund -> payment_billing_or_rate_issue
f) inventory/allotment/stop-sales coordination -> inventory_availability_or_stop_sales
g) human change/cancel/validate/dispute of an EXISTING booking -> booking_change_or_cancellation
h) human availability/quote/proposal/hold/NEW booking -> sales_availability_or_quote_inquiry
i) human asks staff to arrange/price a service or extra -> guest_service_or_ancillary_request
j) human general policy/amenity/facility question -> knowledge_policy_inquiry
k) none of the above -> other_or_unclear

Key boundaries:
- Notification vs sales: a templated channel notice carrying booking details is booking_notification; only a HUMAN asking to quote/hold/book is sales_availability_or_quote_inquiry. Booking details alone are NOT a sales request.
- Closure vs thread: if the latest message only closes/thanks/withdraws, choose thread_closure_or_acknowledgment even if older quoted content has booking/cancel/payment/availability details.
- Sales vs inventory: a guest/partner wanting rooms/rates/quote = sales; operations managing stock/allotment/stop-sales = inventory. The word 'availability' alone is not enough.
- Knowledge vs ancillary: asking for general info/policy = knowledge_policy_inquiry; asking staff to arrange/reserve/price a service = guest_service_or_ancillary_request.
- Existing-booking vs knowledge: 'confirm my booking is active' = booking_change_or_cancellation; 'I booked — do you have parking?' = knowledge_policy_inquiry (the booking is just context).

Facets (assign each independently from its allowed values):
sender_type — who authored the LATEST/inner content (ignore forwarders): automated_system (channel/OTA template), partner_or_agency (agency/wholesaler/DMC), direct_guest (end traveler, incl. via OTA relay), internal_pestana_staff, unknown.
request_type — a DESCRIPTIVE tag of the ask (does NOT decide routing): policy_or_general_question, availability_or_quote_inquiry, new_booking_request, modification_request, cancellation_request, ancillary_service_request, payment_or_billing_inquiry, complaint_or_dispute, withdrawal_or_acknowledgment, none (pure notification), other_or_unclear.
inquiry_answer_source — what kind of source would answer the inquiry: kb_policy (static policy/amenity/facility knowledge), internal_system (live booking/payment/inventory/rate/customer data), human_judgment (staff decision/coordination/exception/arrangement), not_applicable (no inquiry — notification, alert, closure), unclear.
booking_lifecycle_stage — stage of the booking REFERENCED, if any: new, paid, pre_arrival, modified, cancelled, n/a. Existing FUTURE booking in an inquiry -> pre_arrival. Use paid ONLY if payment is explicitly stated. No booking referenced -> n/a.
requires_human_followup — yes (asks for/implies a reply, decision, action, or manual review — a required link/extranet click counts), no (purely informational; routine audit-vs-PMS or an optional action does not count; 'silence = validated' -> no), unclear.
urgency_signal — routine; urgent (URGENT/URGENTE/PLEASE REPLY, payment-problem warnings, imminent arrival even if calm); sensitive_complaint (complaint/dispute/sensitive). Precedence sensitive_complaint > urgent > routine; a stale urgent subject in a resolved thread -> routine.
Note: inquiry_answer_source and requires_human_followup are INDEPENDENT — a system warning is not_applicable + yes; a pure notification is not_applicable + no.

Worked examples (illustrative patterns — not real emails). Format: situation -> category | inquiry_answer_source (+ lesson):
1. 'I booked via Booking.com — do you have parking?' -> knowledge_policy_inquiry | kb_policy, lifecycle pre_arrival. (Amenity question; the booking is just context.)
2. 'Do you have rooms 4-8 June? Please send a quote.' -> sales_availability_or_quote_inquiry | internal_system. (Sounds like a question but needs live availability/rates.)
3. 'Please arrange a private airport pickup and tell me the cost.' -> guest_service_or_ancillary_request | human_judgment, lifecycle pre_arrival. (Arrange + price = staff coordination, not a policy lookup.)
4. 'Please proceed with a reservation 21-22 Feb and send the payment link.' -> sales_availability_or_quote_inquiry | internal_system, lifecycle new.
5. 'Please cancel my booking 678.' -> booking_change_or_cancellation | internal_system, lifecycle cancelled.
6. Channel template 'Reservation 678 has been Modified' (booking code, dates, total, cancellation policy) -> booking_notification | not_applicable, sender automated_system, request_type none, lifecycle modified. (Template details are not a request.)
7. Automated 'credit card declined for reservation 90' -> payment_billing_or_rate_issue | internal_system, urgency urgent, requires_human_followup yes. (Topic is payment.)
8. Latest message 'Brilliant, thank you' after a long booking thread -> thread_closure_or_acknowledgment | not_applicable, request_type withdrawal_or_acknowledgment, requires_human_followup no. (Classify the latest message, not the older thread.)
9. SiteMinder 'reservation could not be delivered to your PMS' -> system_or_channel_delivery_exception | not_applicable.
10. Partner 'please stop-sales / close out these dates, allotment is full' -> inventory_availability_or_stop_sales | not_applicable. (Managing allotment, not booking.)

EXTRACTION IS MANDATORY AND THOROUGH. If a value appears anywhere in the email you MUST populate the matching field — never leave a present value null. Examples:
- 'Check-in: 06-Mar-2026' -> stay.check_in_date = '2026-03-06'
- 'Total Price: 208.17 EUR' -> financials.total_amount = 208.17, financials.currency = 'EUR'
- channel name (e.g. Booking.com) -> booking_identity.source_channel
- 'Booking Confirmation Id: 6310459722' -> booking_identity.booking_reference
- hotel (e.g. 'Pestana - Brussels') -> booking_identity.hotel_name
- guest name (incl. MASKED_NAME_*) -> guest.guest_name
Use null ONLY when the email genuinely lacks the value.
```

### 4.2 User prompt (per email — preprocessor v2 structure)

```text
--- EMAIL ---
Subject: {subject}
From: {from_raw}

[MOST RECENT MESSAGE]
{latest_message}

[EARLIER THREAD — context]
{thread_history}      ← omitted when there is no older thread
--- END EMAIL ---

Return exactly ONE JSON object with the two top-level keys "classification" and "extraction".
```

---

## 5. Gold label (ground truth)

Same 49 emails as v1 (stratified; rare categories kept in full). `sender_type` and
`urgency` carried from v1; `category` (10-way) and `inquiry_answer_source` labeled
fresh. QA: 0 blanks/invalid; **9** flagged `ambiguous`. Two corrected slips: `email_299`
/`email_300` (Mirai "Modified Reservation" notices) → `booking_notification`. Gold RAG
candidates (knowledge_policy AND kb_policy): **2** (`email_4`, `email_24`).

Labeling conventions that define the gold (worked through case by case): classify by
inner/latest content; latest message decides a thread (a closing "thank you" overrides
the thread body); templated channel notices incl. post-hoc Modified/Cancelled →
`booking_notification`; partner/internal request-to-book → `sales_availability…`;
arrange/price a service → `guest_service…`; `inquiry_answer_source` and
`requires_human_followup` are independent (alerts = `not_applicable` + `yes`).

---

## 6. Results — prediction vs gold (same model, same 49 emails)

All three runs were 49/49 schema-valid, 0 errors.

| Metric | v1 (7-cat) | v2.0 | **v2.1** |
|---|---|---|---|
| **Category accuracy (all)** | **79.6%** | 65.3% | **69.4%** |
| Category accuracy (unambiguous) | 75.0% | 67.5% | 72.5% |
| **Macro-F1 (category)** | 0.70 | 0.65 | **0.72** |
| **RAG precision** | (no gate) | 100% | **100%** |
| **RAG recall** | — | 100% | **50%** (1 missed: email_4) |
| **False RAG candidates** | — | 0 | **0** |
| sender_type | 69.4% | 63.3% | **75.5%** |
| request_type | 44.9% | 40.8% | **49.0%** |
| inquiry_answer_source | — | 46.9% | **59.2%** |
| requires_human_followup | 77.6%\* | 61.2% | 71.4% |
| lifecycle | 71.4% | 71.4% | 67.3% |
| urgency_signal | 91.8% | 91.8% | **95.9%** |

\* definition changed (`expects_human_response` → `requires_human_followup`).

### 6.1 v2.1 per-category precision / recall / F1

| category | P | R | F1 | support |
|---|---|---|---|---|
| system_or_channel_delivery_exception | 1.00 | 1.00 | 1.00 | 4 |
| guest_service_or_ancillary_request | 1.00 | 1.00 | 1.00 | 2 |
| inventory_availability_or_stop_sales | 0.67 | 1.00 | 0.80 | 6 |
| payment_billing_or_rate_issue | 1.00 | 0.67 | 0.80 | 3 |
| booking_notification | 0.69 | 0.75 | 0.72 | 12 |
| booking_change_or_cancellation | 0.67 | 0.67 | 0.67 | 3 |
| sales_availability_or_quote_inquiry | 0.62 | 0.45 | 0.53 | 11 |
| knowledge_policy_inquiry | 1.00 | 0.33 | 0.50 | 3 |
| thread_closure_or_acknowledgment | 0.43 | 0.60 | 0.50 | 5 |

### 6.2 What the iteration fixed (v2.0 → v2.1)
- `booking_notification` recall **0.50 → 0.75** (notification-vs-sales rule).
- `thread_closure` recall **0.20 → 0.60** (preprocessor `latest_message` + closure rule).
- `sender_type` **+12.2** (boilerplate/signature cleanup), `inquiry_answer_source`
  **+12.3**, `request_type` **+8.2**, `requires_human_followup` **+10.2**.

### 6.3 What the iteration cost (the 15 remaining v2.1 errors)
- **`thread_closure` over-triggers (4, NEW):** `email_155` (payment thread ending
  "Gracias"), `email_162`, `email_325`, `email_335` (sales requests ending politely) →
  mislabeled `thread_closure`. The closure fix raised recall but dropped precision (0.43).
- **`booking_notification` → `sales` (2, persistent):** `email_110`, `email_133`.
- **`thread_closure` still missed (2):** `email_157`, `email_324`.
- **`sales` → `inventory` (2):** `email_326`, `email_377`.
- **Ambiguous forks (4, gold-flagged):** `email_20`, `email_317`, `email_337`, `email_368`.
- **`email_4` `knowledge_policy` → `sales` (1):** the RAG miss — its *category* flipped,
  so it's no longer a candidate. (Precision unaffected — no false candidate created.)

---

## 7. Interpretation

1. **The iteration worked but plateaued below v1.** v2.1 is the best v2 variant —
   category 69.4% (up from 65.3%), macro-F1 0.72 (now **above** v1's 0.70), and it
   **beats v1** on `sender_type`, `request_type`, `urgency`. But **raw category accuracy
   still trails v1 (69.4% vs 79.6%)**: the 10-way split carries a ~10-point cost on the
   3B that prompt-engineering + preprocessing narrowed but did not erase.
2. **RAG safety is intact on the dangerous axis (precision 100%, 0 false candidates)**,
   but v2.1 dropped recall to 50% (email_4). Per the draft-only risk model this is the
   cheap direction. The original finding stands: **the RAG precision comes from
   `inquiry_answer_source`, not the category split** — it would transfer to v1.
3. **The closure fix is a knife-edge:** pushing recall up introduced false closures.
   Further tuning on these same 49 would risk overfitting.
4. **Caveats:** n=49; development-set numbers (conventions derived from these emails →
   optimistic; needs a held-out run); 10-way is inherently harder than 7-way.

---

## 8. Options

**A. Fall back to v1 + RAG-safety patch.** v1's 7 categories (79.6%) + `inquiry_answer_source`
+ the AND-gate. Best category accuracy + the safety mechanism; **no re-labeling**
(labels exist). Loses the v2 granularity (ancillary / request-to-book / closure as
categories) — though those can live as `request_type` tags.

**B. Lock v2.1.** Richer 10-category taxonomy + better facets (sender/request_type/
urgency) + macro-F1 > v1 + RAG precision 100%. Accepts ~10pt lower raw category
accuracy and the closure-precision/RAG-recall wrinkles.

**C. Iterate v2.2.** Target the closure over-trigger + email_4. Risk: overfitting the
49; uncertain payoff on the 3B.

Author's lean: **A**, unless the richer operational categories have product value
(dashboard tagging, future routing) that justifies B's accuracy cost.

---

## 9. Questions for the reviewer

1. Given v2.1 still trails v1 on raw category accuracy (69.4 vs 79.6) but **beats it on
   macro-F1 and several facets**, which headline metric should drive the decision for a
   *routing* system on a small model?
2. Do you agree the RAG-safety result is attributable to `inquiry_answer_source` (so
   **Option A keeps the safety**), making the 10-way split optional rather than necessary?
3. Is the `thread_closure` over-trigger (false closures on emails ending in "thanks")
   a prompt-fixable issue, or an intrinsic limit of "classify by the latest message" on
   a 3B without better message-boundary parsing?
4. For the thesis: is "redesign tested → safety isolated to one new signal → minimal
   patch adopted" a **stronger** contribution than shipping the richer taxonomy at lower
   accuracy?
5. Under the draft-only risk model (§2.4), is RAG **recall 50%** (1 missed, 0 false)
   acceptable, or should we trade some precision headroom for recall?

---

### Appendix — artifacts
- v2 schema `app/models/llm_output_v2.py` · v2.1 prompt `app/agents/prompts_v2.py` ·
  preprocessor `app/agents/preprocessor.py`
- gold sheet `outputs/gold/gold_labeling_sheet_v2.xlsx`
- per-run snapshots: `gold_{predictions,metrics}_v2.0.*` (65.3%),
  `…_v2.1.*` (69.4%); live `gold_metrics_v2.md` = v2.1
- v1 baseline `outputs/gold/gold_metrics.md` (enriched, 79.6%)