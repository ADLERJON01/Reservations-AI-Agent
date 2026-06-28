# Gold-Label Codebook — v1.0.0 taxonomy

The labeling guide for `gold_labeling_sheet.csv`. Label each email's **category +
5 facets** in the `gold_*` columns from the email body + this codebook. Goal: a
trustworthy human ground truth to score the LLM pipeline against.

## Protocol (read first)
- **Where things are:** label in `gold_labeling_sheet.csv` (one row per email, with
  a short `body_preview`); read the **full email bodies in `gold_emails.md`**. When
  saving from Excel, keep CSV format (ignore the "Possible Data Loss" nag).
- **Label independently from the email**, not from the model. `proposed_category` /
  `proposal_method` are a **heuristic hint** (subject/body rules) — *not* the LLM
  under test and *not* the truth. Use them only to orient; decide from the body.
- **Classify by the INNER content** of forwarded mail, never the forwarder/wrapper
  (`FW:`, `[EXTERNAL]`, `Favor dar seguimento`, `[ ref:…:ref ]` are routing markers).
- **Sender is a FACET, not a category** (see `sender_type`). "It's from a partner"
  does not decide the category — *what they want* does.
- Fill every `gold_*` column. If genuinely torn, put `Y` in `ambiguous` and your
  reasoning in `notes` (these become the inter-rater / hard-case discussion).
- Retain `MASKED_*` tokens as-is; they mark anonymized data, not missing data.

## The 7 categories (operational — *how the team handles it*, not topic)
1. **booking_notification** — system/templated channel email about a single booking
   lifecycle event (new/paid/pre-arrival/modified/cancelled) that is audited vs PMS.
   *Post-hoc notifications of completed changes stay here (not "change request").*
2. **booking_change_or_cancellation** — change/cancellation of an EXISTING booking
   that needs the team to review/validate (a *request/negotiation*, not a notice).
3. **service_or_information_inquiry** — human-written question, quote, new-booking
   request, or service request.
4. **payment_billing_or_rate_issue** — primary topic is payment, billing, invoices,
   fiscal data, rates, tariffs, or commercial contracts.
5. **inventory_availability_or_stop_sales** — room inventory, allotment, stop-sales,
   availability coordination.
6. **system_or_channel_delivery_exception** — system alert/error/exception or a
   delivery/sync failure from a channel manager, PMS, or OTA infrastructure.
7. **other_or_unclear** — anything that does not confidently fit the above
   (e.g. content-form auto-acknowledgments with no operational action).

## The 5 facets (assign each independently from its allowed values)
- **sender_type** — who authored the *inner* content: `automated_system` (channel
  manager/OTA), `partner_or_agency` (agency/wholesaler/DMC), `direct_guest` (end
  traveler), `internal_pestana_staff`, `unknown`.
- **request_type** — `policy_or_general_question`, `availability_or_quote_inquiry`,
  `new_booking_request`, `modification_request`, `cancellation_request`,
  `payment_or_billing_inquiry`, `complaint_or_dispute`,
  `withdrawal_or_acknowledgment`, `none` (purely informational notification),
  `other_or_unclear`.
- **booking_lifecycle_stage** — `new`, `paid`, `pre_arrival`, `modified`,
  `cancelled`, `n/a` (alert/exception/general inquiry). *For booking_notification,
  this mirrors the notification type in the body.*
- **expects_human_response** — `yes` (solicits a reply/decision), `no` (purely
  informational; a routine audit-vs-PMS does NOT count as expecting a reply),
  `unclear`.
- **urgency_signal** — `routine`, `urgent` (URGENT/URGENTE/PLEASE REPLY, payment
  warnings, imminent arrival), `sensitive_complaint` (complaint/dispute/sensitive).

## Reading `borderline_cases.md` — old→new mapping
That file predates v1.0.0 and uses **old category names**. Translate when labeling:

| old (in borderline_cases.md) | new label |
|---|---|
| `automated_reservation_notification` | category **booking_notification** |
| `partner_or_agency_communication` | category **by inner content**; set `sender_type=partner_or_agency` |
| `guest_direct_message` | usually **service_or_information_inquiry**; `sender_type=direct_guest` |
| `internal_operational_request` | category **by content**; `sender_type=internal_pestana_staff` |
| `system_or_technical_exception` | category **system_or_channel_delivery_exception** |
| old `action_required` (yes/no) | facet **expects_human_response** |
| old `urgency_or_sensitivity` | facet **urgency_signal** |

## The fork-points that decide most accuracy (label these carefully)
1. **Forwarding wrapper** (Group A): inner content wins, ignore the forwarder.
2. **Stop-sales** (Group B): a *partner reply* about allotment is the partner's
   intent (inventory/inquiry), not a system exception.
3. **Payment/credit-card** (Group C): system-generated warning → `system_…`;
   partner-initiated invoice thread → category by content; guest-initiated → inquiry.
4. **Cryptic subjects** (Group D, e.g. "Reserva"): the body decides — never the subject.
5. **Auto-acknowledgments** (Group E, e.g. `email_4`): no operational action →
   **other_or_unclear**.
6. **Notifications with embedded remarks** (Group F): a channel-generated email
   stays **booking_notification** even when guest remarks are present (the audit
   checklist surfaces the remark; it is not a change request).

---

# Labeling conventions (resolved during validation, 2026-06)

Rules adopted while labeling the 49-email gold set, to keep facets consistent.
Each is illustrated by the email(s) that surfaced it.

1. **`booking_notification` ⇒ `request_type = none`.** A pure notification asks
   nothing; embedded remarks don't change it (Group F). *(email_36)*
2. **Channel cancellation/modification *notifications* → `booking_notification`**
   (lifecycle `cancelled`/`modified`), **not** `booking_change_or_cancellation`.
   Reserve `booking_change_or_cancellation` for **human-written** change/cancel
   requests and explicit disputes/validation. *(Option A; email_90/297/299/300 vs
   email_361. See the boundary caveat in "Taxonomy findings".)*
3. **Service vs inventory.** Asking to **book/quote a stay** = `service_or_information_inquiry`;
   **managing allotment / stop-sales / availability coordination** =
   `inventory_availability_or_stop_sales`. ("availability" in
   `availability_or_quote_inquiry` is a *request_type under service*, not the
   inventory category.) *(email_157 vs 345)*
4. **`payment_billing_or_rate_issue` is topic-driven.** A payment / credit-card /
   VCC / invoice / rate matter goes here **even when phrased as a "can you help?"
   question** (email_378) or arrives as an automated alert (email_99).
5. **"Automated alert" ≠ `system_or_channel_delivery_exception`.** Classify by
   **content**. That category is **only genuine technical/delivery failures**
   (SiteMinder/PMS errors, sync failures — email_346). A booking change (20), a
   no-availability/inventory alert (205), or a payment problem (99) is **not** a
   system exception.
6. **Threads: classify by the latest message, but read the whole thread for
   context** (the body contains it). A **withdrawal/acknowledgment** closing a
   thread keeps the category and sets `request_type = withdrawal_or_acknowledgment`,
   `expects_human_response = no`. *(email_157, 358)*
7. **`expects_human_response` = reply OR decision/action** (locked def: "reply,
   decision, or follow-up"). **Required/solicited** action → `yes` (a link/extranet
   click counts, not only an email reply); **optional/incidental** → `no`.
   *(317 "must accept" = yes; 345 "favor confirmar" = yes; 205 "you may add,
   do not respond" = no; 369 "silence = validated" = no.)*
8. **Urgency keys on objective signals**, not only tone: **imminent arrival**
   counts even if calm (335); explicit URGENT/URGENTE/PLEASE REPLY markers;
   **payment-problem warnings** (99). A **stale URGENT subject in a resolved
   thread → `routine`** (358). **Precedence: `sensitive_complaint` > `urgent` >
   `routine`** — a dispute outranks an urgency marker (361).

# Labeling assumptions (decisions made without ground truth)

- **Partner "please confirm/accept" bookings → actionable**
  (`service_or_information_inquiry` / `new_booking_request`), not passive
  notifications. **Assumption** — not verified with the reservations team; the
  taxonomy has no "request-to-book" category. *(email_317, 337)*
- **Cancellation/modification boundary = Option A** (convention 2) — chosen because
  "requires validation" (the taxonomy's intended criterion) is **not determinable
  from the email alone**; "channel-templated FYI vs human request" is.

# Taxonomy findings (gaps & inconsistencies surfaced by labeling)

These are thesis material — limitations the gold set exposed, not labeling errors.

1. **`request_type` is booking/guest-centric** and lacks values for:
   (a) **ancillary services** (transfers/extras) → forced into `new_booking_request`
   or `availability_or_quote_inquiry` (161, 332); (b) **inventory/stop-sales
   coordination** → forced into `other_or_unclear` (345, 369).
2. **No category for partner request-to-book** distinct from confirmed-booking
   notifications (317, 337) — handled by assumption above.
3. **`booking_notification` ↔ `booking_change_or_cancellation` boundary is
   under-defined and internally contradictory.** taxonomy.json splits channel
   cancellations/modifications on "requires validation" (not determinable from the
   email), and **double-lists** the Mirai "Modified Reservation" type — its
   inclusion_criteria claim it for `booking_notification`, yet email_299/300 are
   `observed_examples` of `booking_change_or_cancellation`. Resolved here by
   Option A.
4. **`expects_human_response` name vs definition mismatch** — the field name says
   "response" (reply) but the locked definition is "reply, **decision, or
   follow-up**." Resolved by convention 7.
5. **`borderline_cases.md` predates v1.0.0 and is superseded in places** — it uses
   the old 6-category names and, e.g., routes credit-card warnings to
   `system_or_technical_exception` (Group C) where v1.0.0's new
   `payment_billing_or_rate_issue` now applies (email_99), and treats some channel
   notifications differently. **Treat that file as historical context, not the spec.**
   *(This supersedes "fork-point 3" above for payment/credit-card system warnings.)*

---

# v2 / v1.1 labeling updates (resolved 2026-06-28)

Conventions adopted while re-labeling the gold set for the taxonomy redesign
experiment and the chosen final design (**taxonomy_v1_1** = v1's 7 categories + the
`inquiry_answer_source` patch). These supersede the v1 conventions where noted.

## Field changes
- **`expects_human_response` → `requires_human_followup`** (rename; fixes finding #4 —
  the name now matches the "reply OR decision/action" definition).
- **NEW facet `inquiry_answer_source`** — *what kind of source would answer the
  inquiry*: `kb_policy` (static policy/amenity/facility knowledge), `internal_system`
  (live booking/payment/inventory/rate/customer data), `human_judgment` (staff
  decision/coordination/exception/arrangement), `not_applicable` (no inquiry —
  notification/alert/closure), `unclear`.
- **`request_type` adds `ancillary_service_request`** (partially addresses finding #1a:
  transfers/extras now have a tag instead of being forced into new_booking/availability).

## Convention amendments
1. **Convention 7 amended — actionable system warnings ⇒ `requires_human_followup = yes`.**
   The earlier rule (205 "you may add, do not respond" = no) is **superseded**. A
   no-availability alert (**205**) and a payment-problem alert (**99**) are *actionable
   warnings* the team must act on → **yes**. The line is: **actionable system warnings →
   yes; pure FYI notifications and routine audits → no** (a booking notification you only
   audit stays `no`; "silence = validated" 369 stays `no`).
2. **`inquiry_answer_source` and `requires_human_followup` are INDEPENDENT.** A system
   warning is `not_applicable` + `yes`; a pure notification is `not_applicable` + `no`;
   a parking question is `kb_policy` + `yes`. Do not force them to move together.
3. **Thread closure = the LATEST meaningful message decides** (reaffirms convention 6):
   if the latest message only thanks/acknowledges/withdraws, label
   `request_type = withdrawal_or_acknowledgment` and (in v1_1) category
   `service_or_information_inquiry`, *even if* the older quoted thread is full of
   booking/payment/availability content. **Caveat:** a polite closing at the end of a
   *real* request is NOT a closure (the v2.1 model over-triggered closures on 155/325/335).
4. **`inquiry_answer_source` resolutions on the hard cases:** general policy/amenity
   question = `kb_policy` (even when a booking is mentioned as context — email_24, **email_4**
   the Guest-Club procedure question); availability/quote/booking-status/payment-link =
   `internal_system`; arrange/price a service = `human_judgment` (email_332 airport
   pickup); a cancellation-fee dispute fee-waiver decision = `human_judgment` (email_361).
5. **Gold corrections applied:** **email_299 / email_300** (Mirai "Modified Reservation"
   channel notices) → `booking_notification` (Option A; they had been slipped to
   `booking_change_or_cancellation`). **email_4** re-read from v1's `other_or_unclear` to
   a real Guest-Club policy question (`service_or_information_inquiry` + `kb_policy`).

## RAG-safety risk model (why the gate is tuned for precision)
Because the system is **draft-only + human-in-the-loop**, a *false* RAG candidate is
bounded — a wrong draft is never sent, the reviewer discards it. The AND-gate
(`service_or_information_inquiry AND inquiry_answer_source == kb_policy`) therefore
exists to keep drafts **useful and checkable**, not as a safety-of-last-resort. A
*missed* candidate is the cheap error (it just escalates); a *false* one wastes review
and risks automation bias on data-dependent questions. So: prioritise **RAG precision**
(no false candidates); accept more relaxed recall on cheaply-checkable policy questions.

## Note on v1 category labels
For the v1_1 gold, do **not** reuse the original v1 category labels verbatim — derive
them by collapsing the v2 gold (the latest, most careful reads) to the 7 categories
({knowledge_policy, sales_availability, guest_service, thread_closure} →
`service_or_information_inquiry`). email_4 is the proof: its v1 label (`other_or_unclear`)
is stale vs the v2 re-read.
