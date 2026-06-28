# Design Note — Classification Taxonomy (v1.1)

**Status:** **`taxonomy_v1_1` locked 2026-06-28** — v1.0.0's 7 operational categories
+ a targeted "RAG-safety patch" (the new `inquiry_answer_source` facet + supporting
changes), chosen over a fully-explored 10-category v2 redesign on the basis of a
measured ablation. **Part I** below documents the v1.0.0 taxonomy and its first
evaluation (still the backbone). **Part II** documents the v2 exploration, the
evidence, and the v1.1 decision + final locked design — this is the part that carries
the "design decisions & iterations" story for the thesis.

> Implementation note: **v1.1 is LIVE as of 2026-06-28.** The contract
> (`app/models/llm_output.py`), classifier prompt (`app/agents/prompts.py`), Router
> gate (`app/agents/router.py`), `RouterSignals`, `taxonomy.json` (v1.1.0), and the
> 105-test suite are all wired and green; an end-to-end smoke confirmed the
> `kb_policy → RAG` and notification → audit paths. The `*_v1_1.py` files remain as the
> validated drafts behind the eval harness. Field-name note: the live schema keeps
> `predicted_category` as the JSON key (the prompt references category *values*, not the
> key, so behaviour matches the validated run). Remaining follow-ups: RAG-gate challenge
> set, held-out validation, the `sender_type` regression (Part II §E/§F).

This note is the single consolidated reference for the *why*, the *downstream use*,
the *extractor*, and the *measured behaviour* of the taxonomy — written to support
thesis writing and the defense.

Source of truth (do not let this note drift from them):
- Vocabulary: [`outputs/taxonomy.json`](outputs/taxonomy.json) — locked enums + criteria.
- Schema / contract: [`app/models/llm_output.py`](app/models/llm_output.py) — Pydantic `Literal` enums.
- Prompt: [`app/agents/prompts.py`](app/agents/prompts.py) — assembled classifier system prompt.
- Routing: [`outputs/routing_rules.json`](outputs/routing_rules.json) v1.2.0 + [`app/agents/router.py`](app/agents/router.py).
- Labeling rules: [`outputs/gold/CODEBOOK.md`](outputs/gold/CODEBOOK.md).
- Results: [`outputs/gold/gold_metrics.md`](outputs/gold/gold_metrics.md) (enriched) and `gold_metrics_baseline.md` (baseline).

---

## 1. What the taxonomy is

Two layers the LLM emits per email, both gated by one Pydantic contract
(`EmailExtraction` = `classification` + `extraction`):

1. **One category** (7 values) — *how the operations team handles the email*.
2. **Five facets** — orthogonal descriptors (sender, ask, lifecycle stage, whether a
   human reply is solicited, urgency).

Plus two *derived* enums produced downstream, not by the LLM: `audit_finding`
(deterministic Audit) and `recommended_action` (deterministic Router).

### Core design principles (the "why")

These are the locked `design_principles` in `taxonomy.json`, and they explain every
boundary decision below:

- **LLM describes, code decides.** The model only *describes* (category + facets +
  extraction). Every *decision* (audit finding, route, action) is deterministic
  Python. The taxonomy is therefore a **descriptive vocabulary**, not a decision tree
  the model executes — which is what makes the pipeline auditable and the routing
  reproducible.
- **Operational, not semantic.** Categories group by team workflow (audit vs
  escalate vs draft), *not* by topic. Two emails about "a cancellation" can land in
  different categories depending on whether a human must validate it.
- **Forwarding-invariant.** Classify by the *inner* content, never the forwarder
  (`FW:`, `[EXTERNAL]`, `Favor dar seguimento`, CRM `[ ref:…:ref ]` markers).
- **Channel-agnostic.** Booking.com / Expedia / Mirai etc. are *metadata*
  (`source_channel`), never categories.
- **MECE + fallback.** Every email fits exactly one category; `other_or_unclear`
  guarantees totality.
- **Evaluable.** Every category has ≥5 observed examples; every facet value is
  observable from email content alone.

---

## 2. The seven categories (full definitions)

Frequencies are *estimates over the ~378-email corpus* (`taxonomy.json`); the gold
set deliberately over-samples the rare ones (see §8), so do not read gold counts as
production prevalence.

### 2.1 `booking_notification` — ~74%
System-generated, templated channel email about **one** booking lifecycle event.
Team workflow = **audit against PMS**, reply only on a detected mistake.
- **In:** new / paid / pre-arrival notifications from any channel; post-hoc
  *Modified* / *Cancelled* notices **that do not require validation**.
- **Out:** human-written booking requests → `service_or_information_inquiry`;
  channel changes that *require validation* → `booking_change_or_cancellation`;
  PMS/SiteMinder errors → `system_or_channel_delivery_exception`.
- **Signals:** templated subject (`<Channel> Booking for #<ID>`), templated body
  sections (RESERVATION/PAYMENT DETAILS), **no human greeting/signature**, sender
  `automated_system`.
- **Downstream:** the only category that flows to the **Audit** branch (not an
  escalation). Action depends on `audit_finding` (§6).

### 2.2 `booking_change_or_cancellation` — ~13%
A change/cancellation of an **existing** booking that needs the team to
review/validate (a request/negotiation, system- or human-originated).
- **In:** human modification/cancellation requests, fee negotiations, date/room/
  occupancy changes; channel change/cancel notices *requiring validation*.
- **Out:** brand-new booking requests → service; stop-sales/allotment → inventory.
- **Downstream:** `escalate_to_reservations_team`.

### 2.3 `service_or_information_inquiry` — ~9% (corpus) / largest gold stratum
The **default for any human-written message**: a question, quote, new-booking
request, or service/ancillary request that is *not* a change/cancellation and *not*
a payment/inventory/system matter.
- **In:** policy/amenity questions (RAG candidates), availability/quote inquiries,
  new booking requests (guest/partner/agency/internal staff), ancillary requests
  (transfers, extras), withdrawals/acknowledgments of prior inquiries.
- **Out:** payment-topic → payment; existing-booking change → change/cancel;
  allotment coordination → inventory.
- **Downstream:** the **only category whose route depends on a facet** —
  `request_type` splits it three ways (policy→RAG draft, withdrawal→note,
  else→escalate). See §6.

### 2.4 `payment_billing_or_rate_issue` — ~4%
Primary topic is payment, billing, invoices, fiscal data (VAT/CIF/NIF), rates,
tariffs, VCC/credit-card, or commercial contracts — **topic-driven even when phrased
as a question or arriving as an automated alert**.
- **Out:** a booking notification that merely *contains* a VCC field (no payment
  question) stays `booking_notification`.
- **Downstream:** `escalate_to_payment_or_billing`.

### 2.5 `inventory_availability_or_stop_sales` — ~3%
Managing room inventory, allotment, stop-sales, or availability coordination
(partner replies / operational threads / system availability alerts).
- **Out:** a guest/partner *asking to book* (availability as part of a booking flow)
  → service; PMS delivery failures → system.
- **Downstream:** `escalate_to_inventory_or_operations`.

### 2.6 `system_or_channel_delivery_exception` — ~4%
A **genuine technical/delivery failure** from a channel manager / PMS / OTA
(SiteMinder delivery failure, sync error, "reservation could not be found",
extranet alerts requiring login).
- **Out:** Mirai credit-card warnings → payment (topic is payment); availability
  alerts → inventory.
- **Downstream:** `escalate_to_technical_or_operations`.

### 2.7 `other_or_unclear` — ~1%
MECE fallback: auto-acknowledgments with no operational content, ambiguous/garbled/
near-empty bodies, spam.
- **Downstream:** `manual_review_unclear`.

---

## 3. The five facets (full definitions + downstream role)

Facets are assigned independently from their locked value sets. **Crucially, only
some facets change the route** (§6) — the rest are advisory signals for the dashboard
and the human reviewer.

### 3.1 `sender_type`
`automated_system` | `partner_or_agency` | `direct_guest` | `internal_pestana_staff`
| `unknown`. Author of the *inner* content after stripping forwarders.
- **Downstream role:** **descriptive / analytical only** — not consumed by any
  routing rule or decision flag. Its operational weight is *indirect*: it is the
  decisive cue for the category boundary (`automated_system` ⇒ likely
  `booking_notification`; a human author ⇒ a human-intent category).

### 3.2 `request_type`
`policy_or_general_question` | `availability_or_quote_inquiry` | `new_booking_request`
| `modification_request` | `cancellation_request` | `payment_or_billing_inquiry` |
`complaint_or_dispute` | `withdrawal_or_acknowledgment` | `none` | `other_or_unclear`.
- **Downstream role: routing-critical, but only inside
  `service_or_information_inquiry`** (rules R030/R031/R032). `policy_or_general_question`
  → RAG draft; `withdrawal_or_acknowledgment` → audit-only-with-note; anything else
  → escalate to reservations. Also feeds the `requires_internal_system` flag. Outside
  the service category it is descriptive (most notifications are `none`).

### 3.3 `booking_lifecycle_stage`
`new` | `paid` | `pre_arrival` | `modified` | `cancelled` | `n/a`. Mirrors
`extraction.booking_identity.notification_type`.
- **Downstream role: routing-relevant for `booking_notification` only.** It selects
  the **required-field set the Audit checks** (`REQUIRED_BY_LIFECYCLE` in
  `app/agents/audit.py`: e.g. `paid` additionally requires `payment.payment_status`),
  and a stage-vs-`notification_type` disagreement raises a `lifecycle_mismatch`
  consistency flag. Both feed `audit_finding`, which drives the route. For every
  non-notification category, lifecycle is descriptive (typically `n/a`).

### 3.4 `expects_human_response`
`yes` | `no` | `unclear`. Solicits a reply, **decision, or follow-up** — a *required*
extranet/link click counts; a routine audit-vs-PMS does **not**.
- **Downstream role: advisory.** Feeds the `outbound_action_required` decision flag
  (dashboard + output context), never the action choice directly.

### 3.5 `urgency_signal`
`routine` | `urgent` | `sensitive_complaint`. Precedence
`sensitive_complaint > urgent > routine`.
- **Downstream role: advisory.** Feeds `outbound_action_required`. Does not change
  the route.

> **Implication for evaluation:** the signals that actually *change handling* are
> **category**, **request_type** (within service), and **lifecycle** (within
> notification, via Audit). `sender_type`, `expects_human_response`, and
> `urgency_signal` are advisory. This is why a facet's *accuracy* and its
> *operational impact* must be read together (§8).

---

## 4. Derived enums (produced downstream, not by the LLM)

- **`audit_finding`** (`clean` | `missing_fields` | `suspected_error` | `n/a`) —
  deterministic Audit over `booking_notification`. The routing backbone for that
  category.
- **`recommended_action`** (9 values) — deterministic Router output; the final
  routing decision. Enumerated in §6.

---

## 5. Downstream impact map

### 5.1 Category → action (the deterministic Router, `routing_rules.json` v1.2.0)

| Category | Rule(s) | Action |
|---|---|---|
| `other_or_unclear` | R003 | `manual_review_unclear` |
| `booking_notification` | R020–R024 | `audit_with_attention` / `audit_only_with_note` / `audit_only` (by `audit_finding` + validator flag) |
| `service_or_information_inquiry` | R030/R030A/B, R031, R032 | RAG draft *or* escalate *or* note — **by `request_type` + `kb_answerable`** |
| `payment_billing_or_rate_issue` | R040 | `escalate_to_payment_or_billing` |
| `inventory_availability_or_stop_sales` | R041 | `escalate_to_inventory_or_operations` |
| `system_or_channel_delivery_exception` | R042 | `escalate_to_technical_or_operations` |
| `booking_change_or_cancellation` | R043 | `escalate_to_reservations_team` |

Global pre-empts: R001 (schema-invalid) and R002 (forced) → `manual_review_unclear`.
Rules evaluate by ascending priority; first match wins; categories are mutually
exclusive so only the pre-empts cross-cut. **Confidence is logged, never gated**
(decision 2026-06-06).

### 5.2 The `service_or_information_inquiry` sub-routing (only facet-driven branch)

```
service_or_information_inquiry
 ├─ request_type == policy_or_general_question → draft_reply_with_rag (candidate)
 │     └─ RAG #6 resolves: kb_answerable? yes → draft_reply_with_rag
 │                                         no  → escalate_to_reservations_team
 ├─ request_type == withdrawal_or_acknowledgment → audit_only_with_note
 └─ any other request_type                       → escalate_to_reservations_team
```

This is the single place a facet error can silently change the route — e.g. a missed
`policy_or_general_question` loses a RAG draft; a missed `withdrawal` escalates a
closed thread unnecessarily.

---

## 6. The extractor (Classifier+Extractor, Agent #2)

### 6.1 Output schema
One `EmailExtraction` object: `classification` (the 6 enums above + `confidence`
float + `evidence_short`/`reasoning_short` ≤200 chars) and `extraction` — nine nested
groups: `booking_identity`, `guest`, `stay`, `room_and_rate`, `financials`,
`payment`, `policies`, `requests_and_remarks`, `links`. Every leaf is `Optional`
(absent scalar → `null`, absent list → `[]`). The Pydantic `Literal` enums make any
out-of-vocabulary label a hard validation failure — **this model is the contract gate
for every LLM call.**

### 6.2 The system prompt (assembled in `build_system_prompt()`)
Order is deliberate; `EXTRACTION_EMPHASIS` stays **last** (the position proven to lift
extraction completeness 32%→72%):

1. **`SYSTEM_PROMPT`** — role + locked output rules (two top-level keys; category
   from the 7; facets from allowed values; absent→null/[]; never invent; retain
   `MASKED_*`; `total_amount=0.00` valid for cancellations; lifecycle mirrors
   `notification_type`; ≤200-char evidence/reasoning).
2. **`CATEGORY_GUIDE`** — the 7 definitions **+ an explicit stop-at-first-match
   decision order** (added 2026-06-21):
   ```
   a) System/templated channel notice of a booking event → booking_notification
   b) Genuine technical/delivery/sync failure          → system_or_channel_delivery_exception
   c) Primary topic is payment/billing/rates           → payment_billing_or_rate_issue
   d) Inventory/allotment/stop-sales coordination      → inventory_availability_or_stop_sales
   e) Human requests change/cancel of an existing       → booking_change_or_cancellation
      booking, or disputes one
   f) Any OTHER human question/quote/new-booking/        → service_or_information_inquiry
      service request   (THE DEFAULT)
   g) None of the above                                 → other_or_unclear
   ```
3. **`FACET_GUIDE`** — enriched 2026-06-21 with the CODEBOOK conventions:
   `booking_notification ⇒ request_type none`; thread-closure ⇒ `withdrawal`;
   payment topic ⇒ `payment_or_billing_inquiry`; ancillary service ⇒
   `new_booking_request`/`availability_or_quote_inquiry`; read the **latest** thread
   message; `expects_human = reply OR decision` (link click counts); urgency
   precedence + stale-urgent→routine.
4. **`FEWSHOT_EXEMPLARS`** — 8 **abstracted** boundary patterns (added 2026-06-21).
   Deliberately *not* the verbatim gold emails — using scored emails as exemplars
   would be train-on-test contamination of the eval.
5. **`EXTRACTION_EMPHASIS`** — mandatory-and-thorough extraction with concrete
   examples.

Full text in `app/agents/prompts.py`. Assembled prompt ≈ 1,862 tokens.

### 6.3 Runtime (deterministic)
`ministral-3:3b` via Ollama `/api/chat`, **structured output** (`format` = JSON
schema of `EmailExtraction`, `think=False`); `temperature=0.0`, fixed `seed=0`,
`num_predict=2000`, **`num_ctx=8192`** (raised 2026-06-21 so the enriched prompt +
a 6000-char body cannot silently overflow the 4096 default and truncate the rules);
1 bounded salvage retry at `temperature=0.3` on invalid output.

---

## 7. Evaluation (gold set)

**Method.** 49 emails stratified from the curated 77-pool (rare categories kept in
full, large buckets trimmed — so per-category metrics are meaningful), **hand-labeled
blind** against the CODEBOOK to form a human ground truth, then scored against the
live pipeline. 21/49 are flagged `ambiguous`. Predictions were 100% schema-valid
with zero runtime errors in both runs.

### 7.1 Baseline vs enriched prompt

| Signal | Baseline | Enriched (2026-06-21) | Δ | Routing weight |
|---|---|---|---|---|
| **Category (all 49)** | 59.2% | **79.6%** | **+20.4** | primary |
| **Category (28 unambiguous)** | 42.9% | **75.0%** | **+32.1** | primary |
| `sender_type` | 59.2% | 69.4% | +10.2 | advisory |
| `expects_human_response` | 77.6% | 79.6% | +2.0 | advisory |
| `request_type` | 44.9% | 44.9% | **0.0** | routing (within service) |
| `urgency_signal` | 93.9% | 91.8% | −2.1 | advisory |
| `booking_lifecycle_stage` | 71.4% | 65.3% | −6.1 | routing (within notification) |
| Macro-F1 (category) | 0.71 | 0.70 | −0.01 | — |

Category errors fell **20 → 10**. The `service_or_information_inquiry` recall collapse
that defined the baseline (recall 0.24, 16/21 missed) was largely repaired.

### 7.2 Category precision / recall / F1 (enriched)

| Category | P | R | F1 | support |
|---|---|---|---|---|
| system_or_channel_delivery_exception | 1.00 | 1.00 | 1.00 | 4 |
| inventory_availability_or_stop_sales | 0.86 | 1.00 | 0.92 | 6 |
| payment_billing_or_rate_issue | 0.75 | 1.00 | 0.86 | 3 |
| service_or_information_inquiry | 0.88 | 0.71 | 0.79 | 21 |
| booking_notification | 0.64 | 0.90 | 0.75 | 10 |
| booking_change_or_cancellation | 0.67 | 0.50 | 0.57 | 4 |
| other_or_unclear | 0.00 | 0.00 | 0.00 | 1 |

### 7.3 What the enrichment changed (flip diagnosis)

- **request_type flat (22/49 → 22/49):** 4 fixed (90, 99, 151, 297) exactly offset by
  4 broken. Residual errors are dominated by three *non-promptable* causes:
  (a) **taxonomy gap** — 6 inventory/stop-sales emails whose true `request_type` is
  `other_or_unclear` (no clean value exists); (b) **thread-closure not detected** — 5
  `withdrawal_or_acknowledgment` emails the model won't recognize as closures despite
  the rule; (c) the **inherently fuzzy** `new_booking_request` ↔
  `availability_or_quote_inquiry` boundary (~9 emails churning).
- **lifecycle −6 is a *side effect of the category win*, on low-impact emails.**
  Almost every new miss is `→ n/a`: emails correctly moved into
  `service_or_information_inquiry` get `lifecycle=n/a` from the model, but were
  labeled with the *referenced* booking's stage. **For service emails lifecycle does
  not affect routing** (§3.3), so this regression is largely operationally inert — and
  it exposes a genuine labeling ambiguity (does an inquiry referencing a dated booking
  carry that stage, or `n/a`?).

### 7.4 Caveats (state these in the thesis)
- **Development-set numbers.** The conventions were *derived from* these 49 emails, so
  the lift is real but **optimistic**; generalization needs a **held-out** run (the 28
  unused 77-pool emails, or a fresh stratified draw).
- **Macro-F1 distortion.** With 1–6-email rare classes, macro-F1 is dominated by them
  (the single `other_or_unclear` email collapsing to 0.00 flattened it). **Report
  accuracy + per-class support as the headline**, macro-F1 as secondary.
- **`ambiguous` subset.** 21/49 are hard cases; report all-vs-unambiguous in parallel.

---

## 8. Strengths

- **Operational design pays off in routing.** Because categories map to team
  workflow, the Router is a short deterministic guard-clause table with full coverage
  (no fallback fired in the 40-email routing validation).
- **Strong, stable signals where it matters:** `system` (F1 1.00), `inventory`
  (0.92), `payment` (0.86), and `urgency` (~92%) are reliable — the escalation
  categories that protect the security constraints (no internal access) route
  correctly.
- **The decision-order revision is a clean, measurable intervention** (+20.4 category
  / +32.1 unambiguous): good "diagnose → fix → measure" evidence for the defense.
- **Contract-gated.** `Literal` enums + structured output = 100% schema-valid; an
  out-of-vocabulary label cannot leak downstream.
- **MECE + forwarding-invariant + channel-agnostic** held up in practice; the
  fallback (`other_or_unclear`) absorbs the genuinely unclassifiable.

## 9. Weaknesses & open taxonomy issues

Identified during labeling (CODEBOOK findings) and confirmed by the eval. These are
**taxonomy limitations, not classifier bugs** — i.e. the ceiling is partly in the
vocabulary, not the model:

1. **`request_type` is booking/guest-centric.** No value for (a) ancillary services
   (transfers/extras — forced into `new_booking_request`/`availability_or_quote_inquiry`)
   or (b) inventory/stop-sales coordination (forced into `other_or_unclear`). This
   caps `request_type` accuracy regardless of prompt detail (§7.3a).
2. **No "partner request-to-book" category** distinct from confirmed-booking
   notifications (emails 317/337) — currently handled by a documented assumption,
   not a taxonomy slot.
3. **`booking_notification` ↔ `booking_change_or_cancellation` boundary is internally
   contradictory.** `taxonomy.json` splits channel changes on "requires validation"
   (not determinable from the email) and double-lists the Mirai *Modified* type.
   Resolved operationally by **Option A** (channel-templated notice → notification;
   human request → change), but the spec text still carries the contradiction.
4. **`expects_human_response` name vs definition mismatch** — the field says
   "response" but the locked definition is "reply, **decision, or follow-up**."
5. **`booking_lifecycle_stage` is ambiguous for inquiries** that reference a dated
   booking (stage vs `n/a`) — surfaced by the −6 regression (§7.3b). Low routing
   impact, but a labeling-definition gap.
6. **`other_or_unclear` is fragile** at small support (1 email → 0.00 F1). The
   "service is the default" rule can absorb true-`other` emails (email_162). Needs
   more examples and a sharper auto-acknowledgment cue.
7. **Thread-closure detection is weak** in practice — `withdrawal_or_acknowledgment`
   is consistently missed (§7.3c), affecting the R031 note route.

## 10. Recommended next steps

1. **Validate on held-out emails** before claiming the category lift generalizes
   (removes the dev-set optimism of §7.4).
2. **Treat the request_type ceiling as a taxonomy decision, not more prompt text:**
   either add values (ancillary-service, inventory-coordination) in a v1.1.0, or
   document the gap as a stated limitation.
3. **Reconcile the `taxonomy.json` notification↔change contradiction text** with the
   adopted Option A (finding #3) so the spec matches the runtime behaviour.
4. **Decide the lifecycle-on-inquiry convention** (finding #5) and reflect it in both
   CODEBOOK and prompt.
5. Keep the enriched prompt — category is the primary routing signal and its gain
   dwarfs the advisory-facet wobble.

---

# Part II — The v1.1 redesign: exploration, evidence, decision (2026-06-28)

Part I established v1.0.0 at **79.6% category accuracy** (enriched prompt) on the
49-email gold set. Part II is the *design-science core* of the taxonomy chapter: a
hypothesis (a richer taxonomy), a measured ablation, a decisive finding, and an
evidence-based final decision. Additional sources for this part:
- v1.1 schema/prompt (drafts): `app/models/llm_output_v1_1.py`, `app/agents/prompts_v1_1.py`
- preprocessor: `app/agents/preprocessor.py` + [`DESIGN_NOTE_preprocessor.md`](DESIGN_NOTE_preprocessor.md)
- reviewer dialogue: `TAXONOMY_V2_REVIEW_REQUEST.md`
- per-run metrics: `outputs/gold/gold_metrics_v2.0.md`, `…_v2.1.md`, `…_v1_1.md`
- labeling conventions: `outputs/gold/CODEBOOK.md` (§ "v2 / v1.1 labeling updates")

## A. Why we re-opened a "locked" taxonomy (the motivation)
The first gold evaluation exposed three structural weaknesses, all converging on one
risk:
1. **`service_or_information_inquiry` was overloaded** — it absorbed policy questions,
   availability/quote requests, new-booking requests, ancillary-service requests, and
   thread closures. `request_type` (44.9%) was the weakest facet.
2. **RAG eligibility was gated on a fragile signal** — `service AND request_type ==
   policy_or_general_question`. Sitting the safety gate on the weakest facet is
   brittle.
3. **No explicit mechanism prevented *false RAG candidates*** — emails that *look*
   like questions but actually need live data (availability, payment, booking status)
   or staff action. Drafting a static-KB answer to those would violate the project's
   hard constraints (**grounded answers only; no internal-system access**).

So the redesign was **safety-motivated, not cosmetic**. Unlocking a "locked" spec was
justified by (a) the standing principle to never treat architecture as final, and
(b) the fact that the gold set now gave us a *measurement rig* to test alternatives
rather than argue them.

## B. The v2 hypothesis (10-category redesign)
Split the overloaded bucket into four explicit workflows — `knowledge_policy_inquiry`,
`sales_availability_or_quote_inquiry`, `guest_service_or_ancillary_request`,
`thread_closure_or_acknowledgment` — and add a new orthogonal facet
**`inquiry_answer_source`** (`kb_policy` / `internal_system` / `human_judgment` /
`not_applicable` / `unclear`). Derive the RAG gate in code as an **AND of two
independent signals**: `knowledge_policy_inquiry AND kb_policy`.

Design decisions taken here, *with rationale* (these recur in the final design):
- **`rag_candidate` is derived in code, never emitted by the LLM** — it is a
  *decision*, and "the LLM describes, code decides". Emitting it would also let the
  model contradict itself (flag RAG while emitting a non-eligible category/source).
- **Describe-only purity** — the prompt must not mention routing/RAG/escalation. A
  classifier told which label "gets a draft" can drift toward/away from that label for
  routing reasons, corrupting the descriptive signal *and* the evaluation.
- **Kept the field names `category`/`request_type`** (minimise downstream churn);
  **renamed `expects_human_response` → `requires_human_followup`** (the old name
  contradicted its own "reply OR decision/action" definition).
- **`request_type` demoted to a descriptive tag** (the Outlook/dashboard "what is
  this about" label), no longer a routing gate.

## C. The iteration and its measurements (same 49 gold emails, same `ministral-3:3b`)
| Config | What changed | Category (all) | Macro-F1 | RAG precision | RAG recall |
|---|---|---|---|---|---|
| v1.0.0 (enriched) | baseline | **79.6%** | 0.70 | (no gate) | — |
| v2.0 | 10-cat prompt | 65.3% | 0.65 | 100% | 100% |
| v2.1 | + preprocessor v2, trimmed prompt, purity, boundary rules, facet decoupling | 69.4% | 0.72 | 100% | 50% |

v2.0 regressed category badly (the 3B scattered `booking_notification` into the new
`sales` bucket; `thread_closure` recall 0.20). v2.1's preprocessor + prompt work
recovered ground (notification recall 0.50→0.75, closure recall 0.20→0.60, sender
+12) but still trailed v1 on raw category, and introduced a `thread_closure`
over-trigger + a RAG-recall drop.

## D. The decisive finding
**The RAG-safety benefit came from `inquiry_answer_source`, not from the category
split.** Proof: collapsing the v2.1 predictions back to v1's 7 categories and applying
`service_or_information_inquiry AND kb_policy` *preserved* the RAG candidates — the
`kb_policy` facet does the work; the category distinction does not. The 10-way split
was therefore **unnecessary for the safety goal** and cost ~10–12 points of category
accuracy on the small model. This is the pivot of the whole chapter:
*diagnose limitation → propose redesign → measure trade-off → isolate the useful
component → adopt the simpler robust solution.*

## E. The decision — `taxonomy_v1_1` — and its measured result
**Decision:** keep v1's reliable 7-category backbone and add only the components that
earned their place: `inquiry_answer_source`, `ancillary_service_request`,
`requires_human_followup`, the lifecycle convention, describe-only purity, and
preprocessor v2. Derive the RAG gate in code.

We **built it for real and re-measured** rather than trusting the collapse-proxy — and
that honesty mattered, because the proxy over-promised:

| Metric | v1.0.0 | v2.1 | **v1.1 (locked)** |
|---|---|---|---|
| **Category (all)** | 79.6% | 69.4% | **81.6%** (best) |
| Category (unambiguous) | 75.0% | 72.5% | **85.0%** |
| **Macro-F1** | 0.70 | 0.72 | **0.83** (best) |
| **request_type** | 44.9% | 49.0% | **65.3%** |
| urgency_signal | 91.8% | 95.9% | 95.9% |
| RAG precision | — | 100% | **50%** (proxy had said 100%) |
| RAG recall | — | 50% | **100%** |
| sender_type | 69.4% | 75.5% | 57.1% (regressed) |

v1.1 is **the best config on the primary routing signal** (category 81.6%, *beating
the original v1*) and on `request_type` (+20 pts). The RAG gate, however, is weaker
than hoped: precision 50% (false candidates `email_155`, `email_368`). The cause is
structural and worth stating in the thesis: folding everything into the broad
`service` category means the gate **leans entirely on `kb_policy`** with no second
narrowing category, so `kb_policy` errors leak through (v2's two-narrow-signal gate
masked them).

**Decision on the RAG gate (explicit):** **false RAG candidates are accepted.** Under
the **draft-only + human-in-the-loop** design a false candidate is bounded — a wrong
draft is *never sent*; the reviewer discards it. The gate exists to make drafts
*useful and checkable*, not as a safety-of-last-resort. A *missed* candidate (cheap,
just escalates) and a *false* one (discarded) are both low-cost. So gate precision did
**not** block the lock. (If precision is wanted later, a 3-signal gate `service AND
kb_policy AND request_type==policy_or_general_question` measured 67%/100% on the gold.)

**Caveats recorded for the thesis (honesty / threats to validity):**
- **n = 2 gold RAG candidates** — *no* RAG precision/recall number here (50/67/100%)
  is statistically trustworthy. A dedicated **RAG-gate challenge set (30–50 cases)** is
  a required follow-up before the RAG draft path is trusted.
- **`sender_type` regressed to 57%** (advisory facet, does not route) — to investigate.
- **The v1 79.6% baseline predates preprocessor v2**, so v1.1's +2 over it *bundles*
  the preprocessor gain. The clean comparisons are v2.0-vs-v2.1 (preprocessor effect)
  and v1.1-vs-v2.1 (taxonomy effect at equal preprocessing).
- All numbers are **development-set** (the conventions were derived from these 49) —
  optimistic; held-out validation still owed.

## F. The final locked v1.1 design (the spec)
**Categories (7, unchanged):** `booking_notification`, `booking_change_or_cancellation`,
`service_or_information_inquiry`, `payment_billing_or_rate_issue`,
`inventory_availability_or_stop_sales`, `system_or_channel_delivery_exception`,
`other_or_unclear`.

**LLM emits (descriptive only):** `category`, `request_type` (+`ancillary_service_request`;
a descriptive tag), **`inquiry_answer_source`** (new), `sender_type`,
`booking_lifecycle_stage` (referenced-booking convention), `requires_human_followup`
(renamed), `urgency_signal`, `confidence`, `evidence_short`, `reasoning_short`.

**Derived in code (decisions):** `rag_candidate = service_or_information_inquiry AND
inquiry_answer_source == kb_policy`; plus `audit_finding`, `recommended_action`, the
dashboard flags.

**`inquiry_answer_source` semantics:** `kb_policy` (answerable from static
policy/amenity/facility knowledge), `internal_system` (needs live booking/payment/
inventory/rate/customer data), `human_judgment` (needs staff decision/coordination/
exception/arrangement), `not_applicable` (no inquiry — notification/alert/closure),
`unclear`. It is **independent of `requires_human_followup`** (a system warning is
`not_applicable` + `yes`).

**Downstream:** category→action routing is unchanged from v1 (Part I §5); the only
change is that the `service_or_information_inquiry` branch's RAG gate now keys on
`inquiry_answer_source == kb_policy` instead of the old
`request_type == policy_or_general_question`.

**Implementation status:** (1) ✅ **promoted to live 2026-06-28** — contract
(`llm_output.py`), prompt (`prompts.py`), Router gate (`router.py`), `RouterSignals`,
`taxonomy.json` v1.1.0, suite green (105), end-to-end smoke passed. (2) build the
RAG-gate challenge set — *still owed* (gold has only n=2 RAG candidates); (3) held-out
validation run — *still owed*; (4) investigate the `sender_type` regression.

## G. Strengths, weaknesses, limitations (thesis material)
**Strengths:** best measured category (81.6%) and `request_type` (65.3%) on a local 3B;
a real RAG-safety mechanism whose residual risk is *bounded by the draft-only
architecture*; minimal churn (kept the 7 categories); the rich v2 distinctions are
*preserved as `request_type` tags* for the dashboard without paying their category-level
accuracy cost; the decision is *evidence-based* (measured ablation, not intuition).
**Weaknesses / limitations:** RAG-gate precision unvalidated (n=2) and structurally
weaker than v2's two-signal gate; `sender_type` regression; the four workflows are no
longer first-class categories (operational granularity now lives in `request_type`);
all numbers are development-set.

---

### Change log for this note
- **2026-06-21** — created. Documents taxonomy v1.0.0, the 2026-06-21 classifier
  prompt enrichment (decision-order + facet conventions + few-shot + `num_ctx`), and
  the first gold-set evaluation (baseline 59.2% → enriched 79.6% category).
- **2026-06-28** — added Part II: the v2 (10-category) exploration, the v2.0→v2.1
  iteration, the decisive finding (RAG safety came from `inquiry_answer_source`, not
  the split), and the **`taxonomy_v1_1` lock** (v1 7-cat + patch; category 81.6%).
  Updated title/status to v1.1.