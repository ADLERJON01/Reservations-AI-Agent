# Design Note — Router (#5) & Routing-Rules Design

**Purpose:** give an **independent reviewer** enough context to offer a third
opinion on **one open design choice**: how to represent the Router's routing
rules. Self-contained — you should not need the rest of the repo. Decisions
already made are marked **DECIDED**; the open choice is in §5.

Date: 2026-06-07 · Project: Pestana AI Email Agent (master's thesis prototype).

---

## 1. Project in one paragraph

A local, **draft-only, human-in-the-loop** prototype that classifies, audits, and
(later) drafts replies for hotel reservation emails. It never sends mail, never
touches internal systems, never executes operational actions. Runs on a MacBook
M1 via Ollama. Guiding principle: **"LLM describes, code decides"** — LLM agents
emit only descriptive fields; all routing/decisions are deterministic code.

Pipeline (8 agents; only 2–3 are LLM-driven):
```
#1 Preprocessor → #2 Classifier+Extractor → #3 Validator → #4 Audit → #5 Router
   → (#6 RAG if applicable) → #7 Output Generator → #8 Guardrails → DB → API/Dashboard
```

## 2. What is built and working (agents #1–#4)

All deterministic parts are pure Python and fully unit-tested; LLM calls use
Ollama's native structured-output API (primary model `ministral-3:3b`, temp 0,
fixed seed) with a Pydantic contract gate.

- **#1 Preprocessor** — parses raw `.txt` emails → cleaned `EmailInput`. 378/378
  parse, 100% header match vs a reference oracle.
- **#2 Classifier+Extractor** — one LLM call → locked `EmailExtraction`
  (classification: category + 5 facets + confidence; extraction: 9 field groups).
  100% schema-valid; **category accuracy provisional** (~70–83% on a borderline
  sample); **extraction is under-populated** by the 3B model (known issue, parked
  for prompt-engineering / possible larger model for extraction).
- **#3 Validator** — second LLM call, **semantic critique only** → `confirmed` /
  `flagged` + `flagged_fields` + `revised_confidence`. Catches real extraction
  misses but also emits some false flags (expected 3B-critic noise).
- **#4 Audit** — pure-Python deterministic checks: consistency (all categories) +
  lifecycle completeness (booking_notification only) → `audit_finding`
  (`clean`/`missing_fields`/`suspected_error`/`n/a`), `missing_required_fields`,
  `consistency_errors`, `risk_flags` (v1: `checkout_before_checkin`,
  `price_without_currency`, `lifecycle_mismatch`).

Observed end-to-end: Audit and Validator **independently corroborated** the same
extraction failure on a test email — which is the intended cross-check.

## 3. Key architecture decisions already locked (reviewer must respect)

These were settled on 2026-06-06 and **supersede earlier drafts**:

1. **Routing never gates on any single LLM-generated number.** Not the
   classifier `confidence`, not the Validator verdict alone.
2. **Deterministic checks are the routing backbone** (Audit: `audit_finding`,
   `consistency_errors`, `missing_required_fields`, `risk_flags`).
3. **The Validator flag is a *contributing escalation signal*, not the sole
   gate.** (It is the thesis's reframed "reliability checker," to be proven by
   ablation — not claimed as a hard router gate.)
4. **`confidence` and `revised_confidence` are logged/calibrated, never gated.**

## 4. The Router (#5) spec

Pure Python, no LLM. Two components:

**(a) `build_router_signals(state) → RouterSignals`** — assembles a signals
object from #2/#3/#4 and computes two deterministic decision flags:
- `outbound_action_required` = yes if `expects_human_response=yes` OR
  `audit_finding ∈ {missing_fields, suspected_error}` OR
  `urgency ∈ {urgent, sensitive_complaint}`.
- `requires_internal_system` = yes if category ∈ {booking_change_or_cancellation,
  payment_billing_or_rate_issue, inventory_availability_or_stop_sales,
  system_or_channel_delivery_exception} OR `audit_finding ≠ clean` OR
  (service_or_information_inquiry AND request_type ∉ {policy_or_general_question,
  withdrawal_or_acknowledgment}).
- `kb_answerable` = **None for now** (only RAG #6 can set it; RAG isn't built).

**(b) `route(signals) → (recommended_action, routing_reason, rule_id)`** — maps
signals to ONE of 9 actions: `audit_only`, `audit_with_attention`,
`audit_only_with_note`, `draft_reply_with_rag`, `escalate_to_reservations_team`,
`escalate_to_payment_or_billing`, `escalate_to_inventory_or_operations`,
`escalate_to_technical_or_operations`, `manual_review_unclear`.

**Known ordering subtlety:** the policy-question path (`draft_reply_with_rag`)
needs `kb_answerable`, which RAG produces *after* the Router. v1 routes policy
questions to the RAG path optimistically; final answerable/escalate is resolved
when RAG is wired.

**The routing logic is essentially:** `category → escalation target`, with
booking_notification split by `audit_finding`, service_inquiry split by
`request_type` (+ `kb_answerable`), plus a safety overlay (schema-invalid →
manual_review; `suspected_error` → attention) and the Validator flag as a
contributing escalation nudge.

## 5. THE OPEN CHOICE — how to represent the routing rules

### Critical finding driving this
A WIP `routing_rules.json` already exists but **encodes the OLD, rejected
philosophy**. Its top-priority rule routes to `manual_review_unclear` when
`confidence < 0.75` OR `validator = flagged` — i.e. it **gates on confidence**
and makes the **validator a sole top gate**, both of which §3 reverses. So the
rule *content* must be rewritten regardless. The question is the *representation*.

### Three proposals (all assume the §3 corrected philosophy)

**Proposal 1 — Declarative JSON rule list (revise the existing file).**
Priority-ordered, first-match-wins `routing_rules.json`; Router is a generic
evaluator over an `eq/in/lt/and/or` condition DSL on agent_output paths.
- + externally editable; matches the original "deterministic rule table" intent;
  rules visible without reading code; thesis-appendix friendly.
- − must build/maintain a JSON condition-DSL evaluator; multi-signal conditions
  get verbose; per-rule "sets" blocks can drift from a single source of truth.

**Proposal 2 — Two-stage: compute flags + compact decision table (author's lean).**
Stage 1 computes all flags once (single source of truth). Stage 2 = a small flat
table keyed on `category` (+ `audit_finding` for bookings, + `request_type` for
inquiries) → action, fronted by a thin code safety pre-check (schema-invalid →
manual_review; `suspected_error` → attention).
- + clean "derive facts vs pick action" split; tiny, maximally auditable table
  (one row per category/state); flags in exactly one place; no DSL to build;
  still an externalizable JSON artifact; mirrors the locked two-step design.
- − logic in two spots (safety pre-check in code + table); a bit more structure.

**Proposal 3 — Pure-Python guard-clause cascade.**
A single documented `route()` with ordered `if/elif` guards implementing the
priority hierarchy (schema fail → hard deterministic blockers → category mapping
→ validator-flag nudge → fallback); each branch returns a `rule_id`.
- + simplest to write/test; most expressive for `None`/edge-cases/combinations;
  the code is the auditable artifact (every branch traceable); can auto-emit a
  table for the thesis.
- − not externally configurable without a code change; deviates from the
  "routing_rules.json file" intent unless we generate the table from code.

### What we want the reviewer's opinion on
1. **Which representation** (1, 2, or 3) best fits a deterministic,
   auditable, thesis-defensible router given the logic is mostly
   category-driven with a small safety overlay?
2. Is there a **better hybrid** we're missing?
3. For Proposals 2/3, is **losing the single declarative `routing_rules.json`
   file** an acceptable trade for simplicity, given the thesis values an
   auditable rule artifact? (We can auto-generate a rules table from code.)
4. Any concern with the **`kb_answerable` ordering** workaround (§4)?
5. Anyplace the **"LLM describes, code decides"** principle is at risk, or where
   confidence/validator might sneak back into gating?

## 5.5 RESOLUTION (DECIDED) — Proposal 3 + a generated rule artifact

Chose **Proposal 3 — the pure-Python guard-clause `route()`** — with the auditable
rule table **auto-generated from the code** (`routing_rules.generated.{json,md}`),
which keeps a thesis-friendly rule artifact without hand-maintaining a second file
or building a condition-DSL. The mechanical escalations are explicit **`if/elif`
branches (not a lookup dict)** — chosen for readability and per-branch traceability
(each branch returns an `applied_rule_id`, R001…R999). The `kb_answerable` ordering
(Q4) is accepted: policy questions route to `draft_reply_with_rag` as a *candidate*,
RAG resolves answerable-vs-escalate (R030A/R030B) and re-invokes `route()`, so the
action is decided in one place ("code decides"). Locked as **routing_rules v1.2.0**.

## 6. Hard constraints (any proposal must respect)
Draft-only · no internal-system access · no operational actions ·
human-in-the-loop · grounded only · local on M1.

*End of design note.*
