# Design Note — Guardrails Agent (#8) Spec & Dev Plan

**Purpose:** give an **independent reviewer** enough context to critique the spec
and dev plan for the Guardrails Agent before it's built. Self-contained — you
should not need the rest of the repo. **DECIDED** = settled; §10 = open questions.

Date: 2026-06-20 · Project: Pestana AI Email Agent (master's thesis prototype).

---

## 1. Project in one paragraph

A local, **draft-only, human-in-the-loop** prototype that classifies, audits, and
drafts replies for hotel reservation emails. Never sends mail, never touches
internal systems, never executes operational actions. **Grounded responses only.**
Runs on a MacBook M1 via Ollama. Principle: **"LLM describes, code decides."**

Pipeline (8 agents):
```
#1 Preprocessor → #2 Classifier+Extractor → #3 Validator → #4 Audit → #5 Router
   → (#6 RAG if applicable) → #7 Output Generator → #8 Guardrails → DB → API/Dashboard
```

## 2. What is already built (#1–#7)

All tested and wired into LangGraph over a shared `AgentState` (**81 offline
tests, green**). Guardrails is the **last** agent and the only one not yet built.
State it consumes:
- `output.draft_reply` — the **one** free-text, customer-facing artifact (the
  thing Guardrails polices). Present only on the `draft_reply_with_rag` path
  (a small minority of mail); `null` otherwise.
- `output.escalation_summary` / `audit_checklist` / `internal_notes` — internal,
  reviewer-facing, **deterministic** (templated from extracted data) — not
  customer-facing.
- `retrieval.sources` — the FAQ sources the draft was grounded in.
- `recommended_action`, `routing_reason`, `applied_rule_id`.

**Relevant known issue:** the local 3B model (`ministral-3:3b`) is weak; the
`draft_reply` prompt already forbids inventing facts/actions, but a 3B model can
still slip — which is exactly why an **independent** backstop exists.

## 3. Role & the locked output contract (DECIDED)

Guardrails is the **independent, deterministic safety net** that runs last and
checks whether the customer-facing draft makes a claim the system is **forbidden**
to make. It writes the already-locked `agent_output_schema.guardrails` block:
```
guardrails = {
  passed: true,                 # false ⇒ the draft is unsafe
  blocked_claims: [],           # list of { claim_text, rule_id, reason }
  escalation_reason: null       # set when passed=false
}
```
Locked rule (schema): **`passed=false` blocks the output and forces escalation.**
No schema change is needed — this agent implements an existing contract.

## 4. The #7 ↔ #8 boundary — why a SEPARATE agent (DECIDED)

This was debated and settled: keep Guardrails separate from the Output Generator.
The two checks are different in kind:

| | Output Generator (#7) | Guardrails (#8) |
|---|---|---|
| Check | **Structural** self-validation | **Semantic** content check |
| Asks | "Is the draft non-empty and citing real source ids?" | "Does the draft *claim an action was performed* or *system was accessed*?" |
| Trusts the draft? | It produced it | **No** — independent second line |
| Determinism | LLM produced the text | Fully deterministic |

Rationale for separation: **defense-in-depth** (the checker must be more
trustworthy than the thing it checks, so it does not reuse #7's logic),
**single responsibility**, **independently testable**, and — for the thesis —
**ablatable** (run the pipeline with/without #8 to quantify how many unsafe drafts
it catches). The ultimate backstop remains the **human reviewer**; #8 is the
automated layer in front of them.

## 5. CORE DESIGN PROPOSAL — deterministic rule-based scan (DECIDED, pending review)

Guardrails is **deterministic pattern matching over a curated forbidden-claim
lexicon** — *not* an LLM. Reasoning: a guardrail you cannot fully trust is not a
guardrail; "an LLM checking an LLM" is non-deterministic, can hallucinate, and is
hard to defend in a thesis. Deterministic matching is transparent, reproducible,
zero-cost, and fully unit-testable. (LLM-judge alternative is the headline open
question — §10.1.)

**v1 is hard-blocks only — no soft "warning" tier** (DECIDED via review §10). A
two-severity block+warn system was considered and deferred: the locked schema has
no `warnings` slot, and the main warning candidate (absolute-policy language)
overlaps with *faithfulness* checking, which is #7's grounding job, not a brittle
word list's. Revisit only if the eval shows real paraphrase leakage.

Mechanics:
- Scan **only `output.draft_reply`** (the only customer-facing free text). Every
  other path (`audit_only`, escalations, `manual_review_unclear`) has
  `draft_reply=null` ⇒ Guardrails is a **no-op**: `passed=true`, empty
  `blocked_claims`. So it runs work only on the small draft minority.
- Normalize text (lowercase, accent-fold for PT, collapse whitespace), then match
  each rule's patterns. Patterns target **first-person / completed-action /
  "your X is confirmed"** phrasings — *not* bare verbs — to avoid false positives
  on policy descriptions (see §7).
- **Bilingual EN + PT** (Pestana is Portuguese; cross-lingual is in scope).

## 6. Forbidden-claim rule catalogue (DECIDED shape; wording open)

Rules live in code as a versioned list (mirroring the Router's `RULES` pattern),
each `{rule_id, category, patterns[], reason}`. Three categories, mapped directly
to the hard constraints:

**Core 5** (DECIDED via review §10 — payment/refund and availability/price were
split out of the original 3 because they map 1:1 to the hard constraints and test
more cleanly):

| rule_id | Category | Catches (claims that…) | EN / PT example trigger |
|---|---|---|---|
| `GR001_ACTION_PERFORMED` | **ACTION** | an operational action was *done*: booking made/confirmed, modification applied, cancellation done, stop-sale/inventory changed | "I have confirmed your booking" / "a sua reserva foi confirmada" |
| `GR002_SYSTEM_ACCESS` | **SYSTEM_ACCESS** | the agent accessed/checked an internal system (PMS, CRS, channel manager, records) | "I checked our system" / "verifiquei no nosso sistema" |
| `GR003_FIRM_COMMITMENT` | **COMMITMENT** | a firm guarantee the agent can't make: room reserved, upgrade confirmed | "your room is reserved" / "o seu quarto está reservado" |
| `GR004_PAYMENT_REFUND` | **PAYMENT** | a payment/refund/invoice was processed/issued | "your refund has been processed" / "o reembolso foi processado" |
| `GR005_AVAILABILITY_PRICE` | **AVAILABILITY** | availability/price is confirmed/offered (needs internal access) | "this rate is available" / "o quarto está disponível para as suas datas" |

The lexicon is intentionally small and high-precision for v1; it catches the
**common, high-risk phrasings**, with the human reviewer covering the long tail.
**Considered and deferred:** a soft WARN tier + an absolute-policy rule
("always/never/guaranteed" — faithfulness overlap, false-positive risk on grounded
text) and a personal-data-request rule (low volume). Easy to add later.

## 7. The precision problem — the one thing to scrutinise (DECIDED approach)

The hard part is distinguishing a **forbidden performed-action claim** from a
**legitimate policy description**:
- ❌ BLOCK: *"I have cancelled your booking."* (claims an action was taken)
- ✅ ALLOW: *"You can cancel free of charge up to 48h before arrival."* (describes
  policy, grounded in an FAQ source)

So patterns key on **agent-subject + completed/▶ future-commitment** structures
("I have / we have / your booking is now / has been + confirmed/cancelled/refunded
/ processed"), **not** the bare nouns/verbs ("cancel", "refund", "booking"). This
deliberately accepts some **false negatives** (a weird paraphrase slips to the
human) over **false positives** (blocking a correct grounded reply), because the
human is the final gate and over-blocking would make the feature useless.

## 8. Behaviour when a claim is blocked (DECIDED)

On `blocked_claims` non-empty:
- `passed = false`; `escalation_reason` = e.g. *"Draft contained forbidden
  operational/system claim(s); withheld for manual review."*
- **Redact the unsafe draft:** set `output.draft_reply = null` and record the
  withheld text + the violated rules in `output.internal_notes` (prominent
  "🚫 DRAFT BLOCKED — do not send" notice). This mirrors #7's existing
  `_draft_withheld` pattern, so a blocked draft is never presented as sendable.
- The blocked state is surfaced to the human/dashboard via `passed=false` +
  `escalation_reason`. **Guardrails does NOT overwrite `recommended_action`**
  (DECIDED via review §10): the Router is the decision layer, Guardrails the safety
  layer; mixing them blurs the architecture. The dashboard derives a
  "blocked_by_guardrails" status from `passed=false`.

When `passed=true`: leave `output` untouched.

**Project invariant (added via review):** *only `output.draft_reply` may ever be
presented as a customer-facing reply.* Scanning just the draft is sufficient only
if the API/dashboard never lets a human copy `internal_notes` / `escalation_summary`
as a customer message. This is a UI/API contract, enforced there — not inside
Guardrails — but recorded here because it is what makes the scan scope safe.

## 9. Development plan / files

| Action | File | What |
|---|---|---|
| CREATE | `app/models/guardrails.py` | `GuardrailsOutput{passed, blocked_claims, escalation_reason}` + `BlockedClaim{claim_text, rule_id, reason}` (mirrors locked block). |
| CREATE | `app/agents/guardrails.py` | `check_guardrails(state) -> AgentState`: no-op unless `draft_reply` present; normalize → match `RULES` → write block + redact on block. Rule catalogue lives here. |
| MODIFY | `app/models/state.py` | add `AgentState.guardrails: Optional[GuardrailsOutput]`. |
| MODIFY | `app/graph.py` | add `guardrails` node; re-point `output_generator → guardrails → END`. No client injection needed (deterministic). |
| CREATE | `tests/test_guardrails.py` | see §11. |

No new dependency, no LLM client, no schema change. Smallest agent in the pipeline.

## 10. Resolved by independent review (2026-06-20)

The note above was reviewed; outcomes folded in:
1. **Deterministic vs LLM judge** → **deterministic**, confirmed. No LLM judge in v1.
2. **Re-route on block?** → **No.** Flag only (`passed=false` + `escalation_reason`
   + null draft); Router keeps owning `recommended_action`. (Folded into §8.)
3. **Scan scope** → **`draft_reply` only**, confirmed — *plus* the new project
   invariant that only `draft_reply` is ever customer-facing (§8).
4. **False-negative tolerance** → precision-first accepted; framed honestly as a
   "high-precision deterministic backstop, not full semantic safety; human is the
   final gate."
5. **Rule coverage** → **Core 5** (split payment & availability out of the original
   3). EN+PT sufficient for v1; absolute-policy / personal-data / WARN tier
   **deferred** (§6).
6. **Bypass risk** → addressed by the §8 invariant (UI/API contract).
7. **No duplication** → the structural source-id checks (draft cites real,
   non-empty sources) already live in #7's `_draft_reply`; Guardrails does **not**
   repeat them. This validates the #7/#8 split.

**Deferred to the evaluation track (thesis deliverable, not part of the build):** a
synthetic 20–40 draft eval set (safe / unsafe-action / system-access / payment /
availability / PT / borderline) to measure Guardrails' true-positive and
false-positive rates and the with/without-#8 ablation.

## 11. Verification (planned)

- **No-op paths:** `audit_only` / escalation / `manual_review_unclear`
  (`draft_reply=null`) → `passed=true`, `blocked_claims=[]`, draft untouched.
- **Blocks:** ACTION ("I have confirmed your booking" / PT equiv) → `passed=false`,
  one `blocked_claim` with the right `rule_id`, `draft_reply` nulled,
  `internal_notes` carries the blocked text + escalation_reason set. Same for
  SYSTEM_ACCESS and COMMITMENT, EN **and** PT.
- **Precision (the key test):** a clean grounded draft ("You can cancel free of
  charge up to 48h before arrival.") → `passed=true` (no false positive).
- **Graph:** full chain now ends `…router → output_generator → guardrails`;
  `agent_path` includes `guardrails`; a blocked-draft email flows end-to-end.
- **Ablation hook:** because #8 is its own node, the pipeline can run with/without
  it to quantify catches — thesis evidence for the safety layer.

## 12. Hard constraints (any proposal must respect)
Draft-only · no internal-system access · no operational actions ·
human-in-the-loop · **grounded responses only** · local on M1.

*End of design note.*
