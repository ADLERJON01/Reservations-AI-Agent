# Changelog — Taxonomy and Schemas

Versioning applies jointly to:

- `taxonomy.json`
- `llm_output_schema.json`
- `agent_output_schema.json`
- `routing_rules.json`

A version bump in any one of these requires a coordinated review of the
others. Versions follow semantic versioning (MAJOR.MINOR.PATCH):

- **MAJOR** — breaking changes (renamed/removed categories, facets,
  values, field paths, or routing actions).
- **MINOR** — backwards-compatible additions (new optional facet
  value, new routing rule, new extraction field).
- **PATCH** — clarifications to descriptions, examples, or rule notes
  with no behavioral change.

---

## v1.2.0 — 2026-06-12 — RAG (#6) routing resolution

**Scope:** `routing_rules.json` only (additive). Taxonomy/schemas unchanged.

- Added the post-RAG policy-question resolution rules (the action enum is
  unchanged; these reuse existing actions):
  - **`R030A_INQ_POLICY_ANSWERABLE`** — policy question AND `kb_answerable=True`
    → `draft_reply_with_rag` (confirmed).
  - **`R030B_INQ_POLICY_UNANSWERABLE`** — policy question AND `kb_answerable=False`
    → `escalate_to_reservations_team`.
  - `R030_INQ_POLICY` remains the **pre-RAG candidate** (`kb_answerable` unknown).
- **Flow:** the RAG Agent (#6) retrieves from the FAQ KB, sets `kb_answerable`
  (best cosine similarity ≥ `kb_answerable_threshold`), then re-invokes the
  Router so the action is decided in one place ("code decides").
- **Embedding model:** `BAAI/bge-m3` (multilingual; swappable). The 0.65 threshold
  is a starting point — **recalibrate for BGE-M3 with a RAG eval set**; score =
  `1 − cosine_distance` over normalized embeddings.
- MINOR: additive rules slotting into an existing priority; no existing mapping
  broken.

---

## v1.1.0 — 2026-06-07 — Routing rules finalized (philosophy corrected)

**Scope:** `routing_rules.json` only. `taxonomy.json`, `llm_output_schema.json`,
and `agent_output_schema.json` are **unchanged** (no category/facet/value/
field-path/action-enum changes). Treated as MINOR: the v1.0.0 routing rules were
flagged WIP/never-validated, so this is their first real finalization, not a
breaking change to a settled contract. (A strict reading of the joint-semver
policy — "MAJOR if it changes the action mapping for an existing match condition"
— could argue v2.0.0; we treat finalizing the WIP rules as MINOR.)

### What changed and why
- **Removed LLM-confidence gating.** The v1.0.0 `low_confidence` rule
  (`confidence < 0.75 OR validator flagged → manual_review_unclear`) is gone.
  Self-reported confidence from small local models is uncalibrated; it is now
  **logged, never gated** (decision 2026-06-06). The low-confidence threshold
  follow-up from v1.0.0 is therefore dropped, not tuned.
- **Validator demoted to a contributing signal.** A validator flag no longer
  forces manual review on its own; it only changes an otherwise-clean
  `booking_notification` → `audit_only_with_note`. (Reframes the Validator as an
  LLM-based reliability checker, proven by ablation — not a hard router gate.)
- **Deterministic Audit is the routing backbone** for `booking_notification`
  (`audit_finding` → audit_only / audit_with_attention).
- **Representation:** runtime is now a pure-Python guard-clause `route()` in
  `app/agents/router.py` (category-primary, first-match), not a JSON condition
  DSL. `routing_rules.json` + `routing_rules.generated.*` are the documentation;
  rule ids (R001…) are what `agent_output.applied_rule_id` references.
- **`kb_answerable` ordering:** policy questions route to `draft_reply_with_rag`
  as a *candidate* (`rag_required=true`); RAG (#6) resolves answerable-vs-escalate
  afterward. (The 0.65 similarity threshold follow-up from v1.0.0 still stands.)

### Validation
Validated by a 40-email subset batch run (2026-06-07): 100% schema-valid, full
coverage (no `R024`/`R999` fired), category/action distributions consistent with
documented shares. (The separate, upstream extraction-completeness issue —
under-population by `ministral-3:3b` — is tracked outside this spec.)

---

## v1.0.0 — 2026-05-25 — Initial locked taxonomy + schemas

**Status:** Locked. Phase 2 implementation consumes this version.

### Locked artifacts
- `taxonomy.json` — 7 categories, 5 facets, audit_finding enum, recommended_action enum.
- `llm_output_schema.json` — classification block + extraction block (9 field groups).
- `agent_output_schema.json` — full pipeline output incl. validator block, audit block, routing block, retrieval block, output block, guardrails block, logs block.
- `routing_rules.json` — 11 rules + priority-upgrade table + kb_answerable computation.

### Categories
| Name | Estimated frequency |
|---|---|
| `booking_notification` | ~74% |
| `booking_change_or_cancellation` | ~13% |
| `service_or_information_inquiry` | ~9% |
| `payment_billing_or_rate_issue` | ~4% |
| `inventory_availability_or_stop_sales` | ~3% |
| `system_or_channel_delivery_exception` | ~4% |
| `other_or_unclear` | ~1% |

### Facets
- `sender_type` (5 values)
- `request_type` (10 values)
- `booking_lifecycle_stage` (6 values)
- `expects_human_response` (3 values)
- `urgency_signal` (3 values)

### Architecture decision
Adopted multi-agent system orchestrated with LangGraph. Pipeline:
Preprocessor → Classifier+Extractor → **Validator** → Audit → Router →
(RAG conditional) → Output Generator → Guardrails → DB. The Validator
Agent is a novel contribution: an LLM-based critic agent that
re-checks the Classifier+Extractor output before downstream
consumption.

### Notable design decisions
- **Description vs decision separation.** LLM predicts descriptive
  labels (category + 5 facets); the Router computes handling decisions
  (`outbound_action_required`, `requires_internal_system`,
  `kb_answerable`). Decisions are NOT predicted.
- **Forwarding-invariant classification.** The universal `Trade →
  Pestana RPA` wrapper is ignored. Classification depends on the
  embedded original.
- **`booking_lifecycle_stage` facet mirrors
  `extraction.booking_identity.notification_type`.** The extraction
  field is canonical; the facet is a convenience copy.
- **Required-field-per-lifecycle logic lives in the audit module**
  (Phase 6), not the extraction schema. Extraction is unconditional.
- **`kb_answerable` is computed via actual RAG retrieval**, not
  predicted by the LLM. RAG only fires when category =
  `service_or_information_inquiry` AND request_type =
  `policy_or_general_question`.

### Changes vs the original Phase 1 handoff taxonomy
| Removed | Reason |
|---|---|
| 26-value `intent` layer | Replaced by 5 orthogonal facets. No empty buckets. |
| Category name `guest_or_partner_service_inquiry` | Renamed `service_or_information_inquiry`; sender is now a facet. |

| Added | Reason |
|---|---|
| `sender_type` facet (5 values) | Distinguishes guest / partner / internal / automated. |
| `request_type` facet (10 values) | Captures *what* the email is asking — the missing operational dimension. |
| `expects_human_response` facet (3 values) | Descriptive observation about reply solicitation. |
| `urgency_signal` facet (3 values) | Captures tone for routing prioritization. |
| `audit_finding` output field | Captures the agent's audit verdict on booking notifications. |
| `validator` block | Novel multi-agent contribution: LLM critic catches extraction errors. |
| Boundary rule "classify by inner content" | Forwarding wrappers are routing steps, not category signals. |

### Validation status
- Hotel reservations team validated the operational structure (mapped 1:1 to the 5 questions/answers gathered).
- Manual labeling of stratified 77-email sample partially completed by the project owner; ambiguous cases were resolved in the proposal.
- Full manual validation deferred to Phase 2 evaluation chapter (~30–50 emails recommended for accuracy measurement).

### Known follow-ups (not blocking lock)
- Refine the §2.1 vs §2.2 boundary (pure post-hoc notification vs change requiring validation) once real Phase 2 LLM outputs are observed.
- Tune the `kb_answerable` similarity threshold (currently 0.65) during Phase 2 evaluation.
- Tune the low-confidence threshold (currently 0.75) during Phase 2 evaluation.

---

## Notes for future bumps

- A new request_type value (e.g., `loyalty_program_question`) is a
  MINOR bump — add to `taxonomy.json` and document here.
- Renaming a category is a MAJOR bump — all dependent code, prompts,
  and stored records must be migrated.
- Adding a new routing rule is a MINOR bump if it slots between
  existing priorities; a MAJOR bump if it changes the action mapping
  for an existing match condition.
- Changes to `validator` semantics (e.g., adding a third `flagged_partial` state) are a MINOR bump.
