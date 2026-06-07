# Dataset Analysis Summary

Empirical analysis of `emails_extracted_new.jsonl` (378 records, 10 fields:
`email_id, source_file, subject, from_raw, to_raw, cc_raw, date_raw,
date_parsed, body_raw, body_clean`). Phase 1 derived flags and channel
detections were excluded to avoid bias.

---

## 1. Dataset shape

| Metric | Value |
|---|---|
| Total records | 378 |
| Unique senders | 1 (all from `Trade <MASKED_EMAIL_851d9c9d5e>`) |
| `body_clean` length (chars) | min 396, median 2,675, p95 5,752, max 20,407 |
| Thread depth (from body markers) | 334 at depth 2; 44 at depth 3+ |
| Forwarded structure | Effectively 100% — `Trade` always re-forwards an upstream email |

**Implications:**

- The `from_raw` field carries zero classification signal — every email has
  the same wrapper sender. Classification must use `subject` + `body_clean`.
- Thread depth is a weak signal: 88% of emails are simple 2-step forwards.
- The forwarding wrapper is universal, not a discriminator. The Phase 1
  observation that "377 of 378 are forwarded" is uninformative.

---

## 2. Subject line is the strongest classification signal

Subject lines in this dataset are highly structured. Pattern-based bucketing
on the subject alone (after stripping `FW:`/`Re:` prefixes) produces:

| Bucket | Count | % |
|---|---:|---:|
| Automated new-booking notification (channel-formatted) | 160 | 42.3% |
| Mirai check-in / arrival notification | 91 | 24.1% |
| Cancellation (channel-formatted) | 36 | 9.5% |
| Unclassified by subject pattern | 34 | 9.0% |
| Modification (channel-formatted) | 14 | 3.7% |
| System / delivery failure | 8 | 2.1% |
| Operational alert | 8 | 2.1% |
| External thread reply (`[EXTERNAL]`) | 8 | 2.1% |
| Invoice / fiscal | 6 | 1.6% |
| Human-written request | 6 | 1.6% |
| Booking.com guest message ("We received this") | 5 | 1.3% |
| Stop sales | 1 | 0.3% |
| Payment problem | 1 | 0.3% |

**Implications:**

- ~80% of emails follow a small number of templated subject patterns.
- The "unclassified by subject" 34 emails are operationally important —
  inspection (see §3) shows they include human-written agency requests,
  internal Pestana operational messages, and miscellaneous OTA notifications
  with non-standard subject formats.

---

## 3. What the body inspection revealed

Reading body excerpts from each bucket and from the unclassified subset
exposed several patterns that the original Phase 1 taxonomy missed or
mis-bucketed.

### 3.1 Pattern: Pestana front-office forwards ("Favor dar seguimento")

Multiple emails are Pestana hotel front-office staff forwarding an
upstream email to the central reservations team with the phrase *"Favor
dar seguimento"* ("Please follow up"). The forwarding wrapper itself
contains no operational content — the actual issue is in the embedded
original. Examples: `email_98`, `email_335`, `email_336`.

**Implication:** the classifier must read past the outer forwarding
wrapper. The classification depends on the embedded content, not on the
forwarding note.

### 3.2 Pattern: Booking.com extranet guest messages

Two slightly different subject formats wrap the same operational type:

- *"We received this message from ..."* (English) — 5 emails
- *"Recebemos esta mensagem de ..."* (Portuguese) — 2+ in unclassified

Both originate from `<guest> through Booking.com` and contain a guest's
text inside the Booking.com extranet template. They are direct guest
inquiries requiring a human reply.

**Implication:** these should be a single category, not split by subject
language.

### 3.3 Pattern: Internal Pestana staff requesting accommodations

Examples like `email_326` and `email_327` (subject: *"Pestana Alvor South
Beach - Solução Vostio da AssaAbloy"*) are an internal IT manager
requesting accommodation for a technician working on a hotel project.
Body: *"Em âmbito do projeto em assunto, peço pf a reserva de alojamento"*.

These are operationally distinct from partner requests — they involve
internal cost allocation, staff/technician booking, and internal
coordination — but the original taxonomy had no category for them.

### 3.4 Pattern: Partner/agency human-written requests with CRM case numbers

Many emails (especially in `J_invoice` and `L_human_request`, plus
several in the unclassified bucket) carry a *"Case Number: 03XXXXXX [
ref:!00D0N0gGNy.!500MI0...:ref ]"* marker. This is a Salesforce CRM case
reference. The presence of this marker is itself a strong signal that
the email is a human-managed partner/agency thread, not an automated
notification.

Examples: `email_155`, `email_157`, `email_159`, `email_161`, `email_204`,
`email_329`, `email_336`, `email_358`.

**Implication:** the presence of a Salesforce case reference is a useful
classification feature — pre-existing CRM tracking implies human
handling.

### 3.5 Pattern: Withdrawn / "sem efeito" requests

Partners sometimes write back to cancel a previously-sent request:
*"o pedido fica sem efeito"* (`email_204`), *"Por favor ignorem o pedido
acima"* (`email_338`). These do not require operational action — they
nullify a prior message — but they look like partner requests on the
surface.

**Implication:** the taxonomy should allow this as a partner
communication with `action_required = no`, rather than a separate
category.

### 3.6 Pattern: Mirai "Modified Reservation" is a notification, not a request

`email_299` and `email_300` are Mirai-generated emails titled *"Modified
Reservation"* but the body indicates Mirai *already* notified the guest
about the change and is sharing a passbook. They are post-hoc
notifications of a modification, not requests to modify.

**Implication:** "Modified Reservation" subject ≠ partner-requested
modification. It belongs in the automated notification category with a
lifecycle facet of `modified`.

### 3.7 Pattern: Stop-sales communications are mostly partner threads

The single email matching the literal "stop sales" subject pattern
(`email_345`) is a partner replying to a Pestana stop-sales request with
their booked-allotment position. This is a partner communication about
stop-sales, not a system-generated stop-sales alert.

**Implication:** "stop sales" is not a category — it's a topic that
appears mostly inside partner communications and occasionally in system
alerts.

---

## 4. Channel distribution (re-derived from subject)

| Channel | Count |
|---|---:|
| Booking.com | ~73 |
| Mirai | ~92 |
| Expedia | ~54 |
| Hotelbeds | ~38 |
| Agoda | ~12 |
| SiteMinder | ~8 |
| Synergy, Hopper, Open Travel, EC Travel, BEMTours, ODIGEO, Schauinsland, Despegar, easyJet, BA Holidays, Golfbreaks, Juniper/Jet2, DERTOUR | Each <10 |
| Internal / partner / other (no channel marker) | ~40 |

**Implication:** channel is *metadata*, not a category. The list of
channels is long-tail and constantly growing. A taxonomy built on channel
names would be brittle.

---

## 5. KB scope and limitations

| Topic | KB entries | Relevant to reservations inbox? |
|---|---:|---|
| Vouchers Pestana | 75 | Mostly not — voucher T&Cs are out-of-scope for the reservations team |
| Book a stay | 66 | Partially — reservation conditions, group bookings, payments |
| Stay Information | 24 | Yes — check-in/out, pet, kids, restaurants, facilities |
| Meetings & Conferences | 15 | Rarely |
| Weddings & Events | 7 | Rarely |
| Pestana Guest Club | 6 | Rarely |

**Key facts:**

- All 193 KB entries are in **English only**.
- ~98% of dataset emails are mixed-language (PT/EN/ES/DE).
- ~80 KB entries are operationally relevant; the other ~115 are
  vouchers/loyalty/event content.
- Phase 1 found only 5 emails (1.3%) that look like generic policy
  questions answerable from a KB.

**Implication for taxonomy:**

The `kb_answerable` facet will fire on a very small minority of emails.
This should be explicit in the proposal — RAG is a small but real
sub-flow, not a primary feature of the system.

---

## 6. Style heuristic: automated vs human

Counting templated markers (RESERVATION DETAILS, Booking Confirmation Id,
PAYMENT DETAILS, etc.) vs human markers (greetings, signatures,
questions):

| Style | Count |
|---|---:|
| automated | 169 |
| human | 43 |
| unclear (mixed) | 164 |
| empty | 0 |
| mixed | 2 |

The "unclear" bucket is large because forwarded automated emails often
acquire a short human note from the front-office staff who forwarded
them (e.g., *"Favor dar seguimento"*). Style alone cannot classify these
— content interpretation is required.

**Implication:** automated/human is useful as a *facet* but not as a
primary category split.

---

## 7. Summary of key insights for the taxonomy

1. **Sender field is useless** — all emails share one wrapper sender.
2. **Subject patterns drive ~80% of classification** — leverage them.
3. **Forwarding wrappers must be looked past** — classification depends
   on the embedded original email.
4. **Channels are metadata, not categories** — long-tail and growing.
5. **CRM Case Numbers signal human handling** — useful feature.
6. **Partner threads dominate the "interesting" cases** — but they are a
   small fraction of volume (~10%).
7. **Internal Pestana operational requests exist** and were missing from
   the original taxonomy.
8. **The KB will answer very few emails** — RAG is a niche sub-flow.
9. **Most volume (~74%) is passive automated notifications** that need
   audit-style handling, not replies.
