# Design Note — LLM Confidence & Routing-Signal Design

**Purpose of this document:** capture an in-progress design discussion and the
decisions reached, so an **independent LLM (or reviewer) can give a third
opinion**. It is written to be self-contained — you should not need the rest of
the codebase to weigh in. Where we've already decided something, it's marked
**DECISION**; where we want your view, it's marked **OPEN / SEEKING OPINION**.

Date: 2026-06-06 · Status: pre-implementation design · Author: project owner +
assistant.

---

## 1. Minimal project context (read first)

A master's thesis prototype: an **AI email agent for hotel reservations support**
(Pestana Hotels). It **classifies, audits, and drafts replies** for incoming
reservation emails. It is **draft-only** — it never sends mail, never touches
internal hotel systems, never executes operational actions, and is
human-in-the-loop. It must run **locally on a MacBook M1**.

**Models (from a completed model-selection smoke test):**
- Primary: `ministral-3:3b` (100% schema-valid, ~83% category accuracy on a
  10-email screen).
- Fallback: `llama3.2:3b` (fast, but weak classifier).
- Both are **small (3–4B) local models** served via Ollama. This matters: small
  models have **worse-calibrated self-assessment** than large ones.

**Guiding design principle:** **"LLM describes, code decides."** The LLM only
emits *descriptive* fields; all *decisions* (routing, actions) are computed
deterministically downstream.

### The 8-agent pipeline

```
Preprocessor → Classifier+Extractor → Validator → Audit → Router
                                                            ↓
                                                  (RAG, if applicable)
                                                            ↓
                                          Output Generator → Guardrails → DB → API/Dashboard
```

| # | Agent | Role | LLM? |
|---|---|---|---|
| 1 | Preprocessor | Parse raw email thread → clean object | No |
| 2 | Classifier+Extractor | One LLM call: category + 5 facets + structured extraction | **Yes** |
| 3 | **Validator** *(thesis's claimed novel contribution)* | Re-read email + proposed JSON, flag hallucinations/errors | **Yes** |
| 4 | Audit | Deterministic field/lifecycle completeness checks | No |
| 5 | Router | Apply `routing_rules.json` → decision flags + `recommended_action` | No |
| 6 | RAG (conditional) | Retrieve FAQ for policy questions | No (embeddings) |
| 7 | Output Generator | Draft reply / audit checklist / escalation summary | **Yes** |
| 8 | Guardrails | Block unsafe drafts | No |

### Relevant schema facts

- The **classification + extraction output schema is locked at v1.0.0.** It
  currently includes a **`confidence` field emitted by the LLM as a float (0–1).**
- The **Validator** emits: `validation_result` (`confirmed` / `flagged`),
  `flagged_fields` (list of JSON paths), `reasoning_short`, and
  `revised_confidence`.
- The **Router** was originally designed to threshold on
  **`min(classification.confidence, validator.revised_confidence)`** — i.e. a low
  combined confidence forces a `manual_review_unclear` route.
- `routing_rules.json` is **WIP / not locked.** Therefore: changing *how* a
  signal is **consumed** by routing is free; changing or removing a **schema
  field** is a locked-spec bump (requires a CHANGELOG entry).

---

## 2. The problem we're debating

The project owner raised a concern: **the LLM-emitted `confidence` is not
mathematically sound and may not be accurate**, yet the design lets it **gate
routing**. So an unsound number would be driving safety-relevant decisions.

We agreed the concern has **two distinct halves**:
1. **Soundness / false precision** — the float is generated text, not derived
   from token probabilities; it isn't a real `P(correct)`.
2. **Accuracy / calibration** — even a coarse self-rating may not track actual
   correctness (small models are typically overconfident and poorly calibrated).

---

## 3. Analysis & reasoning (the argument so far)

### 3.1 Why self-reported confidence is weak
- It's **not derived from the model's uncertainty** (that would be token
  logprobs, which the emitted number ignores).
- It's typically **overconfident and poorly calibrated**, and **worse on small
  (3B) models** — which is exactly what we're shipping.
- It **clusters** at round values (0.85/0.9/0.95) and barely separates easy from
  hard cases — i.e. the decimal precision is largely noise.

### 3.2 The trap we noticed (important)
Our first instinct was "route on the **Validator's** `confirmed`/`flagged`
verdict instead of confidence." But the Validator is **also an LLM call** — its
verdict is **not mathematically sound either**. Swapping one LLM judgment for
another doesn't escape the problem.

The Validator is nonetheless a **better signal than self-confidence**, for three
reasons (only the third is fully solid):
1. **Different, more grounded task.** Confidence asks the model to *introspect*
   ("how sure are you?"), which LLMs are bad at. The Validator does
   *verification* ("here's the email + the JSON — find specific errors"), which
   checks concrete claims against concrete source text.
2. **It produces checkable evidence** (`flagged_fields` + reasons) rather than an
   opaque scalar — a human or downstream code can inspect *why*.
3. **The genuinely sound signals are deterministic, not LLM-based** — see below.

### 3.3 The deterministic cross-checks (the load-bearing part)
Code can verify things that don't rely on any LLM judgment:
- **Extraction grounding:** is the extracted value actually present in the email
  text?
- **Facet/category consistency:** e.g. `request_type = cancellation_request`
  should agree with `category = booking_change_or_cancellation`.
- **Audit completeness:** are the required fields for the email's lifecycle stage
  present?

These are auditable and reproducible — ideal for a thesis evaluation.

---

## 4. Decisions reached

### DECISION 1 — Routing should not gate on any single LLM-generated number.
Not the classifier's `confidence`, not the Validator's verdict alone. Instead:
- **Deterministic cross-checks = the backbone** (load-bearing, sound, auditable).
- **Validator flags = an escalation trigger on top** (evidence-bearing LLM
  signal; *can* force `manual_review`, but is not the sole gate).
- **Self-reported confidence = kept in the schema, logged, but NOT gated** until
  it is **calibrated against a gold-label set**. That calibration is itself a
  planned **thesis finding** ("we tested whether self-reported confidence was
  calibrated for this task; it was/wasn't, so we route on X instead").

### DECISION 2 — Where the deterministic checks live in the pipeline.
The **Router (#5) consumes signals; it does not compute them** (computing them at
#5 would violate "LLM describes, code decides"). Placement:
- **Extraction grounding → Validator (#3)** (LLM critique **+** deterministic
  grounding = a stronger "verification agent").
- **Audit completeness → Audit (#4)** (already its job).
- **Facet/category consistency → Audit (#4)** (candidate home).
- **Router (#5)** reads those precomputed flags + `routing_rules.json` and maps
  them to `recommended_action`. Pure deterministic decision layer.

### DECISION 3 — Audit scope may be broadened (kept in mind, not yet done).
The locked architecture currently scopes **Audit (#4) as
`booking_notification`-only**. But facet/category consistency and extraction
grounding apply to **all categories**. We've **agreed to potentially broaden
Audit's scope** (or keep cross-category consistency inside the Validator). This
will be settled when we build agents #3/#4 and, if it changes the locked Audit
scope, raised explicitly as a tracked change — not done silently.

### DECISION 4 (direction agreed; representation/timing OPEN) — Confidence → buckets.
We agree the **end state for `confidence` is coarse buckets (`low` / `med` /
`high`)** rather than a float, because three levels match a 3B model's real
resolution and kill false precision.

Two important clarifications attached to this:
- **Buckets fix only half the problem.** They address *false precision* (half 1),
  **not** *accuracy/calibration* (half 2). "high" can still be wrong often. Only
  calibration + not-gating addresses accuracy. So buckets are an
  honesty/readability win, **not** a soundness win, and should not be oversold.
- **The boundaries should be earned from calibration**, not guessed. A principled
  low/med/high split should come from gold-set calibration ("scores in this range
  → <60% accuracy"), not from arbitrary 0.33/0.66 cut-points chosen today —
  otherwise we repeat the premature-commitment mistake we avoided with gating.

---

## 5. OPEN / SEEKING THIRD OPINION

The specific points where an independent view is wanted:

1. **Is "keep the float now, bucket for *display* only, define schema buckets
   after calibration" the right sequencing** — versus committing a
   `low`/`med`/`high` enum into the locked schema **now** (a v1.0.0 bump)?
   - *Lightest option:* keep float in schema → dashboard shows buckets → calibrate
     on gold set → then bump schema to validated buckets.
   - *Commit-now option:* LLM emits `low`/`med`/`high` directly; simpler/honest,
     but representation is locked before we know what the levels are worth.

2. **Is the routing-signal hierarchy sound?** (deterministic backbone + Validator
   flags as escalation trigger + confidence logged-not-gated). Are we
   under-using or over-trusting the Validator? Is there a better way to combine
   an LLM critic with deterministic checks for a safety-critical, draft-only,
   human-in-the-loop system?

3. **Are we right to distrust LLM self-confidence this strongly for a 3B local
   model**, or is there a cheap way to make it trustworthy we're overlooking —
   e.g. **token-logprob-based confidence** (note: Ollama's structured-output path
   does not cleanly expose per-token logprobs, and aggregating them into one
   scalar is its own imperfect choice), self-consistency sampling, etc.? Given
   the local M1 + small-model constraints, is any of that worth the cost?

4. **Audit scope:** broaden Audit (#4) to cover cross-category consistency, or
   keep cross-category deterministic checks inside the Validator (#3)? Which is
   cleaner for a modular, auditable pipeline?

5. **Anything we've missed** — particularly any way the "LLM describes, code
   decides" principle is being quietly violated, or any calibration/evaluation
   pitfall for the thesis.

---

## 6. Hard constraints (any proposal must respect these)

1. Draft-only — never sends email autonomously.
2. No internal system access (no PMS/CRS/payment/booking engine).
3. No execution of operational actions.
4. Human-in-the-loop — every output is human-reviewable.
5. Grounded responses only — no hallucination.
6. Local + cost-efficient — runs on a MacBook M1; open-source preferred.

*End of design note.*
