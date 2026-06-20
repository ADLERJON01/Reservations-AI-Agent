# Design Note — Output Generator Agent (#7) Spec & Dev Plan

**Purpose:** give an **independent reviewer** enough context to critique the spec
and dev plan for the Output Generator before it's built. Self-contained — you
should not need the rest of the repo. **DECIDED** = settled; §9 = open questions.

Date: 2026-06-12 · Project: Pestana AI Email Agent (master's thesis prototype).

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

## 2. What is already built (#1–#6)

All tested (74 offline tests), wired into LangGraph over a shared `AgentState`.
Key state the Output Generator consumes:
- `llm_output.extraction` — 9 field groups (guest, stay, financials, etc.).
- `llm_output.classification` — category + facets.
- `audit` — `audit_finding` (clean/missing_fields/suspected_error/n/a),
  `missing_required_fields`, `consistency_errors`, `risk_flags`.
- `recommended_action` (one of 9) + `routing_reason` + `applied_rule_id`.
- `retrieval` — for the RAG path: `sources[]` (FAQ `question`/`answer`/`score`),
  `kb_answerable`.

Models run locally via Ollama (primary `ministral-3:3b`), structured output via a
schema-generic `LLMClient.call_structured(response_model=…)`. **Known issue:**
`ministral-3:3b` under-extracts unless prompted hard (a fix is pending) — relevant
because draft quality depends on extraction quality.

## 3. Role & the locked output contract (DECIDED)

The Output Generator turns the upstream findings into the **human-facing
artifact**. The locked `agent_output_schema.output` block:
```
output = {
  audit_checklist: [],         # list of verification items (booking audit)
  escalation_summary: null,    # structured summary for an internal team
  clarification_draft: null,   # draft asking the customer to clarify
  draft_reply: null,           # full grounded draft reply to the customer
  internal_notes: null         # free-form note for the human reviewer (not customer-facing)
}
```
Locked rule: **exactly ONE of the four forms is populated per email**;
`internal_notes` may accompany any. This agent produces *presentation*; the
deterministic *findings* are already done by Audit (#4).

## 4. recommended_action → output form mapping (DECIDED)

| recommended_action | Output form | How |
|---|---|---|
| `audit_only` | `audit_checklist` | deterministic |
| `audit_with_attention` | `audit_checklist` (flags highlighted) | deterministic |
| `audit_only_with_note` | `audit_checklist` (+ validator note) | deterministic |
| `escalate_to_reservations_team` | `escalation_summary` | deterministic |
| `escalate_to_payment_or_billing` | `escalation_summary` | deterministic |
| `escalate_to_inventory_or_operations` | `escalation_summary` | deterministic |
| `escalate_to_technical_or_operations` | `escalation_summary` | deterministic |
| `draft_reply_with_rag` | `draft_reply` | **LLM, grounded in `retrieval.sources`** |
| `manual_review_unclear` | `internal_notes` only | deterministic |

`internal_notes` is always populated (assembled from `routing_reason`, audit
flags, validator result) regardless of the primary form.

## 5. CORE DESIGN PROPOSAL — deterministic by default, LLM only where required

The dominant value workflow is **auditing booking notifications (~74% of mail)**,
which is mechanical. So:

- **`audit_checklist` = deterministic** Jinja2 template over `extraction` + `audit`
  findings. For ~74% of mail this means **zero LLM calls** — cheaper, faster, and
  it **cannot hallucinate** (it only restates extracted values + flags). Example
  items: "Verify guest name: MASKED_NAME_x", "Verify check-in 2026-03-06 / out
  2026-03-08", "⚠ Missing: total_amount, currency", "⚠ Suspected: checkout before
  checkin".
- **`escalation_summary` = deterministic** template (category, key extracted
  fields, audit flags, `routing_reason`, why-escalated). Grounded, no hallucination.
- **`internal_notes` = deterministic** (assembled from findings).
- **`draft_reply` = LLM** — the one genuinely free-text, customer-facing artifact.
  Grounded strictly in `retrieval.sources` (see §6).

**Rationale:** LLM generation is reserved for the *only* place free-text is truly
needed (a customer reply), keeping the system cheap, grounded, and defensible.
This also means the audit-automation path (the bulk) is fully deterministic.

## 6. `draft_reply` grounding (DECIDED approach)

- Fires only after RAG confirmed `kb_answerable=True`, so `retrieval.sources`
  exist. The LLM is given **only** those FAQ answers as context.
- The prompt enforces: *answer ONLY from the provided sources; do not invent
  policy; if the sources don't cover it, say so* (Guardrails #8 is the backstop).
- LLM output is wrapped in a small Pydantic model (e.g. `GeneratedReply{reply_text,
  used_source_ids}`) via `call_structured`, so it's validated and we record which
  sources were used (traceability). Deterministic settings (temp 0).

## 7. Graph placement (DECIDED)

The Output Generator runs on **every** path, after RAG-or-router:
```
audit → router → (conditional) ─ rag_required? ─► rag ─┐
                              └─ else ──────────────────┤
                                                        ▼
                                            output_generator → END
```
So the conditional edge targets `rag` vs `output_generator` (not END), and both
flow into `output_generator`. `build_pipeline_graph` gains an injectable
`reply_client` for offline testing.

## 8. Development plan / files

| Action | File | What |
|---|---|---|
| CREATE | `app/agents/output_generator.py` | `generate_output(state, reply_client=None)` — dispatch by `recommended_action`. |
| CREATE | `app/agents/output_templates/` | Jinja2 templates: `audit_checklist`, `escalation_summary`, `internal_notes`, `draft_reply` (LLM prompt). |
| CREATE | `app/models/output.py` | `OutputArtifacts` (mirrors locked block) + `GeneratedReply` (LLM contract). |
| MODIFY | `app/models/state.py` | add `AgentState.output`. |
| MODIFY | `app/graph.py` | add `output_generator` node; re-point the conditional edge; `reply_client` injection. |
| MODIFY | `app/config.py` | (maybe) `reply_temperature=0.0`, template dir. |
| MODIFY | `pyproject.toml` | add `jinja2`. |
| CREATE | `tests/test_output_generator.py` | offline for all deterministic forms; fake `reply_client` for `draft_reply`; gated live. |

## 9. OPEN — what we want the reviewer's opinion on

1. **Deterministic vs LLM split (§5):** is making `audit_checklist` /
   `escalation_summary` / `internal_notes` deterministic templates (LLM only for
   `draft_reply`) the right call — or should `escalation_summary` be LLM-written
   for better prose? (Trade: determinism/grounding/cost vs readability.)
2. **`clarification_draft` is unmapped.** No current routing action cleanly
   triggers it (the system never asks the customer to clarify in v1). Options:
   (a) defer it entirely; (b) wire it to `manual_review_unclear` as a customer
   clarification draft; (c) add a future "needs clarification" route. We lean
   **defer**. Agree?
3. **`draft_reply` safety:** is "ground strictly in `retrieval.sources` + refuse if
   insufficient + Guardrails backstop" enough, given the 3B model and the fragile
   `kb_answerable` threshold (BGE-M3 cosine bands overlap ~0.62–0.68)? Should
   `draft_reply` cite sources inline, or attach them separately for the reviewer?
4. **Template engine:** Jinja2 (per the original spec) vs plain Python f-strings
   for ~3 small templates — is Jinja2 worth the dependency here?
5. **`internal_notes` always-on** alongside the primary form — agree, or only when
   there's something noteworthy?
6. **Anything missed** — especially any path where the agent could emit a
   customer-facing claim not grounded in extracted data or retrieved sources.

## 10. Hard constraints (any proposal must respect)
Draft-only · no internal-system access · no operational actions ·
human-in-the-loop · **grounded responses only** · local on M1.

*End of design note.*
