# Borderline Cases for Manual Validation

These are the emails I identified during analysis where the correct
category is non-obvious, where two categories could plausibly apply, or
where the email exposes a weakness in the proposed taxonomy. Label these
first when you do the manual validation — your decision on each one
either confirms the taxonomy or signals a needed revision.

Each entry below includes:
- the `email_id`,
- a one-line description of the email,
- the categories that *could* apply,
- my proposed category and rationale,
- the specific reason this is a borderline case.

---

## Group A — "Forwarded by Pestana front-office with 'Favor dar seguimento'"

The Pestana hotel front-office team forwards an upstream email to the
central reservations team with a brief Portuguese forwarding note.
**Question:** is the category determined by the inner content or the
outer wrapper?

**Proposed rule:** classify by the inner content. The forwarding
wrapper is a routing step, not an operational signal.

| email_id | Description | Could be | Proposed |
|---|---|---|---|
| `email_98` | Front-office of Pestana Casino Park forwards "Change of booking" thread | `partner_or_agency_communication` vs `internal_operational_request` | `partner_or_agency_communication` (inner content is a booking change negotiation) |
| `email_335` | Front-office of Pestana Grand forwards a "Reserva" thread with no inner detail shown | `partner_or_agency_communication` vs `internal_operational_request` vs `other_or_unclear` | Depends on inner content — read full body before deciding |
| `email_336` | Front-office of Pestana Casino Park forwards a "Reserva" thread with a Salesforce case number | `partner_or_agency_communication` vs `internal_operational_request` | `partner_or_agency_communication` (CRM case + inner content) |

**Validation question.** Do you agree with the rule "classify by inner
content, ignore the forwarding wrapper"?

---

## Group B — Stop-sales communications

Only one email matches the literal "stop sales" subject pattern, but it
is operationally a partner thread (a partner replying to a
Pestana-initiated stop-sales request), not a system alert.

| email_id | Description | Could be | Proposed |
|---|---|---|---|
| `email_345` | Partner replying with allotment position after Pestana stop-sales request | `system_or_technical_exception` vs `partner_or_agency_communication` | `partner_or_agency_communication` |
| `email_369` | `[EXTERNAL] - RE: Stop sales Hotel Pestana Fisherman` | Same as above | `partner_or_agency_communication` |

**Validation question.** Is there ever a case where stop-sales would be
its own category? If yes, the taxonomy may need a stop-sales-specific
category; if no, the proposal stands.

---

## Group C — Payment / credit card issues

Three different operational patterns are mixed together here:

| email_id | Description | Could be | Proposed |
|---|---|---|---|
| `email_99` | Mirai-templated "Problems with your credit card" warning forwarded to Pestana | `system_or_technical_exception` vs `automated_reservation_notification` (with payment lifecycle) | `system_or_technical_exception` with `urgency_or_sensitivity = urgent` |
| `email_155` | Spanish partner thread about invoices without CIF, Case Number present | `partner_or_agency_communication` (invoice topic) | `partner_or_agency_communication` |
| `email_161` | Guest (forwarded via reservations) asking to book a transfer and confirm | `guest_direct_message` vs `partner_or_agency_communication` | Borderline — content is a guest request but routed via reservations team; needs your read |

**Validation question.** Do you want a separate `payment_or_billing`
category, or are you content with the current split (system-generated →
exception; partner-initiated → partner; guest-initiated → guest)?

---

## Group D — "Reserva" (one-word subject) and other cryptic subjects

These subjects carry no operational signal — the body must decide.

| email_id | Subject | Likely category after body read |
|---|---|---|
| `email_24` | `Booking` | `guest_direct_message` (short direct guest question about parking) |
| `email_335` | `Reserva` | TBD — read body |
| `email_337` | `Reserva de Hotel 339920` | `partner_or_agency_communication` (Soltrópico booking confirmation) |
| `email_338` | `Re: Reserva de Hotel 339920` (withdrawal of `email_337`) | `partner_or_agency_communication` with `action_required = no` |
| `email_376` | `novo reserva codigo: 260620_Spicher_AT Pestana Tropico` | `partner_or_agency_communication` (Vista Verde new booking request) |
| `email_378` | `rsv #7292692` | TBD — read body |
| `email_377` | `ref 01769700 - marrakech` | TBD — read body |

**Validation question.** Are short cryptic subjects always
partner-initiated, or do they appear in other categories too?

---

## Group E — Internal Pestana requests vs partner forwards

The boundary between `internal_operational_request` and
`partner_or_agency_communication` is the *origin* of the underlying
operational ask, not the forwarder.

| email_id | Description | Could be | Proposed |
|---|---|---|---|
| `email_326` | Pestana IT manager requests technician accommodation at Alvor South Beach | `internal_operational_request` | `internal_operational_request` (clear: Pestana staff is the requester) |
| `email_327` | Pestana IT manager requests technician accommodation at Promenade | Same | `internal_operational_request` |
| `email_324` | Pestana staff trip request (vereador da Câmara do Sal) | `internal_operational_request` vs `partner_or_agency_communication` | Probably `internal_operational_request` — needs body read |
| `email_325` | Pestana staff trip request for Vintage Lisboa | Same | Probably `internal_operational_request` |
| `email_4` | Pestana web contact-form auto-acknowledgment | `internal_operational_request` vs `other_or_unclear` | `other_or_unclear` (no operational action; informational auto-reply) |

**Validation question.** Should `email_4`-style auto-acknowledgments be
under `internal_operational_request` (origin) or `other_or_unclear`
(no action needed)? Recommendation: `other_or_unclear`.

---

## Group F — Reservation notifications with embedded actionable remarks

Some channel-generated notifications carry guest remarks that could be
interpreted as actionable.

| email_id | Description | Could be | Proposed |
|---|---|---|---|
| `email_127` | Expedia new booking, remarks contain *"Working in travel industry. Please provide nice room, if possible upgrade."* | `automated_reservation_notification` with note vs `partner_or_agency_communication` | `automated_reservation_notification`; the audit checklist should *surface* the remark for human attention |
| `email_133` | Expedia new booking, remarks: *"Value Add Promotion: 1 Free bottle of wine per stay"* | Same | `automated_reservation_notification`; remark is operational info |
| `email_72` | Booking.com new booking with detailed cancellation/payment policy text | Same | `automated_reservation_notification`; policy text is boilerplate, not an action request |

**Validation question.** Confirm the rule: channel-generated email
remains in `automated_reservation_notification` even when remarks are
embedded; the audit checklist surfaces them.

---

## Group G — Partner thread replies (`[EXTERNAL] - RE:` pattern)

These are multi-turn threads. The subject `[EXTERNAL] - RE:` is a
routing marker, not a category.

| email_id | Description | Proposed |
|---|---|---|
| `email_368` | `[EXTERNAL] - DERTOUR Notification` thread | `partner_or_agency_communication` |
| `email_369` | `[EXTERNAL] - RE: Stop sales Hotel Pestana Fisherman` | `partner_or_agency_communication` |
| `email_358` | `URGENT - PLEASE REPLY - QE5211 ...` thread | `partner_or_agency_communication` with `urgency_or_sensitivity = urgent` |

**Validation question.** Confirm that `[EXTERNAL]` and `[ ref:!00D0...
:ref ]` are routing/CRM markers, never categories.

---

## Group H — Withdrawn / "sem efeito" requests

Partners withdrawing previously-sent requests. Same category as the
original request, but `action_required = no`.

| email_id | Description | Proposed |
|---|---|---|
| `email_157` | Osttour: clients did not pay, tour bought elsewhere | `partner_or_agency_communication`, `action_required = no` |
| `email_204` | Euromar Madeira: *"o pedido fica sem efeito"* | `partner_or_agency_communication`, `action_required = no` |
| `email_338` | Soltrópico: *"Por favor ignorem o pedido acima"* | `partner_or_agency_communication`, `action_required = no` |

**Validation question.** Confirm withdrawn requests stay in the partner
category with `action_required = no` (rather than being moved to
`other_or_unclear`).

---

## Group I — Mirai "Modified Reservation"

These are post-hoc notifications of completed modifications, not
modification requests.

| email_id | Description | Proposed |
|---|---|---|
| `email_299` | Mirai sends Apple Wallet passbook for modified reservation | `automated_reservation_notification`, lifecycle = `modified` |
| `email_300` | Same pattern, different booking | `automated_reservation_notification`, lifecycle = `modified` |

**Validation question.** Confirm Mirai's "Modified Reservation" emails
are notifications, not requests.

---

## Group J — Cancellation negotiations

Partners contesting cancellation fees or asking for waivers.

| email_id | Description | Proposed |
|---|---|---|
| `email_361` | Travelstore contesting cancellation fees due to weather event | `partner_or_agency_communication`, `urgency_or_sensitivity = urgent`, `action_required = yes` |

**Validation question.** Should "cancellation negotiation" be a
specific intent inside `partner_or_agency_communication`, or is the
generic category enough? Recommendation: generic category is enough;
intent-level granularity is decoration.

---

## Summary of validation focus

When you label, please pay particular attention to:

1. The forwarding-wrapper rule (Group A).
2. The stop-sales attribution (Group B).
3. The payment / credit-card split (Group C).
4. Short cryptic subjects (Group D).
5. The `email_4`-style auto-acknowledgments (Group E).
6. Whether reservation-notification remarks merit a separate
   classification (Group F).

These six decisions together determine ~80% of the taxonomy's
operational accuracy. The other groups are confirmations rather than
fork-points.
