# Project Details — Pestana AI Email Agent (Implementation)

**Read this first.** Single source of truth for a new session/developer. It
supersedes the old `HANDOVER.md`. Specific deep-dives are linked at the bottom.

| | |
|---|---|
| **Owner** | Erjon, master's student at NOVA IMS (Lisbon); sole owner/developer |
| **Thesis** | An AI email agent for hotel reservations support (Pestana Hotels) |
| **Workspace** | `/Implementation/` (this directory) |
| **Sibling workspaces** | `/Sandbox/` (exploratory — model smoke test), `/Phase 1 …/` (archive), `/Hotel AI Agent/` (original handoff archive) |
| **Spec freeze** | 2026-05-25 (taxonomy, schemas, LLM contract — locked v1.0.0) |
| **Doc updated** | 2026-06-07 |
| **Current phase** | Implementation — **core triage pipeline (#1–#5) built, tested, and wired into LangGraph**; next is batch-run on 378 |

---

## 1. What this project is — in one minute

A thesis prototype that **classifies, audits, and (later) drafts replies for
hotel reservation emails**. It does *not* send email, does not access internal
systems, does not execute operational actions. Every output is a draft surfaced
to a human reviewer.

Data: **378 anonymized email threads** from the Pestana reservations inbox +
a **193-entry FAQ knowledge base** (English). Phase 1 analyzed the data and
drafted a taxonomy; Phase 2 locked the taxonomy/schemas and designed the
architecture; we are now **building and testing the pipeline**.

The thesis evaluation will measure per-agent accuracy (classification,
extraction, validator catches, routing) against a human-labeled subset.

---

## 2. Non-negotiable constraints (the only truly immutable parts)

1. **Draft-only.** Never sends email autonomously.
2. **No internal system access.** No PMS, CRS, payment, booking engine, channel
   manager. Escalate anything needing internal validation.
3. **No operational actions.** No bookings, modifications, cancellations,
   payments, refunds, invoices, inventory updates.
4. **Human-in-the-loop.** Every output is human-reviewable before any effect.
5. **Grounded responses only.** No hallucination — answer only from email
   content, extracted fields, retrieved KB, or deterministic rules.
6. **Local + cost-efficient.** Runs on a MacBook M1; open-source preferred.

Everything else (architecture, tech stack, agent decomposition) is a **working
hypothesis** — propose better alternatives with tradeoffs rather than treating
the spec as final. (Owner explicitly wants a technical advisor who challenges
decisions, not a clerk who enforces them.)

---

## 3. Workspace layout

```
Implementation/
├── PROJECT_DETAILS.md          ← you are here (single source of truth)
├── DESIGN_NOTE_confidence_and_routing.md   ← reviewer note: confidence/routing
├── DESIGN_NOTE_router_routing_rules.md     ← reviewer note: router design
├── SMOKE_TEST_HANDOFF.md       ← model-selection smoke test pickup doc
├── pyproject.toml · .gitignore · .venv/
├── inputs/                     ← READ ONLY
│   ├── cleaned_dataset/emails_extracted_new.jsonl   (378 rows; Phase-1 artifact)
│   ├── raw_emails/email_N.txt                       (×378 — the RUNTIME input)
│   └── knowledge_base/pestana_faqs_en.jsonl         (193 FAQ entries)
├── outputs/                    ← LOCKED v1.0.0 spec (+ generated artifacts)
│   ├── taxonomy.json · taxonomy_proposal.md · CHANGELOG.md
│   ├── llm_output_schema.json/.md · agent_output_schema.json
│   ├── routing_rules.json                  ⚠ WIP — being replaced (see §11)
│   ├── routing_rules.generated.json/.md    ← generated from the Router
│   ├── dataset_analysis.md · borderline_cases.md
│   └── manual_label_validated.csv (74/378, OLD 6-cat taxonomy — see §11 gold labels)
├── app/                        ← production code (built this phase)
│   ├── config.py               settings: models, Ollama, paths, DB, classifier knobs
│   ├── models/                 llm_output · validator · audit · router_signals · state
│   ├── llm/                    client (protocol) · ollama_native · instructor_stub (parked)
│   ├── agents/                 preprocessor · prompts · classifier_extractor · validator · audit · router
│   ├── graph.py                LangGraph wiring of #1–#5 (build_pipeline_graph · run_pipeline)
│   ├── db/models.py            EmailRecord · AgentOutputRecord · init_db
│   └── api/main.py             FastAPI: /health live, /process-email stubbed (501)
└── tests/                      51 offline tests + Ollama-gated live integration
```

`/Sandbox/` = throwaway experiments. `/Implementation/` = thesis-defended code.
When unsure where something goes, default to `/Sandbox/`.

---

## 4. The locked spec (`outputs/`, frozen 2026-05-25)

Bumping any of these requires a coordinated review + a `CHANGELOG.md` entry.

| File | Purpose | Status |
|---|---|---|
| `taxonomy.json` | Canonical vocabulary (categories + facets + enums) | Locked |
| `taxonomy_proposal.md` | Prose spec of taxonomy + architecture rationale | Locked |
| `llm_output_schema.json/.md` | What the LLM emits per email | Locked |
| `agent_output_schema.json` | Full pipeline output structure | Locked |
| `routing_rules.json` | Priority-ordered routing rules | **⚠ WIP — being superseded by the generated artifact (§11)** |
| `CHANGELOG.md` | Version history + bump policy | Locked |
| `dataset_analysis.md`, `borderline_cases.md` | Empirical analysis / edge cases | Locked |
| `manual_label_*.csv` | Partial labeling sheet (OLD taxonomy) | See §11 (gold labels) |

---

## 5. The taxonomy — quick reference

**7 categories** (LLM predicts one): `booking_notification` (~74%),
`booking_change_or_cancellation` (~13%), `service_or_information_inquiry` (~9%),
`payment_billing_or_rate_issue` (~4%), `inventory_availability_or_stop_sales`
(~3%), `system_or_channel_delivery_exception` (~4%), `other_or_unclear` (~1%).

**5 facets** (predicted independently): `sender_type`, `request_type`,
`booking_lifecycle_stage`, `expects_human_response`, `urgency_signal`.

**Router-computed decision flags** (NOT LLM-predicted): `outbound_action_required`,
`requires_internal_system`, `kb_answerable` (from RAG).

**Audit output** (`booking_notification` only): `audit_finding` ∈
`clean / missing_fields / suspected_error / n/a`.

**Router output**: `recommended_action` — one of 9 values (`audit_only`,
`audit_with_attention`, `audit_only_with_note`, `draft_reply_with_rag`,
`escalate_to_reservations_team`, `escalate_to_payment_or_billing`,
`escalate_to_inventory_or_operations`, `escalate_to_technical_or_operations`,
`manual_review_unclear`).

Design principle: **"LLM describes, code decides."**

---

## 6. Architecture (current, working hypothesis)

```
#1 Preprocessor → #2 Classifier+Extractor → #3 Validator → #4 Audit → #5 Router
   → (#6 RAG if applicable) → #7 Output Generator → #8 Guardrails → DB → API/Dashboard
```

| # | Agent | Role | LLM? | Status |
|---|---|---|---|---|
| 1 | **Preprocessor** | Parse raw `.txt` thread → cleaned `EmailInput` + `input_metadata` | No | ✅ built |
| 2 | **Classifier+Extractor** | One call → classification + extraction (`EmailExtraction`) | Yes | ✅ built |
| 3 | **Validator** | LLM **semantic critique only** → `confirmed`/`flagged` + flags + `revised_confidence` | Yes | ✅ built |
| 4 | **Audit** | **All deterministic checks**: consistency + lifecycle completeness + risk flags | No | ✅ built |
| 5 | **Router** | Pure-Python guard clauses → `recommended_action` (+ `rule_id`, reason) | No | ✅ built |
| 6 | **RAG** (conditional) | Retrieve FAQ for policy questions; sets `kb_answerable` | No (embeddings) | ⬜ |
| 7 | **Output Generator** | Produce `audit_checklist` / `escalation_summary` / `clarification_draft` / `draft_reply` | Mixed | ⬜ |
| 8 | **Guardrails** | Block unsafe drafts; force escalation | No | ⬜ |

**Key architecture decisions (2026-06-06/07) — these refine the original spec:**
- **Validator = LLM semantic critique ONLY.** All deterministic checks
  (consistency, completeness, grounding) live in the **broadened Audit** (#4),
  not in the Validator.
- **Routing never gates on any single LLM number.** Deterministic Audit signals
  are the backbone; the Validator flag is a *contributing* signal (it only
  changes an otherwise-clean `booking_notification` → `audit_only_with_note`);
  `confidence`/`revised_confidence` are **logged, never gated**.
- **Router is pure-Python guard clauses** (category-primary, uniform if/elif),
  not a JSON rule-engine. An auditable rule table is **generated** from the code
  (`routing_rules.generated.{md,json}`). See `DESIGN_NOTE_router_routing_rules.md`.
- **Audit `audit_finding` stays `booking_notification`-only**; the human-facing
  audit summary + checklist are produced later by the **Output Generator (#7)**,
  not the Audit agent.

---

## 7. Tech stack

**Python 3.11+ · Pydantic · SQLModel + SQLite · FastAPI + Uvicorn · LangGraph
(planned) · Ollama · ChromaDB + sentence-transformers (planned) · Streamlit
(planned) · pytest.**

- **LLM transport (changed from the original spec):** the LLM call **defaults to
  Ollama's native structured-output API** (`POST /api/chat`, `think:false`,
  `format=<schema>`), validated by Pydantic. LiteLLM + Instructor — the originally
  specced stack — could not disable reasoning-model "thinking" (200–400 s/call)
  and broke the small models, so they are **parked behind a swappable `LLMClient`
  seam** (`app/llm/instructor_stub.py`). The client is **schema-generic**
  (`call_structured(response_model=…)`) so one client serves every LLM agent.
- **Models (from the smoke test):** primary `ministral-3:3b`, fallback
  `llama3.2:3b`. The Classifier/Validator run deterministically (temp 0, fixed
  seed), **primary-only** (no auto-fallback; on failure → `llm_output` empty →
  routes to `manual_review_unclear`).

---

## 8. Implementation status — what's built (as of 2026-06-07)

**The core triage pipeline (#1–#5) is complete, deterministic, and tested.**
51/51 offline tests pass; live integration tests (gated on a running Ollama)
confirm the real model path end-to-end.

- **#1 Preprocessor** — parses the raw `.txt` header block + body; cleans body
  (strips CAUTION banner / logo placeholders; retains `MASKED_*`); computes
  `thread_length_estimate` + `body_clean_length`; emits the locked
  `input_metadata`. 378/378 parse; **100% header match** vs the Phase-1 jsonl
  used purely as a test oracle (the **raw `.txt` files are the runtime input**;
  the jsonl was only a Phase-1 taxonomy-design artifact).
- **#2 Classifier+Extractor** — one Ollama call → `EmailExtraction`. **100%
  schema-valid**; category accuracy provisional (~70–83% on a borderline
  sample). Enriched-but-concise prompt (category guide + facet defs + extraction
  rules) in `app/agents/prompts.py`.
- **#3 Validator** — second LLM call, semantic critique; maps to
  `state.validator`; skips when there's no `llm_output`.
- **#4 Audit** — pure Python: consistency (all categories) + lifecycle
  completeness (`booking_notification` only) + risk flags. v1 risk flags
  (high-precision): `checkout_before_checkin`, `price_without_currency`,
  `lifecycle_mismatch`. **No deterministic grounding in v1** (reserved).
- **#5 Router** — `build_router_signals()` (facts + decision flags +
  `rag_required`) → `route()` guard clauses → `recommended_action` + `rule_id` +
  reason. Generated rule artifact for the thesis appendix.
- **LangGraph wiring** (`app/graph.py`) — #2–#5 compiled as a linear `StateGraph`
  over `AgentState`; `run_pipeline(path)` preprocesses then invokes it. LLM
  clients are injectable so the graph is tested offline. (A conditional RAG edge
  is the next graph addition.)

**Observed behaviour:** Audit and Validator *independently corroborate* extraction
failures (the intended cross-check). Routing in the wild is driven by the
deterministic Audit, not by confidence or the validator flag — exactly as designed.

---

## 9. Decisions made — and why (do not re-open without strong reason)

Original Phase 1→2 decisions (still hold): 7 categories not 6/12; hybrid
categories+facets (not category+intent); `sender_type` is a facet; "LLM
describes, router decides"; forwarding-invariant (classify by inner content);
required-field logic lives in Audit not the schema; `kb_answerable` from real
RAG; one LLM call for classify+extract; pure-Python router.

**Added this phase (2026-06-06/07):**
| Decision | Rationale |
|---|---|
| Native Ollama API is the default LLM transport | LiteLLM+Instructor couldn't disable thinking / broke small models (smoke test) |
| Schema-generic `LLMClient.call_structured(response_model=…)` | One structured-output client for Classifier + Validator + future agents |
| Confidence is logged, **never gates routing**; buckets are display-only, calibrate later | Self-reported 3B confidence is uncalibrated; gating on it is indefensible |
| Validator reframed: LLM critique only; deterministic checks → Audit | Clean separation; deterministic part is the sound, testable backbone |
| Router = pure-Python guard clauses + generated rule artifact (not a JSON DSL) | Simplest/most testable/most defensible at this scale; still auditable |
| Router is category-primary; Audit/validator/risk are *modifiers within a branch* | Avoids misrouting a payment email to manual_review on a booking-only signal |
| Audit grounding deferred (v1) | Reformatted dates/amounts + MASKED names make substring grounding noisy |

---

## 10. Approaches rejected — do not revive (without new evidence)

CrewAI / AutoGen (collaboration patterns we don't need); LangFlow / LangChain
core (heavy, brittle); LlamaIndex (overkill for 193 FAQs — ChromaDB direct);
12-category flat taxonomy; splitting notifications into per-lifecycle categories;
LLM-predicted handling flags (moved to router); confidence-gated routing (see §9).

*(Per owner preference, "rejected" ≠ off-limits — raise any of these with a
rationale if a better fit emerges. The §2 constraints are the only hard line.)*

---

## 11. OPEN TO-DOS & CONSIDERATIONS

### A. Immediate next steps (pick one)
- **Batch-run all 378** through #1–#5 (plain function chaining already works).
  First real distribution (category/action/audit/validator rates, extraction
  completeness). Heavy: ~6 h on M1 at classify+validate (~60 s/email) — run
  overnight, or a stratified ~40-email subset first for a fast read.
- **Finalize + lock `routing_rules.json`**: promote `routing_rules.generated.*`
  to replace the WIP file + add a CHANGELOG entry. (`agent_output_schema.json`'s
  `applied_rule_id` references `routing_rules.json`, so keep rule_ids aligned.)

### B. Remaining agents
- **#6 RAG** — ChromaDB + sentence-transformers over the 193 FAQs. **Resolves the
  `kb_answerable` ordering**: Router currently sets `rag_required=true` and treats
  `draft_reply_with_rag` as a *candidate*; RAG runs after and flips it to a
  grounded answer or an escalation.
- **#7 Output Generator** — produces `audit_checklist` / `escalation_summary` /
  `clarification_draft` / `draft_reply` from the Audit findings + extraction.
  **Consideration:** for `booking_notification` (~74%, mechanical), generate the
  `audit_checklist` **deterministically from a template** rather than via an LLM
  call — cheaper/faster/more reliable; reserve the LLM for free-text drafts.
- **#8 Guardrails** — block unsafe drafts; force escalation.
- **Streamlit dashboard** — thesis demo.

### C. The gold-label set — the real evaluation blocker
There are **no usable v1.0.0 gold labels** yet. The dataset has no category
field; `manual_label_validated.csv` covers only 74/378 in an **older 6-category
taxonomy** with the validated column empty. "Build the eval set" = **produce gold
labels in the v1.0.0 7-category taxonomy from scratch** (~30–50 min). This gates
every accuracy number and the whole evaluation chapter. Runs as a parallel track;
it does not block building.

### D. Deferred prompt-engineering backlog (batch at the eval milestone)
1. **Validator `flagged_fields` pollution** — model interleaves free-text into
   the paths list; tighten the prompt ("paths only"), likely a one-shot example.
2. **Classifier borderline misses** — `email_334`, `email_4`; candidate fix:
   few-shot / contrastive examples per category.
3. **Validator false-flag noise** — flags correct ISO dates etc.; measure via the
   Validator ablation rather than over-tuning.
4. **Extraction under-population** — `ministral-3:3b` classifies OK but leaves
   clearly-present fields null (Audit + Validator both caught it). Candidate fix:
   stronger extraction prompt/few-shot, and **possibly a larger model for the
   extraction half** vs the classification half. Measure field-level extraction
   accuracy against the gold set before deciding.

### E. Confidence calibration (policy resolved; revisit at eval)
Routing does not use confidence. Keep the `float` field; the dashboard may show
derived `low/med/high` buckets. At the eval milestone, **measure whether
self-reported confidence tracks accuracy** (reliability check) — a planned thesis
finding; only then consider a calibrated bucket schema bump.

### F. Supervisor conversation (thesis framing)
The **Validator is no longer claimed as "the novel contribution."** A standalone
LLM critic is a known pattern; reframe it as an **"LLM-based reliability checker"
proven by ablation** (Pipeline A: Classifier+Extractor only vs Pipeline B:
+Validator+deterministic verification). If anything, frame the **hybrid**
(LLM critique + deterministic verification for safe, draft-only triage) as the
contribution. **Needs a conversation with the supervisor** since it shifts the
established framing.

### G. Documentation/spec housekeeping
- This file replaces `HANDOVER.md`.
- Lock `routing_rules.json` (item A).
- The `agent_output_schema` validator block still describes the old
  `min(confidence, revised_confidence)` router use — **superseded; do not
  implement.**

---

## 12. Supervisor / thesis framing rules (enforce without being asked)

Supervisor prefers hyped AI framing, but **engineering quality + evaluation rigor
come first.**

**Acceptable:** "multi-agent system orchestrated with LangGraph"; "Validator
Agent for output critique" (as an **LLM-based reliability checker**, proven by
ablation — *not* claimed as a novel invention); "deterministic routing alongside
LLM agents".

**Not acceptable (overclaiming):** "autonomous AI agent" (it's human-in-the-loop,
draft-only); "end-to-end automation" (no operational actions); "conversational
AI" (single-pass triage).

---

## 13. Backlog (build order)

| # | Task | Status |
|---|---|---|
| 1–5 | Preprocessor → Classifier+Extractor → Validator → Audit → Router | ✅ done |
| 11 | Wire #1–#5 into LangGraph (shared `AgentState`) | ✅ done |
| 13 | Batch-run all 378 + persist | next |
| 12 | DB layer + `POST /process-email` (DB stub + API stub exist) | partial |
| 6 | RAG agent + ingest KB into ChromaDB | ⬜ |
| 7 | Output Generator (templates; deterministic audit_checklist) | ⬜ |
| 8 | Guardrails | ⬜ |
| 17 | Streamlit dashboard (thesis demo) | ⬜ |
| 18 | Build ~30–50 gold labels in v1.0.0 taxonomy (parallel track) | ⬜ |
| 19 | Run on labeled set; per-agent accuracy + Validator ablation | ⬜ |
| 20 | Thesis write-up (architecture, reliability-checker framing, results) | ⬜ |
| 21 | (Deferred) Phase 3: Outlook integration via Microsoft Graph | ⬜ |

---

## 14. Working rules for the assistant

- **Sandbox vs Implementation** — throwaway in `/Sandbox/`; thesis code in `/Implementation/`.
- **Don't silently change locked spec** — raise it + propose a CHANGELOG bump.
- **Working hypothesis ≠ frozen** — challenge the architecture/stack with evidence; the §2 constraints are the only hard line. Propose alternatives openly with tradeoffs.
- **Enforce framing rules (§12) without being asked.**
- **Verify before asserting** — run code/tests; report failures honestly.

## 15. Deeper-detail documents
- `outputs/taxonomy_proposal.md` — full taxonomy + architecture rationale.
- `outputs/agent_output_schema.json` — per-agent I/O contract.
- `outputs/llm_output_schema.md` — extraction field rules (incl. lifecycle required-field table used by Audit).
- `outputs/borderline_cases.md` — classification edge cases (eval set guide).
- `DESIGN_NOTE_confidence_and_routing.md`, `DESIGN_NOTE_router_routing_rules.md` — reviewer notes behind the §9 decisions.
- `SMOKE_TEST_HANDOFF.md` / `/Sandbox/SMOKE_DECISION.md` — model selection.

**End of project details.**
